"""POST /dialog/import — B 파이의 대화 로그(jsonl 줄)를 한 번에 적재.

`dialog/dlog.py` 가 남긴 줄을 그대로 받는다 (`rec` 가 "session" 이면 세션, 아니면 턴).
필드 이름이 컬럼명과 같아서 매핑이 없다. 같은 파일을 두 번 보내도 결과가 같다.
"""
from __future__ import annotations

import json

from fastapi import APIRouter, Body, Depends

from .. import db, ingest
from ..security import require

router = APIRouter(tags=["dialog (B 대화 로그)"])

SESSION_COLS = ["session_id", "visitor_id", "started_at", "ended_at", "outcome", "destination",
                "purpose", "confidence", "retry_count", "escalation_reason"]
TURN_COLS = ["session_id", "turn_no", "ts", "stt_raw", "stt_corrected", "candidates",
             "confidence", "presence", "decision", "prompt_id", "touch_wait_ms",
             "stt_ms", "tts_ms", "total_ms"]


@router.post("/dialog/import", summary="대화 로그 일괄 적재")
def import_logs(records: list[dict] = Body(...), _=Depends(require("dialog:write"))):
    sessions = [r for r in records if r.get("rec") == "session"]
    turns = [r for r in records if r.get("rec") != "session"]
    skipped = []
    with db.tx() as c:
        for r in sessions:
            ingest.ensure_session(c, r["session_id"], r.get("visitor_id"))
            vals = [r.get(k) for k in SESSION_COLS]
            sets = ", ".join(f"{k} = COALESCE(EXCLUDED.{k}, dialog_sessions.{k})"
                             for k in SESSION_COLS[1:])
            c.execute(f"""INSERT INTO dialog_sessions ({', '.join(SESSION_COLS)})
                          VALUES ({', '.join(['%s'] * len(SESSION_COLS))})
                          ON CONFLICT (session_id) DO UPDATE SET {sets}""", vals)
        known = {r["session_id"] for r in sessions}
        for r in turns:
            if r.get("session_id") not in known:
                c.execute("SELECT 1 FROM dialog_sessions WHERE session_id = %s", (r.get("session_id"),))
                if c.fetchone() is None:
                    skipped.append(r.get("session_id"))
                    continue
            vals = [json.dumps(r.get(k), ensure_ascii=False) if k == "candidates" and r.get(k) is not None
                    else r.get(k) for k in TURN_COLS]
            c.execute(f"""INSERT INTO dialog_turns ({', '.join(TURN_COLS)})
                          VALUES ({', '.join(['%s'] * len(TURN_COLS))})
                          ON CONFLICT (session_id, turn_no) DO NOTHING""", vals)
    return {"sessions": len(sessions), "turns": len(turns) - len(skipped),
            "skipped_turns_without_session": len(skipped)}
