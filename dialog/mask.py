# -*- coding: utf-8 -*-
"""개인정보 마스킹 (`NFR-B-702`).

**저장·발행 직전에만 부른다.** 매칭·LLM 분류는 원문으로 해야 한다 —
"김 과장님 만나러 왔어요" 에서 이름을 미리 지우면 `FR-B-405`(담당자명 추정)가
아무것도 못 찾는다. 즉 순서는 **판단 → 마스킹 → 저장/발행** 이다.

왜 필요한가
-----------
`11` 데이터정의서 §1.3 이 `purpose`·`stt_raw` 를 **마스킹 후 저장**으로 규정한다.
음성을 아예 저장하지 않기로 했으므로(`FR-B-205` W 강등) **텍스트가 유일한 기록**이고,
그래서 마스킹이 유일한 보호 수단이다.

무엇을 가리나 — 순서가 곧 중요도다
-----------------------------------
**① 이름·호칭이 주 대상이다.** `FR-B-405` 가 담당자명을 **정상 입력으로 받게**
설계돼 있어서 실제로 들어온다.

**② 전화번호는 보조다.** B 는 번호를 물어본 적이 없고 방문자가 자발적으로 말할 일도
드물다. 정규식 한 줄이라 넣어 두는 것이지 주 위험이 아니다.
(`03` v1.5 에서 순서를 이렇게 정정했다 — 예전 표기는 번호가 먼저였는데,
그건 우리 대화 흐름에서 나온 게 아니라 일반적인 개인정보 목록에서 온 것이었다.)
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

# 010-1234-5678 · 01012345678 · 010.1234.5678 을 모두 잡는다.
_PHONE = re.compile(r"01[016789][-.\s]?\d{3,4}[-.\s]?\d{4}")

# 직함 앞에 붙은 이름만 지우고 **직함은 남긴다** — "OO 과장님" 이 "OO님" 보다
# 로그를 읽을 때 상황이 드러난다. 성만 부르는 경우가 흔해 1~3자를 받는다.
_TITLES = "과장|부장|차장|대리|팀장|이사|사장|주임|반장|소장|점장"
_NAME_TITLE = re.compile(rf"[가-힣]{{1,3}}\s*(?={_TITLES})")

MASK = "OO"


def _schedule_hosts() -> list[str]:
    """일정표에 적힌 담당자 이름.

    직함 없이 이름만 말하는 경우("김철수 씨 만나러 왔는데요")는 패턴으로 잡을 수 없다.
    대신 **우리가 이미 알고 있는 이름**(오늘 일정의 `host`)은 정확히 지울 수 있다.
    모르는 이름을 못 지우는 건 한계로 남지만, 아는 이름을 남겨 둘 이유는 없다.
    """
    path = Path(os.environ.get("SCHEDULE_FILE",
                               Path(__file__).parent / "schedule.json"))
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    out = []
    for item in data.get("items") or []:
        host = (item.get("host") or "").strip()
        # 2자 미만은 지우면 오히려 엉뚱한 글자가 날아간다.
        if len(host) >= 2:
            out.append(host)
    # 긴 이름부터 지워야 "김철수" 가 "김철" 로 반쪽 치환되지 않는다.
    return sorted(set(out), key=len, reverse=True)


def mask(text: str | None) -> str | None:
    """마스킹한 문자열. `None` 은 그대로 `None`."""
    if not text:
        return text
    out = _PHONE.sub("010-****-****", text)
    out = _NAME_TITLE.sub(MASK, out)
    for host in _schedule_hosts():
        out = out.replace(host, MASK)
    return out


if __name__ == "__main__":       # 수동 점검: python3 mask.py
    for s in ["김 과장님 만나러 왔어요",
              "연락처가 010-1234-5678 이에요",
              "박부장 뵈러 왔습니다",
              "입고 도크 가려고요"]:
        print(f"{s!r:40} -> {mask(s)!r}")
