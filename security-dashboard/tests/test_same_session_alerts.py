#!/usr/bin/env python3
"""같은 session_id 안에서 사유(reason)가 다른/같은 alert.event가 겹칠 때의 회귀 테스트.

배경: 활성 경고를 `session_id`만으로 식별하면, 같은 세션에서 D(예: unauthorized)와
B/C(예: dialog_timeout, escort_lost)가 서로 다른 사유로 경고를 내는 경우 서로
덮어써서 하나가 화면에서 통째로 사라지는 버그가 있었다(2026-09-14 재검토 때 발견).
2026-09-15 수정: 활성 경고를 `(session_id, reason)` 조합으로 식별하도록
`dashboard_state.py`/`mqtt_client.py`를 변경했다 - 이 파일은 그 수정이 실제로
문제를 고치는지 확인한다.

실제 MQTT 브로커나 실물 로봇 연동 없이(Mock), `_on_message`를 직접 호출해서
로직만 검증한다 - `test_alert_forwarding.py`와 같은 방식.

검증 항목:
    1. 같은 세션에서 사유가 다른 경고(D의 unauthorized + B의 dialog_timeout)가
       동시에 표시되고, 관리자가 그중 하나만 지정해서 개별 해제할 수 있다. 또한
       D 자신이 낸 경고가 아닌(B가 낸) 경고를 해제해도 D 내부의 판정 상태
       (security_state)는 건드리지 않아야 한다 - 그렇지 않으면 D의 같은 판정이
       또 들어왔을 때 "안 바뀐 상태"인데 불필요하게 다시 발행해버린다.
    2. 같은 (session_id, reason)의 alert.event가 (중복 전달 등으로) 두 번 들어와도
       활성 목록에 카드가 2개로 늘어나지 않는다(최신 내용으로 갱신될 뿐).
    3. 관리자가 해제한 뒤 같은 세션에서 같은 사유의 위반이 다시 발생하면, 활성
       경고로 다시 등록된다(재경보가 막히지 않는다).

A/D가 같은 사유를 중복 발행하는 문제, B/C가 관리자의 resolved 재발행을 실제로
참고하는지는 팀 합의가 필요한 별개 사항으로 남겨둔다(DECISIONS.md 항목 4 참고) -
이 테스트는 대시보드 자체의 표시/해제 로직만 검증한다. 실물 MechDog 동작은
검증하지 않는다.

실행 (security-dashboard 폴더 기준):
    python tests/test_same_session_alerts.py
"""

from __future__ import annotations

import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent / "app"
sys.path.insert(0, str(APP_DIR))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import mqtt_client as mqtt_client_mod  # noqa: E402
from test_alert_forwarding import external_envelope, feed, make_client  # noqa: E402

FAILURES: list[str] = []


def check(label: str, cond: bool) -> None:
    status = "PASS" if cond else "FAIL"
    print(f"[{status}] {label}")
    if not cond:
        FAILURES.append(label)


def active_reasons(state) -> set[str]:
    return {a["reason"] for a in state.snapshot()["active_alerts"]}


def scenario_1_same_session_different_reasons() -> None:
    print("\n--- 시나리오 1: 같은 세션, 서로 다른 사유의 경고 동시 표시 + 개별 해제 ---")
    client, state, published = make_client()
    session_s = "sess-20260915-mechdog_a-multi0001"

    # D 자신: 얼굴 미인가 -> ALERT(reason=unauthorized)
    feed(
        client,
        "vision.face",
        mqtt_client_mod.make_envelope(
            session_id=session_s,
            payload={
                "msg_type": "vision.face",
                "visitor_id": "visitor-multi",
                "result": "unauthorized",
                "confidence": 0.95,
                "similarity": 0.2,
                "snapshot_path": "/data/snap/multi/face.jpg",
            },
        ),
    )
    check("D의 unauthorized 경고 발행 1건", len(published) == 1)

    # 같은 세션에서 B가 dialog_timeout 발행 (외부, 미해결)
    feed(
        client,
        "alert.event",
        external_envelope(
            src="mechdog_b",
            session_id=session_s,
            payload={
                "msg_type": "alert.event",
                "level": "warn",
                "reason": "dialog_timeout",
                "track_id": "visitor-multi",
                "snapshot_path": None,
                "resolved": False,
            },
        ),
    )

    check(
        "같은 세션에서 D(unauthorized)와 B(dialog_timeout)가 동시에 활성 상태",
        active_reasons(state) == {"unauthorized", "dialog_timeout"},
    )
    check("B의 외부 경고 수신으로 D가 재발행하지 않음(발행 1건 그대로)", len(published) == 1)

    # 관리자가 dialog_timeout만 해제 -> unauthorized는 그대로 남아야 함
    cleared = client.clear_active_alert(session_s, "dialog_timeout")
    check("clear_active_alert(세션, dialog_timeout) 성공", cleared is True)
    check("해제 후에도 unauthorized는 활성 상태로 남음", active_reasons(state) == {"unauthorized"})
    check("dialog_timeout 해제로 resolved 재발행 1건 추가(총 2건)", len(published) == 2)

    # D가 낸 게 아닌(B가 낸) 경고를 해제했으므로, D의 내부 판정 상태(security_state)는
    # 건드리지 않아야 한다 - 같은 vision.face(unauthorized)가 다시 들어와도 상태가
    # 안 바뀌었으니 재발행하면 안 된다.
    feed(
        client,
        "vision.face",
        mqtt_client_mod.make_envelope(
            session_id=session_s,
            payload={
                "msg_type": "vision.face",
                "visitor_id": "visitor-multi",
                "result": "unauthorized",
                "confidence": 0.95,
                "similarity": 0.2,
                "snapshot_path": "/data/snap/multi/face_2.jpg",
            },
        ),
    )
    check(
        "B의 경고만 해제했을 뿐이므로 D의 판정 상태는 그대로(재발행 없음, 여전히 2건)",
        len(published) == 2,
    )
    check("unauthorized는 여전히 활성 상태 1건", active_reasons(state) == {"unauthorized"})

    # 이번엔 D 자신의 unauthorized를 해제 -> 이번엔 reset_status가 걸려야 한다
    cleared_d = client.clear_active_alert(session_s, "unauthorized")
    check("clear_active_alert(세션, unauthorized) 성공", cleared_d is True)
    check("두 사유 모두 해제 후 활성 경고 없음", active_reasons(state) == set())

    # D 자신의 경고를 해제했으므로 이번엔 판정 상태가 초기화되어, 같은 판정이 다시
    # 오면 "새로운 변화"로 취급돼 재발행돼야 한다(재경보 가능).
    feed(
        client,
        "vision.face",
        mqtt_client_mod.make_envelope(
            session_id=session_s,
            payload={
                "msg_type": "vision.face",
                "visitor_id": "visitor-multi",
                "result": "unauthorized",
                "confidence": 0.95,
                "similarity": 0.2,
                "snapshot_path": "/data/snap/multi/face_3.jpg",
            },
        ),
    )
    # 지금까지 발행 횟수: ①unauthorized 발생 ②dialog_timeout 해제 ③unauthorized 해제
    # ④이번 재발행 = 4건째
    check("D 자신의 경고 해제 후에는 같은 판정이 재발행됨(4건째)", len(published) == 4)
    check("재발행 후 unauthorized가 다시 활성 상태", active_reasons(state) == {"unauthorized"})


def scenario_2_duplicate_receipt_no_duplicate_card() -> None:
    print("\n--- 시나리오 2: 같은 (session_id, reason) 중복 수신 시 카드 중복 방지 ---")
    client, state, published = make_client()
    session_s = "sess-20260915-mechdog_c-dup0002"

    payload = {
        "msg_type": "alert.event",
        "level": "warn",
        "reason": "escort_lost",
        "track_id": None,
        "snapshot_path": None,
        "resolved": False,
    }
    # MQTT QoS 1은 "중복 전달 가능"이므로(schema/topics.json), 같은 경고가 두 번
    # 들어오는 상황을 재현한다(msg_id/ts만 다르고 나머지는 동일 - 실제 재전달과 동일한 모양).
    feed(client, "alert.event", external_envelope(src="mechdog_c", session_id=session_s, payload=payload))
    feed(client, "alert.event", external_envelope(src="mechdog_c", session_id=session_s, payload=payload))

    active = state.snapshot()["active_alerts"]
    check("중복 수신에도 활성 카드는 1개만 존재", len(active) == 1 and active[0]["reason"] == "escort_lost")
    check("D는 외부 경고를 재발행하지 않음(발행 0건)", len(published) == 0)


def scenario_3_reraise_after_resolve() -> None:
    print("\n--- 시나리오 3: 해제 후 같은 사유 재발생 ---")
    client, state, published = make_client()
    session_s = "sess-20260915-mechdog_a-reraise0003"

    def feed_ppe(overall: str, helmet: str) -> None:
        feed(
            client,
            "vision.ppe",
            mqtt_client_mod.make_envelope(
                session_id=session_s,
                payload={
                    "msg_type": "vision.ppe",
                    "visitor_id": "visitor-reraise",
                    "items": {"helmet": helmet, "vest": "pass"},
                    "overall": overall,
                    "confidence": 0.9,
                    "snapshot_path": "/data/snap/reraise/ppe.jpg",
                },
            ),
        )

    # 1차: 안전모 미착용 -> WARNING
    feed_ppe("fail", "fail")
    check("1차 위반으로 no_helmet 경고 발행", len(published) == 1)
    check("no_helmet이 활성 상태", active_reasons(state) == {"no_helmet"})

    # 관리자가 해제
    cleared = client.clear_active_alert(session_s, "no_helmet")
    check("관리자 해제 성공", cleared is True)
    check("해제 후 활성 경고 없음", active_reasons(state) == set())

    # 같은 세션에서 안전모 미착용이 다시 발생 -> 재경보돼야 함
    feed_ppe("fail", "fail")
    # 지금까지 발행 횟수: ①no_helmet 발생 ②해제 ③이번 재발행 = 3건째
    check("해제 후 같은 사유 재발생 시 다시 경고 발행됨(3건째)", len(published) == 3)
    check("no_helmet이 다시 활성 상태로 등록됨", active_reasons(state) == {"no_helmet"})


def main() -> None:
    orig_warning = mqtt_client_mod.warning_action
    orig_alert = mqtt_client_mod.alert_action
    mqtt_client_mod.warning_action = lambda: None
    mqtt_client_mod.alert_action = lambda: None
    try:
        scenario_1_same_session_different_reasons()
        scenario_2_duplicate_receipt_no_duplicate_card()
        scenario_3_reraise_after_resolve()
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
