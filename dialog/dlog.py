# -*- coding: utf-8 -*-
"""대화 로그 (`FR-B-802`) — JSON Lines 로 남긴다.

왜 파일인가 — 협의를 기다리지 않으려고
---------------------------------------
`11_공유용_B_데이터항목.md` 가 `dialog_sessions`·`dialog_turns` 두 테이블을
**팀에 공유된 정의로** 확정해 뒀다. 그런데 **누가 INSERT 하는지**는 정해진 적이 없다
(B 가 직접 넣나, 여도훈 수집기가 넣나). 그건 나중에 정해도 되는 문제인데,
그걸 기다리는 동안 **로그가 하나도 안 쌓이는 게 진짜 손해**다 —
`NFR-B-101`(p50/p95)·`NFR-B-403`(세션 누수)·`NFR-B-502`(턴 수)가 전부
이 로그를 측정 방법으로 지정하고 있어서, 없으면 **측정 자체가 불가능**하다.

그래서 **파일로 먼저 쌓는다.** 대신 협의가 필요 없도록 요령을 하나 썼다 —

    **필드 이름을 DB 컬럼명과 글자 그대로 맞춘다.**

`stt_raw`·`candidates`·`presence`·`decision`·`touch_wait_ms`·`stt_ms`·`tts_ms`·
`total_ms` … 전부 공유된 정의서의 컬럼명 그대로다. 그래서 나중에 누가 옮기든
**매핑을 물어볼 게 없다.** `tools/dialog_log_to_sql.py` 가 이 파일을 그대로
`INSERT` 문으로 바꿔 준다.

지키는 것
---------
**대화를 절대 멈추지 않는다.** 로그는 부수적인 일이라 디스크가 차든 권한이 없든
대화가 죽으면 안 된다. 모든 쓰기를 통째로 감싸고, 실패하면 한 번만 알리고 조용해진다.

**마스킹하고 쓴다** (`NFR-B-702`). 음성을 저장하지 않으므로 이 텍스트가 유일한
기록이고, 그래서 여기가 마지막 방어선이다.

`prompt_id` 에 대하여
---------------------
공유 정의서의 주석은 `M-01 ~ M-14` 로 적혀 있지만, **실제로 재생한 멘트 키**
(`confirm_inbound_dock`, `where_exit_gate` …)를 넣는다. M 번호 표는
`FR-B-706`·`707`·`708` 멘트가 생기기 전에 만든 것이라 **지금 멘트의 절반을 못 가리킨다.**
아래 `M_MAP` 이 옛 번호와의 대응을 남겨 두므로 필요하면 그때 바꿔 읽으면 된다.
"""
from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

from mask import mask

LOG_DIR = Path(os.environ.get("DIALOG_LOG_DIR", Path.home() / "dialog_logs"))

# 옛 M 번호 ↔ 멘트 키 (`08_B_QA_재질문_시나리오` §1.1~1.2).
# 확인 질의 M-07~M-14 는 `confirm_<목적지>` 로 규칙이 잡혀 굳이 나열하지 않는다.
M_MAP = {"greet": "M-01", "reprompt": "M-02", "reprompt_2": "M-03",
         "nudge": "M-04", "escalate": "M-05"}

_pending: dict = {}
_turn_no = 0
_session_id: str | None = None
_visitor_id: str | None = None
_started_at: str | None = None
_t_session = 0.0
_warned = False


def _write(rec: dict) -> None:
    """한 줄 추가. **실패해도 대화는 계속된다.**"""
    global _warned
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        path = LOG_DIR / f"{datetime.now().strftime('%Y%m%d')}.jsonl"
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except OSError as e:
        if not _warned:                 # 매 턴 찍으면 콘솔이 묻힌다
            _warned = True
            print(f"[로그] 기록 실패 — 대화는 계속한다: {e}")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def stage(**cols) -> None:
    """이번 턴에 알게 된 값을 모아 둔다. 턴이 끝날 때 한 줄로 나간다.

    여기저기서 조금씩 알게 되는 값들이라(녹음 길이는 `listen`, 재생 시간은 `say`,
    판단 결과는 `_after_touch`) 한 군데서 다 모아 쓰는 게 불가능하다.
    """
    _pending.update(cols)


def next_utterance() -> None:
    """방문자가 **새로 말하기 시작한다** — 앞 발화를 한 줄로 닫는다.

    공유 정의서의 `dialog_turns` 는 **\"방문자가 한 번 말할 때마다 1행\"** 이다. 그런데 B 의 한 턴 안에는
    말이 여러 번 오간다(목적지 → 확인 \"네\" → 직접 안내 \"네\"). 예전에는 턴 끝에서 한 줄만 써서
    **값이 서로 덮어써졌다** — 촬영 로그에서 발화 텍스트는 첫 문장인데 응답 시간은 마지막 \"네\" 것이
    찍혀 있었다(`LOG-80`). 그래서 **듣기를 시작할 때마다** 앞 발화를 닫는다.

    터치 대기·초음파 값만 있고 아직 말이 없으면 닫지 않는다 — 그 값은 곧 들어올 발화의 것이다.
    """
    if "stt_ms" in _pending or "stt_raw" in _pending:
        turn()


def open_session(session_id: str, visitor_id: str | None = None) -> None:
    global _turn_no, _session_id, _t_session, _started_at, _visitor_id
    _pending.clear()
    _turn_no = 0
    _session_id = session_id
    _visitor_id = visitor_id
    _t_session = time.time()
    # `dialog_sessions.started_at` 은 **NOT NULL** 이다 — 여기서 안 잡으면
    # 나중에 INSERT 가 통째로 거부된다.
    _started_at = _now()


def turn() -> None:
    """한 턴을 기록한다 (`dialog_turns` 1행).

    모아 둔 값이 없으면 **쓰지 않는다** — 터치를 기다리기만 하고 아무 일도
    없었던 순환까지 남기면 턴 수(`NFR-B-502`)가 부풀어 오른다.
    """
    global _turn_no
    if not _pending or _session_id is None:
        _pending.clear()
        return
    _turn_no += 1
    rec = {
        "rec": "turn",
        "session_id": _session_id,
        "turn_no": _turn_no,
        "ts": _now(),
        "stt_raw": mask(_pending.get("stt_raw")),
        "stt_corrected": mask(_pending.get("stt_corrected")),
        "candidates": _pending.get("candidates"),
        "confidence": _pending.get("confidence"),
        "presence": _pending.get("presence", "not_checked"),
        "decision": _pending.get("decision"),
        "prompt_id": _pending.get("prompt_id"),
        "touch_wait_ms": _pending.get("touch_wait_ms"),
        "stt_ms": _pending.get("stt_ms"),
        "tts_ms": _pending.get("tts_ms"),
        # `NFR-B-101` 이 재는 구간 — **발화 종료부터 응답 재생 개시까지**.
        # 녹음 시간과 재생 길이는 빼야 한다(그건 방문자가 말한 시간·로봇이 말한 시간이지
        # 기다린 시간이 아니다). `stt_ms` + 매칭·LLM 이 여기 들어간다.
        "total_ms": _pending.get("total_ms"),
    }
    _pending.clear()
    _write(rec)


def close_session(outcome: str, destination: str | None = None,
                  purpose: str | None = None, confidence: float | None = None,
                  retry_count: int = 0,
                  escalation_reason: str | None = None) -> None:
    """세션 1건을 기록한다 (`dialog_sessions` 1행).

    `outcome` 은 공유 정의서의 enum 을 그대로 쓴다 —
    `confirmed · escalated · abandoned_silent · abandoned_no_touch ·
    abandoned_timeout · rejected`.
    **`rejected` 는 여기서 안 나온다** — 미인가·PPE 불합격은 세션을 아예 열지 않아
    `Session` 객체가 만들어지지 않기 때문이다(`FR-B-102`).
    """
    if _session_id is None:
        return
    turn()                              # 남은 턴이 있으면 먼저 흘려보낸다
    _write({
        "rec": "session",
        "session_id": _session_id,
        "visitor_id": _visitor_id,
        "started_at": _started_at,
        "ended_at": _now(),
        # 아래 둘은 DB 컬럼이 아니라 **사람이 읽을 때 쓰는 값**이다.
        # 변환 스크립트가 컬럼 목록으로만 고르므로 섞여 있어도 무해하다.
        "duration_ms": int((time.time() - _t_session) * 1000),
        "outcome": outcome,
        "destination": destination,
        "purpose": mask(purpose),
        "confidence": confidence,
        "retry_count": int(retry_count),
        "escalation_reason": escalation_reason,
        "turns": _turn_no,
    })
    _end_session()


def _end_session() -> None:
    global _session_id
    _session_id = None           # 한 세션을 두 번 닫지 않게


def close_interrupted() -> None:
    """운영자가 끊었다(Ctrl+C). **결과는 비워 두고 닫는다.**

    안 닫으면 턴만 있고 세션 줄이 없어 **누수(`NFR-B-403`)로 잡힌다** — 촬영 로그 5건이 전부 이것이었다.
    그렇다고 `abandoned_timeout` 같은 값을 붙이면 **일어나지 않은 일을 기록**하게 된다. `outcome` 은
    NULL 을 허용하므로 비우고, 사람이 읽을 `note` 만 남긴다.
    """
    if _session_id is None:
        return
    turn()
    _write({"rec": "session", "session_id": _session_id, "visitor_id": _visitor_id,
            "started_at": _started_at, "ended_at": _now(),
            "duration_ms": int((time.time() - _t_session) * 1000),
            "outcome": None, "note": "interrupted", "turns": _turn_no})
    _end_session()
