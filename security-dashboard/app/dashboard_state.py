"""웹 대시보드(Flask)와 MQTT 클라이언트가 함께 들여다보는 공유 상태.

MQTT 메시지는 paho-mqtt가 만드는 네트워크 스레드에서 처리되고, 웹 화면 요청은
Flask 개발 서버의 요청 스레드에서 처리된다 - 서로 다른 스레드가 같은 데이터를
동시에 건드릴 수 있어서 Lock으로 보호한다. 이 파일은 "지금 화면에 뭘 보여줄지"만
담당하고, 보안 판정 로직 자체는 여전히 security_state.py에 있다.
"""

from __future__ import annotations

import threading
from collections import deque

MAX_RECENT_ALERTS = 20


class DashboardState:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.mqtt_connected = False
        self.node_health: dict[str, dict] = {}  # node -> {"state":.., "detail":.., "ts":..}
        self.recent_alerts: deque[dict] = deque(maxlen=MAX_RECENT_ALERTS)
        self.active_alert: dict | None = None
        self.emergency_stop = False

    def set_mqtt_connected(self, connected: bool) -> None:
        with self._lock:
            self.mqtt_connected = connected

    def update_node_health(self, node: str, state: str, detail: str | None, ts: str) -> None:
        with self._lock:
            self.node_health[node] = {"state": state, "detail": detail, "ts": ts}

    def record_alert(self, alert: dict) -> None:
        """alert.event가 발행될 때마다(발생이든 해제든) 호출한다.

        resolved=false인 새 경고가 오면 그게 곧 '현재 활성 경고'가 된다.
        resolved=true가 오면(관리자 해제) 활성 경고를 비운다.
        """
        with self._lock:
            self.recent_alerts.appendleft(alert)
            if alert["resolved"]:
                if self.active_alert and self.active_alert.get("session_id") == alert.get("session_id"):
                    self.active_alert = None
            else:
                self.active_alert = alert

    def get_active_alert(self) -> dict | None:
        with self._lock:
            return self.active_alert

    def set_emergency_stop(self, value: bool) -> None:
        with self._lock:
            self.emergency_stop = value

    def snapshot(self) -> dict:
        """/api/state 응답용 - 현재 상태를 통째로 dict로 복사해서 반환."""
        with self._lock:
            return {
                "mqtt_connected": self.mqtt_connected,
                "node_health": dict(self.node_health),
                "recent_alerts": list(self.recent_alerts),
                "active_alert": self.active_alert,
                "emergency_stop": self.emergency_stop,
            }
