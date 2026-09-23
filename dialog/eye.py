# -*- coding: utf-8 -*-
"""눈 LED 상태 발행 — 대화 파이프라인이 자기 상태를 본체에 알린다.

왜 필요한가
-----------
방문자가 "지금 말해도 되는지"를 알 방법이 안내 음성밖에 없으면, 물류센터 정문처럼
시끄러운 곳에서는 사실상 알 수 없다. 눈 색이 그 역할을 한다 —
초록이면 말하고, 주황이면 기다리고, 파랑이면 듣는다.

본체 펌웨어(`firmware/mechdog_b_body`, v1.1+)가 `mechdog/internal/b/eye` 를 구독한다.
색과 전이(페이드)는 **펌웨어가 갖고 있고**, 여기서는 상태 이름만 보낸다.
색을 바꾸고 싶으면 `set_color()` 로 직접 지정할 수 있다(재업로드 없이 실물 색 맞추기용).

MQTT 가 없거나 끊겨도 **대화는 계속돼야 하므로**, 실패는 전부 조용히 삼킨다.
눈이 안 바뀌는 건 불편한 일이지 대화를 멈출 일이 아니다.
"""
from __future__ import annotations

import atexit
import json
import os
import threading

TOPIC = "mechdog/internal/b/eye"
HOST = os.environ.get("MQTT_HOST", "127.0.0.1")
PORT = int(os.environ.get("MQTT_PORT", "1883"))

IDLE, LISTENING, THINKING, SPEAKING, ERROR = (
    "idle", "listening", "thinking", "speaking", "error")

_client = None
_lock = threading.Lock()


def _connect():
    """느긋하게(lazy) 연결한다. import 시점에 브로커를 요구하면 테스트가 못 돈다."""
    global _client
    if _client is not None:
        return _client
    try:
        import paho.mqtt.client as mqtt
    except ImportError:
        return None
    try:
        # paho-mqtt 2.x 는 콜백 API 버전을 요구한다(1.x 스타일도 되지만 경고를 뿜는다).
        # 파이에 깔린 건 2.1.0 이지만, 다른 환경에서 1.x 를 만날 수도 있어 둘 다 받는다.
        if hasattr(mqtt, "CallbackAPIVersion"):
            c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,
                            client_id="mechdog_b_dialog_eye")
        else:
            c = mqtt.Client(client_id="mechdog_b_dialog_eye")
        c.connect(HOST, PORT, keepalive=30)
        c.loop_start()
        atexit.register(lambda: (c.loop_stop(), c.disconnect()))
        _client = c
    except OSError:
        return None
    return _client


def _publish(payload: dict) -> bool:
    with _lock:
        c = _connect()
        if c is None:
            return False
        try:
            # retain=True — 본체가 나중에 붙어도 마지막 상태를 바로 따라온다.
            c.publish(TOPIC, json.dumps(payload), retain=True)
            return True
        except OSError:
            return False


def set_state(state: str) -> bool:
    """대기/듣는중/처리중/안내중/오류 중 하나를 보낸다."""
    return _publish({"state": state})


def set_color(r: int, g: int, b: int) -> bool:
    """색을 직접 지정한다(튜닝용). 상태 기계보다 우선한다 — 되돌리려면 set_state()."""
    return _publish({"r": int(r), "g": int(g), "b": int(b)})


if __name__ == "__main__":   # 수동 확인: python3 eye.py listening
    import sys
    import time

    arg = sys.argv[1] if len(sys.argv) > 1 else "demo"
    if arg == "demo":
        # 실제 대화 순서대로 한 바퀴 — 실물에서 색이 구분되는지 눈으로 보는 용도
        for s, sec in ((IDLE, 2), (LISTENING, 2), (THINKING, 3),
                       (SPEAKING, 3), (ERROR, 2), (IDLE, 1)):
            ok = set_state(s)
            print(f"  {s:<10} {'전송' if ok else '실패(MQTT 연결 확인)'}")
            time.sleep(sec)
    elif arg == "color":
        print(set_color(*map(int, sys.argv[2:5])))
    else:
        print(set_state(arg))
