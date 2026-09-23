# -*- coding: utf-8 -*-
"""**데려다주지 않고 말로만 알려주는 장소** — 화장실·계단·흡연실 등.

목적지 8종과 무엇이 다른가
--------------------------
  목적지 8종   C(에스코트)가 실제로 동행한다. 좌표·ArUco 마커가 필요하고,
               팀 공용 스키마의 `Destination` enum 에 들어 있다. 늘리려면 팀 합의가 필요하다.
  여기 있는 곳  B 가 위치를 한마디 해 주고 끝이다. **C 도 스키마도 건드리지 않는다.**

화장실 가는 사람을 로봇이 따라갈 이유가 없다. 그런데 안 물어보는 것도 아니라서,
"안내 못 합니다" 로 넘기면 방문자는 답을 못 얻는다. 말로 알려주면 둘 다 해결된다.

이 모듈이 하지 않는 것
----------------------
**위치를 지어내지 않는다.** 문구가 비어 있으면 그 장소는 아예 인식되지 않는다 —
틀린 위치를 자신 있게 말하는 것보다 아무 말도 안 하는 쪽이 낫다.
문구는 시연장 배치가 정해진 뒤 `phrases.json` 에 채운다.
"""
from __future__ import annotations

import json
from pathlib import Path

from hangul import find_fuzzy

CONF = json.loads((Path(__file__).parent / "phrases.json").read_text(encoding="utf-8"))
PLACES: dict = CONF.get("음성안내", {})

# 키워드 길이에 비례해 오차를 허용한다. 짧은 키워드에 거리 2 를 그대로 주면
# 엉뚱한 말에 걸린다 — `LOG-40`("들어왔"→"들었")·`LOG-48`("네"→"내") 에서 두 번 겪었다.
def _max_dist(keyword: str) -> int:
    return 0 if len(keyword) <= 2 else 1


def find(text: str) -> str | None:
    """발화에서 **말로만 알려주는 장소**를 찾는다. 없으면 `None`.

    문구가 비어 있는 장소는 건너뛴다(위치를 모르므로 말할 게 없다).
    """
    best_score: tuple[int, int] | None = None
    best_key: str | None = None
    for key, spec in PLACES.items():
        if not spec.get("문구"):
            continue
        for kw in spec.get("키워드", []):
            hit = find_fuzzy(text, kw, _max_dist(kw))
            if hit is None:
                continue
            # 오차가 작을수록, 같으면 키워드가 길수록 낫다 — 근거가 더 많다
            score = (hit[0], -len(kw))
            if best_score is None or score < best_score:
                best_score, best_key = score, key
    return best_key


def ready() -> list[str]:
    """문구가 채워져 실제로 동작하는 장소 목록."""
    return [k for k, v in PLACES.items() if v.get("문구")]


if __name__ == "__main__":       # 수동 확인
    import sys
    print(f"등록된 장소: {list(PLACES)}")
    print(f"동작하는 장소(문구 있음): {ready() or '없음 — phrases.json 의 음성안내 문구가 비어 있다'}")
    for t in sys.argv[1:]:
        print(f"  {t!r} -> {find(t)}")
