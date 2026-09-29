#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""C(안내견) 대역 — `escort.status` 를 키보드로 바꿔 가며 발행한다.

C 없이 `FR-B-708`(에스코트 가용 확인)을 시험·촬영하려고 만들었다.

    python tools/fake_escort.py                    # 브로커 127.0.0.1
    MQTT_HOST=<브로커 IP> python tools/fake_escort.py

    i  idle     대기 중   → "네" 하면 C 에게 넘긴다 (dialog.result 발행)
    m  moving   안내 중   → "네" 해도 "지금은 모든 안내견이 안내 중이에요"
    a  arrived  도착      → 위와 같음
    x  aborted  중단      → 위와 같음
    s  침묵     발행 중지 → 3초 뒤 B 가 "모른다" 로 보고 위와 같음 (AC-708-4)
    q  종료

    어느 상태든 B 는 "직접 안내해 드릴까요?" 를 **묻는다.** C 상태는 방문자가
    **"네" 한 뒤에** 본다 — 안내해 달라고 하지도 않았는데 사정부터 말하면 뜬금없다.

왜 1초마다 보내나
-----------------
B 는 **3초 넘게 조용하면 모르는 걸로 친다**(`bus.py` `ESCORT_STALE_S`).
오래된 값으로 판단하면 못 지킬 약속을 하게 되기 때문이다. 그래서 retained 메시지
한 번으로는 안 되고, 실제 C 처럼 1 Hz 로 계속 흘려야 한다.

**B 가 구독하는 토픽과 같아야 한다** — 기본 `mechdog/v1/escort/status`.
B 를 `ESCORT_TOPIC` 으로 바꿔 띄웠다면 여기도 같은 값을 준다.
"""
from __future__ import annotations

import json
import os
import sys
import threading
import time
import uuid
from datetime import datetime, timezone

import paho.mqtt.client as mqtt

HOST = os.environ.get("MQTT_HOST", "127.0.0.1")
PORT = int(os.environ.get("MQTT_PORT", "1883"))
TOPIC = os.environ.get("ESCORT_TOPIC", "mechdog/v1/escort/status")

KEYS = {"i": "idle", "m": "moving", "a": "arrived", "x": "aborted", "s": None}
state: str | None = "idle"
stop = threading.Event()


def doc(st: str) -> str:
    return json.dumps({
        "ver": 1, "msg_id": uuid.uuid4().hex,
        "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
        "src": "mechdog_c", "session_id": "fake-escort",
        "payload": {"msg_type": "escort.status", "state": st},
    })


def pump(c: mqtt.Client) -> None:
    while not stop.is_set():
        if state:
            c.publish(TOPIC, doc(state), qos=0, retain=False)
        stop.wait(1.0)


def getkey() -> str:
    if os.name == "nt":
        import msvcrt
        return msvcrt.getwch().lower()
    import termios, tty
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        return sys.stdin.read(1).lower()
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


def main() -> int:
    global state
    kw = {"client_id": f"fake_escort_{uuid.uuid4().hex[:6]}"}
    if hasattr(mqtt, "CallbackAPIVersion"):
        kw["callback_api_version"] = mqtt.CallbackAPIVersion.VERSION2
    c = mqtt.Client(**kw)
    try:
        c.connect(HOST, PORT, keepalive=30)
    except OSError as e:
        print(f"브로커 접속 실패 ({HOST}:{PORT}): {e}")
        return 1
    c.loop_start()
    threading.Thread(target=pump, args=(c,), daemon=True).start()

    print(f"C 대역 — {HOST}:{PORT}  {TOPIC}")
    print("  i=idle  m=moving  a=arrived  x=aborted  s=침묵  q=종료")
    print(f"  현재: {state}")
    try:
        while True:
            k = getkey()
            if k == "q":
                break
            if k in KEYS:
                state = KEYS[k]
                print(f"  → {state or '침묵 (3초 뒤 B 는 모른다로 판단)'}", flush=True)
    except KeyboardInterrupt:
        pass
    stop.set()
    c.loop_stop()
    c.disconnect()
    print("종료")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
