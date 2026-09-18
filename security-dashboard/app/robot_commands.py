"""D 로봇(MechDog D) 동작 명령 인터페이스.

2026-09-17: 고정 배치(A 바로 옆, 이동 없음) 시나리오로 실물 연동 1단계 구현.
드라이버는 두 가지뿐이다.

    MECHDOG_D_DRIVER=mock   (기본값) - 콘솔 출력만 함. 실물 없는 팀원 환경에서도
                            항상 이 모드로 그대로 동작해야 한다.
    MECHDOG_D_DRIVER=serial - 실제 UART로 CMD 프로토콜을 보낸다. 이 모드일 때는
                            MECHDOG_D_SERIAL_PORT를 반드시 지정해야 한다(임의로
                            COM3 같은 기본값을 쓰지 않는다 - 잘못된 포트에 실수로
                            쓰는 사고를 피하기 위해서다).

CMD 프로토콜 문자열은 추측이 아니라
references/03 Arduino Programming Projects/05 Serial Communication Practical
Lessons/MechDog_Slave_Program/MechDog_uart/MechDog_uart.ino 의 실제 파싱 로직을
근거로 만들었다:
    - "CMD|f0|f1|...|$" 형태로, 마지막 필드 뒤에도 "|"가 있어야 한다(63-69행 파싱 규칙).
    - case 2(동작 그룹 호출, 121-131행) + actions_flg==1의 case 6(325행)이
      action_run("stand_two_legs")를 실행 -> "CMD|2|1|6|$"
    - 같은 경로의 case 16(365행)이 action_run("normal_attitude") -> "CMD|2|1|16|$"
    - 부저(case 7)는 이 펌웨어에 아직 없다 - firmware/mechdog_d_uart/ 의 패치
      제안 참고(원본 references/는 수정하지 않았고, ESP32에 업로드도 하지 않았다).
      "CMD|7|1|$" 는 그 패치가 실제로 적용된 이후에만 의미가 있다.

로봇은 이동하지 않으므로(2026-09-17 시나리오 변경) 이동/복귀 관련 명령은 없다.
경고 자세(stand_two_legs)+부저는 세션과 무관하게 로봇 전체에 걸린 "지금 경고
중인가"라는 하나의 물리 상태로 다룬다 - 로봇이 1대뿐이라 세션별로 나뉜 물리
상태를 가질 수 없기 때문이다(security-dashboard/README.md의 설계 설명 참고).
"""

from __future__ import annotations

import os
import threading
import traceback

# --- 명령 문자열 (파일 상단 docstring의 근거 참고) --------------------------

_STAND_TWO_LEGS_CMD = "CMD|2|1|6|$"
_NORMAL_ATTITUDE_CMD = "CMD|2|1|16|$"
_BUZZER_ONESHOT_CMD = "CMD|7|1|$"  # firmware/mechdog_d_uart/ 패치 제안 - 아직 실물 펌웨어에 없음

# --- 드라이버 설정 (모듈 로드 시 환경변수로 1회 초기화, configure()로 재설정 가능) ---

DRIVER = "mock"
_SERIAL_PORT: str | None = None
_SERIAL_BAUD = 9600
_BUZZER_INTERVAL_S = 1.0

_serial_conn = None  # 지연 연결 - configure()/에러 시 None으로 리셋되어 다음 전송에서 재시도
_last_error: str | None = None

_write_lock = threading.Lock()  # 자세 명령과 부저 반복 스레드가 같은 시리얼에 동시에 쓰지 않도록

_buzzer_thread: threading.Thread | None = None
_buzzer_stop_event = threading.Event()


def configure(
    *,
    driver: str | None = None,
    port: str | None = None,
    baud: int | None = None,
    buzzer_interval_s: float | None = None,
) -> None:
    """드라이버 설정을 (재)적용한다.

    인자를 생략하면 환경변수(MECHDOG_D_DRIVER 등)에서 읽는다 - 앱 시작 시
    자동으로 그렇게 된다(파일 맨 아래 configure() 최초 호출 참고). 테스트는
    이 함수를 인자와 함께 직접 호출해서, 프로세스 재시작이나 모듈 reload 없이
    mock/serial을 오갈 수 있다.
    """
    global DRIVER, _SERIAL_PORT, _SERIAL_BAUD, _BUZZER_INTERVAL_S, _serial_conn

    DRIVER = driver if driver is not None else os.environ.get("MECHDOG_D_DRIVER", "mock")
    if DRIVER not in ("mock", "serial"):
        raise ValueError(f"MECHDOG_D_DRIVER는 'mock' 또는 'serial'이어야 합니다 (받은 값: {DRIVER!r})")

    _SERIAL_PORT = port if port is not None else os.environ.get("MECHDOG_D_SERIAL_PORT")
    if DRIVER == "serial" and not _SERIAL_PORT:
        raise ValueError(
            "MECHDOG_D_DRIVER=serial인데 MECHDOG_D_SERIAL_PORT가 없습니다. "
            "잘못된 포트에 실수로 명령을 보내는 사고를 피하기 위해 COM3 같은 임의 "
            "기본값을 쓰지 않습니다 - 실제 포트(예: COM5, /dev/ttyUSB0)를 명시하세요."
        )

    _SERIAL_BAUD = baud if baud is not None else int(os.environ.get("MECHDOG_D_SERIAL_BAUD", "9600"))
    _BUZZER_INTERVAL_S = (
        buzzer_interval_s
        if buzzer_interval_s is not None
        else float(os.environ.get("MECHDOG_D_BUZZER_INTERVAL_S", "1.0"))
    )
    _serial_conn = None  # 드라이버/포트가 바뀌었을 수 있으니 다음 전송에서 새로 연결


def _get_serial():
    """실제 pyserial 연결을 지연 생성한다.

    테스트에서는 이 함수 자체를 통째로 바꿔치기해서(가짜 연결 객체를 반환하도록)
    실물 포트를 전혀 열지 않고도 _send()의 나머지 로직을 검증한다.
    """
    global _serial_conn
    if _serial_conn is None:
        import serial  # 지연 import - mock 모드에서는 pyserial이 없어도 이 줄까지 오지 않는다

        _serial_conn = serial.Serial(_SERIAL_PORT, _SERIAL_BAUD, timeout=1)
    return _serial_conn


def _send(cmd: str) -> bool:
    """mock이면 콘솔 출력만, serial이면 실제로 씀. 실패해도 예외를 절대 밖으로 던지지 않는다.

    이 함수는 MQTT 콜백 스레드(mqtt_client._on_message)에서 호출될 수 있어서,
    여기서 예외가 새어나가면 paho-mqtt의 콜백이 죽고 이후 메시지 처리가 멈출
    위험이 있다 - 그래서 광범위하게 잡아 로그만 남기고 False를 반환한다.
    """
    global _last_error, _serial_conn

    if DRIVER != "serial":
        print(f"[D ROBOT][mock] would send: {cmd}")
        return True

    try:
        with _write_lock:
            conn = _get_serial()
            conn.write(cmd.encode("ascii"))
        _last_error = None
        return True
    except Exception as exc:  # noqa: BLE001 - 의도적으로 넓게 잡음(실물 연결 실패가 대시보드를 죽이면 안 됨)
        _last_error = f"{type(exc).__name__}: {exc}"
        print(f"[D ROBOT][serial] 전송 실패 ({cmd!r}): {_last_error}")
        traceback.print_exc()
        _serial_conn = None  # 다음 시도에서 재연결하도록 리셋
        return False


def last_error() -> str | None:
    """웹 화면에 ERROR 상태를 보여주기 위한 조회용 - web_server.py에서 사용."""
    return _last_error


def is_warning_active() -> bool:
    """지금 로봇이 경고 자세+부저 상태인지(부저 반복 스레드가 살아있는지)."""
    return _buzzer_thread is not None and _buzzer_thread.is_alive()


def _buzzer_loop() -> None:
    while not _buzzer_stop_event.is_set():
        _send(_BUZZER_ONESHOT_CMD)
        _buzzer_stop_event.wait(_BUZZER_INTERVAL_S)


def start_buzzer_and_posture() -> None:
    """경고 자세(stand_two_legs) + 부저 반복 시작.

    이미 진행 중이면(부저 스레드가 살아있으면) 아무 것도 하지 않고 그냥
    돌아간다 - stand_two_legs 명령도 다시 보내지 않는다. 이게 "같은 세션에
    사유가 추가되거나 다른 세션이 겹쳐도 물리 동작은 1회만"의 핵심이다.
    세션/사유별 판단은 이 함수를 부르기 전에 이미 끝나 있을 필요가 없다 - 이
    함수 자체가 (전역, 세션 무관) 멱등성을 보장한다.
    """
    global _buzzer_thread
    if _buzzer_thread is not None and _buzzer_thread.is_alive():
        return

    _send(_STAND_TWO_LEGS_CMD)
    _buzzer_stop_event.clear()
    _buzzer_thread = threading.Thread(target=_buzzer_loop, daemon=True, name="mechdog-d-buzzer")
    _buzzer_thread.start()


def stop_buzzer_and_return_posture() -> None:
    """부저 반복 중지 + 기본 자세(normal_attitude) 복귀.

    호출하는 쪽(mqtt_client.py)이 "D 소유 활성 경고가 전역적으로 0개가 됐을
    때만" 이 함수를 부르도록 책임진다 - 이 함수 자체는 세션/경고를 모른다.
    """
    _buzzer_stop_event.set()
    if _buzzer_thread is not None:
        _buzzer_thread.join(timeout=2.0)
    _send(_NORMAL_ATTITUDE_CMD)


def _reset_for_tests() -> None:
    """테스트 전용: 모듈 전역 상태(스레드, 드라이버, 에러)를 mock 기준으로 초기화한다.

    robot_commands는 모듈 전역 상태를 갖고 있어서(로봇이 실제로 1대뿐이라
    인스턴스화하지 않음) 테스트 간에 상태가 새면 안 된다 - 각 테스트 시나리오
    시작 전에 이 함수를 호출해 깨끗한 상태에서 시작한다.
    """
    global _serial_conn, _last_error, _buzzer_thread
    _buzzer_stop_event.set()
    if _buzzer_thread is not None:
        _buzzer_thread.join(timeout=2.0)
    _buzzer_thread = None
    _buzzer_stop_event.clear()
    _serial_conn = None
    _last_error = None
    configure(driver="mock")


# --- mqtt_client.py가 그대로 쓰는 이름들(기존 호출부와의 호환) -----------------


def warning_action() -> None:
    print("[D ROBOT] WARNING ACTION")
    start_buzzer_and_posture()


def alert_action() -> None:
    print("[D ROBOT] ALERT ACTION")
    start_buzzer_and_posture()


def clear_alert() -> None:
    print("[D ROBOT] CLEAR_ALERT")
    stop_buzzer_and_return_posture()


def emergency_stop() -> None:
    """주의: 이 단계의 EMERGENCY_STOP은 실제 전원 차단이 아니다.

    로봇이 이동하지 않는 고정 배치 시나리오라, 지금 할 수 있는 것은 부저 반복을
    멈추고 normal_attitude를 요청하는 것뿐이다(웹 화면에도 동일하게 표시,
    security-dashboard/app/templates/index.html 참고). 실제 전원 차단/모터
    토크 해제 같은 진짜 긴급정지는 구현돼 있지 않다 - 필요하면 별도로 물리
    스위치나 배터리 커넥터를 써야 한다.
    """
    print(
        "[D ROBOT] EMERGENCY_STOP "
        "(주의: 실제 전원 차단이 아님 - 부저 중지 + normal_attitude 요청만 수행)"
    )
    stop_buzzer_and_return_posture()


configure()  # 모듈 로드 시 1회: 환경변수 기준으로 기본 설정(기본값 mock)
