#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""대화 로그(jsonl) → API 서버 `POST /dialog/import` (`FR-B-802`).

`dialog_log_to_sql.py` 와 같은 일을 API 경유로 한다 — 0929 회의에서
"DB 쓰기는 API 서버를 거친다" 로 정해서, B 는 DB 에 직접 붙지 않는다.

    API_URL=http://<API 서버 IP>:8080 API_TOKEN=<mechdog_b 토큰> \
        python3 tools/dialog_log_upload.py ~/dialog_logs/20260928.jsonl

같은 파일을 두 번 올려도 된다 (서버가 중복을 거른다).
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request
from pathlib import Path


def main(argv: list[str]) -> int:
    url, token = os.environ.get("API_URL"), os.environ.get("API_TOKEN")
    if len(argv) < 2 or not url or not token:
        print(__doc__, file=sys.stderr)
        return 2
    recs, bad = [], 0
    for path in argv[1:]:
        for line in Path(path).read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                recs.append(json.loads(line))
            except json.JSONDecodeError:
                bad += 1                     # 쓰다 만 줄은 버린다
    req = urllib.request.Request(
        url.rstrip("/") + "/dialog/import", method="POST",
        data=json.dumps(recs, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req, timeout=30) as r:
        print(r.read().decode("utf-8"))
    if bad:
        print(f"깨진 줄 {bad}건 건너뜀", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
