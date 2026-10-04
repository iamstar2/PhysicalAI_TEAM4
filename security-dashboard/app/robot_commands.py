"""D 로봇(MechDog D) 동작 명령 인터페이스.

2026-09-27: 실물 D의 실제 펌웨어가 (예전에 가정했던 Arduino UART 스케치가 아니라)
**MicroPython**이고, CMD 프로토콜이 도달하는 경로가 COM 포트(UART0 = MicroPython
REPL)가 아니라 **WiFi/UDP(포트 9027)** 임을 이번 학기 실물 조사로 확정한 뒤 드라이버를
다시 짰다. 아래 세 드라이버를 지원한다.

    MECHDOG_D_DRIVER=mock    (기본값) - 콘솔 출력만 함. 실물 없는 팀원 환경에서도
                             항상 이 모드로 그대로 동작해야 한다.
    MECHDOG_D_DRIVER=serial - COM 포트로 원문 그대로 씀. **주의**: 실물 조사 결과
                             이 포트는 MicroPython REPL이 물려 있어 CMD 파서에
                             도달하지 않는다(레거시/구 Arduino 가정 경로 - 지금
                             하드웨어에서는 검증된 유효 경로가 아니다). 남겨는
                             두되 신규로 이 경로를 신뢰하지 않는다.
    MECHDOG_D_DRIVER=udp    - 실제로 검증된 경로. 로봇의 WiFi UDP 소켓
                             (MECHDOG_D_UDP_HOST:MECHDOG_D_UDP_PORT, 기본 포트 9027)
                             으로 CMD 문자열을 sendto() 한다.

CMD 프로토콜 문자열의 근거(추측 아님, firmware/mechdog_d_uart/build/wifi_buzzer_candidate/main.py
의 실제 소스 확인, 이 파일은 2026-09-20에 로봇 /main.py로 교체 완료 - 다음 부팅부터 적용):
    - "CMD|f0|f1|...|$" 형태, 마지막 필드 뒤에도 "|" 필요 (main.py 파싱 규칙 동일).
    - stand_two_legs: WiFi 분기 `elif _COMMAND == 2`가 `_ACTION_TYPE=1,
      _ACTION_NUM=6`일 때 `dong_zuo_zu_yun_xing(6)` -> `action_list[6]` ==
      "stand_two_legs" -> "CMD|2|1|6|$".
    - 부저: main.py에 새로 추가한 `elif _COMMAND == 7` 분기. `_REC_PARSE_VALUE[1]`이
      1이면(0->1 전이일 때만) `beep.playTone(800,100,True)` 1회, 0이면 상태만 해제.
      즉 "CMD|7|1|$" = 경고 시작(0.1초 원샷, 반복 수신은 펌웨어가 무시),
      "CMD|7|0|$" = 경고 해제(소리 없이 상태만 리셋). **CMD|7은 부저 상태 전이만
      담당하고, 자세와는 완전히 무관한 별개 명령이다** - CMD|7 전송 성공을
      stand_two_legs/정상 자세 복귀가 성공했다는 근거로 쓰면 안 된다.
    - 기본 자세 복귀("normal_attitude" 개념): main.py의 액션 사전(action_list)은
      1~15번뿐이고 옛 Arduino case 16(normal_attitude)에 대응하는 항목이 없다.
      대신 WiFi 분기는 `_ACTION_TYPE==1`일 때 항상 `doghw.set_default_pose(duration=500)`
      을 먼저 호출한 뒤 `dong_zuo_zu_yun_xing(_ACTION_NUM)`을 부르는데, 이 함수는
      `if (dong_zuo <= 15):`로 감싸져 있어 16 이상 값은 조용히 무시된다(action_run
      호출 자체가 안 됨 - 존재하지 않는 액션 이름으로 예외를 낼 위험이 없다).
      그래서 `_ACTION_NUM=99`(15 초과 아무 값)를 보내면 `set_default_pose`만
      안전하게 실행되고 그 외 동작은 트리거되지 않는다 -> "CMD|2|1|99|$".
      **이 매핑은 main.py 소스 분석으로 도출한 것이며 실물 하드웨어로 아직
      재검증하지 않았다** - 자동 배포 전에 반드시 단독으로 먼저 시험할 것.

로봇은 이동하지 않으므로(2026-09-17 시나리오 변경) 이동/복귀 관련 명령은 없다.
경고 자세(stand_two_legs)+부저는 세션과 무관하게 로봇 전체에 걸린 "지금 경고
중인가"라는 하나의 물리 상태로 다룬다 - 로봇이 1대뿐이라 세션별로 나뉜 물리
상태를 가질 수 없기 때문이다(security-dashboard/README.md의 설계 설명 참고).

2026-09-27: 부저가 이제 펌웨어 쪽에서 0->1 전이만 반응하고 반복 수신은 스스로
무시하므로(위 근거 참고), PC 쪽에서 1초마다 반복 전송하던 예전 `_buzzer_loop`
스레드를 없앴다 - 경고 시작/해제 "상태 전이" 시점에 각각 1회씩만 보낸다.
"""

from __future__ import annotations

import os
import threading
import traceback

# --- 명령 문자열 (파일 상단 docstring의 근거 참고) --------------------------

_STAND_TWO_LEGS_CMD = "CMD|2|1|6|$"
_NORMAL_ATTITUDE_CMD = "CMD|2|1|99|$"  # set_default_pose만 트리거 (근거: 파일 상단 docstring)
_BUZZER_ON_CMD = "CMD|7|1|$"
_BUZZER_OFF_CMD = "CMD|7|0|$"

# 눈 LED(발광 초음파 모듈의 RGB 2개, index 0 = 양쪽) - 앱 BLE 프로토콜에 이미 있는
# "CMD|4|3|R|G|B|$"(main.py BLE 분기 `_COMMAND==4, _DATA==3` -> i2csonar.setRGB(0,R,G,B))와
# 같은 형식이다. 원래 WiFi 분기에는 이 명령이 없어 펌웨어에 추가했다
# (firmware/mechdog_d_micropython/, 2026-10-03 실물 적용). 그 이전 펌웨어에서는
# 로봇이 이 명령을 조용히 무시한다. 주황/노랑은 2026-10-03 실물 눈 LED를 보며 맞춘 값이다 -
# 이 LED는 빨강이 강하게 나와 일반 RGB 값(255,80,0)/(255,255,0)은 둘 다 같은 주황으로 보였다.
_EYE_RGB = {
    "blue": (0, 0, 255),      # NORMAL
    "red": (255, 0, 0),       # ALERT (미인가)
    "orange": (255, 20, 0),   # WARNING (안전모/조끼 미착용)
    "yellow": (255, 130, 0),  # PENDING (판정 보류)
}

# --- 드라이버 설정 (모듈 로드 시 환경변수로 1회 초기화, configure()로 재설정 가능) ---

DRIVER = "mock"
_SERIAL_PORT: str | None = None
_SERIAL_BAUD = 9600
_UDP_HOST: str | None = None
_UDP_PORT = 9027
_UDP_RESPONSE_TIMEOUT_S = 0.5

_serial_conn = None  # 지연 연결 - configure()/에러 시 None으로 리셋되어 다음 전송에서 재시도
_udp_sock = None  # 지연 생성 - UDP는 연결이 없어 실패해도 소켓 자체는 재사용 가능하지만 일관성 있게 동일 패턴 적용
_last_error: str | None = None

_write_lock = threading.Lock()  # 같은 시리얼/소켓에 자세 명령과 부저 명령이 동시에 쓰지 않도록
_state_lock = threading.Lock()  # _warning_active 플래그 보호 (start/stop 멱등성 판단용)

_warning_active = False  # "지금 경고 자세+부저 상태인가" - 부저 반복 스레드 대신 이 플래그 하나로 관리
_eye_color: str | None = None  # 마지막으로 전송에 성공한 눈 색 - 같은 색 재전송 방지용


def configure(
    *,
    driver: str | None = None,
    port: str | None = None,
    baud: int | None = None,
    udp_host: str | None = None,
    udp_port: int | None = None,
    udp_timeout_s: float | None = None,
) -> None:
    """드라이버 설정을 (재)적용한다.

    인자를 생략하면 환경변수(MECHDOG_D_DRIVER 등)에서 읽는다 - 앱 시작 시
    자동으로 그렇게 된다(파일 맨 아래 configure() 최초 호출 참고). 테스트는
    이 함수를 인자와 함께 직접 호출해서, 프로세스 재시작이나 모듈 reload 없이
    mock/serial/udp를 오갈 수 있다.
    """
    global DRIVER, _SERIAL_PORT, _SERIAL_BAUD, _UDP_HOST, _UDP_PORT, _UDP_RESPONSE_TIMEOUT_S
    global _serial_conn, _udp_sock

    DRIVER = driver if driver is not None else os.environ.get("MECHDOG_D_DRIVER", "mock")
    if DRIVER not in ("mock", "serial", "udp"):
        raise ValueError(f"MECHDOG_D_DRIVER는 'mock', 'serial', 'udp' 중 하나여야 합니다 (받은 값: {DRIVER!r})")

    _SERIAL_PORT = port if port is not None else os.environ.get("MECHDOG_D_SERIAL_PORT")
    if DRIVER == "serial" and not _SERIAL_PORT:
        raise ValueError(
            "MECHDOG_D_DRIVER=serial인데 MECHDOG_D_SERIAL_PORT가 없습니다. "
            "잘못된 포트에 실수로 명령을 보내는 사고를 피하기 위해 COM3 같은 임의 "
            "기본값을 쓰지 않습니다 - 실제 포트(예: COM5, /dev/ttyUSB0)를 명시하세요."
        )
    _SERIAL_BAUD = baud if baud is not None else int(os.environ.get("MECHDOG_D_SERIAL_BAUD", "9600"))

    _UDP_HOST = udp_host if udp_host is not None else os.environ.get("MECHDOG_D_UDP_HOST")
    if DRIVER == "udp" and not _UDP_HOST:
        raise ValueError(
            "MECHDOG_D_DRIVER=udp인데 MECHDOG_D_UDP_HOST가 없습니다. "
            "잘못된 IP로 실수 전송하는 사고를 피하기 위해 임의 기본값을 쓰지 않습니다 - "
            "실제 로봇 IP(예: 192.168.137.63)를 명시하세요."
        )
    _UDP_PORT = (
        udp_port if udp_port is not None else int(os.environ.get("MECHDOG_D_UDP_PORT", "9027"))
    )  # 9027 = 이 펌웨어(main.py)의 wifi.port를 REPL로 직접 읽어 확인한 값(고정 프로토콜 상수, 환경별 값 아님)
    _UDP_RESPONSE_TIMEOUT_S = (
        udp_timeout_s
        if udp_timeout_s is not None
        else float(os.environ.get("MECHDOG_D_UDP_TIMEOUT_S", "0.5"))
    )

    _serial_conn = None  # 드라이버/포트가 바뀌었을 수 있으니 다음 전송에서 새로 연결
    _udp_sock = None


def _get_serial():
    """실제 pyserial 연결을 지연 생성한다.

    테스트에서는 이 함수 자체를 통째로 바꿔치기해서(가짜 연결 객체를 반환하도록)
    실물 포트를 전혀 열지 않고도 _send()의 나머지 로직을 검증한다.
    """
    global _serial_conn
    if _serial_conn is None:
        import serial  # 지연 import - mock/udp 모드에서는 pyserial이 없어도 이 줄까지 오지 않는다

        _serial_conn = serial.Serial(_SERIAL_PORT, _SERIAL_BAUD, timeout=1)
    return _serial_conn


def _get_udp_socket():
    """실제 UDP 소켓을 지연 생성한다.

    테스트에서는 이 함수를 통째로 바꿔치기해서(가짜 소켓 객체를 반환하도록) 실제
    네트워크를 전혀 쓰지 않고도 _send()의 나머지 로직을 검증한다.
    """
    global _udp_sock
    if _udp_sock is None:
        import socket  # 지연 import - mock/serial 모드에서는 이 줄까지 오지 않는다

        _udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    return _udp_sock


def _send(cmd: str) -> bool:
    """mock/serial/udp 드라이버에 따라 전송한다. 실패해도 예외를 절대 밖으로 던지지 않는다.

    이 함수는 MQTT 콜백 스레드(mqtt_client._on_message)에서 호출될 수 있어서,
    여기서 예외가 새어나가면 paho-mqtt의 콜백이 죽고 이후 메시지 처리가 멈출
    위험이 있다 - 그래서 광범위하게 잡아 로그만 남기고 False를 반환한다.

    반환값 True는 "전송(sendto/write) 자체가 성공했다"는 뜻일 뿐이다. 로봇이
    실제로 그 명령대로 움직였는지(물리 동작 확인)는 이 함수가 보장하지 않는다 -
    특히 udp 드라이버는 이 펌웨어의 응답 포맷이 검증되지 않아, 응답이 왔어도
    "참고용 원시 바이트"로만 로그에 남기고 동작 확인으로 취급하지 않는다.
    """
    global _last_error, _serial_conn, _udp_sock

    if DRIVER == "mock":
        print(f"[D ROBOT][mock] would send: {cmd}")
        return True

    if DRIVER == "serial":
        try:
            with _write_lock:
                conn = _get_serial()
                conn.write(cmd.encode("ascii"))
            _last_error = None
            print(f"[D ROBOT][serial] SENT {cmd!r} (전송 성공 - 이 포트가 실제 CMD 파서에 닿는지는 검증되지 않음)")
            return True
        except Exception as exc:  # noqa: BLE001 - 의도적으로 넓게 잡음(실물 연결 실패가 대시보드를 죽이면 안 됨)
            _last_error = f"{type(exc).__name__}: {exc}"
            print(f"[D ROBOT][serial] 전송 실패 ({cmd!r}): {_last_error}")
            traceback.print_exc()
            _serial_conn = None  # 다음 시도에서 재연결하도록 리셋
            return False

    if DRIVER == "udp":
        try:
            with _write_lock:
                sock = _get_udp_socket()
                sock.sendto(cmd.encode("ascii"), (_UDP_HOST, _UDP_PORT))
                print(f"[D ROBOT][udp] SENT {cmd!r} -> {_UDP_HOST}:{_UDP_PORT} "
                      f"(전송 성공 - 로봇이 실제로 그 동작을 했는지는 미확인, 육안 확인 필요)")
                try:
                    sock.settimeout(_UDP_RESPONSE_TIMEOUT_S)
                    data, addr = sock.recvfrom(1024)
                    print(f"[D ROBOT][udp] 응답 수신 {addr}: {data!r} "
                          f"(참고용 - 이 펌웨어의 응답 포맷은 검증되지 않아 '동작 확인'으로 취급하지 않음)")
                except OSError:
                    # socket.timeout도 OSError의 서브클래스 - 이전 실물 UDP 시험에서
                    # 실제로 응답이 오지 않았음을 이미 확인했다(로봇 rec_addr는 갱신되나
                    # 회신은 없음). 타임아웃은 실패가 아니라 "동작 미확인" 상태일 뿐이다.
                    print(f"[D ROBOT][udp] 응답 없음(타임아웃 {_UDP_RESPONSE_TIMEOUT_S}s) - "
                          f"전송은 성공했으나 로봇 동작 여부는 육안으로 확인해야 함")
            _last_error = None
            return True
        except Exception as exc:  # noqa: BLE001 - 의도적으로 넓게 잡음(네트워크 실패가 대시보드를 죽이면 안 됨)
            _last_error = f"{type(exc).__name__}: {exc}"
            print(f"[D ROBOT][udp] 전송 실패 ({cmd!r}): {_last_error}")
            traceback.print_exc()
            _udp_sock = None  # 다음 시도에서 재생성하도록 리셋
            return False

    return False  # 도달하지 않음(configure()가 DRIVER 값을 이미 검증함)


def last_error() -> str | None:
    """웹 화면에 ERROR 상태를 보여주기 위한 조회용 - web_server.py에서 사용."""
    return _last_error


def is_warning_active() -> bool:
    """지금 로봇이 경고 자세+부저 상태인지(대시보드가 그렇게 판단하고 있는지).

    2026-09-27부터는 부저 반복 스레드가 없다(펌웨어가 0->1 전이만 반응하므로
    반복 전송이 불필요해짐) - 대신 이 모듈이 마지막으로 start/stop 중 무엇을
    불렀는지를 플래그 하나로 기억한다. 실제 로봇이 그 상태인지를 재확인하는
    것은 아니다(응답 채널이 없음) - "대시보드가 마지막으로 어떤 명령을 보냈는가"
    를 뜻한다.
    """
    return _warning_active


def current_eye_color() -> str | None:
    """대시보드가 마지막으로 보낸 눈 색(실물이 그 색인지 재확인한 값은 아님)."""
    return _eye_color


def set_eye_color(color: str) -> None:
    """눈 LED 색을 바꾼다. 이미 같은 색을 보냈으면 다시 보내지 않는다.

    부저/자세와는 독립된 별개 명령이다 - WARNING->ALERT처럼 부저/자세는 그대로
    두고 눈 색만 바꿔야 하는 경우가 있어 start_buzzer_and_posture()와 분리했다.
    전송에 실패하면 _eye_color를 갱신하지 않아 다음 상태 변화 때 다시 시도한다.
    """
    global _eye_color
    if color not in _EYE_RGB:
        raise ValueError(f"지원하지 않는 눈 색: {color!r}")
    with _state_lock:
        if _eye_color == color:
            return
    r, g, b = _EYE_RGB[color]
    if _send(f"CMD|4|3|{r}|{g}|{b}|$"):
        with _state_lock:
            _eye_color = color


def start_buzzer_and_posture() -> None:
    """경고 자세(stand_two_legs) + 부저 시작 명령을 각각 1회씩 보낸다.

    이미 진행 중이면 아무 것도 하지 않고 그냥 돌아간다 - 두 명령 모두 다시
    보내지 않는다. 이게 "같은 세션에 사유가 추가되거나 다른 세션이 겹쳐도
    물리 동작은 1회만"의 핵심이다. 세션/사유별 판단은 이 함수를 부르기 전에
    이미 끝나 있을 필요가 없다 - 이 함수 자체가 (전역, 세션 무관) 멱등성을
    보장한다.

    stand_two_legs(자세)와 buzzer-on(부저)은 서로 독립된 별개의 CMD이므로
    각각 별도로 _send()하고 각자 성공/실패를 따로 로그에 남긴다 - 부저 전송
    성공이 자세 전송 성공을 의미하지 않는다(그 반대도 마찬가지).
    """
    global _warning_active
    with _state_lock:
        if _warning_active:
            return
        _warning_active = True

    _send(_STAND_TWO_LEGS_CMD)
    _send(_BUZZER_ON_CMD)


def stop_buzzer_and_return_posture() -> None:
    """부저 정지 + 기본 자세 복귀 명령을 각각 1회씩 보낸다.

    호출하는 쪽(mqtt_client.py)이 "D 소유 활성 경고가 전역적으로 0개가 됐을
    때만" 이 함수를 부르도록 책임진다 - 이 함수 자체는 세션/경고를 모른다.
    buzzer-off와 normal_attitude도 서로 독립된 별개의 CMD라 각각 따로 보내고
    따로 로그를 남긴다.
    """
    global _warning_active
    with _state_lock:
        _warning_active = False

    _send(_BUZZER_OFF_CMD)
    _send(_NORMAL_ATTITUDE_CMD)


def _reset_for_tests() -> None:
    """테스트 전용: 모듈 전역 상태(연결, 플래그, 드라이버, 에러)를 mock 기준으로 초기화한다.

    robot_commands는 모듈 전역 상태를 갖고 있어서(로봇이 실제로 1대뿐이라
    인스턴스화하지 않음) 테스트 간에 상태가 새면 안 된다 - 각 테스트 시나리오
    시작 전에 이 함수를 호출해 깨끗한 상태에서 시작한다.
    """
    global _serial_conn, _udp_sock, _last_error, _warning_active, _eye_color
    _warning_active = False
    _eye_color = None
    _serial_conn = None
    _udp_sock = None
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
