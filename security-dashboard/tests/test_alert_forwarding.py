#!/usr/bin/env python3
"""alert.event 구독/표시 로직 회귀 테스트 - 실제 MQTT 브로커 없이(Mock) 검증한다.

실물 브로커/로봇 연동은 여기서 하지 않는다 - `SecurityDashboardClient.client.publish`를
네트워크로 내보내는 대신 리스트에 기록하는 스텁으로 바꿔치고, `_on_message`를
paho가 브로커로부터 실제로 메시지를 받았을 때와 동일한 인자 모양으로 직접 호출해서
로직만 검증한다. tools/mock_publisher.py 같은 실제 프로세스 간 발행/구독은 하지
않으므로 "Mock" 테스트다 (docstring 최상단에 명시).

검증 항목 (사용자 요청 우선순위 1):
    1. D 자신의 vision.face/vision.ppe 판정으로 낸 alert.event가 화면(active_alerts/
       recent_alerts)에 반영되고, D의 물리 동작(warning_action/alert_action)이 호출된다.
    2. D가 방금 발행한 메시지가 alert.event 구독으로 자기 자신에게 "echo"되어 돌아와도
       (src=mechdog_d) 중복 표시되거나 재발행 루프가 생기지 않는다.
    3. B/C 등 다른 노드가 낸 alert.event(dialog_timeout, escort_lost)가 화면에 표시되고,
       세션이 다르면 D 자신의 활성 경고와 서로 덮어쓰지 않고 동시에 유지된다. 이때
       D의 물리 동작은 호출되지 않는다(표시만).
    4. 관리자 해제(clear_active_alert)가 지정한 세션만 정확히 지우고, 다른 세션의
       활성 경고는 그대로 남는다. 해제 시 재발행되는 resolved=true 메시지가 다시
       echo돼도 안전하다(2번과 동일한 이유).
    5. 이미 해제된 세션을 다시 해제하려 하면 False를 반환한다.

실행 (security-dashboard 폴더 기준):
    python tests/test_alert_forwarding.py
"""

from __future__ import annotations

import json
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent / "app"
sys.path.insert(0, str(APP_DIR))

import dashboard_state as dashboard_state_mod  # noqa: E402
import mqtt_client as mqtt_client_mod  # noqa: E402

KST = timezone(timedelta(hours=9))

FAILURES: list[str] = []


def check(label: str, cond: bool) -> None:
    status = "PASS" if cond else "FAIL"
    print(f"[{status}] {label}")
    if not cond:
        FAILURES.append(label)


class FakeMqttMessage:
    """paho의 MQTTMessage를 흉내낸다 - _on_message가 쓰는 .topic/.payload만 있으면 된다."""

    def __init__(self, topic: str, envelope: dict) -> None:
        self.topic = topic
        self.payload = json.dumps(envelope, ensure_ascii=False).encode("utf-8")


def external_envelope(*, src: str, session_id: str, payload: dict) -> dict:
    """A/B/C 등 다른 노드가 보냈다고 가정하는 envelope을 직접 만든다.

    mqtt_client.make_envelope()은 src를 SRC_NODE(mechdog_d)로 고정하므로 D가 아닌
    노드의 메시지를 만들 때는 쓸 수 없다 - tools/_common.make_envelope과 같은 모양으로 만든다.
    """
    return {
        "ver": 1,
        "msg_id": uuid.uuid4().hex,
        "ts": datetime.now(KST).isoformat(),
        "src": src,
        "session_id": session_id,
        "payload": payload,
    }


def make_client():
    """실제 브로커에 connect()/loop_start()를 하지 않고 클라이언트만 만든다.

    publish()는 실제 소켓으로 나가면 안 되므로(연결 안 된 상태라 어차피 에러가 나거나,
    설사 연결돼 있어도 이 테스트는 브로커 없이 로직만 보는 게 목적이라) 호출 내용을
    기록만 하는 스텁으로 바꿔친다.
    """
    state = dashboard_state_mod.DashboardState()
    client = mqtt_client_mod.SecurityDashboardClient(dashboard_state=state)
    published: list[dict] = []

    def fake_publish(topic, payload, qos=0, retain=False):
        published.append({"topic": topic, "payload": json.loads(payload)})

    client.client.publish = fake_publish
    return client, state, published


def feed(client, msg_type: str, envelope: dict) -> None:
    topic, _qos, _retain = mqtt_client_mod.topic_qos_retain(msg_type)
    client._on_message(client.client, None, FakeMqttMessage(topic, envelope))


def main() -> None:
    robot_actions: list[str] = []
    orig_warning = mqtt_client_mod.warning_action
    orig_alert = mqtt_client_mod.alert_action
    mqtt_client_mod.warning_action = lambda: robot_actions.append("warning_action")
    mqtt_client_mod.alert_action = lambda: robot_actions.append("alert_action")

    try:
        client, state, published = make_client()

        # --- 1) D 자신의 판정: 세션 A, 얼굴 미인가 -> ALERT ----------------------
        session_a = "sess-20260914-mechdog_a-aaaa0001"
        feed(
            client,
            "vision.face",
            mqtt_client_mod.make_envelope(
                session_id=session_a,
                payload={
                    "msg_type": "vision.face",
                    "visitor_id": "visitor-a",
                    "result": "unauthorized",
                    "confidence": 0.95,
                    "similarity": 0.21,
                    "snapshot_path": "/data/snap/a/face.jpg",
                },
            ),
        )

        check("D 자신의 ALERT 판정 -> alert.event 1건 발행", len(published) == 1)
        check("D의 물리 동작(alert_action) 1회 호출", robot_actions == ["alert_action"])

        snap = state.snapshot()
        check("활성 경고에 세션 A 1건 등록", [a["session_id"] for a in snap["active_alerts"]] == [session_a])
        check("세션 A 경고의 발행처=D로 기록", snap["active_alerts"][0]["src"] == "mechdog_d")
        check("최근 경고 이력 1건", len(snap["recent_alerts"]) == 1)

        # --- 2) D가 방금 낸 메시지가 구독으로 자기 자신에게 echo되어 돌아오는 상황 ---
        echoed = published[0]["payload"]
        feed(client, "alert.event", echoed)

        check("자기 echo 수신 후에도 재발행 안 됨(발행 1건 그대로)", len(published) == 1)
        check("자기 echo 수신 후에도 활성 경고 중복 없음(1건 그대로)", len(state.snapshot()["active_alerts"]) == 1)
        check("자기 echo 수신 후에도 이력 중복 없음(1건 그대로)", len(state.snapshot()["recent_alerts"]) == 1)
        check("자기 echo로 물리 동작이 또 호출되지 않음", robot_actions == ["alert_action"])

        # --- 3) B가 낸 외부 경고: 세션 B, dialog_timeout ------------------------
        session_b = "sess-20260914-mechdog_b-bbbb0002"
        feed(
            client,
            "alert.event",
            external_envelope(
                src="mechdog_b",
                session_id=session_b,
                payload={
                    "msg_type": "alert.event",
                    "level": "warn",
                    "reason": "dialog_timeout",
                    "track_id": "visitor-b",
                    "snapshot_path": None,
                    "resolved": False,
                },
            ),
        )

        check("B의 외부 경고 수신 시 D가 재발행하지 않음(발행 1건 그대로)", len(published) == 1)
        check("B의 외부 경고로 D 물리 동작이 호출되지 않음", robot_actions == ["alert_action"])

        snap = state.snapshot()
        active_sessions = {a["session_id"] for a in snap["active_alerts"]}
        check("세션 A(D)와 세션 B(외부)가 동시에 활성 상태", active_sessions == {session_a, session_b})
        b_alert = next(a for a in snap["active_alerts"] if a["session_id"] == session_b)
        check("세션 B 경고의 발행처=B로 기록", b_alert["src"] == "mechdog_b")
        check("세션 B 경고 사유=dialog_timeout", b_alert["reason"] == "dialog_timeout")
        check("최근 경고 이력 2건(A, B)", len(snap["recent_alerts"]) == 2)

        # --- 4) C가 낸 외부 경고: 세션 C, escort_lost ---------------------------
        session_c = "sess-20260914-mechdog_c-cccc0003"
        feed(
            client,
            "alert.event",
            external_envelope(
                src="mechdog_c",
                session_id=session_c,
                payload={"msg_type": "alert.event", "level": "warn", "reason": "escort_lost", "resolved": False},
            ),
        )
        active_sessions = {a["session_id"] for a in state.snapshot()["active_alerts"]}
        check("세션 A/B/C 세 개 동시 활성", active_sessions == {session_a, session_b, session_c})

        # --- 5) 관리자가 세션 A(D 자신의 경고)만 해제 ----------------------------
        cleared = client.clear_active_alert(session_a)
        check("clear_active_alert(A) 성공", cleared is True)
        check("해제 시 resolved=true 재발행 1건 추가(총 2건)", len(published) == 2)
        check("재발행 envelope의 src=mechdog_d", published[1]["payload"]["src"] == "mechdog_d")
        check("재발행 payload.resolved=true", published[1]["payload"]["payload"]["resolved"] is True)

        active_sessions = {a["session_id"] for a in state.snapshot()["active_alerts"]}
        check("세션 A는 활성 목록에서 제거, B/C는 유지", active_sessions == {session_b, session_c})
        check("이력은 4건(A발생, A해제 포함 누적)", len(state.snapshot()["recent_alerts"]) == 4)

        # --- 6) 세션 A 해제 메시지도 구독으로 echo되어 돌아오는 상황 -------------
        resolved_echo = published[1]["payload"]
        feed(client, "alert.event", resolved_echo)
        check("해제 echo 수신 후에도 재발행 안 됨(2건 그대로)", len(published) == 2)
        check("해제 echo 수신 후에도 이력 중복 없음(4건 그대로)", len(state.snapshot()["recent_alerts"]) == 4)
        active_sessions = {a["session_id"] for a in state.snapshot()["active_alerts"]}
        check("해제 echo 이후에도 B/C만 활성으로 유지", active_sessions == {session_b, session_c})

        # --- 7) 이미 해제된 세션 A를 다시 해제하면 실패 --------------------------
        check("이미 해제된 세션 재해제 시도는 False", client.clear_active_alert(session_a) is False)

        # --- 8) 관리자가 세션 B(B가 낸 외부 경고)를 해제 -------------------------
        cleared_b = client.clear_active_alert(session_b)
        check("clear_active_alert(B, 외부 발행 경고)도 성공", cleared_b is True)
        check("세션 B 해제 재발행도 D 명의로 나감", published[2]["payload"]["src"] == "mechdog_d")
        active_sessions = {a["session_id"] for a in state.snapshot()["active_alerts"]}
        check("세션 B 해제 후 C만 활성으로 남음", active_sessions == {session_c})

    finally:
        mqtt_client_mod.warning_action = orig_warning
        mqtt_client_mod.alert_action = orig_alert

    print()
    if FAILURES:
        print(f"{len(FAILURES)}건 실패:")
        for f in FAILURES:
            print(f"  - {f}")
        sys.exit(1)
    print("전부 통과.")


if __name__ == "__main__":
    main()
