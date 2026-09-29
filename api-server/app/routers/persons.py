"""얼굴 등록 — 대시보드가 등록하고, A 가 가져간다.

- 사진은 person_photos.image 에 **암호화해서** 저장한다. 키는 API 서버만 가진다.
- 얼굴 특징값(임베딩)은 DB 에 넣지 않는다 (스키마 주석 — A 내부 보관). A 는 사진을 받아 직접 계산한다.
- 생체정보 수집 동의(consent)가 없으면 받지 않는다.
"""
from __future__ import annotations

import hashlib
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile
from pydantic import BaseModel

from .. import db
from ..security import decrypt, encrypt, encryption_ready, require

router = APIRouter(prefix="/persons", tags=["persons (얼굴 등록)"])

ALLOWED_TYPES = {"image/jpeg", "image/png"}
MAX_PHOTO_BYTES = 5 * 1024 * 1024


class PersonIn(BaseModel):
    name: str
    person_id: str | None = None        # 비우면 서버가 만든다


class PersonPatch(BaseModel):
    name: str | None = None
    active: bool | None = None          # false = 재직 아님 → A 가 등록 삭제


def _person(c, pid: str) -> dict:
    c.execute("SELECT * FROM persons WHERE person_id = %s", (pid,))
    row = c.fetchone()
    if row is None:
        raise HTTPException(404, "등록되지 않은 사람입니다")
    return row


@router.post("", status_code=201, summary="사람 등록")
def create(body: PersonIn, _=Depends(require("persons:write"))):
    pid = body.person_id or f"p-{uuid.uuid4().hex[:8]}"
    with db.tx() as c:
        c.execute("""INSERT INTO persons (person_id, name) VALUES (%s, %s)
                     ON CONFLICT (person_id) DO NOTHING RETURNING *""", (pid, body.name))
        row = c.fetchone()
    if row is None:
        raise HTTPException(409, "이미 있는 person_id 입니다")
    return row


@router.patch("/{pid}", summary="이름 변경 · 비활성화")
def update(pid: str, body: PersonPatch, _=Depends(require("persons:write"))):
    with db.tx() as c:
        _person(c, pid)
        c.execute("""UPDATE persons SET name = COALESCE(%s, name), active = COALESCE(%s, active),
                            updated_at = now() WHERE person_id = %s RETURNING *""",
                  (body.name, body.active, pid))
        return c.fetchone()


@router.post("/{pid}/photos", status_code=201, summary="등록 사진 추가 (1인당 3장 이상 권장)")
async def add_photo(pid: str, file: UploadFile = File(...), consent: bool = Form(...),
                    _=Depends(require("persons:write"))):
    if not consent:
        raise HTTPException(400, "생체정보 수집 동의(consent=true)가 필요합니다")
    if not encryption_ready():
        raise HTTPException(503, "PHOTO_KEY 가 없어 등록 사진을 받을 수 없습니다")
    if file.content_type not in ALLOWED_TYPES:
        raise HTTPException(415, f"jpeg · png 만 받습니다 ({file.content_type})")
    data = await file.read()
    if not data or len(data) > MAX_PHOTO_BYTES:
        raise HTTPException(413, "사진이 비었거나 너무 큽니다 (최대 5MB)")
    with db.tx() as c:
        _person(c, pid)
        c.execute("""INSERT INTO person_photos (person_id, image, content_type, sha256, consent)
                     VALUES (%s, %s, %s, %s, true)
                     RETURNING photo_id, person_id, content_type, sha256, updated_at""",
                  (pid, encrypt(data), file.content_type, hashlib.sha256(data).hexdigest()))
        row = c.fetchone()
        c.execute("UPDATE persons SET updated_at = now() WHERE person_id = %s", (pid,))
    return row


@router.delete("/{pid}/photos/{photo_id}", status_code=204, summary="등록 사진 삭제")
def delete_photo(pid: str, photo_id: int, _=Depends(require("persons:write"))):
    with db.tx() as c:
        c.execute("DELETE FROM person_photos WHERE person_id = %s AND photo_id = %s",
                  (pid, photo_id))
        if c.rowcount == 0:
            raise HTTPException(404, "사진이 없습니다")
        c.execute("UPDATE persons SET updated_at = now() WHERE person_id = %s", (pid,))


@router.get("", summary="등록 목록 — A 는 updated_since 로 바뀐 사람만 가져간다")
def list_persons(updated_since: datetime | None = None, _=Depends(require("persons:read"))):
    with db.tx() as c:
        c.execute("""SELECT p.*, COALESCE(json_agg(json_build_object(
                         'photo_id', ph.photo_id, 'sha256', ph.sha256,
                         'content_type', ph.content_type, 'updated_at', ph.updated_at)
                       ) FILTER (WHERE ph.photo_id IS NOT NULL), '[]') AS photos
                     FROM persons p LEFT JOIN person_photos ph USING (person_id)
                     WHERE %s::timestamptz IS NULL OR p.updated_at > %s::timestamptz
                     GROUP BY p.person_id ORDER BY p.updated_at""",
                  (updated_since, updated_since))
        return c.fetchall()


@router.get("/{pid}/photos/{photo_id}", summary="등록 사진 원본 (복호화해서 보냄)")
def get_photo(pid: str, photo_id: int, _=Depends(require("persons:read"))):
    with db.tx() as c:
        c.execute("""SELECT image, content_type FROM person_photos
                     WHERE person_id = %s AND photo_id = %s""", (pid, photo_id))
        row = c.fetchone()
    if row is None:
        raise HTTPException(404, "사진이 없습니다")
    return Response(decrypt(row["image"]), media_type=row["content_type"],
                    headers={"Cache-Control": "no-store"})
