#!/usr/bin/env python3
"""D 로봇 실물 연동(고정 배치, Serial/UDP) 회귀 테스트.

실제 하드웨어를 전혀 쓰지 않는다 - MQTT는 test_alert_forwarding.py와 같은 방식으로
_on_message를 직접 호출하고(Mock), Serial/UDP는 각각 robot_commands._get_serial /
_get_udp_socket을 FakeSerialConn / FakeUdpSocket으로 바꿔치기해서(Fake) 실제 포트나
네트워크를 열지 않는다. ESP32 업로드도, 실물 명령 전송도 하지 않는다.

검증 항목 (정책 문서: security-dashboard/README.md "실물 D 로봇 연동" 절 참고):
    1. 동일 세션 다중 사유에서 물리 경고(stand_two_legs) 1회
    2. 서로 다른 세션 경고가 겹쳐도 물리 경고 1회
    3. 일부 경고만 해제하면 기본 자세로 복귀하지 않음
    4. 모든 D 소유 경고 해제 시에만 부저 중지 및 기본 자세 복귀
    5. B/C 경고가 자세·부저를 실행하지 않음
    6. A의 NORMAL 재판정만으로 물리 경고가 종료되지 않음
    7. Serial 전송 실패 시 대시보드(MQTT 콜백)가 종료되지 않음
    8. 반복 호출해도 물리 명령이 중복 전송되지 않음(부저 반복 스레드는 2026-09-27 제거)
    9. UDP 드라이버에서 부저(CMD|7)와 자세 명령이 별개 패킷으로 분리 전송됨
    10. UDP 전송 실패 시 대시보드(MQTT 콜백)가 종료되지 않음

실행 (security-dashboard 폴더 기준):
    python tests/test_robot_dispatch.py
"""

from __future__ import annotations

import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent / "app"
sys.path.insert(0, str(APP_DIR))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import mqtt_client as mqtt_client_mod  # noqa: E402
import robot_commands  # noqa: E402
from test_alert_forwarding import external_envelope, feed, make_client  # noqa: E402

FAILURES: list[str] = []


def check(label: str, cond: bool) -> None:
    status = "PASS" if cond else "FAIL"
    print(f"[{status}] {label}")
    if not cond:
        FAILURES.append(label)


class FakeSerialConn:
    """robot_commands._get_serial()을 대체하는 가짜 시리얼 연결 - 실제 포트를 열지 않는다."""

    def __init__(self, fail: bool = False) -> None:
        self.writes: list[bytes] = []
        self.fail = fail

    def write(self, data: bytes) -> int:
        if self.fail:
            raise OSError("simulated serial failure (test)")
        self.writes.append(data)
        return len(data)


class FakeUdpSocket:
    """robot_commands._get_udp_socket()을 대체하는 가짜 UDP 소켓 - 실제 네트워크를 쓰지 않는다.

    실물 UDP 시험에서 이미 확인된 대로(2026-09 실물 조사) 이 펌웨어는 응답을
    보내지 않으므로, recvfrom()은 기본적으로 항상 timeout을 흉내낸다(응답 있음
    시나리오가 필요하면 responses 리스트에 (addr, bytes)를 미리 넣어둔다).
    """

    def __init__(self, fail: bool = False) -> None:
        self.sent: list[tuple[bytes, tuple[str, int]]] = []
        self.fail = fail
        self.responses: list[tuple[tuple[str, int], bytes]] = []
        self._timeout = None

    def sendto(self, data: bytes, addr: tuple[str, int]) -> int:
        if self.fail:
            raise OSError("simulated udp failure (test)")
        self.sent.append((data, addr))
        return len(data)

    def settimeout(self, value: float) -> None:
        self._timeout = value

    def recvfrom(self, bufsize: int):
        if self.responses:
            return self.responses.pop(0)
        raise TimeoutError("simulated: 실물에서도 응답이 오지 않음을 이미 확인함")


def _setup_serial_driver(port: str = "TEST_PORT", fail: bool = False) -> FakeSerialConn:
    """serial 모드로 전환하되 실제 pyserial은 절대 열지 않는다(FakeSerialConn 사용)."""
    robot_commands.configure(driver="serial", port=port)
    fake = FakeSerialConn(fail=fail)
    robot_commands._get_serial = lambda: fake  # noqa: SLF001 - 테스트 전용 바꿔치기
    return fake


def _setup_udp_driver(host: str = "192.0.2.1", fail: bool = False) -> FakeUdpSocket:
    """udp 모드로 전환하되 실제 네트워크는 절대 쓰지 않는다(FakeUdpSocket 사용)."""
    robot_commands.configure(driver="udp", udp_host=host, udp_port=9027, udp_timeout_s=0.01)
    fake = FakeUdpSocket(fail=fail)
    robot_commands._get_udp_socket = lambda: fake  # noqa: SLF001 - 테스트 전용 바꿔치기
    return fake


def _stand_two_legs_count(fake: FakeSerialConn) -> int:
    return sum(1 for w in fake.writes if b"CMD|2|1|6|$" in w)


def _normal_attitude_count(fake: FakeSerialConn) -> int:
    return sum(1 for w in fake.writes if b"CMD|2|1|99|$" in w)


def _face_unauthorized_envelope(session_id: str, snapshot_suffix: str = "1"):
    return mqtt_client_mod.make_envelope(
        session_id=session_id,
        payload={
            "msg_type": "vision.face",
            "visitor_id": "visitor-x",
            "result": "unauthorized",
            "confidence": 0.95,
            "similarity": 0.2,
            "snapshot_path": f"/data/snap/x/face_{snapshot_suffix}.jpg",
        },
    )


def _ppe_envelope(session_id: str, overall: str, helmet: str):
    return mqtt_client_mod.make_envelope(
        session_id=session_id,
        payload={
            "msg_type": "vision.ppe",
            "visitor_id": "visitor-x",
            "items": {"helmet": helmet, "vest": "pass"},
            "overall": overall,
            "confidence": 0.9,
            "snapshot_path": "/data/snap/x/ppe.jpg",
        },
    )


def scenario_same_session_multi_reason_single_dispatch() -> None:
    print("\n--- 1) 동일 세션 다중 사유 -> 물리 경고 1회 ---")
    robot_commands._reset_for_tests()
    fake = _setup_serial_driver()
    client, state, published = make_client()
    session_s = "sess-robot-0001"

    # 먼저 PPE 위반(WARNING/no_helmet) - security_state._compute_status는
    # face=unauthorized를 ppe=fail보다 항상 우선하므로, 두 사유가 서로 다른
    # alert.event로 각각 발행되게 하려면 WARNING을 먼저 만들고 나중에 ALERT로
    # 전이시켜야 한다(먼저 unauthorized를 보내면 그 뒤 ppe=fail이 와도 상태가
    # 계속 ALERT라 "바뀜"이 없어 두 번째 alert.event가 아예 발행되지 않는다).
    feed(client, "vision.ppe", _ppe_envelope(session_s, overall="fail", helmet="fail"))
    check("첫 위반(WARNING)으로 stand_two_legs 전송됨", _stand_two_legs_count(fake) == 1)
    check("부저 반복이 시작됨", robot_commands.is_warning_active())

    # 같은 세션에서 얼굴 미인가(ALERT, 다른 reason)로 전이
    feed(client, "vision.face", _face_unauthorized_envelope(session_s))

    check("사유가 WARNING->ALERT로 바뀌어도 stand_two_legs는 여전히 1회만 전송됨", _stand_two_legs_count(fake) == 1)
    check("D 소유 활성 경고는 2건(사유별: no_helmet, unauthorized)", len(state.snapshot()["active_alerts"]) == 2)

    robot_commands._reset_for_tests()


def scenario_different_sessions_overlap_single_dispatch() -> None:
    print("\n--- 2) 서로 다른 세션 경고가 겹쳐도 물리 경고 1회 ---")
    robot_commands._reset_for_tests()
    fake = _setup_serial_driver()
    client, state, published = make_client()

    feed(client, "vision.face", _face_unauthorized_envelope("sess-robot-A"))
    feed(client, "vision.face", _face_unauthorized_envelope("sess-robot-B"))

    check("서로 다른 두 세션이 겹쳐도 stand_two_legs는 1회만 전송됨", _stand_two_legs_count(fake) == 1)
    check("두 세션 모두 D 소유 활성 경고로 등록됨(2건)", len(state.snapshot()["active_alerts"]) == 2)

    robot_commands._reset_for_tests()


def scenario_partial_clear_does_not_return_and_full_clear_does() -> None:
    print("\n--- 3) 일부 해제 시 복귀 안 함 / 4) 전부 해제 시에만 복귀 ---")
    robot_commands._reset_for_tests()
    fake = _setup_serial_driver()
    client, state, published = make_client()

    feed(client, "vision.face", _face_unauthorized_envelope("sess-robot-A"))
    feed(client, "vision.face", _face_unauthorized_envelope("sess-robot-B"))

    cleared_a = client.clear_active_alert("sess-robot-A", "unauthorized")
    check("세션 A 해제 자체는 성공", cleared_a is True)
    check("세션 A만 해제했을 때는 normal_attitude를 보내지 않음", _normal_attitude_count(fake) == 0)
    check("부저 스레드가 여전히 살아있음(세션 B가 남음)", robot_commands.is_warning_active())

    cleared_b = client.clear_active_alert("sess-robot-B", "unauthorized")
    check("세션 B 해제도 성공", cleared_b is True)
    check("D 소유 경고가 모두 해제되면 normal_attitude가 전송됨", _normal_attitude_count(fake) == 1)
    check("부저 스레드가 정지됨", not robot_commands.is_warning_active())

    robot_commands._reset_for_tests()


def scenario_external_alert_no_physical_action() -> None:
    print("\n--- 5) B/C 경고가 자세/부저를 실행하지 않음 ---")
    robot_commands._reset_for_tests()
    fake = _setup_serial_driver()
    client, state, published = make_client()

    feed(
        client,
        "alert.event",
        external_envelope(
            src="mechdog_b",
            session_id="sess-robot-ext",
            payload={
                "msg_type": "alert.event",
                "level": "warn",
                "reason": "dialog_timeout",
                "track_id": None,
                "snapshot_path": None,
                "resolved": False,
            },
        ),
    )
    check("B의 외부 경고로는 시리얼 명령이 전혀 나가지 않음", len(fake.writes) == 0)
    check("부저 반복도 시작되지 않음", not robot_commands.is_warning_active())
    check("그래도 화면(active_alerts)에는 표시됨", len(state.snapshot()["active_alerts"]) == 1)

    robot_commands._reset_for_tests()


def scenario_auto_normal_does_not_end_physical_warning() -> None:
    print("\n--- 6) A의 NORMAL 재판정만으로 물리 경고가 종료되지 않음 ---")
    robot_commands._reset_for_tests()
    fake = _setup_serial_driver()
    client, state, published = make_client()
    session_s = "sess-robot-renorm"

    feed(client, "vision.ppe", _ppe_envelope(session_s, overall="fail", helmet="fail"))
    check("최초 위반으로 경고 자세 진입", robot_commands.is_warning_active())

    feed(client, "vision.ppe", _ppe_envelope(session_s, overall="pass", helmet="pass"))
    check("재검사 통과(NORMAL)만으로는 부저/자세가 종료되지 않음", robot_commands.is_warning_active())
    check("normal_attitude가 자동으로 전송되지 않음", _normal_attitude_count(fake) == 0)

    client.clear_active_alert(session_s, "no_helmet")
    check("관리자 수동 해제 후에는 정상 종료됨", not robot_commands.is_warning_active())
    check("이번엔 normal_attitude가 전송됨", _normal_attitude_count(fake) == 1)

    robot_commands._reset_for_tests()


def scenario_serial_failure_does_not_crash() -> None:
    print("\n--- 7) Serial 전송 실패 시 대시보드가 종료되지 않음 ---")
    robot_commands._reset_for_tests()
    _setup_serial_driver(fail=True)
    client, state, published = make_client()

    crashed = False
    try:
        feed(client, "vision.face", _face_unauthorized_envelope("sess-robot-fail"))
    except Exception as exc:  # noqa: BLE001 - 정말 아무 예외도 새어나오면 안 됨을 검증
        crashed = True
        print(f"    예외가 전파됨(실패로 간주): {exc!r}")

    check("Serial write 실패가 MQTT 콜백 밖으로 예외를 던지지 않음", not crashed)
    check("실패가 last_error()에 기록됨", robot_commands.last_error() is not None)
    check("경고 자체는 대시보드에 정상 기록됨(활성 경고 1건)", len(state.snapshot()["active_alerts"]) == 1)

    robot_commands._reset_for_tests()


def scenario_repeated_start_not_duplicated() -> None:
    print("\n--- 8) 반복 호출해도 물리 명령이 중복 전송되지 않음 ---")
    robot_commands._reset_for_tests()
    fake = _setup_serial_driver()

    robot_commands.start_buzzer_and_posture()
    robot_commands.start_buzzer_and_posture()
    robot_commands.start_buzzer_and_posture()

    check("반복 호출해도 warning_active는 계속 True", robot_commands.is_warning_active())
    check("stand_two_legs 전송도 최초 1회뿐", _stand_two_legs_count(fake) == 1)
    check("버저 on 명령도 최초 1회뿐", sum(1 for w in fake.writes if b"CMD|7|1|$" in w) == 1)

    robot_commands.stop_buzzer_and_return_posture()
    check("정지 후에는 경고 비활성", not robot_commands.is_warning_active())
    robot_commands._reset_for_tests()


def scenario_udp_driver_separates_posture_and_buzzer() -> None:
    print("\n--- 9) UDP 드라이버: 부저(CMD|7)와 자세 명령이 완전히 분리되어 전송됨 ---")
    robot_commands._reset_for_tests()
    fake = _setup_udp_driver()

    robot_commands.start_buzzer_and_posture()
    sent_cmds = [data for data, _addr in fake.sent]
    check("경고 시작 시 stand_two_legs 1회 전송", sent_cmds.count(b"CMD|2|1|6|$") == 1)
    check("경고 시작 시 버저 on(CMD|7|1|$) 1회 전송 - 자세 명령과 별개 패킷", sent_cmds.count(b"CMD|7|1|$") == 1)
    check("모든 전송이 설정한 (host, 9027)로 나감", all(addr == ("192.0.2.1", 9027) for _data, addr in fake.sent))

    robot_commands.stop_buzzer_and_return_posture()
    sent_cmds = [data for data, _addr in fake.sent]
    check("해제 시 버저 off(CMD|7|0|$) 1회 전송", sent_cmds.count(b"CMD|7|0|$") == 1)
    check("해제 시 기본 자세 복귀(CMD|2|1|99|$) 1회 전송 - 버저 off와 별개 패킷", sent_cmds.count(b"CMD|2|1|99|$") == 1)
    check("last_error는 비어 있음(응답 없음은 오류가 아님)", robot_commands.last_error() is None)

    robot_commands._reset_for_tests()


def scenario_udp_failure_does_not_crash() -> None:
    print("\n--- 10) UDP 전송 실패 시 대시보드가 종료되지 않음 ---")
    robot_commands._reset_for_tests()
    _setup_udp_driver(fail=True)
    client, state, published = make_client()

    crashed = False
    try:
        feed(client, "vision.face", _face_unauthorized_envelope("sess-robot-udp-fail"))
    except Exception as exc:  # noqa: BLE001 - 정말 아무 예외도 새어나오면 안 됨을 검증
        crashed = True
        print(f"    예외가 전파됨(실패로 간주): {exc!r}")

    check("UDP sendto 실패가 MQTT 콜백 밖으로 예외를 던지지 않음", not crashed)
    check("실패가 last_error()에 기록됨", robot_commands.last_error() is not None)
    check("경고 자체는 대시보드에 정상 기록됨(활성 경고 1건)", len(state.snapshot()["active_alerts"]) == 1)

    robot_commands._reset_for_tests()


def main() -> None:
    scenario_same_session_multi_reason_single_dispatch()
    scenario_different_sessions_overlap_single_dispatch()
    scenario_partial_clear_does_not_return_and_full_clear_does()
    scenario_external_alert_no_physical_action()
    scenario_auto_normal_does_not_end_physical_warning()
    scenario_serial_failure_does_not_crash()
    scenario_repeated_start_not_duplicated()
    scenario_udp_driver_separates_posture_and_buzzer()
    scenario_udp_failure_does_not_crash()

    print()
    if FAILURES:
        print(f"{len(FAILURES)}건 실패:")
        for f in FAILURES:
            print(f"  - {f}")
        sys.exit(1)
    print("전부 통과.")


if __name__ == "__main__":
    main()
