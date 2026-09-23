# -*- coding: utf-8 -*-
"""도메인 보정 + 목적지 슬롯 추출 + 신뢰도 산정.

구현 근거
  - `FR-B-302`  도메인 보정 (자모 편집거리 ≤ 2)
  - `FR-B-401`  목적지 슬롯 추출 (주/보조 키워드)
  - `FR-B-402`  신뢰도 산정 — `05_B_AI_Flow.md` §5.1 산식
  - `BR-B-04`   후보 2개 이상이면 신뢰도와 무관하게 선택형 재질문
"""

from __future__ import annotations

from dataclasses import dataclass, field

from destinations import DESTINATIONS
from hangul import find_fuzzy

MAX_JAMO_DIST = 2          # FR-B-302 AC-2

# S_match 등급 — 05 §5.1 표 그대로
S_PRIMARY_EXACT = 1.00
S_PRIMARY_DIST1 = 0.80
S_SECONDARY = 0.60
S_CORRECTED = 0.50         # 주 키워드 거리2, 또는 보조 키워드 오타 보정

# 행동 결정 임계 — 05 §5.2
TH_CONFIRM = 0.75
TH_FLOOR = 0.45


@dataclass
class Candidate:
    dest: str
    s_match: float
    matched: str           # 발화에서 실제로 매칭된 조각
    keyword: str           # 사전의 어느 키워드에 걸렸는지
    dist: int              # 자모 편집거리 (0 = 정확)


@dataclass
class MatchResult:
    text: str
    candidates: list[Candidate] = field(default_factory=list)
    confidence: float = 0.0
    p_stt: float = 0.0
    margin: float = 0.0
    action: str = "reprompt"     # confirm | strong_confirm | disambiguate | reprompt
    dest: str | None = None      # 단일 후보일 때만 채워진다
    note: str = ""               # 보정 규칙이 개입했으면 사유


def _score_destination(text: str, dest: str, spec: dict) -> Candidate | None:
    """한 목적지에 대해 가장 좋은 매칭 하나를 고른다."""
    best: Candidate | None = None

    def better(c: Candidate) -> bool:
        return best is None or c.s_match > best.s_match

    for kw in spec["primary"]:
        hit = find_fuzzy(text, kw, MAX_JAMO_DIST)
        if hit is None:
            continue
        dist, sub = hit
        score = {0: S_PRIMARY_EXACT, 1: S_PRIMARY_DIST1}.get(dist, S_CORRECTED)
        c = Candidate(dest, score, sub, kw, dist)
        if better(c):
            best = c

    for kw in spec["secondary"]:
        hit = find_fuzzy(text, kw, MAX_JAMO_DIST)
        if hit is None:
            continue
        dist, sub = hit
        score = S_SECONDARY if dist == 0 else S_CORRECTED
        c = Candidate(dest, score, sub, kw, dist)
        if better(c):
            best = c

    return best


def _apply_dock_rule(text: str, cands: list[Candidate]) -> tuple[list[Candidate], str]:
    """"출고" ↔ "출구" 오인식 보정 (`09_작업기록 LOG-27`).

    실측에서 "출고 도크로 가려고요" 가 "**출구**, 도크로 가려고요" 로 인식됐다.
    `출구`(exit_gate)와 `출고`(outbound_dock)는 정반대 방향의 목적지라, 이대로 두면
    방문자를 반대로 안내하게 된다. STT 단계에서는 이 음운 쌍을 못 가르므로 여기서 막는다.

    규칙: 발화에 `"도크"` 가 함께 있으면 `exit_gate` 후보를 버린다.
      - 실존 지명은 "출고 도크"·"입고 도크" 뿐이고 "출구 도크" 라는 곳은 없다.
      - 진짜로 출구로 가려는 사람이 "도크" 를 같이 말할 이유도 없다.
    """
    if "도크" not in text:
        return cands, ""
    kept = [c for c in cands if c.dest != "exit_gate"]
    if len(kept) == len(cands):
        return cands, ""
    return kept, "'도크' 동반 → exit_gate 억제 (출고/출구 오인식 방어, LOG-27)"


# 위아래로 움직이는 표현. `나가` 와 자모 한 글자 차이라 exit_gate 로 새어 들어간다.
VERTICAL = ["올라가", "올라갈", "내려가", "내려갈", "위층", "2층", "이층"]


def _apply_vertical_rule(text: str, cands: list[Candidate]) -> tuple[list[Candidate], str]:
    """`올라가` 가 `나가` 로 읽혀 출구로 가는 것을 막는다.

    실측: *"위에 올라가려고요"* 가 **전사는 완벽한데** `exit_gate` 로 확정됐다.
    `올라**가**` 의 `라가` 와 `나가` 는 **자모 거리 1**(`ㄹ`↔`ㄴ`)이라 0.80 으로 붙는다.
    2층에 가려는 사람을 **정반대인 정문으로 내보내는** 셈이다.

    `나가` 를 빼거나 2글자 키워드를 전부 정확매칭으로 바꾸는 방법도 있는데,
    그러면 `입고`→`잊고` 같은 **정상적인 오타 보정까지 죽는다.**
    그래서 위아래 표현이 있을 때만 exit_gate 를 억제한다 — `_apply_dock_rule` 과 같은 방식이다.
    """
    if not any(k in text for k in VERTICAL):
        return cands, ""
    kept = [c for c in cands if c.dest != "exit_gate"]
    if len(kept) == len(cands):
        return cands, ""
    # **비워도 된다.** exit_gate 가 유일한 후보였다면 그건 `올라가` 를 `나가` 로 잘못 읽은
    # 것이므로, 후보 0개로 만들어 LLM 폴백에 넘기는 편이 낫다 —
    # 정반대 방향으로 확정하느니 한 번 더 판단하는 게 맞다.
    return kept, "위아래 표현 동반 → exit_gate 억제 ('올라가'↔'나가' 방어)"


def match(text: str, p_stt: float) -> MatchResult:
    """인식 텍스트 → 목적지 후보 + 신뢰도 + 행동."""
    res = MatchResult(text=text, p_stt=p_stt)

    cands = [c for c in (
        _score_destination(text, d, spec) for d, spec in DESTINATIONS.items()
    ) if c is not None]

    cands, note = _apply_dock_rule(text, cands)
    cands, note2 = _apply_vertical_rule(text, cands)
    res.note = " / ".join(x for x in (note, note2) if x)

    cands.sort(key=lambda c: c.s_match, reverse=True)
    res.candidates = cands

    if not cands:
        res.confidence = 0.30 * p_stt        # S_match=0, Margin 없음
        res.action = "reprompt"
        return res

    # Margin — 1·2위 점수 격차 (05 §5.1)
    if len(cands) == 1:
        margin = 1.00
    else:
        gap = cands[0].s_match - cands[1].s_match
        margin = 1.00 if gap >= 0.4 else (0.70 if gap >= 0.2 else 0.50)
    res.margin = margin

    res.confidence = 0.30 * p_stt + 0.50 * cands[0].s_match + 0.20 * margin

    # BR-B-04 우선: 후보가 2개 이상이면 신뢰도와 무관하게 선택형 재질문.
    #
    # "모호하다"의 기준은 **격차 < 0.2** 로 둔다 — 05 §5.1 Margin 표가 0.2~0.4 를
    # 별도 구간(0.70)으로 구분해 두었으므로, 그 구간은 "모호"가 아니라 "덜 확실"로 보고
    # 확인 강도를 낮추는 쪽(strong_confirm)으로 흘려보내는 게 문서 의도에 맞다.
    #
    # 실제 사례: "출고 도크로 가려고요" → STT "출구, 도크로..." 일 때
    #   outbound(0.80, '출구'→'출고' 보정) vs inbound(0.60, '도크')
    # 주 키워드 보정 매칭이 범용 보조 키워드보다 확실히 강한 증거인데, 이걸 모호로
    # 처리하면 방문자에게 불필요한 선택 질문을 한 턴 더 하게 된다.
    # `round` 를 쓰는 이유: 1.00 - 0.80 이 이진 부동소수점에서 **0.19999999999999996** 이라
    # "0.2 이상이면 모호가 아니다" 라는 규칙이 경계에서 정반대로 동작한다.
    # 실제로 주 키워드 정확(1.00) vs 거리1 보정(0.80) 조합이 전부 모호로 빠지고 있었다.
    if len(cands) >= 2 and round(cands[0].s_match - cands[1].s_match, 6) < 0.2:
        res.action = "disambiguate"
        return res

    res.dest = cands[0].dest
    if res.confidence >= TH_CONFIRM:
        res.action = "confirm"
    elif res.confidence >= TH_FLOOR:
        res.action = "strong_confirm"
    else:
        res.action = "reprompt"
        res.dest = None          # 확정 시도 자체를 안 한다 (BR-B-10)
    return res
