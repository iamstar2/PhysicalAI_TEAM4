# -*- coding: utf-8 -*-
"""TTS 합성 발화로 STT→매칭 파이프라인을 한 번에 돌려보는 회귀 테스트.

주의: 여기 쓰는 샘플은 **Piper TTS 합성음**이다. 사람 목소리 328샘플 정식 테스트셋
(`B_실행_TODO.md` 4.7.2)을 대체하지 않는다. 파이프라인이 안 깨졌는지 보는 용도다.

사용법 (RPi5 에서):
    python3 run_testset.py ~/tts_test
"""

from __future__ import annotations

import sys
from pathlib import Path

from destinations import DESTINATIONS
from matcher import match
from stt import transcribe

# (파일명, 원문, 기대 목적지 또는 기대 행동)
#   None       = 매칭 0개가 정상 (재질문으로 가야 함)
#   "*ambig"   = 후보 2개 이상이라 선택형 재질문이 정상
CASES = [
    ("p01.wav", "입고요",                 "inbound_dock"),
    ("p02.wav", "출고 도크로 가려고요",     "outbound_dock"),
    ("p03.wav", "회의실 예약했는데요",       "meeting_room_1"),
    ("p04.wav", "안전교육 받으러 왔어요",    "safety_training_room"),
    ("p05.wav", "검수하러 왔습니다",         "inspection_area"),
    # 2층 목적지는 elevator_hall 로 안내하는 게 규칙 (01 문서 §5.2 설계 원칙)
    ("p06.wav", "2층 사무실 미팅이요",       "elevator_hall"),
    ("p07.wav", "안내데스크가 어디예요",     "reception"),
    ("p08.wav", "나가려고요",              "exit_gate"),
    ("p09.wav", "도크 갈게요",             "*ambig"),   # 입고/출고 모호 (BR-B-04)
    ("p10.wav", "상차 왔어요",             "outbound_dock"),
    ("p11.wav", "납품 왔어요",             "inbound_dock"),
    ("p12.wav", "김 과장님 만나러 왔어요",   None),        # v1 미지원 → 재질문
]


def main() -> int:
    base = Path(sys.argv[1] if len(sys.argv) > 1 else Path.home() / "tts_test")

    print(f"{'파일':<9} {'인식 결과':<26} {'목적지':<21} {'신뢰도':>6}  {'행동':<16} 판정")
    print("-" * 108)

    ok = 0
    total = 0
    for fname, original, expect in CASES:
        wav = base / fname
        if not wav.exists():
            print(f"{fname:<9} (파일 없음)")
            continue

        stt = transcribe(wav)
        m = match(stt.text, stt.p_stt)
        total += 1

        if expect == "*ambig":
            good = m.action == "disambiguate"
        elif expect is None:
            good = m.dest is None
        else:
            good = m.dest == expect

        ok += good
        dest_shown = m.dest or (
            "+".join(c.dest for c in m.candidates[:2]) if m.action == "disambiguate" else "-"
        )
        print(f"{fname:<9} {stt.text[:24]:<26} {dest_shown:<21} "
              f"{m.confidence:>6.3f}  {m.action:<16} {'OK' if good else 'FAIL'}")
        if not good:
            print(f"{'':11}└ 기대={expect}  원문=\"{original}\"  note={m.note or '-'}")

    print("-" * 108)
    print(f"통과 {ok}/{total}")
    return 0 if ok == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
