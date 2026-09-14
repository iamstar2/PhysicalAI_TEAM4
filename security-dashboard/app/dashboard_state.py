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
        # (session_id, reason) -> alert. 2026-09-14: 단일 슬롯 -> 세션별 dict로 변경.
        # 2026-09-15: session_id만으로는 부족해서(session_id, reason) 조합으로 재변경 -
        # 같은 세션에서 D(예: unauthorized)와 B/C(예: dialog_timeout)가 서로 다른
        # 사유로 동시에 경고를 내면 session_id만 키로 쓸 때 서로 덮어써서 하나가
        # 화면에서 통째로 사라지는 문제가 있었다
        # (재현: tests/test_same_session_alerts.py, 수정 전 진단 기록은 그 파일 참고).
        self.active_alerts: dict[tuple[str, str], dict] = {}
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
        구독으로 들어온 B/C 등 다른 노드의 alert.event도 이 함수를 거친다.

        활성 경고는 (session_id, reason) 조합으로 식별한다. schema/README.md 기준
        AlertReason 각 값은 노드 하나에 대응하도록 설계돼 있어(unauthorized/no_helmet/
        no_vest/face_timeout -> A, dialog_timeout/dialog_failed -> B, escort_lost -> C;
        지금은 A 대신 D가 대신 발행 중인 것은 별개 이슈, DECISIONS.md 항목 4 참고)
        session_id와 묶으면 "이 세션에서 벌어진 이 종류의 위반"을 안정적으로 가리킨다.
        session_id만 키로 쓰면 같은 세션에서 사유가 다른 경고(D의 unauthorized +
        B의 dialog_timeout)가 겹칠 때 서로 덮어써서 하나가 화면에서 사라지는 문제가
        있었다(2026-09-15 수정, tests/test_same_session_alerts.py 참고).

        resolved=false: 그 (session_id, reason) 조합을 활성 경고로 등록/갱신 - 같은
        키에 새 메시지가 또 오면(중복 수신 포함) 최신 내용으로 교체할 뿐 카드가
        늘어나지는 않는다.
        resolved=true(관리자 해제 또는 원 발행 노드의 자동 해제): 그 조합을 제거한다.
        이후 같은 세션에서 같은 사유가 다시 발생하면 새 활성 경고로 재등록된다(재경보).
        """
        with self._lock:
            self.recent_alerts.appendleft(alert)
            key = (alert.get("session_id"), alert.get("reason"))
            if alert["resolved"]:
                self.active_alerts.pop(key, None)
            else:
                self.active_alerts[key] = alert

    def get_active_alert(self, session_id: str, reason: str) -> dict | None:
        """관리자가 특정 세션의 특정 사유 경고를 해제할 때 조회 (mqtt_client.clear_active_alert)."""
        with self._lock:
            return self.active_alerts.get((session_id, reason))

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
