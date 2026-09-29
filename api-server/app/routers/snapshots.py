"""경고 사진 — A · D 가 올리고 대시보드가 본다.

각자 노트북에서 돌기 때문에 A 노트북의 파일 경로를 D 가 열 수 없다.
그래서 사진을 여기로 올리고, 돌려받은 `path` 를 메시지의 snapshot_path 에 넣는다.

TODO(협의): snapshot_path 에 무엇을 넣을지 — 지금은 `/data/snap/<session>/<file>` 모양을
유지해서 스키마 · 기존 D 코드와 맞춘다. D 는 이 path 를 `GET /snapshots/<session>/<file>` 로 바꿔 부르면 된다.
"""
from __future__ import annotations

import re
import time
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile

from .. import config
from ..security import decrypt, encrypt, encryption_ready, require

router = APIRouter(prefix="/snapshots", tags=["snapshots (경고 사진)"])

_SAFE = re.compile(r"^[A-Za-z0-9._-]{1,120}$")
_TYPES = {"image/jpeg": ".jpg", "image/png": ".png"}
_ENC = ".enc"


def _check(part: str) -> str:
    if not _SAFE.match(part) or part in (".", "..") or part.endswith(_ENC):
        raise HTTPException(400, f"허용되지 않는 이름: {part}")
    return part


@router.post("", status_code=201, summary="사진 업로드 → snapshot_path 돌려받기")
async def upload(file: UploadFile = File(...), session_id: str = Form(...),
                 kind: str = Form("alert"), _=Depends(require("snapshots:write"))):
    if config.ENCRYPT_SNAPSHOTS and not encryption_ready():
        # 얼굴이 찍힌 사진이라 평문으로 몰래 저장하지 않는다. 평문이 필요하면 ENCRYPT_SNAPSHOTS=0
        raise HTTPException(503, "PHOTO_KEY 가 없어 경고 사진을 암호화할 수 없습니다")
    ext = _TYPES.get(file.content_type or "")
    if ext is None:
        raise HTTPException(415, "jpeg · png 만 받습니다")
    data = await file.read()
    if not data or len(data) > config.SNAPSHOT_MAX_BYTES:
        raise HTTPException(413, "사진이 비었거나 너무 큽니다")
    sid, kind = _check(session_id), _check(kind)
    name = f"{kind}-{uuid.uuid4().hex[:8]}{ext}"
    folder = config.SNAPSHOT_ROOT / sid
    folder.mkdir(parents=True, exist_ok=True)
    if config.ENCRYPT_SNAPSHOTS:
        (folder / (name + _ENC)).write_bytes(encrypt(data))
    else:
        (folder / name).write_bytes(data)
    return {"snapshot_path": f"{config.SNAPSHOT_PATH_PREFIX}/{sid}/{name}",
            "url": f"/snapshots/{sid}/{name}"}


@router.get("/{session_id}/{name}", summary="사진 보기")
def get(session_id: str, name: str, _=Depends(require("snapshots:read"))):
    folder = config.SNAPSHOT_ROOT / _check(session_id)
    name = _check(name)
    media = "image/png" if name.endswith(".png") else "image/jpeg"
    if (folder / (name + _ENC)).is_file():
        data = decrypt((folder / (name + _ENC)).read_bytes())
    elif (folder / name).is_file():
        data = (folder / name).read_bytes()
    else:
        raise HTTPException(404, "사진이 없습니다 (보관 기간이 지났을 수 있음)")
    return Response(data, media_type=media, headers={"Cache-Control": "no-store"})


def cleanup(now: float | None = None) -> int:
    """보관 기간이 지난 사진 삭제. 지운 파일 수를 돌려준다."""
    root: Path = config.SNAPSHOT_ROOT
    if not root.is_dir():
        return 0
    limit = (now or time.time()) - config.SNAPSHOT_RETENTION_DAYS * 86400
    n = 0
    for f in root.glob("*/*"):
        if f.is_file() and f.stat().st_mtime < limit:
            f.unlink()
            n += 1
    for d in root.iterdir():
        if d.is_dir() and not any(d.iterdir()):
            d.rmdir()
    return n
