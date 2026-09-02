"""MQTT 토픽 생성 규칙 + QoS/Retain 정책.

토픽 규칙: mechdog/v1/<msg_type를 '.'->'/'로 치환> (system.health 는 노드별로 구분해야
하므로 뒤에 노드 이름을 붙인다: mechdog/v1/system/health/<node>).
"""

from __future__ import annotations

from .enums import MsgType, Node

TOPIC_PREFIX = "mechdog/v1"

# 전 토픽 구독용 와일드카드 (echo_subscriber.py, DB 브릿지 등에서 사용)
SUBSCRIBE_ALL = f"{TOPIC_PREFIX}/#"


def topic_for(msg_type: MsgType, node: Node | None = None) -> str:
    """msg_type(+ system.health의 경우 node)에 대응하는 발행 토픽 문자열을 반환."""
    base = msg_type.value.replace(".", "/")
    if msg_type is MsgType.SYSTEM_HEALTH:
        if node is None:
            raise ValueError("system.health 토픽은 node가 필요합니다 (누구 상태인지 구분).")
        return f"{TOPIC_PREFIX}/{base}/{node.value}"
    return f"{TOPIC_PREFIX}/{base}"


# --- QoS 정책 ------------------------------------------------------------
# 근거 (회의록 4-A "통신 서버 관리" 항목과 동일한 기준):
#   - QoS 0: 상태를 "스트림"으로 계속 흘려보내는 메시지. 한두 개 유실돼도
#     곧이어 최신 값이 다시 오므로 재전송 비용을 들일 이유가 없다.
#   - QoS 1: "판정 결과"나 "경고"처럼 그 순간이 유일하게 유효한, 다시 오지 않는
#     이벤트. 유실되면 대응(경고/이관/DB 적재)이 통째로 빠지므로 최소 1회 전달을
#     보장해야 한다.
#   - QoS 2(정확히 1회 전달)는 브로커/클라이언트 핸드셰이크가 4-way라 오버헤드가
#     크고, 이 규모(팀 4명, 노드 8개 남짓)에서는 QoS 1의 "중복 가능, 누락 불가"
#     특성만으로 충분해서 쓰지 않는다.
QOS_POLICY: dict[MsgType, int] = {
    # 얼굴 인가 판정: 유실되면 미인가자를 그대로 통과시키는 것과 같은 효과 -> QoS 1
    MsgType.VISION_FACE: 1,
    # PPE 판정: 유실되면 안전모/조끼 미착용자를 그대로 통과 -> QoS 1
    MsgType.VISION_PPE: 1,
    # A->B 세션 인계: 유실되면 B가 방문자를 못 받아 대화가 시작되지 않음 -> QoS 1
    MsgType.GATE_SESSION: 1,
    # 목적지 확정 결과: 유실되면 C가 어디로 에스코트할지 모름 -> QoS 1
    MsgType.DIALOG_RESULT: 1,
    # 에스코트 위치: 1Hz로 계속 갱신되는 스트림, 한 틱 유실돼도 다음 틱이 바로 옴 -> QoS 0
    MsgType.ESCORT_STATUS: 0,
    # 보안 경고: 유실되면 미인가/복장불량 대응이 발생하지 않음 -> QoS 1 (반드시 전달)
    MsgType.ALERT_EVENT: 1,
    # 헬스체크: 주기적으로 반복 발행되고, LWT가 비정상 종료를 별도로 커버 -> QoS 0
    MsgType.SYSTEM_HEALTH: 0,
}

# --- Retain 정책 ----------------------------------------------------------
# retain=True 로 두는 것은 "새로 접속한 클라이언트(대시보드 등)가 마지막 상태를
# 즉시 봐야 하는" 메시지만. 판정/경고처럼 "그 순간의 이벤트"는 retain 하지 않는다
# (retain 해두면 새 구독자가 오래된 이벤트를 최신 상태처럼 오해할 수 있음).
RETAIN_POLICY: dict[MsgType, bool] = {
    MsgType.VISION_FACE: False,
    MsgType.VISION_PPE: False,
    MsgType.GATE_SESSION: False,
    MsgType.DIALOG_RESULT: False,
    MsgType.ESCORT_STATUS: True,
    MsgType.ALERT_EVENT: False,
    MsgType.SYSTEM_HEALTH: True,
}


def qos_for(msg_type: MsgType) -> int:
    return QOS_POLICY[msg_type]


def retain_for(msg_type: MsgType) -> bool:
    return RETAIN_POLICY[msg_type]
