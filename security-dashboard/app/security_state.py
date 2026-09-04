"""세션(session_id)별 보안 상태 판단 로직.

규칙 (1차 구현, 팀과 합의된 값만 사용):
    face authorized + ppe overall pass  -> NORMAL
    ppe overall fail                    -> WARNING
    face unauthorized                   -> ALERT (WARNING보다 우선)
    face 또는 ppe가 undetermined,
    또는 아직 둘 중 하나를 못 받음        -> PENDING ("판정 보류 / 재검사 필요")

PENDING은 팀 스펙(schema/)에 있는 공식 상태값이 아니라, 재시도 횟수·경고
자동 해제 조건이 DECISIONS.md에서 아직 미확정이라 "함부로 ALERT로 단정하지
않기 위한" 내부 상태다. NORMAL/WARNING/ALERT만 alert.event 발행 대상이며,
PENDING은 콘솔 출력만 하고 MQTT로는 아무것도 내보내지 않는다.

같은 session_id에 대해 상태가 실제로 바뀔 때만(new_status != old_status)
alert.event를 내보내도록 SecurityStateStore가 이전 상태를 기억한다 - 이게
"중복 경고 방지"의 전부다. transitions 같은 별도 상태머신 라이브러리는
이 규모에 과해서 쓰지 않았다.
"""

from __future__ import annotations

from dataclasses import dataclass, field

NORMAL = "NORMAL"
WARNING = "WARNING"
ALERT = "ALERT"
PENDING = "PENDING"


@dataclass
class SessionRecord:
    visitor_id: str | None = None
    face_result: str | None = None
    ppe_overall: str | None = None
    ppe_items: dict = field(default_factory=dict)
    status: str | None = None
    snapshot_path: str | None = None


@dataclass
class Transition:
    session_id: str
    visitor_id: str | None
    old_status: str | None
    new_status: str
    changed: bool
    trigger: str  # "face" 또는 "ppe" - 어떤 메시지가 이 판단을 유발했는지
    face_result: str | None
    ppe_overall: str | None
    ppe_items: dict
    snapshot_path: str | None


def _compute_status(face_result: str | None, ppe_overall: str | None) -> str:
    """요청받은 우선순위 그대로: unauthorized > ppe fail > (undetermined는 PENDING) > normal.

    ppe=fail은 얼굴이 아직 authorized로 확인되지 않았어도(심지어 아직 face 메시지를
    못 받았어도) WARNING을 낸다 - "PPE fail -> WARNING"이 얼굴 판정과 별개의 독립
    규칙으로 주어졌고, 팀의 tools/mock_publisher.py no_helmet 시나리오도 vision.face
    없이 vision.ppe만 보내는 것을 전제로 만들어져 있다.
    """
    if face_result == "unauthorized":
        return ALERT
    if ppe_overall == "fail":
        return WARNING
    if face_result == "undetermined" or ppe_overall == "undetermined":
        return PENDING
    if face_result == "authorized" and ppe_overall == "pass":
        return NORMAL
    return PENDING


class SecurityStateStore:
    """session_id -> SessionRecord 를 메모리에 들고 있는 저장소.

    지금은 프로세스 안 메모리(dict)에만 저장한다 - DB가 아직 없고, 이 단계
    목표(콘솔 출력 + alert.event 발행 검증)에는 이걸로 충분하다.
    """

    def __init__(self) -> None:
        self._sessions: dict[str, SessionRecord] = {}
        self.last_session_id: str | None = None

    def apply_face(
        self, *, session_id: str, visitor_id: str, result: str, snapshot_path: str | None
    ) -> Transition:
        rec = self._sessions.setdefault(session_id, SessionRecord())
        rec.visitor_id = visitor_id
        rec.face_result = result
        return self._transition(session_id, rec, trigger="face", snapshot_path=snapshot_path)

    def apply_ppe(
        self,
        *,
        session_id: str,
        visitor_id: str,
        overall: str,
        items: dict,
        snapshot_path: str | None,
    ) -> Transition:
        rec = self._sessions.setdefault(session_id, SessionRecord())
        rec.visitor_id = visitor_id
        rec.ppe_overall = overall
        rec.ppe_items = items or {}
        return self._transition(session_id, rec, trigger="ppe", snapshot_path=snapshot_path)

    def _transition(
        self, session_id: str, rec: SessionRecord, *, trigger: str, snapshot_path: str | None
    ) -> Transition:
        new_status = _compute_status(rec.face_result, rec.ppe_overall)
        old_status = rec.status
        rec.status = new_status
        if snapshot_path:
            rec.snapshot_path = snapshot_path
        self.last_session_id = session_id
        return Transition(
            session_id=session_id,
            visitor_id=rec.visitor_id,
            old_status=old_status,
            new_status=new_status,
            changed=old_status != new_status,
            trigger=trigger,
            face_result=rec.face_result,
            ppe_overall=rec.ppe_overall,
            ppe_items=rec.ppe_items,
            snapshot_path=snapshot_path,
        )

    def latest(self) -> tuple[str | None, SessionRecord | None]:
        """대시보드 '현재 방문자' 패널용 - 가장 최근에 메시지가 들어온 세션."""
        if self.last_session_id is None:
            return None, None
        return self.last_session_id, self._sessions.get(self.last_session_id)

    def reset_status(self, session_id: str) -> None:
        """관리자가 경고를 수동 해제했을 때, 그 세션의 판정 상태를 초기화한다.

        얼굴/PPE 원본 값(face_result, ppe_overall)은 그대로 두고 status만 지운다 -
        다음에 A로부터 같은(혹은 다른) 판정이 다시 들어오면 "새로운 변화"로 취급되어
        재경보가 가능해야 하기 때문이다. 원본 값을 지워버리면 다음 메시지가 올 때까지
        '현재 방문자' 패널에 정보가 사라지는 부작용이 생겨 status만 초기화한다.
        """
        rec = self._sessions.get(session_id)
        if rec is not None:
            rec.status = None
