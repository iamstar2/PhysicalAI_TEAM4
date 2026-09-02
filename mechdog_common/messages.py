"""MechDog 공용 메시지 스키마 (Pydantic v2 기반).

모든 노드는 이 모듈에서 정의한 Envelope 으로만 메시지를 주고받는다.
스키마에 없는 필드는 extra="forbid" 로 무조건 거부되므로, 필드를 추가하려면
이 파일을 고쳐서 팀 전체에 배포해야 한다 (로컬에서 임의로 필드를 얹으면
다른 팀원 쪽에서 파싱 에러로 즉시 드러난다 - 의도된 동작).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Annotated, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .enums import (
    AlertLevel,
    AlertReason,
    Destination,
    EscortState,
    FaceResult,
    MsgType,
    Node,
    NodeState,
    PpeItem,
    PpeResult,
)

# 대시보드/로그 기준 시간대. MechDog 운영 현장이 한국이므로 KST(+09:00)로 고정한다.
KST = timezone(timedelta(hours=9))


def now_iso() -> datetime:
    """현재 시각을 KST(+09:00) 타임존 정보가 붙은 datetime으로 반환."""
    return datetime.now(KST)


def new_session_id(node: Node = Node.MECHDOG_A) -> str:
    """방문자 세션 ID 발급.

    A가 방문자를 처음 감지했을 때 호출해 세션을 열고, 이후 B/C/D는 이 값을
    Envelope.session_id 로 그대로 물려받아 같은 방문자의 메시지를 추적한다.

    [동시 접근 충돌 분석]
    같은 초에 두 방문자가 동시에 게이트에 접근하면 "초 단위 타임스탬프만"으로
    ID를 만들 경우 충돌한다 (예: sess-20260902120005 형태는 그 초 안에서 유일하지
    않음). 여기에 프로세스 내부 순번(카운터)만 덧붙이는 방법도 검토했지만,
    A 서비스가 재시작되면 순번이 0부터 다시 시작해 재시작 전 세션과 겹칠 수 있고,
    (향후 A가 여러 인스턴스로 뜨는 경우) 인스턴스마다 카운터가 별도라 역시 겹칠
    수 있어 완전한 해법이 아니다.

    최종적으로 선택한 방식: 타임스탬프(가독성/정렬용) + uuid4 8자리(고유성 보장).
    uuid4는 프로세스 재시작이나 다중 인스턴스 여부와 무관하게 128비트 난수이므로
    (8자리만 써도 32비트 = 약 43억분의 1 충돌 확률) 순번 관리 없이도 실질적으로
    충돌하지 않는다. 타임스탬프 접두어는 유일성 보장 목적이 아니라 로그를 눈으로
    볼 때 시간순으로 정렬/식별하기 쉽게 하기 위한 것이다.
    """
    ts = datetime.now(KST).strftime("%Y%m%d%H%M%S")
    return f"sess-{ts}-{node.value}-{uuid.uuid4().hex[:8]}"


class Point(BaseModel):
    """실내 좌표. 단위는 미터(m)로 통일."""

    model_config = ConfigDict(extra="forbid")

    x: float
    y: float
    z: float = 0.0


class PayloadBase(BaseModel):
    model_config = ConfigDict(extra="forbid")


class VisionFacePayload(PayloadBase):
    msg_type: Literal[MsgType.VISION_FACE] = MsgType.VISION_FACE
    visitor_id: str
    result: FaceResult
    confidence: float = Field(ge=0.0, le=1.0)
    similarity: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    snapshot_path: str


class VisionPpePayload(PayloadBase):
    msg_type: Literal[MsgType.VISION_PPE] = MsgType.VISION_PPE
    visitor_id: str
    items: dict[PpeItem, PpeResult]
    overall: PpeResult
    confidence: float = Field(ge=0.0, le=1.0)
    snapshot_path: str


class GateSessionPayload(PayloadBase):
    """A -> B 세션 인계 메시지."""

    msg_type: Literal[MsgType.GATE_SESSION] = MsgType.GATE_SESSION
    visitor_id: str
    face_result: FaceResult
    ppe_result: PpeResult
    handoff_to: Node


class DialogResultPayload(PayloadBase):
    msg_type: Literal[MsgType.DIALOG_RESULT] = MsgType.DIALOG_RESULT
    destination: Destination
    purpose: str
    confidence: float = Field(ge=0.0, le=1.0)
    retry_count: int = Field(ge=0, default=0)


class EscortStatusPayload(PayloadBase):
    msg_type: Literal[MsgType.ESCORT_STATUS] = MsgType.ESCORT_STATUS
    state: EscortState
    destination: Destination
    position: Point
    heading_deg: float = Field(ge=0.0, le=360.0)
    distance_to_target_m: float = Field(ge=0.0)


class AlertEventPayload(PayloadBase):
    msg_type: Literal[MsgType.ALERT_EVENT] = MsgType.ALERT_EVENT
    level: AlertLevel
    reason: AlertReason
    track_id: Optional[str] = None
    snapshot_path: Optional[str] = None
    resolved: bool = False


class SystemHealthPayload(PayloadBase):
    msg_type: Literal[MsgType.SYSTEM_HEALTH] = MsgType.SYSTEM_HEALTH
    node: Node
    state: NodeState
    detail: Optional[str] = None


Payload = Annotated[
    Union[
        VisionFacePayload,
        VisionPpePayload,
        GateSessionPayload,
        DialogResultPayload,
        EscortStatusPayload,
        AlertEventPayload,
        SystemHealthPayload,
    ],
    Field(discriminator="msg_type"),
]


class Envelope(BaseModel):
    """모든 MQTT 메시지의 공통 겉봉투."""

    model_config = ConfigDict(extra="forbid")

    ver: int = 1
    msg_id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    ts: datetime = Field(default_factory=now_iso)
    src: Node
    session_id: str
    payload: Payload

    @field_validator("ts")
    @classmethod
    def _require_timezone(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError(
                "ts must be timezone-aware ISO 8601 (e.g. 2026-09-02T12:00:00+09:00)"
            )
        return v


def make_envelope(*, src: Node, session_id: str, payload: PayloadBase) -> Envelope:
    """Envelope 생성 헬퍼. bus.py의 publish()가 내부적으로 사용."""
    return Envelope(src=src, session_id=session_id, payload=payload)
