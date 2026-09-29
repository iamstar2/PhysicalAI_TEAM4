"""테스트 환경 — 팀 스키마를 올린 PostgreSQL 이 필요하다.

    docker run -d --name mechdog_api_testdb -e POSTGRES_USER=mechdog -e POSTGRES_PASSWORD=mechdog \
        -e POSTGRES_DB=mechdog -p 55432:5432 postgres:16
    docker exec -i mechdog_api_testdb psql -U mechdog -d mechdog < mechdog_team_schema.sql
    TEST_DATABASE_URL=postgresql://mechdog:mechdog@localhost:55432/mechdog pytest -q
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "api-server"))

_tmp = Path(tempfile.mkdtemp(prefix="mechdog_api_"))
os.environ.update({
    "DATABASE_URL": os.environ.get("TEST_DATABASE_URL",
                                   "postgresql://mechdog:mechdog@localhost:55432/mechdog"),
    "API_TOKENS": "collector:t-col,dashboard:t-dash,mechdog_a:t-a,mechdog_b:t-b,mechdog_d:t-d",
    "SNAPSHOT_ROOT": str(_tmp / "snap"),
    "API_LOG_DIR": str(_tmp / "logs"),
})
if "PHOTO_KEY" not in os.environ:
    from cryptography.fernet import Fernet
    os.environ["PHOTO_KEY"] = Fernet.generate_key().decode()

from fastapi.testclient import TestClient  # noqa: E402

from app import db, ingest  # noqa: E402
from app.main import app  # noqa: E402

TABLES = ["dialog_turns", "dialog_sessions", "alert_logs", "access_decisions", "person_photos",
          "persons", "escort_logs", "event_logs", "system_health", "sessions"]


def H(tok: str) -> dict:
    return {"Authorization": f"Bearer {tok}"}


@pytest.fixture(autouse=True)
def clean():
    if not db.ping():
        pytest.skip("테스트 DB 에 연결할 수 없습니다 (conftest.py 설명 참고)")
    with db.tx() as c:
        c.execute("TRUNCATE " + ", ".join(TABLES) + " RESTART IDENTITY CASCADE")
    ingest.reset_cache()
    yield


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def examples() -> dict[str, dict]:
    out = {}
    for f in (ROOT / "schema" / "examples").glob("*.json"):
        m = json.loads(f.read_text(encoding="utf-8"))
        out[m["payload"]["msg_type"]] = m
    return out


def rows(sql: str, *args) -> list[dict]:
    with db.tx() as c:
        c.execute(sql, args)
        return c.fetchall()
