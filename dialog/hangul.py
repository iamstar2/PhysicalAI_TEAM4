# -*- coding: utf-8 -*-
"""한글 자모 분해 + 자모 단위 편집거리.

`FR-B-302`(도메인 보정, 자모 편집거리 ≤ 2)를 위한 유틸.
외부 패키지 없이 유니코드 한글 조합 규칙만으로 구현한다 — RPi5에 설치할 의존성을 늘리지 않기 위해서다.

음절 단위로 비교하면 "입고"/"입구"가 편집거리 1이지만, 자모로 풀면 `ㅇㅣㅂㄱㅗ` vs `ㅇㅣㅂㄱㅜ`로
**모음 하나 차이(거리 1)** 라는 게 드러난다. STT 오인식은 대부분 이런 자모 한두 개 차이라서
자모 단위로 재는 게 음절 단위보다 정확하다.
"""

_BASE = 0xAC00
_LAST = 0xD7A3

CHOSUNG = "ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ"
JUNGSUNG = "ㅏㅐㅑㅒㅓㅔㅕㅖㅗㅘㅙㅚㅛㅜㅝㅞㅟㅠㅡㅢㅣ"
JONGSUNG = " ㄱㄲㄳㄴㄵㄶㄷㄹㄺㄻㄼㄽㄾㄿㅀㅁㅂㅄㅅㅆㅇㅈㅊㅋㅌㅍㅎ"


def decompose(text: str) -> str:
    """문자열을 자모 시퀀스로 편다. 한글이 아닌 문자는 그대로 둔다."""
    out = []
    for ch in text:
        code = ord(ch)
        if _BASE <= code <= _LAST:
            idx = code - _BASE
            out.append(CHOSUNG[idx // 588])
            out.append(JUNGSUNG[(idx % 588) // 28])
            jong = JONGSUNG[idx % 28]
            if jong != " ":
                out.append(jong)
        else:
            out.append(ch)
    return "".join(out)


def edit_distance(a: str, b: str) -> int:
    """레벤슈타인 거리 (삽입/삭제/치환 각 1)."""
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)

    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(
                prev[j] + 1,        # 삭제
                cur[j - 1] + 1,     # 삽입
                prev[j - 1] + (ca != cb),  # 치환
            ))
        prev = cur
    return prev[-1]


def jamo_distance(a: str, b: str) -> int:
    """자모로 편 뒤의 편집거리."""
    return edit_distance(decompose(a), decompose(b))


def allowed_distance(keyword: str, cap: int = 2) -> int:
    """키워드 길이에 맞춰 허용 편집거리를 깎는다.

    `FR-B-302`는 상한을 2로 두지만, **짧은 키워드에 2를 그대로 허용하면 오매칭이 폭증한다.**
    실측 예 — "안내"(자모 5개)에 거리 2를 허용하면 "**안전**교육"이 매칭되고,
    "나가"(자모 4개)에는 "**왔어**요"가 매칭됐다. 자모 5개 중 2개가 틀려도 통과시키는 셈이라
    사실상 다른 단어까지 다 걸린다.

    자모 3개당 1의 오차를 허용하고 상한을 씌운다:
      "안내"(5)  → 1   "입고"(5) → 1  (→ "입구"는 거리 1이라 여전히 보정됨)
      "안전교육장"(11) → 2
    """
    return max(1, min(cap, len(decompose(keyword)) // 3))


def find_fuzzy(text: str, keyword: str, max_dist: int = 2):
    """`text` 안에서 `keyword`와 자모 편집거리 이하인 부분문자열을 찾는다.

    반환: (거리, 매칭된 부분문자열) — 못 찾으면 None.
    실제 허용 거리는 `allowed_distance()`로 키워드 길이에 맞춰 줄여서 쓴다.

    키워드 길이 ±1 범위의 창만 훑는다. 그보다 길이 차가 크면 어차피 편집거리가
    허용치를 넘기 때문에 계산할 필요가 없다.
    """
    if keyword in text:
        return (0, keyword)

    max_dist = allowed_distance(keyword, max_dist)
    klen = len(keyword)
    best = None
    for win in (klen - 1, klen, klen + 1):
        if win <= 0 or win > len(text):
            continue
        for i in range(len(text) - win + 1):
            sub = text[i:i + win]
            d = jamo_distance(sub, keyword)
            if d <= max_dist and (best is None or d < best[0]):
                best = (d, sub)
                if d == 1:   # 더 좋아질 여지가 거의 없다
                    return best
    return best
