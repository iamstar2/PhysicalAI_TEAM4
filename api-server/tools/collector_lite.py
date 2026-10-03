"""비상용 간이 수집서버 — 브로커의 mechdog/v1/# 를 받아 API 서버 POST /events 로 그대로 넘긴다.

수집서버는 여도훈(A) 담당이다. 이건 그게 없을 때 시험 · 시연을 이어 가기 위한 최소 구현으로,
api-server/README.md 의 "수집서버" 약속을 그대로 따른다.

    pip install paho-mqtt requests
    MQTT_HOST=<브로커 IP> API_URL=http://<B IP>:8080 API_TOKEN=<collector 토큰> python tools/collector_lite.py

- 메시지를 바꾸지 않고 그대로 보낸다 (msg_id · ts 유지)
- 200 → 다음 · 422 → 버림(서버가 rejected 로그에 남김) · 401/403 → 설정 문제라 멈춤
- 503 · 500 · 연결 실패 → 메모리 큐에 쌓아 두고 5초마다 /events/batch 로 재전송
- mechdog/internal/# (B 본체 내부 토픽)은 팀 규격 밖이라 보내지 않는다
"""
from __future__ import annotations

import json
import os
import sys
import threading
import time
from collections import deque

import paho.mqtt.client as mqtt
import requests

MQTT_HOST = os.environ.get("MQTT_HOST", "127.0.0.1")
MQTT_PORT = int(os.environ.get("MQTT_PORT", "1883"))
MQTT_USER = os.environ.get("MQTT_USER") or None
MQTT_PASS = os.environ.get("MQTT_PASS") or None
API_URL = os.environ.get("API_URL", "http://127.0.0.1:8080").rstrip("/")
API_TOKEN = os.environ.get("API_TOKEN", "")
TOPIC = "mechdog/v1/#"
RETRY_S = 5
QUEUE_MAX = 10_000

_queue: deque[dict] = deque(maxlen=QUEUE_MAX)
_lock = threading.Lock()
_s = requests.Session()
_s.headers.update({"Authorization": f"Bearer {API_TOKEN}", "Content-Type": "application/json"})
stats = {"ok": 0, "dropped": 0, "queued": 0}


def _send(msg: dict) -> str:
    """'ok' · 'drop' · 'retry' · 'fatal'"""
    try:
        r = _s.post(f"{API_URL}/events", data=json.dumps(msg, ensure_ascii=False).encode(), timeout=5)
    except requests.RequestException:
        return "retry"
    if r.status_code == 200:
        return "ok"
    if r.status_code == 422:
        return "drop"
    if r.status_code in (401, 403):
        return "fatal"
    return "retry"


def _on_message(client, userdata, m):
    try:
        msg = json.loads(m.payload)
    except ValueError:
        print(f"[skip] JSON 아님: {m.topic}")
        return
    with _lock:
        if _queue:                       # 밀린 게 있으면 순서를 지키려고 뒤에 붙인다
            _queue.append(msg); stats["queued"] += 1
            return
    res = _send(msg)
    if res == "ok":
        stats["ok"] += 1
    elif res == "drop":
        stats["dropped"] += 1
        print(f"[422] 버림: {m.topic} {msg.get('msg_id')}")
    elif res == "fatal":
        print("[401/403] 토큰 · 권한 문제 — API_TOKEN 을 확인하세요"); os._exit(2)
    else:
        with _lock:
            _queue.append(msg); stats["queued"] += 1
        print(f"[retry] API 응답 없음 — 쌓아 둠 ({len(_queue)}건)")


def _retry_loop():
    while True:
        time.sleep(RETRY_S)
        with _lock:
            batch = list(_queue)
        if not batch:
            continue
        try:
            r = _s.post(f"{API_URL}/events/batch",
                        data=json.dumps(batch, ensure_ascii=False).encode(), timeout=15)
        except requests.RequestException:
            continue
        if r.status_code == 200:
            with _lock:
                for _ in batch:
                    _queue.popleft()
            stats["ok"] += r.json().get("ok", 0)
            print(f"[retry] 재전송 {len(batch)}건 완료")


def main() -> int:
    if not API_TOKEN:
        print("API_TOKEN 이 없습니다 (collector 토큰)"); return 2
    if hasattr(mqtt, "CallbackAPIVersion"):
        c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="collector_lite",
                        clean_session=False)
    else:
        c = mqtt.Client(client_id="collector_lite", clean_session=False)
    if MQTT_USER:
        c.username_pw_set(MQTT_USER, MQTT_PASS)
    c.on_message = _on_message
    c.on_connect = lambda cl, u, f, rc, p=None: cl.subscribe(TOPIC, qos=1)
    c.connect(MQTT_HOST, MQTT_PORT, keepalive=30)
    threading.Thread(target=_retry_loop, daemon=True).start()
    print(f"[collector_lite] {MQTT_HOST}:{MQTT_PORT} {TOPIC} → {API_URL}/events")
    c.loop_start()
    try:
        while True:
            time.sleep(10)
            print(f"[stat] 적재 {stats['ok']} · 버림 {stats['dropped']} · 대기 {len(_queue)}")
    except KeyboardInterrupt:
        pass
    c.loop_stop(); c.disconnect()
    return 0


if __name__ == "__main__":
    sys.exit(main())
