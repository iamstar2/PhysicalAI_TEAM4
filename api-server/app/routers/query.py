"""조회 · 통계 — 대시보드 이력 화면용.

TODO(협의): 대시보드가 실제로 쓰는 화면이 정해지면 응답 모양을 맞춘다 (백경률).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from .. import config, db
from ..security import require

router = APIRouter(tags=["query (조회 · 통계)"])


@router.get("/alerts", summary="경고 이력")
def alerts(resolved: bool | None = None, limit: int = Query(50, le=500),
           _=Depends(require("query:read"))):
    with db.tx() as c:
        c.execute("""SELECT * FROM alert_logs
                     WHERE %s::boolean IS NULL OR resolved = %s::boolean
                     ORDER BY occurred_at DESC LIMIT %s""", (resolved, resolved, limit))
        return c.fetchall()


@router.patch("/alerts/{msg_id}/resolve", summary="경고 해제 기록 (보통은 필요 없음)")
def resolve(msg_id: str, _=Depends(require("alerts:resolve"))):
    # 대시보드가 MQTT 로 resolved=true 를 발행하면 수집서버를 거쳐 자동으로 반영된다.
    # 이건 MQTT 를 거치지 않고 DB 기록만 바로 고쳐야 할 때를 위한 것.
    with db.tx() as c:
        c.execute("""UPDATE alert_logs SET resolved = true, resolved_at = COALESCE(resolved_at, now())
                     WHERE msg_id = %s RETURNING *""", (msg_id,))
        row = c.fetchone()
    if row is None:
        raise HTTPException(404, "경고가 없습니다")
    return row


@router.get("/sessions/{session_id}", summary="방문자 한 명의 전체 기록 (A → B → C → D)")
def session(session_id: str, _=Depends(require("query:read"))):
    with db.tx() as c:
        c.execute("SELECT * FROM sessions WHERE session_id = %s", (session_id,))
        s = c.fetchone()
        if s is None:
            raise HTTPException(404, "세션이 없습니다")
        c.execute("SELECT * FROM dialog_sessions WHERE session_id = %s", (session_id,))
        dialog = c.fetchone()
        c.execute("SELECT * FROM dialog_turns WHERE session_id = %s ORDER BY turn_no", (session_id,))
        turns = c.fetchall()
        c.execute("SELECT * FROM alert_logs WHERE session_id = %s ORDER BY occurred_at", (session_id,))
        alerts_ = c.fetchall()
    # access_decisions · escort_logs 에는 session_id 칸이 없어 여기서 묶지 못한다 (sql/proposed_changes.sql)
    return {"session": s, "dialog": dialog, "turns": turns, "alerts": alerts_}


@router.get("/health/latest", summary="노드별 최근 상태")
def health_latest(_=Depends(require("query:read"))):
    with db.tx() as c:
        c.execute("""SELECT DISTINCT ON (node) node, status, occurred_at, detail
                     FROM system_health ORDER BY node, health_id DESC""")   # LWT ts 는 믿을 수 없어 받은 순서
        return c.fetchall()


@router.get("/stats/today", summary="오늘 통계")
def stats_today(_=Depends(require("query:read"))):
    with db.tx() as c:
        # "오늘 0시" 를 DB 서버 시간대가 아니라 LOCAL_TZ 기준으로 (도커 Postgres 기본은 UTC)
        c.execute("SELECT date_trunc('day', now() AT TIME ZONE %s) AT TIME ZONE %s AS t0",
                  (config.LOCAL_TZ, config.LOCAL_TZ))
        t0 = c.fetchone()["t0"]
        c.execute("SELECT count(*) AS n FROM sessions WHERE created_at >= %s", (t0,))
        visitors = c.fetchone()["n"]
        c.execute("""SELECT destination, count(*) AS n FROM dialog_sessions
                     WHERE started_at >= %s AND destination IS NOT NULL
                     GROUP BY destination ORDER BY n DESC""", (t0,))
        dest = c.fetchall()
        c.execute("""SELECT reason, count(*) AS n, count(*) FILTER (WHERE NOT resolved) AS open
                     FROM alert_logs WHERE occurred_at >= %s
                     GROUP BY reason ORDER BY n DESC""", (t0,))
        al = c.fetchall()
        c.execute("""SELECT count(*) AS n, count(*) FILTER (WHERE success = 1) AS ok
                     FROM escort_logs WHERE start_time >= %s""", (t0,))
        esc = c.fetchone()
    return {"since": t0, "visitors": visitors, "destinations": dest, "alerts": al, "escorts": esc}
