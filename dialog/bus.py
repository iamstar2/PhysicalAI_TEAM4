# -*- coding: utf-8 -*-
"""MQTT 입출력 — 본체 센서 수신 · 공용 스키마 메시지 발행.

두 네임스페이스를 함께 다룬다.
  `mechdog/internal/b/...` — 본체 ESP32 와 주고받는 우리끼리의 신호(터치·초음파·눈).
                             공용 스키마 검증 대상이 아니다(`LOG-25`).
  `mechdog/v1/...`         — 팀 공용 메시지. **스키마가 `additionalProperties:false`** 라
                             필드를 하나라도 더 붙이면 다른 노드의 검증이 깨진다.

연결이 끊겨도 **대화는 계속돼야 한다**(`04` §4.6 — MQTT 단절은 에스컬레이션이 아니다).
발행 실패는 로컬 큐에 최대 10건 보관했다가 재접속 때 다시 보낸다.
"""
from __future__ import annotations

import json
import os
import threading
import time
import uuid
from collections import deque
from datetime import datetime, timedelta, timezone

HOST = os.environ.get("MQTT_HOST", "127.0.0.1")
PORT = int(os.environ.get("MQTT_PORT", "1883"))

T_TOUCH = "mechdog/internal/b/touch"
T_ULTRA = "mechdog/internal/b/ultrasonic"
T_EYE = "mechdog/internal/b/eye"
T_SESSION = "mechdog/v1/gate/session"
T_RESULT = "mechdog/v1/dialog/result"
T_ALERT = "mechdog/v1/alert/event"
T_HEALTH = "mechdog/v1/system/health/mechdog_b"

KST = timezone(timedelta(hours=9))
QUEUE_MAX = 10          # 04 §4.6

# system.health 는 방문자 세션과 무관하다. 그런데 봉투의 `session_id` 가 required 라
# 무언가는 넣어야 한다 — 팀이 같은 값을 써야 나중에 DB 에서 걸러낼 수 있어서
# `mock_publisher.py` 가 쓰던 값으로 통일한다.
HEALTH_SESSION = "system"


def now_ts() -> str:
    """KST ISO8601.

    파이 시간대가 `Europe/London` 로 잡혀 있어 **모든 `ts` 가 8시간 틀린 채로**
    C 의 DB·D 의 대시보드에 들어가던 적이 있다(`LOG-39`). 시스템 시간대에 기대지 않고
    여기서 KST 를 명시한다 — 같은 실수가 다시 나도 메시지는 맞는다.
    """
    return datetime.now(KST).isoformat()


def envelope(session_id: str, payload: dict) -> dict:
    return {
        "ver": 1,
        "msg_id": uuid.uuid4().hex,
        "ts": now_ts(),
        "src": "mechdog_b",
        "session_id": session_id,
        "payload": payload,
    }


class Bus:
    def __init__(self) -> None:
        self._c = None
        self._lock = threading.Lock()
        self._queue: deque[tuple[str, dict]] = deque(maxlen=QUEUE_MAX)

        self.touch_pressed = False
        self._touch_seen = False     # retain 된 첫 값은 누름으로 치지 않는다
        self.touch_edge = threading.Event()

        self.distance_cm: int | None = None
        self.distance_at = 0.0
        self.sessions: deque[dict] = deque(maxlen=4)

    # ---- 연결 ------------------------------------------------------------
    def connect(self, timeout_s: float = 5.0) -> bool:
        try:
            import paho.mqtt.client as mqtt
        except ImportError:
            print("[bus] paho-mqtt 없음 — MQTT 없이 동작한다")
            return False
        try:
            if hasattr(mqtt, "CallbackAPIVersion"):
                c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,
                                client_id="mechdog_b_dialog")
            else:
                c = mqtt.Client(client_id="mechdog_b_dialog")
            c.on_message = self._on_message
            c.on_connect = self._on_connect
            # **유언(LWT)은 연결 전에 등록해야 한다.** 프로세스가 죽거나 전원이 나가면
            # 자기 입으로 "죽었다"고 말할 수 없으니, 브로커가 대신 발행하도록 맡겨 둔다.
            # 여기 박히는 `ts` 는 **연결 시각**이다 — 죽은 시각이 아니다.
            # 수집기는 state=offline 인 행의 ts 를 믿지 말고 받은 시각을 써야 한다.
            c.will_set(T_HEALTH,
                       json.dumps(envelope(HEALTH_SESSION, {
                           "msg_type": "system.health",
                           "node": "mechdog_b",
                           "state": "offline",
                           "detail": "LWT — 연결 끊김 (ts 는 연결 시각)",
                       }), ensure_ascii=False),
                       qos=0, retain=True)
            c.connect(HOST, PORT, keepalive=30)
            c.loop_start()
            self._c = c
        except OSError as e:
            print(f"[bus] 브로커 연결 실패 ({HOST}:{PORT}): {e}")
            return False

        deadline = time.time() + timeout_s
        while time.time() < deadline and not c.is_connected():
            time.sleep(0.1)
        return c.is_connected()

    def _on_connect(self, client, userdata, flags, rc, properties=None) -> None:
        for t in (T_TOUCH, T_ULTRA, T_SESSION):
            client.subscribe(t, qos=1)
        self._flush()
        self.publish_health("ready")

    def _on_message(self, client, userdata, msg) -> None:
        try:
            d = json.loads(msg.payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return

        if msg.topic == T_TOUCH:
            pressed = bool(d.get("touch"))
            # retain=True 라 붙자마자 마지막 상태가 온다. 그걸 "방금 눌렀다"로 읽으면
            # 인사도 하기 전에 청취가 열린다 — 첫 수신은 상태만 반영하고 넘어간다.
            if self._touch_seen and pressed and not self.touch_pressed:
                self.touch_edge.set()
            self.touch_pressed = pressed
            self._touch_seen = True

        elif msg.topic == T_ULTRA:
            self.distance_cm = d.get("distance_cm") if d.get("valid") else None
            self.distance_at = time.time()

        elif msg.topic == T_SESSION:
            self.sessions.append(d)

    # ---- 발행 ------------------------------------------------------------
    def _send(self, topic: str, doc: dict) -> bool:
        with self._lock:
            if self._c is None or not self._c.is_connected():
                self._queue.append((topic, doc))
                return False
            try:
                self._c.publish(topic, json.dumps(doc, ensure_ascii=False), qos=1)
                return True
            except OSError:
                self._queue.append((topic, doc))
                return False

    def _flush(self) -> None:
        while self._queue:
            topic, doc = self._queue.popleft()
            try:
                self._c.publish(topic, json.dumps(doc, ensure_ascii=False), qos=1)
            except OSError:
                self._queue.appendleft((topic, doc))
                return

    def publish_result(self, session_id: str, dest: str, purpose: str,
                       confidence: float, retry_count: int) -> bool:
        """㉗ dialog.result. 스키마가 엄격해서 **여기 있는 필드가 전부**다."""
        return self._send(T_RESULT, envelope(session_id, {
            "msg_type": "dialog.result",
            "destination": dest,
            "purpose": purpose,
            "confidence": round(float(confidence), 2),
            "retry_count": int(retry_count),
        }))

    def publish_alert(self, session_id: str, level: str, reason: str) -> bool:
        """⑪ 이탈 판정(info) · ⑲ 실패 에스컬레이션(warn)."""
        return self._send(T_ALERT, envelope(session_id, {
            "msg_type": "alert.event",
            "level": level,
            "reason": reason,
        }))

    def publish_health(self, state: str, detail: str | None = None) -> bool:
        """노드 상태 보고 (`system.health`).

        대시보드가 "B 가 살아 있나" 를 아는 유일한 경로다. **와이파이가 붙어 있는 것과
        이 프로그램이 도는 것은 다르다** — 파이는 멀쩡한데 B 만 죽으면 ping 은 되지만
        대화는 못 한다. MQTT 연결은 파이가 아니라 이 프로세스가 맺으므로, 연결이
        끊겼다는 사실 자체가 프로세스가 죽었다는 신호가 된다.

        `booting` 은 쓰지 않는다 — 부팅 중에는 아직 브로커에 연결되지 않아 보낼 방법이 없다.
        `retain=True` 라 나중에 켠 대시보드도 마지막 상태를 바로 본다.
        """
        doc = envelope(HEALTH_SESSION, {
            "msg_type": "system.health",
            "node": "mechdog_b",
            "state": state,
            "detail": detail,
        })
        with self._lock:
            if self._c is None or not self._c.is_connected():
                return False        # 큐에 쌓지 않는다 — 지난 상태를 나중에 보내면 거짓말이 된다
            try:
                self._c.publish(T_HEALTH, json.dumps(doc, ensure_ascii=False),
                                qos=0, retain=True)
                return True
            except OSError:
                return False

    def close(self) -> None:
        """정상 종료. **LWT 는 여기서 안 나간다** — DISCONNECT 를 보내면 브로커가
        유언을 버리기 때문이다. 그래서 직접 offline 을 찍고 끊는다."""
        self.publish_health("offline", "정상 종료")
        with self._lock:
            if self._c is not None:
                try:
                    self._c.loop_stop()
                    self._c.disconnect()
                except OSError:
                    pass

    # ---- 센서 조회 --------------------------------------------------------
    def present(self, max_cm: int = 150, stale_s: float = 2.0) -> bool | None:
        """1.5m 이내면 재실 (`FR-B-1001`). 값이 오래됐으면 `None`(모름)."""
        if self.distance_cm is None:
            if time.time() - self.distance_at > stale_s:
                return None          # 센서가 끊겼다 — 부재로 단정하지 않는다
            return False
        return self.distance_cm <= max_cm

    def wait_touch(self, timeout_s: float) -> bool:
        """누름 전이를 기다린다. 이미 누르고 있는 상태는 새 누름이 아니다."""
        self.touch_edge.clear()
        ok = self.touch_edge.wait(timeout_s)
        # **소비했으면 반드시 끈다.** threading.Event 는 수동 리셋이라 wait() 가 True 를
        # 돌려줘도 set 상태 그대로다. 안 끄면 그 뒤의 모든 재생이 "터치됐다" 로 읽혀
        # 즉시 중단되고, 대기도 계속 생략된다.
        self.touch_edge.clear()
        return ok
