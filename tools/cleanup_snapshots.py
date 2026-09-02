#!/usr/bin/env python3
"""보관 기간이 지난 스냅샷/오디오 파일을 정리하는 스크립트 (독립 실행, 외부 의존성 없음).

개인정보(얼굴 이미지) 보관 정책: 기본 7일이 지난 날짜 디렉터리(yyyymmdd)를
통째로 삭제한다. 보관 기간은 환경변수 MECHDOG_RETENTION_DAYS 로 조정한다.
저장 경로는 MECHDOG_SNAPSHOT_ROOT(기본 /data/snap), MECHDOG_AUDIO_ROOT(기본 /data/audio).

사용법:
    python tools/cleanup_snapshots.py --dry-run   # 삭제 대상만 미리 보기
    python tools/cleanup_snapshots.py             # 실제 삭제

주기 실행 방법은 README.md 참고.
"""

from __future__ import annotations

import argparse
import os
import shutil
from datetime import datetime, timedelta
from pathlib import Path

DEFAULT_RETENTION_DAYS = 7


def _snapshot_root() -> Path:
    return Path(os.environ.get("MECHDOG_SNAPSHOT_ROOT", "/data/snap"))


def _audio_root() -> Path:
    return Path(os.environ.get("MECHDOG_AUDIO_ROOT", "/data/audio"))


def _retention_days() -> int:
    raw = os.environ.get("MECHDOG_RETENTION_DAYS")
    if raw is None:
        return DEFAULT_RETENTION_DAYS
    try:
        return int(raw)
    except ValueError:
        print(
            f"[cleanup] MECHDOG_RETENTION_DAYS='{raw}' 를 정수로 해석할 수 없어 "
            f"기본값({DEFAULT_RETENTION_DAYS}일)을 사용합니다."
        )
        return DEFAULT_RETENTION_DAYS


def _date_dirs(root: Path) -> list[Path]:
    if not root.exists():
        return []
    return [p for p in root.iterdir() if p.is_dir() and len(p.name) == 8 and p.name.isdigit()]


def _expired_dirs(root: Path, retention_days: int, today: datetime) -> list[Path]:
    cutoff = today - timedelta(days=retention_days)
    expired = []
    for d in _date_dirs(root):
        try:
            day = datetime.strptime(d.name, "%Y%m%d")
        except ValueError:
            continue
        if day < cutoff:
            expired.append(d)
    return sorted(expired)


def main() -> int:
    parser = argparse.ArgumentParser(description="보관 기간 초과 스냅샷/오디오 정리")
    parser.add_argument("--dry-run", action="store_true", help="삭제하지 않고 대상 목록만 출력")
    args = parser.parse_args()

    retention_days = _retention_days()
    today = datetime.now()
    print(f"[cleanup] 보관 기간: {retention_days}일 (기준일: {today:%Y-%m-%d})")

    targets: list[Path] = []
    for root in (_snapshot_root(), _audio_root()):
        targets.extend(_expired_dirs(root, retention_days, today))

    if not targets:
        print("[cleanup] 삭제 대상 없음.")
        return 0

    for d in targets:
        if args.dry_run:
            print(f"[dry-run] 삭제 예정: {d}")
        else:
            shutil.rmtree(d, ignore_errors=True)
            print(f"[cleanup] 삭제됨: {d}")

    action = "삭제 예정" if args.dry_run else "삭제 완료"
    print(f"[cleanup] {action}: {len(targets)}건")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
