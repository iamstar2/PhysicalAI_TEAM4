"""환경변수 설정 — 협의로 바뀔 값은 전부 여기서 읽는다.

코드를 고치지 않고 `.env` 만 바꿔서 맞출 수 있게 하는 게 목적이다.
값의 의미와 예시는 `api-server/.env.example` 참고.
"""
from __future__ import annotations

import os
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]      # 저장소 루트


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def _flag(name: str, default: bool) -> bool:
    v = _env(name, "1" if default else "0").lower()
    return v in ("1", "true", "yes", "on")


# --- DB (최현수) ---------------------------------------------------------
DATABASE_URL = _env("DATABASE_URL", "postgresql://mechdog:mechdog@localhost:5432/mechdog")

# --- 인증 -----------------------------------------------------------------
# "이름:토큰" 을 쉼표로. 예) collector:abc123,dashboard:def456,mechdog_a:ghi789
# 이름은 권한 표(security.PERMISSIONS)의 키와 감사 로그에 쓰인다.
API_TOKENS = {
    tok.strip(): name.strip()
    for name, _, tok in (p.partition(":") for p in _env("API_TOKENS").split(",") if ":" in p)
}
# 개발용 — 토큰 없이 전부 허용. 시연 · 통합 시험에서는 끈다.
AUTH_DISABLED = _flag("AUTH_DISABLED", False)

# --- 암호화 (등록 사진 · 경고 사진) ----------------------------------------
# Fernet 키 (python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
# 비어 있으면 등록 사진 업로드를 거부한다 — 생체정보를 평문으로 저장하지 않기 위해.
PHOTO_KEY = _env("PHOTO_KEY")
ENCRYPT_SNAPSHOTS = _flag("ENCRYPT_SNAPSHOTS", True)

# --- 파일 -----------------------------------------------------------------
SNAPSHOT_ROOT = Path(_env("SNAPSHOT_ROOT", "/data/snap"))
SNAPSHOT_RETENTION_DAYS = int(_env("SNAPSHOT_RETENTION_DAYS", "7"))   # access_decisions 주석: 7일 보관
SNAPSHOT_MAX_BYTES = int(_env("SNAPSHOT_MAX_BYTES", str(5 * 1024 * 1024)))
LOG_DIR = Path(_env("API_LOG_DIR", str(_ROOT / "api-server" / "logs")))

# --- 메시지 스키마 ----------------------------------------------------------
SCHEMA_PATH = Path(_env("SCHEMA_PATH", str(_ROOT / "schema" / "mechdog_messages.schema.json")))

# --- 적재 규칙 스위치 (협의 결과에 따라 켜고 끈다) ---------------------------
# sessions 행이 없을 때 자동으로 만든다. A 가 gate.session 보다 vision.* 을 먼저 보내고,
# D 경고가 gate.session 없이 올 수 있어서(미인가자) 기본은 켠다.
AUTO_CREATE_SESSION = _flag("AUTO_CREATE_SESSION", True)
# 모든 메시지 원본을 event_logs 에도 남길지. 1초 주기 escort · health 까지 쌓여 커지므로 기본은 끈다.
EVENT_LOG_ALL = _flag("EVENT_LOG_ALL", False)
# 방문자와 무관한 메시지가 쓰는 session_id — sessions 행을 만들지 않는다 (B health 는 "system")
NO_SESSION_IDS = {s.strip() for s in _env("NO_SESSION_IDS", "system,unknown,none").split(",")}

# --- 기타 -----------------------------------------------------------------
# "오늘" 통계의 기준 시간대 — DB 서버 시간대(도커 기본 UTC)에 기대지 않는다
LOCAL_TZ = _env("LOCAL_TZ", "Asia/Seoul")
# 브라우저가 API 를 직접 부를 때만 필요 (쉼표 구분, 예: http://192.168.0.10:3000).
# 대시보드 서버가 대신 부르는 구조면 비워 둔다 — 토큰을 브라우저에 두지 않는 쪽이 안전하다.
CORS_ORIGINS = [o.strip() for o in _env("CORS_ORIGINS").split(",") if o.strip()]
# snapshot_path 에 넣는 논리 경로의 앞부분. 스키마 예시 · 기존 D 코드와 맞춘 값이며
# 실제 저장 위치(SNAPSHOT_ROOT)와는 별개다.
SNAPSHOT_PATH_PREFIX = "/data/snap"
