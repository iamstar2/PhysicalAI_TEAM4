"""감사 로그 · 적재 실패 로그 — 파일(jsonl)에 남긴다.

설계도의 "감사 로그" 항목. 팀 스키마에 테이블이 없어서 우선 파일로 두고,
`sql/proposed_changes.sql` 의 audit_logs 가 추가되면 DB 로 옮길 수 있다.
"""
from __future__ import annotations

import json
import threading
from datetime import datetime, timezone

from . import config

_lock = threading.Lock()


def _write(kind: str, rec: dict) -> None:
    config.LOG_DIR.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).astimezone()
    rec = {"at": now.isoformat(timespec="milliseconds"), **rec}
    path = config.LOG_DIR / f"{kind}_{now:%Y%m%d}.jsonl"
    with _lock, path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")


def request(client: str, method: str, path: str, status: int, ms: float) -> None:
    _write("audit", {"client": client, "method": method, "path": path,
                     "status": status, "ms": round(ms, 1)})


def rejected(client: str, msg: dict | None, reason: str) -> None:
    """스키마 검사 실패 · 적재 실패 메시지 — 버리지 않고 남겨서 원인을 찾는다."""
    _write("rejected", {"client": client, "reason": reason, "msg": msg})
