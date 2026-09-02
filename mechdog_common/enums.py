"""MechDog 프로젝트 전역 고정 상수.

여기 정의된 값은 팀 전체가 공유하는 "규약"이다. 로컬에서 값을 추가/변경하면
다른 팀원의 메시지 파싱이 깨지므로, 변경이 필요하면 PR로만 반영한다.
"""

from __future__ import annotations

from enum import Enum


class Node(str, Enum):
    """MQTT 클라이언트 ID / 컨테이너 이름과 1:1로 매칭되는 노드 식별자."""

    MECHDOG_A = "mechdog_a"
    MECHDOG_B = "mechdog_b"
    MECHDOG_C = "mechdog_c"
    MECHDOG_D = "mechdog_d"
    RPI = "rpi"
    PC = "pc"
    DB = "db"
    DASHBOARD = "dashboard"


class MsgType(str, Enum):
    """Envelope.payload 의 discriminator 값. topics.py 의 토픽 경로와도 1:1 대응."""

    VISION_FACE = "vision.face"
    VISION_PPE = "vision.ppe"
    GATE_SESSION = "gate.session"
    DIALOG_RESULT = "dialog.result"
    ESCORT_STATUS = "escort.status"
    ALERT_EVENT = "alert.event"
    SYSTEM_HEALTH = "system.health"


class FaceResult(str, Enum):
    """얼굴 인가 판정 결과.

    UNAUTHORIZED(미인가)와 UNDETERMINED(판정 불가)는 절대 합치지 않는다.
    전자는 등록되지 않은 얼굴로 확정된 것이라 D의 보안 대응(경고/출동)으로 이어지고,
    후자는 인식 자체가 실패한 것이라 B의 재촬영 유도로 이어진다. 후속 처리 경로가
    완전히 다르기 때문에 2값으로 합치면 오탐 시 잘못된 대응(예: 재촬영 실패자를
    바로 경고 처리)이 발생한다.
    """

    AUTHORIZED = "authorized"
    UNAUTHORIZED = "unauthorized"
    UNDETERMINED = "undetermined"


class PpeResult(str, Enum):
    """PPE(안전모/안전조끼) 착용 판정 결과. FaceResult와 동일한 이유로 3값을 유지한다."""

    PASS = "pass"
    FAIL = "fail"
    UNDETERMINED = "undetermined"


class PpeItem(str, Enum):
    HELMET = "helmet"
    VEST = "vest"


class AlertLevel(str, Enum):
    INFO = "info"
    WARN = "warn"
    CRITICAL = "critical"


class AlertReason(str, Enum):
    UNAUTHORIZED = "unauthorized"
    NO_HELMET = "no_helmet"
    NO_VEST = "no_vest"
    FACE_TIMEOUT = "face_timeout"
    ESCORT_LOST = "escort_lost"


class EscortState(str, Enum):
    IDLE = "idle"
    MOVING = "moving"
    PAUSED = "paused"
    ARRIVED = "arrived"
    ABORTED = "aborted"


class NodeState(str, Enum):
    BOOTING = "booting"
    READY = "ready"
    BUSY = "busy"
    ERROR = "error"
    OFFLINE = "offline"


# TODO: 실제 값으로 교체 필요 - 담당자: 최현수/여도훈
# 목적지 ID <-> 실내 좌표 매핑표가 확정되기 전까지 임시로 5개만 넣어둔다.
# 최현수(에스코트/맵) + 여도훈(게이트) 협의 후 확정되면 여기 값만 바꾸면 되고,
# 다른 코드는 Destination enum 멤버 이름을 참조하므로 값(value)이 바뀌어도 영향 없다.
class Destination(str, Enum):
    LOBBY = "lobby"
    MEETING_ROOM_1 = "meeting_room_1"
    MEETING_ROOM_2 = "meeting_room_2"
    OFFICE_2F = "office_2f"
    WAREHOUSE = "warehouse"


# TODO: 실제 값으로 교체 필요 - 담당자: 최현수/여도훈
# 얼굴 임베딩 코사인 유사도 임계값. 회의록 기준 0.5~0.6 권장 범위 중 임시로 중간값 사용.
# 등록자 데이터셋으로 실측 튜닝 후 확정 필요 (여도훈 vision-service 담당,
# 오탐율 기준은 최현수와 협의).
FACE_SIMILARITY_THRESHOLD = 0.55
