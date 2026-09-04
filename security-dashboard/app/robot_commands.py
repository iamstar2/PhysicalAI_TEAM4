"""D 로봇(MechDog D) 동작 명령 인터페이스.

실제 MechDog SDK가 아직 연결되지 않았으므로, 지금은 콘솔에 출력만 한다.
나중에 SDK가 준비되면 이 파일 안의 함수 내용만 실제 로봇 제어 코드로
바꾸면 된다 - 호출하는 쪽(security_state.py 등)은 수정할 필요 없다.

주의: WARNING/ALERT/CLEAR_ALERT/EMERGENCY_STOP은 MQTT로 나가는 공식
메시지가 아니라, 이 서비스(mechdog_d) 내부에서만 쓰는 함수 이름이다.
schema/에는 이런 msg_type이 정의되어 있지 않다.
"""

from __future__ import annotations


def warning_action() -> None:
    print("[D ROBOT] WARNING ACTION")


def alert_action() -> None:
    print("[D ROBOT] ALERT ACTION")


def clear_alert() -> None:
    print("[D ROBOT] CLEAR_ALERT")


def emergency_stop() -> None:
    print("[D ROBOT] EMERGENCY_STOP")
