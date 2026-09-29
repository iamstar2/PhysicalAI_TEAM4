"""POST /events — 수집서버가 MQTT 메시지를 받은 그대로 넘기는 곳.

응답 코드 약속 (수집서버가 재전송 여부를 이걸로 판단한다)
- 200: 적재됨 (이미 받은 메시지면 건너뜀) → 다음 메시지로
- 422: 메시지가 틀림 (스키마 · 규칙 · 제약 위반) → 다시 보내도 같다. 버린다 (rejected 로그에 남음)
- 503: DB 에 못 붙음 → 쌓아 두고 나중에 다시 보낸다
- 500: API 서버 버그 → 쌓아 두고 다시 보낸다 (고친 뒤 재전송하면 들어간다)
"""
from __future__ import annotations

import psycopg
from fastapi import APIRouter, Body, Depends, HTTPException
from psycopg_pool import PoolTimeout

from .. import audit, db, ingest, validate
from ..security import require

router = APIRouter(tags=["events (수집서버)"])

# 메시지 탓인 실패 — 다시 보내도 결과가 같다
_BAD_MESSAGE = (ValueError, psycopg.errors.DataError, psycopg.errors.IntegrityError)


def _one(client: str, msg: dict) -> dict:
    errs = validate.errors(msg)
    if errs:
        audit.rejected(client, msg, "; ".join(errs))
        return {"msg_id": msg.get("msg_id") if isinstance(msg, dict) else None,
                "ok": False, "errors": errs}
    try:
        with db.tx() as c:
            where = ingest.store(c, msg)
    except (psycopg.OperationalError, PoolTimeout) as e:
        raise HTTPException(503, f"DB 연결 실패 — 잠시 후 다시 보내 주세요 ({type(e).__name__})")
    except _BAD_MESSAGE as e:
        audit.rejected(client, msg, f"{type(e).__name__}: {e}")
        return {"msg_id": msg["msg_id"], "ok": False, "errors": [str(e).splitlines()[0]]}
    except Exception as e:           # 그 밖의 예외는 서버 쪽 버그 — 메시지를 버리게 하면 안 된다
        audit.rejected(client, msg, f"서버 오류 {type(e).__name__}: {e}")
        raise HTTPException(500, f"API 서버 오류 — 메시지를 버리지 말고 나중에 다시 보내 주세요 "
                                 f"({type(e).__name__})")
    ingest.remember(msg)
    return {"msg_id": msg["msg_id"], "ok": True, "stored": where}


@router.post("/events", summary="메시지 1건 적재")
def post_event(msg: dict = Body(...), client: str = Depends(require("events:write"))):
    r = _one(client, msg)
    if not r["ok"]:
        raise HTTPException(422, r)
    return r


@router.post("/events/batch", summary="메시지 여러 건 적재 (끊겼다 다시 붙었을 때 몰아 보내기)")
def post_events(msgs: list[dict] = Body(...), client: str = Depends(require("events:write"))):
    # 한 건이 422 여도 나머지는 계속한다. 503 · 500 이면 거기서 멈추고 전체를 다시 보내면 된다
    # (이미 들어간 건은 중복으로 건너뛴다).
    results = [_one(client, m) for m in msgs]
    return {"ok": sum(r["ok"] for r in results), "failed": sum(not r["ok"] for r in results),
            "results": results}
