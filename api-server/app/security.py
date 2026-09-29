"""토큰 인증 · 권한 · 암호화.

권한 표(PERMISSIONS)는 **협의 대상**이다 — 누가 무엇을 호출하는지 정해지면 여기만 고친다.
"""
from __future__ import annotations

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from . import config

# 권한 이름 → 호출할 수 있는 클라이언트 이름(API_TOKENS 의 이름)
# TODO(협의): 실제 호출 주체가 확정되면 조정
PERMISSIONS: dict[str, set[str]] = {
    "events:write":    {"collector"},                          # 수집서버(여도훈)
    "persons:write":   {"dashboard"},                          # 얼굴 등록(D 대시보드)
    "persons:read":    {"dashboard", "mechdog_a"},             # A 가 등록 사진을 가져감
    "snapshots:write": {"mechdog_a", "mechdog_d"},             # 경고 사진 업로드
    "snapshots:read":  {"dashboard"},
    "query:read":      {"dashboard"},
    "alerts:resolve":  {"dashboard"},
    "dialog:write":    {"mechdog_b"},                          # B 대화 로그 일괄 적재
}
ADMIN = "admin"      # 모든 권한 (시험용)

_bearer = HTTPBearer(auto_error=False)


def client_name(request: Request,
                cred: HTTPAuthorizationCredentials | None = Depends(_bearer)) -> str:
    if config.AUTH_DISABLED:
        name = "anonymous"
    elif cred is None or cred.credentials not in config.API_TOKENS:
        raise HTTPException(401, "토큰이 없거나 틀렸습니다")
    else:
        name = config.API_TOKENS[cred.credentials]
    request.state.client = name          # 감사 로그용
    return name


def require(perm: str):
    def dep(name: str = Depends(client_name)) -> str:
        if config.AUTH_DISABLED or name == ADMIN or name in PERMISSIONS.get(perm, set()):
            return name
        raise HTTPException(403, f"'{name}' 은(는) {perm} 권한이 없습니다")
    return dep


# --- 암호화 ---------------------------------------------------------------

def _fernet():
    if not config.PHOTO_KEY:
        return None
    from cryptography.fernet import Fernet
    return Fernet(config.PHOTO_KEY.encode())


def encryption_ready() -> bool:
    return _fernet() is not None


def encrypt(data: bytes) -> bytes:
    f = _fernet()
    if f is None:
        raise HTTPException(503, "PHOTO_KEY 가 설정되지 않아 암호화할 수 없습니다")
    return f.encrypt(data)


def decrypt(data: bytes) -> bytes:
    from cryptography.fernet import InvalidToken
    f = _fernet()
    if f is None:
        raise HTTPException(503, "PHOTO_KEY 가 설정되지 않아 복호화할 수 없습니다")
    try:
        return f.decrypt(bytes(data))
    except InvalidToken:
        raise HTTPException(500, "저장할 때와 PHOTO_KEY 가 달라 복호화할 수 없습니다")
