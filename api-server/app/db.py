"""DB 연결 — 요청마다 풀에서 하나 빌려 쓰고, 끝나면 commit 또는 rollback."""
from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from . import config

_pool: ConnectionPool | None = None


def open_pool() -> None:
    global _pool
    if _pool is None:
        # timeout: DB 가 꺼져 있을 때 요청이 오래 매달리지 않게 (수집서버는 503 을 받고 재전송)
        _pool = ConnectionPool(config.DATABASE_URL, min_size=1, max_size=5, timeout=5,
                               kwargs={"row_factory": dict_row}, open=True)


def close_pool() -> None:
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None


@contextmanager
def tx() -> Iterator[psycopg.Cursor]:
    """트랜잭션 하나(커서로 받는다). 예외가 나면 전부 되돌린다."""
    open_pool()
    assert _pool is not None
    with _pool.connection() as conn:
        with conn.transaction(), conn.cursor() as cur:
            yield cur


def ping() -> bool:
    try:
        with tx() as c:
            c.execute("SELECT 1")
        return True
    except Exception:
        return False
