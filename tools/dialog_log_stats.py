#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""대화 로그에서 비기능 지표를 낸다 (`NFR-B-101` 측정 도구).

    python3 tools/dialog_log_stats.py ~/dialog_logs/*.jsonl

내는 값
-------
**`NFR-B-101` 종단 응답 시간** — p50 ≤ 3,800ms / p95 ≤ 4,000ms / 최악 ≤ 5,500ms.
`total_ms` 는 **발화 종료부터 응답 재생 개시까지**만 담는다. 녹음 길이와 재생 길이는
빼야 한다 — 그건 사람이 말한 시간이지 기다린 시간이 아니다.

**`NFR-B-403` 세션 누수** — `outcome` 이 안 찍힌 세션. 턴은 있는데 세션 줄이 없으면
그 세션은 **끝나지 못한 것**이다(프로세스가 죽었거나 경로가 빠졌거나).

**`NFR-B-502` 대화 턴 수** · **`NFR-B-204` 1회 발화 확정률**(`retry_count == 0` 비율).

p95 를 쓰는 이유
----------------
평균은 **느린 꼬리를 감춘다.** 10번 중 9번이 2초라도 한 번이 8초면 방문자는 그 한 번을
기억한다. 표본이 20건 미만이면 p95 가 사실상 최댓값이라 경고를 붙인다.
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

TARGET = {"p50": 3800, "p95": 4000, "max": 5500}       # NFR-B-101


def pct(xs: list[int], q: float) -> int:
    """백분위 (최근접 순위법). 표본이 적을 때 보간하면 없는 정밀도를 꾸며 내게 된다."""
    if not xs:
        return 0
    s = sorted(xs)
    k = max(0, min(len(s) - 1, int(round(q * len(s) + 0.5)) - 1))
    return s[k]


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__, file=sys.stderr)
        return 2

    turns, sessions, broken = [], [], 0
    for path in argv[1:]:
        for line in Path(path).read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                broken += 1
                continue
            (sessions if r.get("rec") == "session" else turns).append(r)

    if not turns and not sessions:
        print("로그가 비어 있다 — 측정할 게 없다")
        return 1

    print(f"세션 {len(sessions)}건 · 턴 {len(turns)}건"
          + (f" · 깨진 줄 {broken}건" if broken else ""))

    # ── NFR-B-101 ────────────────────────────────────────────────────────
    tot = [t["total_ms"] for t in turns if t.get("total_ms")]
    print("\n[NFR-B-101] 종단 응답 시간 — 발화 종료 → 응답 재생 개시")
    if not tot:
        print("  측정 불가 — total_ms 가 담긴 턴이 없다")
    else:
        got = {"p50": pct(tot, .50), "p95": pct(tot, .95), "max": max(tot)}
        for k in ("p50", "p95", "max"):
            ok = "통과" if got[k] <= TARGET[k] else "**초과**"
            print(f"  {k:4} {got[k]:6,} ms   (목표 {TARGET[k]:,} ms)  {ok}")
        print(f"  표본 {len(tot)}건")
        if len(tot) < 20:
            print("  ※ 표본 20건 미만 — p95 가 사실상 최댓값이라 값을 믿기 어렵다")

    # 단계별 — 어디가 병목인지
    for col, name in [("stt_ms", "STT 추론"), ("tts_ms", "재생 길이"),
                      ("touch_wait_ms", "터치 대기")]:
        xs = [t[col] for t in turns if t.get(col)]
        if xs:
            print(f"  {name:8} p50 {pct(xs, .50):6,} ms · p95 {pct(xs, .95):6,} ms "
                  f"· n={len(xs)}")

    # ── NFR-B-403 · 세션 누수 ────────────────────────────────────────────
    closed = {s["session_id"] for s in sessions}
    seen = {t["session_id"] for t in turns}
    leaked = sorted(seen - closed)
    print(f"\n[NFR-B-403] 세션 누수 — 미종료 {len(leaked)}건 (목표 0건)")
    for sid in leaked[:5]:
        print(f"  {sid}")

    # ── NFR-B-502 · 턴 수 / NFR-B-204 · 1회 확정률 ───────────────────────
    if sessions:
        turn_counts = [s.get("turns", 0) for s in sessions]
        print(f"\n[NFR-B-502] 확정까지 턴 수 — 평균 "
              f"{sum(turn_counts) / len(turn_counts):.2f} (목표 2턴 이하)")
        conf = [s for s in sessions if s.get("outcome") == "confirmed"]
        if conf:
            once = sum(1 for s in conf if not s.get("retry_count"))
            print(f"[NFR-B-204] 1회 발화 확정률 — {once}/{len(conf)} "
                  f"({once / len(conf) * 100:.0f} %, 목표 70 % 이상)")
        print("\n[결과 분포] " + " · ".join(
            f"{k} {v}" for k, v in Counter(
                s.get("outcome") for s in sessions).most_common()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
