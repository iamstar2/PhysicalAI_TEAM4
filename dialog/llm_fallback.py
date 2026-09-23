# -*- coding: utf-8 -*-
"""LLM 폴백 — 로컬 룰 매칭이 실패했을 때, **목적지 분류만** 시킨다.

v2 (2026-09-17) — 역할을 "작은 챗봇"에서 "8지선다 분류기"로 좁혔다
--------------------------------------------------------------
이전 버전은 LLM 이 방문자에게 들려줄 **문장까지 직접 생성**했다(날씨 질문에도 답하는 식).
그런데 그러면 위험이 두 가지 생긴다 — ① 환각(화장실 위치·날씨를 지어냄, 실측 확인) ②
"어디까지 답하게 둘지"를 팀이 넓게 합의해야 함.

이번 버전은 **LLM 이 문장을 만들지 않는다.** 딱 하나만 시킨다 —
"이 발화가 8곳 중 어디로 가려는 건지, 아니면 목적지 얘기가 아닌지" 분류.
목적지를 찾으면 **이미 캐시해 둔 고정 멘트**(`tts_cache/confirm_<dest>.wav`)를 그대로 쓴다.
LLM 이 말을 지어낼 방법 자체가 없으니 환각이 구조적으로 불가능하다.

여기서 처리하는 것 한 가지만:
  룰이 놓친 목적지 표현 인식 ("짐 내리러 왔어요" → inbound_dock, "글리 베이터" → elevator_hall)

**날씨·잡담 등 목적지 밖 질문은 이 모듈의 범위가 아니다.** 그건 별도 FR·별도 설계가 필요하고,
지금은 목적지 8종 인식 정확도를 올리는 용도로만 쓴다 — 룰 매칭의 연장선이지 새 기능이 아니다.

안전장치:
  - 타임아웃을 걸고, 넘으면 포기 → 호출 측이 기존 고정 멘트(재질문)로 폴백
  - 목적지는 8종 enum 밖의 값을 절대 반환하지 않는다(코드에서 재검증)
  - **답변 문장을 LLM 이 만들지 않는다** — 전부 사전 캐시된 고정 멘트 사용
  - 실패(키 없음·네트워크·파싱)는 전부 `None` 으로 수렴

API 키는 환경변수 `GEMINI_API_KEY` 로 읽는다. **코드나 저장소에 넣지 말 것.**
"""

from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from destinations import DESTINATIONS

API_KEY_ENV = "GEMINI_API_KEY"
MODEL = os.environ.get("GEMINI_MODEL", "gemini-flash-lite-latest")
# 실측 분포가 대략 0.9~1.2초. 분류만 하므로 문장 생성하던 v1보다 약간 더 빠르다(출력 토큰 적음).
TIMEOUT_S = float(os.environ.get("LLM_TIMEOUT_S", "6.0"))

_ENDPOINT = ("https://generativelanguage.googleapis.com/v1beta/models/"
             "{model}:generateContent")

# 예전에는 **확인 멘트 문장에서 장소 이름을 잘라** 썼다("...로 안내" 앞부분).
# 멘트 문구를 다듬으면 조용히 깨지는 방식이라, 이제 `name` 을 그대로 쓴다.
_DEST_LIST = "\n".join(
    f"- {key}: {spec['name']}" for key, spec in DESTINATIONS.items()
)


def _info_list() -> tuple[str, set[str]]:
    """**말로만 알려주는 곳**(화장실·계단 …)을 프롬프트에 넣을 문자열로 만든다.

    데려다주지 않으므로 목적지 8종과 분리돼 있다(`info_places.py`).
    **문구가 비어 있는 곳은 뺀다** — 분류해 봐야 들려줄 음성이 없다.

    왜 LLM 에도 알려주나: 키워드로는 "화장실" 밖에 못 잡는데 사람은
    "똥 마려운데 어디로 가요", "손 좀 씻고 싶은데요" 처럼 말한다.
    키워드를 계속 늘리면 오탐이 늘어난다(`LOG-40`) — 의미 판단은 LLM 에 맡기는 게 맞다.
    """
    import info_places

    keys = info_places.ready()
    if not keys:
        return "", set()
    label = {"restroom": "화장실", "stairs": "계단",
             "smoking_area": "흡연 구역", "vending": "자판기·정수기"}
    lines = "\n".join(f"- {k}: {label.get(k, k)}" for k in keys)
    return ("\n[말로만 알려주는 곳 — 데려다주지는 않고 위치만 알려준다]\n"
            + lines + "\n"), set(keys)


_INFO_TEXT, _INFO_KEYS = _info_list()


def _load_schedule() -> tuple[str, dict]:
    """일정표를 프롬프트 문자열과 {키: 항목} 으로 만든다.

    **왜 넣나**: 방문자는 목적지를 직접 말하지 않는다 — "2시에 오라고 해서 왔는데요",
    "김 과장님 만나러 왔어요" 처럼 말한다. 일정표를 주면 **근거를 갖고** 판단할 수 있다.
    지어내는 게 아니라 우리가 준 데이터를 읽는 것이라 환각이 아니다.

    **날짜를 검사하지 않는다** (2026-09-18 변경). 예전에는 파일 날짜가 오늘이 아니면
    일정을 통째로 버렸는데, 그러면 **시연 당일 파일을 안 고쳤다가 기능이 죽는다.**
    시연은 아무 날에나 돌아가야 한다. 실제 운영에서는 C(DB)가 그날 일정을 넣어 준다.
    """
    path = Path(os.environ.get("SCHEDULE_FILE",
                               Path(__file__).parent / "schedule.json"))
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return "", {}

    items = data.get("items") or []
    if not items:
        return "", {}
    by_key = {i["키"]: i for i in items if i.get("키")}
    lines = "\n".join(
        f"- {i.get('키')} / {i.get('time', '?')} / {i.get('place', '?')} / "
        f"{i.get('title', '')} / 담당 {i.get('host', '')}"
        for i in items
    )
    return (f"\n[오늘 방문 일정 — 현재 시각 {datetime.now().strftime('%H:%M')}]\n"
            f"{lines}\n"), by_key


_SCHEDULE, _SCHED_ITEMS = _load_schedule()

_SYSTEM = f"""너는 물류센터 정문 안내 로봇의 **목적지 분류기**다. 문장을 만들지 않는다 —
음성인식(STT)으로 옮긴 방문자 발화를 보고, 아래 8곳 중 어디로 가려는 건지만 고른다.

[목적지 8종]
{_DEST_LIST}
{_INFO_TEXT}{_SCHEDULE}
STT 오인식이 섞여 있을 수 있다. **발음이 비슷하면 원래 말을 복원해서 판단해라.**
실제로 이렇게 들어온다:
  "글리 베이터" → 엘리베이터        "집내리로 왔어요" → 짐 내리러 왔어요(입고)
  "짐 시리로 왔습니다" → 짐 실으러 왔습니다(출고)   "고사로 왔습니다" → 검수하러 왔습니다
  "김거장님" → 김 과장님
**짐을 내리면 입고, 짐을 실으면 출고다.**

규칙:
- 8곳 중 하나로 가려는 것이면 그 key 를 destination 에 넣는다.
- **일정표가 주어졌다면 그것을 근거로 추론해도 된다.** 방문자가 목적지를 직접 말하지 않아도
  ("담당자 만나러 왔다", "2시에 오라고 해서 왔다", "○○님 뵈러 왔다") 일정과 맞아떨어지면
  그 장소로 판단하고, **그때는 `schedule` 에 그 일정의 키(s1·s2 …)를 넣어라.**
  시각은 대략만 맞아도 된다("2시" ↔ 14:30). **단, 일정표에 없는 내용을 지어내지 마라.**
  **목적지를 직접 말했으면 `schedule` 은 null 이다.** "회의실 어디예요" 처럼 장소를 그대로
  말한 사람에게 일정 멘트("두 시 반에 미팅이 있으시네요")를 들려주면, 묻지도 않은 일정을
  꺼내는 셈이라 엉뚱하게 들린다. `schedule` 은 **시각·담당자·용건으로 추론했을 때만** 넣는다.
- **"○○이 어디예요?" 는 그곳으로 가려는 것이다.** 위 8곳 중 하나를 묻는 것이면 그 key 를 넣어라.
  방문자가 "안내해 달라" 고 말해야만 목적지인 것이 아니다 — 위치를 묻는 것이 곧 안내 요청이다.
- **말하다 스스로 고친 경우, 고친 뒤의 것이 진짜다.**
  "입고 도크 어디예요? 아 아니다 출고 도크요" → outbound_dock.
  단 **부정된 쪽을 고르지 마라** — "입고 도크요, 출고 아니고" 는 inbound_dock 이다.
- **8곳 밖의 장소가 같이 언급돼도, 8곳 중 하나로 가겠다는 말이 있으면 그 key 를 골라라.**
  "출고로 갈게요. 그전에 화장실 가고싶은데 어디에요?" → outbound_dock.
  (화장실은 우리가 안내 못 하지만, 이 사람의 목적지는 출고 도크가 맞다.)
- 두 곳 이상을 순서대로 말하면 **먼저 갈 곳**을 골라라.
  "검수장 갔다가 출고 도크 갈게요" → inspection_area.
- **말로만 알려주는 곳**을 물으면 `info_place` 에 그 key 를 넣는다.
  **돌려서 말해도 알아들어라** — "똥 마려운데 어디로 가요", "손 좀 씻고 싶은데요" → restroom.
  이건 destination 과 **따로** 다. 둘 다 해당하면 둘 다 채운다
  ("출고로 갈게요. 그전에 화장실 어디에요?" → destination=outbound_dock, info_place=restroom).
- 어느 목록에도 없으면 둘 다 null 로 둔다. **모르면 null — 추측해서 아무 key 나 넣지 마라.**
- reply 나 설명 문장은 만들지 않는다. 이유(reason)는 5단어 이내로 간단히만 적는다
  (디버깅용, 방문자에게 들려주지 않는다).

출력 형식: 아래 JSON 만 출력한다. 다른 텍스트를 붙이지 마라.
{{"destination": "<목적지 key 또는 null>", "info_place": "<위 key 또는 null>", "schedule": "<일정 키 또는 null>", "reason": "<5단어 이내>"}}"""


@dataclass
class LlmResult:
    destination: str | None   # 8종 중 하나, 또는 None(목적지 아님/모름)
    reason: str = ""          # 디버깅용 — 방문자에게 들려주지 않는다
    info_place: str | None = None   # 말로만 알려주는 곳(화장실 …), 또는 None
    schedule: str | None = None     # 어느 일정으로 풀었나(s1 …). 전용 멘트를 고를 때 쓴다


def available() -> bool:
    return bool(os.environ.get(API_KEY_ENV))


def _extract_json(text: str) -> dict | None:
    """모델이 JSON 앞뒤에 뭔가 붙여도 건져낸다."""
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return None


def ask(utterance: str) -> LlmResult | None:
    """룰 매칭 실패 발화를 LLM 에 넘겨 **목적지만** 분류받는다.

    성공해도 destination 이 None 일 수 있다(목적지 얘기가 아니었다는 뜻) —
    호출 측은 이 경우도 기존 재질문/미지원 멘트로 처리하면 된다.
    실패(키 없음·타임아웃·파싱 오류)는 전부 None 을 반환해 호출 측이 구분 없이 폴백하게 한다.
    """
    key = os.environ.get(API_KEY_ENV)
    if not key or not utterance.strip():
        return None

    body = {
        "systemInstruction": {"parts": [{"text": _SYSTEM}]},
        "contents": [{"role": "user", "parts": [{"text": f"방문자 발화: {utterance}"}]}],
        "generationConfig": {"temperature": 0.1, "maxOutputTokens": 80},
    }

    req = urllib.request.Request(
        _ENDPOINT.format(model=MODEL),
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json", "x-goog-api-key": key},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        cand = payload["candidates"][0]
        text = "".join(p.get("text", "") for p in cand["content"]["parts"])
    except (urllib.error.URLError, TimeoutError, KeyError, IndexError,
            json.JSONDecodeError, OSError):
        return None

    parsed = _extract_json(text)
    if parsed is None:
        return None

    dest = parsed.get("destination")
    if dest not in DESTINATIONS:      # 스키마를 안 걸었으므로 여기서 꼭 막는다
        dest = None

    info = parsed.get("info_place")
    if info not in _INFO_KEYS:        # 모델이 만들어 낸 key 를 그대로 믿지 않는다
        info = None

    sched = parsed.get("schedule")
    if sched not in _SCHED_ITEMS:     # 없는 키를 만들어 내지 못하게 막는다
        sched = None

    reason = " ".join(str(parsed.get("reason") or "").split())[:50]
    return LlmResult(dest, reason, info, sched)


# ===========================================================================
# 확인 응답 분류 — "네/아니요" 를 낱말 목록으로 덮을 수 없어서 붙였다.
# ===========================================================================
_REPLY_SYSTEM = """너는 안내 로봇의 **확인 응답 분류기**다. 문장을 만들지 않는다.

로봇이 방문자에게 "{question}" 이라고 물었고, 방문자가 답했다.
그 답이 **긍정인지 부정인지**만 고른다.

규칙:
- 맞다는 뜻이면 yes. "네"·"맞아요"·"그렇죠"·"응"·"어" 뿐 아니라
  **되묻는 말투로 수긍하는 것도 yes** 다 — "아 거기요?"·"맞지 않나요?"·"거기 어디예요?"
  (위치를 묻는 건 **가겠다는 뜻**이다. 로봇이 곧 위치를 알려준다)
- 아니라는 뜻이면 no. "아니요"·"아뇨"·"거기 말고"·"틀렸어요"
- 안내가 필요 없다는 뜻("괜찮아요"·"혼자 갈게요"·"됐어요")도 **no** 로 둔다.
- **다른 곳을 말하면 null 이다** — "회의실인데요"·"아뇨 검수장이요" 처럼
  틀렸다는 신호와 **올바른 목적지를 함께** 말한 경우다. no 로 두면 안 된다:
  호출 측이 그 말을 **새 발화로 다시 해석**해서 바로 그 목적지로 가야 하는데,
  no 면 "어디로 가시나요" 를 다시 묻게 되어 방문자가 방금 한 말을 또 해야 한다.
- 도무지 모르겠을 때도 null.

출력 형식: 아래 JSON 만. 다른 텍스트를 붙이지 마라.
{{"reply": "yes" | "no" | null}}"""


def confirm_reply(text: str, question: str) -> str | None:
    """확인 질의의 답을 `yes` / `no` 로 분류한다. 모르면 `None`.

    **룰이 판정하지 못했을 때만 부른다.** "네" 한 마디는 0ms 로 끝나는데
    1초를 쓸 이유가 없다 — 목적지 매칭에 쓰는 것과 같은 방식이다.

    긍정 표현은 낱말 목록으로 덮이지 않는다. "맞지 않나요?"·"거기 어디예요?" 처럼
    **되묻는 말투로 수긍하는 경우**가 흔하고, 목록에 넣으려면 끝이 없다.
    실제로 짧은 낱말 목록으로 판정하다가 **아무 말에나 긍정 도장을 찍은 적이 있다**(`LOG-48`).
    """
    key = os.environ.get(API_KEY_ENV)
    if not key or not text.strip():
        return None

    body = {
        "systemInstruction": {"parts": [{"text": _REPLY_SYSTEM.format(question=question)}]},
        "contents": [{"role": "user", "parts": [{"text": f"방문자 답: {text}"}]}],
        "generationConfig": {"temperature": 0.0, "maxOutputTokens": 30},
    }
    req = urllib.request.Request(
        _ENDPOINT.format(model=MODEL),
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json", "x-goog-api-key": key},
        method="POST")
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        raw = "".join(p.get("text", "")
                      for p in payload["candidates"][0]["content"]["parts"])
    except (urllib.error.URLError, TimeoutError, KeyError, IndexError,
            json.JSONDecodeError, OSError):
        return None

    parsed = _extract_json(raw) or {}
    v = parsed.get("reply")
    return v if v in ("yes", "no") else None
