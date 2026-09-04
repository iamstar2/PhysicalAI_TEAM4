"""웹 대시보드 백엔드 (Flask).

Flask를 고른 이유: 지금 코드가 이미 순수 Python(스레드 기반 MQTT 클라이언트)
이라 FastAPI가 요구하는 async 스타일과 안 맞고, uvicorn 같은 별도 ASGI
서버도 필요 없다. Flask는 내장 개발 서버로 바로 뜨고, 라우트 하나에 함수
하나면 되는 가장 단순한 구조라 이 프로젝트 규모에 맞다.

화면 갱신 방식: 1초 간격 폴링(브라우저 JS가 /api/state를 주기적으로 fetch).
WebSocket/SSE도 검토했지만, 이 화면은 서버 -> 브라우저 단방향 정보 전달만
있으면 되고, 사람 눈에는 1초 지연과 즉시 반영이 사실상 구분되지 않는다.
WebSocket/SSE는 연결을 계속 열어두고 스레드 간 큐/이벤트로 데이터를 흘려보내야
해서 구현이 한 단계 더 복잡해지는데, 이 프로젝트 규모에서 그 복잡도를 감수할
이유가 없다고 판단했다 (자세한 이유는 README.md에도 기록).
"""

from __future__ import annotations

import os
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory

APP_DIR = Path(__file__).resolve().parent
REPO_ROOT = APP_DIR.parent.parent

NODES = ["mechdog_a", "mechdog_b", "mechdog_c", "mechdog_d"]


def create_app(mqtt_dashboard_client) -> Flask:
    app = Flask(__name__, template_folder=str(APP_DIR / "templates"), static_folder=str(APP_DIR / "static"))

    @app.get("/")
    def index():
        return send_from_directory(app.template_folder, "index.html")

    @app.after_request
    def _no_cache_api(response):
        # /api/* 는 폴링으로 매초 새로 읽어야 하는데, 브라우저가 GET 응답을
        # 캐시해버리면 리셋/해제 같은 상태 변화가 화면에 늦게(또는 안) 반영된다.
        if request.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/api/state")
    def api_state():
        snap = mqtt_dashboard_client.state.snapshot()

        nodes = {}
        for node in NODES:
            health = snap["node_health"].get(node)
            if health is None:
                nodes[node] = {"state": "UNKNOWN", "detail": None, "ts": None}
            else:
                nodes[node] = health

        session_id, rec = mqtt_dashboard_client.store.latest()
        if rec is None:
            current_visitor = None
        else:
            current_visitor = {
                "session_id": session_id,
                "visitor_id": rec.visitor_id,
                "face_result": rec.face_result,
                "ppe": {
                    "helmet": rec.ppe_items.get("helmet"),
                    "vest": rec.ppe_items.get("vest"),
                    "overall": rec.ppe_overall,
                },
                "status": rec.status,
                "snapshot_path": rec.snapshot_path,
            }

        return jsonify(
            {
                "mqtt_connected": snap["mqtt_connected"],
                "nodes": nodes,
                "current_visitor": current_visitor,
                "active_alert": snap["active_alert"],
                "recent_alerts": snap["recent_alerts"],
                "emergency_stop": snap["emergency_stop"],
            }
        )

    @app.get("/api/snapshot")
    def api_snapshot():
        """스냅샷 이미지 파일 서빙. MECHDOG_SNAPSHOT_ROOT 아래 상대경로만 허용.

        alert.event/vision.* 의 snapshot_path는 절대경로 문자열(예:
        /data/snap/.../face.jpg)로 온다 - 그 경로를 그대로 파일시스템에서
        찾아 보여준다. 파일이 없으면 404로 응답하고, 프런트가 '스냅샷 없음'을
        표시한다(가짜 이미지를 만들지 않는다).
        """
        path = request.args.get("path", "")
        if not path:
            return jsonify({"error": "path required"}), 400
        full_path = Path(path)
        if not full_path.is_absolute():
            full_path = Path(os.environ.get("MECHDOG_SNAPSHOT_ROOT", "/data/snap")) / path
        if not full_path.exists() or not full_path.is_file():
            return jsonify({"error": "not found"}), 404
        return send_from_directory(str(full_path.parent), full_path.name)

    @app.post("/api/actions/clear_alert")
    def api_clear_alert():
        cleared = mqtt_dashboard_client.clear_active_alert()
        if not cleared:
            return jsonify({"ok": False, "message": "해제할 활성 경고가 없습니다."}), 400
        return jsonify({"ok": True})

    @app.post("/api/actions/emergency_stop")
    def api_emergency_stop():
        mqtt_dashboard_client.trigger_emergency_stop()
        return jsonify({"ok": True})

    @app.post("/api/actions/emergency_reset")
    def api_emergency_reset():
        mqtt_dashboard_client.reset_emergency_stop()
        return jsonify({"ok": True})

    return app
