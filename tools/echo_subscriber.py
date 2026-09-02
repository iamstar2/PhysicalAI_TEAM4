#!/usr/bin/env python3
"""전 토픽을 구독해서 수신 메시지를 콘솔에 출력하는 디버그 스크립트.

schema/mechdog_messages.schema.json 로 각 메시지를 검증하면서 출력한다.

사용법:
    python tools/echo_subscriber.py
    MQTT_HOST=192.168.0.10 python tools/echo_subscriber.py
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import paho.mqtt.client as mqtt
from jsonschema import Draft202012Validator

from _common import SUBSCRIBE_ALL

ROOT = Path(__file__).resolve().parent.parent
with open(ROOT / "schema" / "mechdog_messages.schema.json", encoding="utf-8") as f:
    VALIDATOR = Draft202012Validator(json.load(f))


def on_connect(client, userdata, flags, rc) -> None:
    print(f"[echo] connected (rc={rc}), subscribing to {SUBSCRIBE_ALL}")
    client.subscribe(SUBSCRIBE_ALL)


def on_message(client, userdata, msg) -> None:
    try:
        data = json.loads(msg.payload)
    except json.JSONDecodeError as exc:
        print(f"[{msg.topic}] (invalid JSON: {exc}) raw={msg.payload!r}")
        return

    errors = list(VALIDATOR.iter_errors(data))
    if errors:
        print(f"[{msg.topic}] (schema violation: {errors[0].message}) {json.dumps(data, ensure_ascii=False)}")
    else:
        print(f"[{msg.topic}] {json.dumps(data, ensure_ascii=False)}")


def main() -> None:
    host = os.environ.get("MQTT_HOST", "localhost")
    port = int(os.environ.get("MQTT_PORT", "1883"))

    client = mqtt.Client(client_id="echo_subscriber")

    user = os.environ.get("MQTT_USER")
    if user:
        client.username_pw_set(user, os.environ.get("MQTT_PASS"))

    client.on_connect = on_connect
    client.on_message = on_message

    print(f"[echo] connecting to {host}:{port} ...")
    client.connect(host, port)
    client.loop_forever()


if __name__ == "__main__":
    main()
