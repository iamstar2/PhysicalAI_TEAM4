# -*- coding: utf-8 -*-
"""초음파 센서 실시간 보기.

    python tools/ultra_watch.py                      # 기본 127.0.0.1
    MQTT_HOST=<브로커 IP> python tools/ultra_watch.py

거리와 **재실 판정**(1.5 m 이내면 '있음')을 같이 찍는다 — 센서 값만 봐서는
세션이 왜 이탈로 끝났는지 알 수 없다. `FR-B-1001` 기준을 그대로 적용한다.

같은 값이 이어지면 줄을 새로 만들지 않고 제자리에서 갱신한다. 초당 3~4번 오는데
전부 새 줄로 찍으면 화면이 순식간에 넘어가 정작 변화를 못 본다.
"""
import json
import os
import sys
import time

# Windows 콘솔은 기본이 cp949 라 한글이 깨진다. 출력 스트림만 UTF-8 로 돌린다.
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import paho.mqtt.client as mqtt

HOST = os.environ.get("MQTT_HOST", "127.0.0.1")
PORT = int(os.environ.get("MQTT_PORT", "1883"))
TOPIC = "mechdog/internal/b/ultrasonic"
PRESENT_CM = 150          # FR-B-1001 — 1.5 m

_last_body = None


def on_message(client, userdata, msg):
    global _last_body
    try:
        d = json.loads(msg.payload.decode("utf-8"))
    except Exception:
        return

    cm = d.get("distance_cm")
    if not d.get("valid"):
        body = f"{'--':>4}cm  감지 없음"
    else:
        here = cm <= PRESENT_CM
        mark = "■ 있음 (1.5m 이내)" if here else "□ 멀다"
        bar = "#" * max(1, min(40, int(cm / 10)))
        body = f"{cm:>4}cm  {mark:<18} {bar}"

    line = f"{time.strftime('%H:%M:%S')}  {body}"
    sys.stdout.write("\r" + line.ljust(76))
    if body != _last_body:
        sys.stdout.write("\n")
    sys.stdout.flush()
    _last_body = body


def main() -> int:
    c = (mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
         if hasattr(mqtt, "CallbackAPIVersion") else mqtt.Client())
    c.on_message = on_message
    print(f"브로커 {HOST}:{PORT} · 토픽 {TOPIC}")
    print(f"{PRESENT_CM}cm 이내면 '있음' · Ctrl+C 로 종료\n")
    c.connect(HOST, PORT, 10)
    c.subscribe(TOPIC, qos=0)
    try:
        c.loop_forever()
    except KeyboardInterrupt:
        print("\n종료")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
