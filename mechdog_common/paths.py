"""이미지/오디오 저장 경로 규칙.

MQTT 브로커에 원본 프레임/오디오를 그대로 싣지 않는다 (브로커가 먼저 죽는다).
MechDog/RPi/PC는 파일을 공유 볼륨에 저장하고, MQTT 메시지에는 이 모듈이 만든
경로 문자열만 실어 보낸다. 컨테이너 환경에서는 모든 서비스가 같은 볼륨을
`/data/snap`, `/data/audio` 로 마운트한다는 전제.
"""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

SNAPSHOT_ROOT = Path(os.environ.get("MECHDOG_SNAPSHOT_ROOT", "/data/snap"))
AUDIO_ROOT = Path(os.environ.get("MECHDOG_AUDIO_ROOT", "/data/audio"))

# 개인정보(얼굴 이미지) 보관 정책: 기본 7일 후 자동 삭제.
# tools/cleanup_snapshots.py 가 이 환경변수를 읽어 주기 정리한다.
DEFAULT_RETENTION_DAYS = 7


def snapshot_path(session_id: str, kind: str, ts: datetime | None = None) -> Path:
    """얼굴/PPE 스냅샷 저장 경로. kind 예: 'face', 'ppe', 'alert'.

    구조: {SNAPSHOT_ROOT}/{yyyymmdd}/{session_id}/{HHMMSS_ffffff}_{kind}.jpg
    날짜 디렉터리로 나눠두면 cleanup_snapshots.py가 디렉터리명만 보고 보관 기간
    초과 여부를 빠르게 판단할 수 있다.
    """
    ts = ts or datetime.now()
    day = ts.strftime("%Y%m%d")
    fname = f"{ts.strftime('%H%M%S_%f')}_{kind}.jpg"
    return SNAPSHOT_ROOT / day / session_id / fname


def audio_path(session_id: str, ts: datetime | None = None) -> Path:
    """대화 오디오 저장 경로. 구조는 snapshot_path와 동일한 규칙을 따른다."""
    ts = ts or datetime.now()
    day = ts.strftime("%Y%m%d")
    fname = f"{ts.strftime('%H%M%S_%f')}.wav"
    return AUDIO_ROOT / day / session_id / fname


def date_dirs(root: Path) -> list[Path]:
    """root 바로 아래의 yyyymmdd 형태 날짜 디렉터리만 반환 (cleanup 스크립트용)."""
    if not root.exists():
        return []
    result = []
    for p in root.iterdir():
        if p.is_dir() and len(p.name) == 8 and p.name.isdigit():
            result.append(p)
    return result
