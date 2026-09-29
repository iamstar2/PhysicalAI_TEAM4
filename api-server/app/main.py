"""MechDog API 서버 — DB 쓰기 · 조회의 유일한 창구 (HW 설계도 호스트2).

    uvicorn app.main:app --host 0.0.0.0 --port 8080

`--host 0.0.0.0` 이어야 다른 노트북에서 접속할 수 있다 (localhost 로 띄우면 이 PC 에서만 됨).
"""
from __future__ import annotations

import logging
import threading
import time
from contextlib import asynccontextmanager

import psycopg
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from psycopg_pool import PoolTimeout

from . import audit, config, db
from .routers import dialog, events, persons, query, snapshots
from .security import encryption_ready

log = logging.getLogger("api")


def _cleanup_loop(stop: threading.Event) -> None:
    while not stop.is_set():
        try:
            n = snapshots.cleanup()
            if n:
                log.info("보관 기간 지난 사진 %d개 삭제", n)
        except Exception:
            log.exception("사진 정리 실패")
        stop.wait(3600)


@asynccontextmanager
async def lifespan(_: FastAPI):
    if config.AUTH_DISABLED:
        log.warning("AUTH_DISABLED=1 — 토큰 검사를 하지 않습니다 (개발용)")
    elif not config.API_TOKENS:
        log.warning("API_TOKENS 가 비어 있어 모든 요청이 401 이 됩니다")
    if not encryption_ready():
        log.warning("PHOTO_KEY 가 없어 등록 사진 업로드가 거부됩니다")
    stop = threading.Event()
    threading.Thread(target=_cleanup_loop, args=(stop,), daemon=True).start()
    yield
    stop.set()
    db.close_pool()


app = FastAPI(title="MechDog API", version="0.1.0", lifespan=lifespan,
              description="수집서버 적재 · 얼굴 등록 · 경고 사진 · 조회. 인증: `Authorization: Bearer <토큰>`")


if config.CORS_ORIGINS:
    app.add_middleware(CORSMiddleware, allow_origins=config.CORS_ORIGINS,
                       allow_methods=["*"], allow_headers=["*"])


# 모든 엔드포인트 공통 — DB 가 돌려준 오류를 원인에 맞는 코드로 (호출하는 쪽이 재시도 여부를 판단)
@app.exception_handler(psycopg.OperationalError)
@app.exception_handler(PoolTimeout)
async def _db_down(_: Request, e: Exception):
    return JSONResponse({"detail": f"DB 연결 실패 — 잠시 후 다시 시도 ({type(e).__name__})"}, 503)


@app.exception_handler(psycopg.errors.DataError)
@app.exception_handler(psycopg.errors.IntegrityError)
async def _bad_data(_: Request, e: Exception):
    return JSONResponse({"detail": f"DB 가 값을 거부했습니다: {str(e).splitlines()[0]}"}, 422)


@app.middleware("http")
async def _audit(request: Request, call_next):
    t0 = time.perf_counter()
    status = 500
    try:
        resp = await call_next(request)
        status = resp.status_code
        return resp
    finally:
        if request.url.path not in ("/healthz", "/docs", "/openapi.json"):
            audit.request(getattr(request.state, "client", "-"), request.method,
                          request.url.path, status, (time.perf_counter() - t0) * 1000)


@app.get("/healthz", tags=["system"], summary="살아 있는지 · DB 연결")
def healthz():
    return {"ok": True, "db": db.ping(), "encryption": encryption_ready(),
            "auth": "disabled" if config.AUTH_DISABLED else f"{len(config.API_TOKENS)} tokens"}


for r in (events.router, persons.router, snapshots.router, query.router, dialog.router):
    app.include_router(r)
