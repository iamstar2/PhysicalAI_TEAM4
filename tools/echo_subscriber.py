#!/usr/bin/env python3
"""전 토픽을 구독해서 수신 메시지를 콘솔에 출력하는 디버그 스크립트.

사용법:
    python tools/echo_subscriber.py
    MQTT_HOST=192.168.0.10 python tools/echo_subscriber.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import paho.mqtt.client as mqtt

from mechdog_common import SUBSCRIBE_ALL, Envelope


def on_connect(client, userdata, flags, rc) -> None:
    print(f"[echo] connected (rc={rc}), subscribing to {SUBSCRIBE_ALL}")
    client.subscribe(SUBSCRIBE_ALL)


def on_message(client, userdata, msg) -> None:
    try:
        env = Envelope.model_validate_json(msg.payload)
        print(f"[{msg.topic}] {env.model_dump_json()}")
    except Exception as exc:  # noqa: BLE001 - 디버그 도구이므로 스키마 위반도 그대로 보여준다
        print(f"[{msg.topic}] (invalid envelope: {exc}) raw={msg.payload!r}")


def main() -> None:
    host = os.environ.get("MQTT_HOST", "localhost")
    port = int(os.environ.get("MQTT_PORT", "1883"))

    client = mqtt.Client(client_id="echo_subscriber")

    user = os.environ.get("MQTT_USER")
    password = os.environ.get("MQTT_PASS")
    if user:
        client.username_pw_set(user, password)

    client.on_connect = on_connect
    client.on_message = on_message

    print(f"[echo] connecting to {host}:{port} ...")
    client.connect(host, port)
    client.loop_forever()


if __name__ == "__main__":
    main()
