#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""대화 로그(jsonl) → `INSERT` 문 (`FR-B-802`).

`dialog/dlog.py` 가 남긴 줄을 `11_공유용_B_데이터항목.md` 의 두 테이블에 넣을
SQL 로 바꾼다. **필드 이름이 컬럼명과 이미 같아서 옮길 때 매핑이 필요 없다** —
이 스크립트가 하는 일은 따옴표 처리와 순서 맞추기뿐이다.

    python3 tools/dialog_log_to_sql.py ~/dialog_logs/20260928.jsonl > turns.sql

왜 이 스크립트가 따로 있나
--------------------------
**`dialog_turns` 에 누가 INSERT 하는지가 아직 안 정해졌다** — B 가 직접 넣을 수도,
여도훈 수집기가 넣을 수도 있다. 그 협의를 기다리는 동안 로그가 안 쌓이면
`NFR-B-101`·`403`·`502` 를 **측정할 방법 자체가 없어진다.** 그래서 파일로 먼저 쌓고,
결정이 나면 이 스크립트로 한 번에 옮긴다. 어느 쪽으로 정해지든 데이터는 이미 다 있다.

`dialog_sessions` 를 먼저 넣는다 — `dialog_turns.session_id` 가 그걸 참조한다.
같은 파일을 두 번 돌려도 되게 `ON CONFLICT DO NOTHING` 을 붙였다.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

SESSION_COLS = ["session_id", "visitor_id", "started_at", "ended_at",
                "outcome", "destination", "purpose",
                "confidence", "retry_count", "escalation_reason"]
TURN_COLS = ["session_id", "turn_no", "ts", "stt_raw", "stt_corrected",
             "candidates", "confidence", "presence", "decision", "prompt_id",
             "touch_wait_ms", "stt_ms", "tts_ms", "total_ms"]


def lit(v, *, as_json: bool = False) -> str:
    """SQL 리터럴. 작은따옴표는 두 번 써서 escape 한다."""
    if v is None:
        return "NULL"
    if as_json:
        return "'" + json.dumps(v, ensure_ascii=False).replace("'", "''") + "'::jsonb"
    if isinstance(v, bool):
        return "TRUE" if v else "FALSE"
    if isinstance(v, (int, float)):
        return str(v)
    return "'" + str(v).replace("'", "''") + "'"


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__, file=sys.stderr)
        return 2

    sessions, turns = [], []
    bad = 0
    for path in argv[1:]:
        for line in Path(path).read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                bad += 1            # 쓰다 만 줄(전원이 나갔다든지)은 버린다
                continue
            (sessions if rec.get("rec") == "session" else turns).append(rec)

    print("-- dialog/dlog.py 가 남긴 로그에서 생성됨 (FR-B-802)")
    print(f"-- 세션 {len(sessions)}건 · 턴 {len(turns)}건"
          + (f" · 깨진 줄 {bad}건 건너뜀" if bad else ""))
    print("BEGIN;")

    for r in sessions:
        vals = ", ".join(lit(r.get(c)) for c in SESSION_COLS)
        print(f"INSERT INTO dialog_sessions ({', '.join(SESSION_COLS)})\n"
              f"  VALUES ({vals})\n  ON CONFLICT (session_id) DO NOTHING;")

    for r in turns:
        vals = ", ".join(lit(r.get(c), as_json=(c == "candidates"))
                         for c in TURN_COLS)
        print(f"INSERT INTO dialog_turns ({', '.join(TURN_COLS)})\n"
              f"  VALUES ({vals})\n  ON CONFLICT (session_id, turn_no) DO NOTHING;")

    print("COMMIT;")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
