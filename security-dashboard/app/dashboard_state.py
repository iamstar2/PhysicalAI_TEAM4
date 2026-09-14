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
        self.active_alerts: dict[str, dict] = {}  # session_id -> alert (2026-09-14: 단일 슬롯 -> 세션별로 변경)
        self.emergency_stop = False

    def set_mqtt_connected(self, connected: bool) -> None:
        with self._lock:
            self.mqtt_connected = connected

    def update_node_health(self, node: str, state: str, detail: str | None, ts: str) -> None:
        with self._lock:
            self.node_health[node] = {"state": state, "detail": detail, "ts": ts}

    def record_alert(self, alert: dict) -> None:
        """alert.event가 발행/수신될 때마다 호출한다.

        D 자신이 낸 경고(mqtt_client._publish_alert)뿐 아니라, 2026-09-14부터는
        구독으로 들어온 B/C 등 다른 노드의 alert.event도 이 함수를 거친다 - 그래서
        "활성 경고"를 세션(session_id)별로 따로 들고 있어야 한다. D가 세션 X에 대해
        낸 경고와, B가 세션 Y에 대해 낸 경고가 동시에 활성 상태일 수 있는데 예전처럼
        슬롯이 하나면 나중에 온 쪽이 먼저 것을 지워버린다.

        resolved=false: 그 세션의 활성 경고로 등록(같은 세션에 새 경고가 오면 최신 것으로 교체).
        resolved=true(관리자 해제 또는 원 발행 노드의 자동 해제): 그 세션의 활성 경고를 제거.
        """
        with self._lock:
            self.recent_alerts.appendleft(alert)
            session_id = alert.get("session_id")
            if alert["resolved"]:
                self.active_alerts.pop(session_id, None)
            else:
                self.active_alerts[session_id] = alert

    def get_active_alert(self, session_id: str) -> dict | None:
        """관리자가 특정 세션의 경고를 해제할 때 조회 (mqtt_client.clear_active_alert)."""
        with self._lock:
            return self.active_alerts.get(session_id)

    def set_emergency_stop(self, value: bool) -> None:
        with self._lock:
            self.emergency_stop = value

    def snapshot(self) -> dict:
        """/api/state 응답용 - 현재 상태를 통째로 dict로 복사해서 반환.

        active_alerts는 최신 발생 순(ts 내림차순)으로 정렬해서 화면에 그대로 뿌릴 수 있게 한다.
        """
        with self._lock:
            return {
                "mqtt_connected": self.mqtt_connected,
                "node_health": dict(self.node_health),
                "recent_alerts": list(self.recent_alerts),
                "active_alerts": sorted(
                    self.active_alerts.values(), key=lambda a: a.get("ts", ""), reverse=True
                ),
                "emergency_stop": self.emergency_stop,
            }
