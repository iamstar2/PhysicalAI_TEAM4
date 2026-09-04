#!/usr/bin/env python3
"""security-dashboard 전체 진입점: MQTT 클라이언트 + 웹 대시보드를 함께 띄운다.

MQTT는 paho-mqtt의 loop_start()로 백그라운드 스레드에서 돌리고, 웹 서버(Flask)는
메인 스레드에서 돈다. 두 스레드는 dashboard_state.DashboardState를 통해서만
데이터를 주고받는다 (mqtt_client.py, web_server.py 참고).

사용법 (security-dashboard 폴더 기준):
    python app/main.py
    MQTT_HOST=localhost MQTT_PORT=1883 PORT=3000 python app/main.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from dashboard_state import DashboardState  # noqa: E402
from mqtt_client import SecurityDashboardClient  # noqa: E402
from web_server import create_app  # noqa: E402


def main() -> None:
    state = DashboardState()
    client = SecurityDashboardClient(dashboard_state=state)
    client.start()

    app = create_app(client)
    port = int(os.environ.get("PORT", "3000"))
    try:
        app.run(host="0.0.0.0", port=port, threaded=True)
    finally:
        client.stop()


if __name__ == "__main__":
    main()
