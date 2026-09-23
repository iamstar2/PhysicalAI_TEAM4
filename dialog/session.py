# -*- coding: utf-8 -*-
"""대화 세션 — `04_B_비즈니스_Flow.md` §2 의 흐름을 그대로 돈다.

    python3 session.py --demo     # 세션 인계 없이 한 판 (테스트용)
    python3 session.py            # gate.session 을 기다렸다가 진행 (실제 운용)

지금까지는 단계별 스크립트만 있었고 **처음부터 끝까지 도는 것은 이게 처음**이다.
STT·매칭·LLM 폴백·TTS·눈 LED 는 이미 각각 검증됐고, 여기서는 그것들을 문서 순서대로 잇는다.

흐름 번호(⑥·⑧-2·⑭-2 …)는 `04` 문서와 같은 번호다. 읽다 막히면 문서의 같은 번호를 보면 된다.

문서와 다르게 구현한 것 — 옮길 때 한 번 보고 갈 것
---------------------------------------------------
- **㉒ 강한 확인 질의**를 문서는 "실시간 합성"으로 적어 뒀는데, 여기서는 **㉑ 과 같은 캐시 멘트**를 쓴다.
  런타임 합성은 인터넷이 필요해서(`gen_tts.py` 주석) 지금 구조에서는 불가능하다.
  확인 질의 자체는 하므로 안전 성격(`BR-B-10`)은 유지된다 — 톤만 같아진다.
- **㉔ 2층 대체**는 별도 단계가 없다. 목적지 사전이 2층 관련 표현을 이미 `elevator_hall` 로
  보내고, 그 확인 멘트가 "2층은 직접 올라가셔야 해서…" 라고 말한다. 같은 결과다.
"""
from __future__ import annotations

import os
import random
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

import eye
import info_places
import llm_fallback
from audio import play, record_until_silence
from bus import Bus
from destinations import DESTINATIONS
from hangul import find_fuzzy
from matcher import match
from stt import transcribe

CACHE = Path(os.environ.get("TTS_OUT", Path.home() / "tts_cache"))
WORK = Path(os.environ.get("DIALOG_WORK", "/tmp/mechdog_b"))

TOUCH_WAIT_S = float(os.environ.get("TOUCH_WAIT_S", "15.0"))   # 6-2 / 10
SESSION_MAX_S = 60.0     # NFR-B-103
MAX_ATTEMPTS = 3         # BR-B-05 — 최초 1 + 재질문 2
MAX_AMBIG = 3            # BR-B-13 — 선택형 재질문 상한
MAX_STT_FAIL = 3         # 04 §4.6
PRESENT_CM = 150         # FR-B-1001 — 1.5m
ABSENT_STREAK = 3        # AC-1001-4 — 연속 3회 미감지일 때만 부재 확정


YES = ["네", "예", "맞아요", "맞습니다", "그래요", "좋아요", "응"]
NO = ["아니요", "아니오", "아니", "아뇨", "틀려요", "아닙니다"]

# 말하다 스스로 고치는 표지. 이게 있으면 목적지가 두 개 나와도 **둘 중 하나는 취소된 것**이다.
#   "입고 도크가 어딨어요? 아 아니다 출고 도크가 어디에요?"
# "마지막에 말한 쪽" 규칙은 못 쓴다 — "입고 도크요, 출고 아니고" 에서는 마지막이 부정된 쪽이다.
# 어느 쪽이 취소됐는지는 말의 의미를 봐야 알 수 있어서 LLM 에 맡긴다.
# "죄송"·"미안" 도 넣는다. 사과가 곧 정정은 아니지만("죄송합니다, 회의실 어디예요?"),
# 이 표지는 **결정이 아니라 LLM 에게 한 번 물어보는 방아쇠**일 뿐이라 헛걸음 비용이 작다.
CORRECTION = ["아니", "말고", "말구", "아니라", "잘못", "죄송", "미안"]

# **사양("괜찮습니다"·"혼자 갈게요")을 낱말로 잡지 않는다.**
# 안내가 필요 없는 사람은 **그냥 가버린다.** 재실 확인(초음파)이 그걸 잡아서 이탈 판정으로
# 보낸다 — 말로 구분하려고 목록을 만들면 끝이 없고, 어차피 결과가 같다.
# 확인 질의에서 필요한 건 **긍정인가 아닌가** 둘뿐이다.

# LLM 이 건져낸 목적지에 줄 신뢰도.
# 룰 매칭이 실패한 발화라 확실하다고 할 수 없고, 그렇다고 버릴 정도도 아니다.
# 0.45~0.75 구간에 두어 **반드시 확인 질의를 거치게** 한다 (16 통과, 20 미달 → 22).
LLM_CONFIDENCE = 0.60

# `confirm()` 이 돌려주는 특수 신호. **사양은 실패가 아니다** —
# `None`(= 확인 실패 → 재질문)과 섞이면 방문자가 안내를 사양했을 뿐인데
# 시도 횟수를 까먹고 결국 에스컬레이션까지 간다(실측으로 확인했다).
LOOP_BACK = "__loop__"

# (v3.2 에서 폐기) 예전에는 첫 발화에서 룰이 확신하면 LLM 을 건너뛰었다.
# 지금은 **LLM 이 먼저**라 쓰이지 않는다 — 아래 설명은 왜 그렇게 했다가 뒤집었는지의 기록이다.
#
# 왜 이렇게 나누나: 오늘 잡은 결함이 전부 "룰이 말의 의미를 모른다" 는 한 지점이었다
# (짧은 키워드 오탐, 자기정정 못 읽음, "똥 마려운데" 못 알아들음 …). 그래서 LLM 을 앞에 두는
# 안을 검토했는데, 그러면 **흔한 경우까지 매번 1초를 더 쓴다.**
#
# 그럴 필요가 없다 — "입고요" 처럼 **룰이 확신하는 쉬운 발화는 룰이 맞다.**
# 삐끗한 뒤에만(재질문 이후) LLM 을 앞세우면, 흔한 경우는 2,850ms 를 지키고
# 어려운 경우만 3,850ms 가 된다. 어려운 경우는 원래 재질문(4~5초)으로 빠지던 자리라 순이득이고,
# `NFR-B-101` 상한(3,500ms)을 올리지 않아도 된다.
#
# STT 신뢰도까지 보는 이유: 매칭 점수는 **자모 보정 덕에 높게 나올 수 있다.**
# 실제로 "입고요" 가 `잊고요` 로 인식돼도(p=0.66) 매칭은 0.90 이 나왔다.
# 전사가 흔들린 발화는 룰이 우연히 맞힌 것일 수 있으므로 LLM 에 한 번 보낸다.
P_STT_TRUST = 0.70


CHIME = Path.home() / "chimes"


_after_listen = False       # 방금 들은 말을 처리하고 답하려는 참인가
_bus = None                 # 재생 중 터치를 감시하려면 버스가 필요하다
_cut_by_touch = False       # 멘트를 터치로 끊었나 (그 터치를 대기에서 또 쓰면 안 된다)


def _stop_on_touch() -> bool:
    """재생 중 터치가 들어왔는지. 터치는 '지금 말하겠다' 는 뜻이라 즉시 입을 다문다."""
    global _cut_by_touch
    if _bus is not None and _bus.touch_edge.is_set():
        _bus.touch_edge.clear()        # 여기서 소비한다 — 안 끄면 다음 재생도 즉시 끊긴다
        _cut_by_touch = True
        return True
    return False


def chime(name: str) -> None:
    """청취 신호음. **이게 없으면 방문자는 언제 말해야 할지 알 수 없다.**

    멘트가 끝난 뒤 조용해지는 것만으로는 "말하라는 건지 기다리라는 건지" 가 구분되지
    않는다. 눈 LED 로도 알리지만 물류센터 정문에서 로봇 얼굴을 계속 보고 있을 수는 없다.

      chime_listen  440→659 Hz (올라감)  녹음 시작 — 지금 말하세요
      chime_stop    523 Hz 한 음 90 ms   녹음 끝 — 그만 말해도 됩니다
      chime_speak   659→440 Hz (내려감)  연산 끝 — 이제 대답합니다

    마지막 것이 필요한 이유: 녹음이 끝나고 STT·LLM 이 도는 3초 동안 **아무 소리가
    없다.** 방문자는 못 알아들은 건지 생각 중인지 알 수 없어서 다시 말하게 되고,
    그러면 다음 녹음에 겹쳐 들어간다.
    """
    f = CHIME / f"{name}.wav"
    if not f.exists():
        print(f"  [효과음] 파일 없음: {f}")
        return
    print(f"  [효과음] {name}")
    play(f)


def say(key: str) -> bool:
    """캐시된 안내 음성을 재생한다 (눈은 '안내중').

    같은 멘트에 **변형이 여러 개면 그중 하나를 무작위로** 고른다
    (`greet_1.wav`, `greet_2.wav` ...). 같은 상황에서 매번 똑같은 문장이 나오면
    그것만으로 기계 티가 나기 때문이다. 변형이 없으면 `greet.wav` 하나를 쓴다.
    """
    global _after_listen
    variants = sorted(CACHE.glob(f"{key}_[0-9].wav"))
    path = random.choice(variants) if variants else CACHE / f"{key}.wav"

    # 방금 방문자 말을 듣고 처리한 직후라면 **"이제 대답한다" 는 신호**를 먼저 낸다.
    if _after_listen:
        _after_listen = False
        chime("chime_speak")

    eye.set_state(eye.SPEAKING)
    ok = play(path, stop=_stop_on_touch)
    if not ok:
        print(f"[say] 재생 실패: {key}")
    return ok


def listen(tag: str, no_speech_s: float | None = None):
    """7 청취 — 녹음하고 인식까지 한다. 발화가 없으면 `None`."""
    WORK.mkdir(parents=True, exist_ok=True)
    wav = WORK / f"{tag}.wav"

    eye.set_state(eye.LISTENING)
    if no_speech_s is not None:
        os.environ["NO_SPEECH_TIMEOUT_S"] = str(no_speech_s)
    chime("chime_listen")          # 지금 말하세요
    rec = record_until_silence(wav)
    chime("chime_stop")            # 끝났습니다
    print(f"  [녹음] {rec.dur_s:.2f}초 · 발화 {rec.speech} · 종료 {rec.reason} "
          f"· rms {rec.rms}")
    if not rec.speech:
        return None

    global _after_listen
    _after_listen = True           # 여기서부터 연산 구간 — 다음 say 앞에 완료음이 붙는다
    eye.set_state(eye.THINKING)
    t0 = time.time()
    res = transcribe(wav)
    print(f'  [STT ] {time.time()-t0:.2f}초 · p={res.p_stt:.2f} · "{res.text}"')
    return res


_BOUNDARY = " ,.!?…~"


def _starts_with_word(text: str, words: list[str]) -> bool:
    """문장이 그 낱말로 **시작**하는가. 뒤에 다른 글자가 붙으면 인정하지 않는다.

    `startswith` 만 쓰면 **"예약했는데요" 가 "예" 로 시작한다고 긍정이 된다.**
    그래서 낱말 뒤가 끝이거나 구두점·공백일 때만 인정한다.
    """
    for k in words:
        if text == k:
            return True
        if text.startswith(k) and text[len(k)] in _BOUNDARY:
            return True
    return False


def yes_no(text: str) -> bool | None:
    """확인 질의 응답 판정. 예도 아니오도 아니면 `None`.

    **왜 편집거리를 쓰지 않는가** — 예전 구현은 `find_fuzzy(text, k, 1)` 로 찾았는데,
    `네`·`예`·`응` 은 **한 글자**라 편집거리 1 안에 `내`·`데`·`애` 같은 음절이 전부 들어온다.
    그래서 **"안내데스크가 어디예요"·"회의실 예약했는데요" 가 전부 긍정으로 판정됐다.**
    확인 질의는 오확정을 막는 마지막 관문인데, 그 관문이 아무 말에나 도장을 찍고 있었다
    (실측으로 확인 — 방문자가 "회의실" 이라고 했는데 입고 도크로 확정·발행됐다).
    `LOG-40` 의 짧은 키워드 문제와 **원인이 같다.** 거기서는 목적지 사전만 고쳤다.

    그래서 두 가지로 나눈다.
      - 짧은 응답(`네`, `아니요` …) — **문장 맨 앞에서 낱말 단위로 정확히** 일치할 때만
      - 긴 표현(`맞습니다`, `아닙니다` …) — 3글자 이상이라 오탐 여지가 작으므로
        문장 어디에 있어도 인정하고, 오타 보정(편집거리 1)도 허용한다

    부정을 먼저 본다 — "아니요" 안에 "네" 가 들어 있어서, 긍정을 먼저 보면
    거절을 승낙으로 읽는다. 잘못 확정하는 쪽이 못 확정하는 쪽보다 위험하다(`BR-B-10`).
    """
    t = text.strip()
    if not t:
        return None

    if _starts_with_word(t, NO):
        return False
    if _starts_with_word(t, YES):
        return True

    long_no = [k for k in NO if len(k) >= 3]
    long_yes = [k for k in YES if len(k) >= 3]
    if any(find_fuzzy(t, k, 1) for k in long_no):
        return False
    if any(find_fuzzy(t, k, 1) for k in long_yes):
        return True
    return None


def verdict(text: str, question: str) -> bool | None:
    """확인 질의 응답을 **긍정/부정**으로 판정한다. 모르면 `None`.

    **룰이 확실할 때만 룰을 쓰고, 애매하면 LLM 에 맡긴다** — 목적지 매칭과 같은 방식이다.
    "네" 한 마디는 0ms 로 끝나는데 1초를 쓸 이유가 없고, 반대로 긍정 표현은
    낱말 목록으로 덮이지 않는다:

        "맞지 않나요?"  "거기 어디예요?"  "아 거기요?"  "입고 도크요"

    되묻는 말투로 수긍하는 경우가 흔한데, 목록에 넣으려면 끝이 없다.
    실제로 짧은 낱말 목록으로 판정하다 **아무 말에나 긍정 도장을 찍은 적이 있다**(`LOG-48`).
    """
    v = yes_no(text)
    if v is not None:
        return v
    r = llm_fallback.confirm_reply(text, question)
    if r:
        print(f"  [응답] LLM 판정 → {r}")
    return {"yes": True, "no": False}.get(r)


@dataclass
class Session:
    bus: Bus
    session_id: str
    attempt: int = 1
    ambig: int = 0
    stt_fail: int = 0
    absent_streak: int = 0
    said_info: bool = False        # 이번 턴에 음성안내를 이미 했나 (중복 재생 방지)
    served: bool = False           # 방문자가 원한 정보를 이미 준 적 있나
    sched: str | None = None       # LLM 이 어느 일정으로 풀었나 (전용 확인 멘트용)
    opened: bool = False           # 터치로 대화가 열렸나 (터치는 세션당 처음 한 번)
    started: float = field(default_factory=time.time)

    # ---- 보조 ------------------------------------------------------------
    def expired(self) -> bool:
        return time.time() - self.started > SESSION_MAX_S

    def present(self) -> bool:
        """8-2 · 17-2 재실 확인. **연속 3회 미감지일 때만** 부재로 확정한다.

        초음파는 지향각이 좁아 방문자가 몸을 틀면 한 번씩 놓친다(`FR-B-1001` 미해결 항목).
        1회 미감지로 대화를 끊으면 멀쩡히 서 있는 사람을 버리게 된다.
        """
        p = self.bus.present(PRESENT_CM)
        if p is None:                      # 센서 두절 — 부재로 단정하지 않는다
            return True
        self.absent_streak = 0 if p else self.absent_streak + 1
        return self.absent_streak < ABSENT_STREAK

    def leave(self, why: str = "앞에 사람 없음") -> str:
        """11 이탈 판정.

        이유를 받는다 — 부재 확정과 "앞에 있는데 반응이 없음" 은 **원인이 다르다.**
        둘 다 "앞에 사람 없음" 으로 찍으면, 재실 확인이 멀쩡히 True 인데도 로그만 보고
        초음파를 의심하게 된다(실제로 첫 실행에서 그럴 뻔했다 — 57cm 에 서 계셨다).
        """
        print(f"  → 이탈 판정 ({why})")
        if self.served:
            # 원하는 걸 듣고 간 것은 **실패가 아니다.** 경고를 보내면 D 대시보드에
            # 정상 응대가 이탈로 쌓인다.
            print("     (이미 안내를 마쳤으므로 alert 발행 안 함)")
        else:
            self.bus.publish_alert(self.session_id, "info", "dialog_timeout")
        eye.set_state(eye.IDLE)
        return "left"

    def escalate(self, reason: str) -> str:
        """19 실패 안내 + D 에스컬레이션."""
        print(f"  → 에스컬레이션 ({reason})")
        eye.set_state(eye.ERROR)
        say("escalate")
        self.bus.publish_alert(self.session_id, "warn", reason)
        eye.set_state(eye.IDLE)
        return "escalated"

    # ---- 확정 -------------------------------------------------------------
    def confirm(self, dest: str, confidence: float, purpose: str,
                depth: int = 0) -> str | None:
        """21/22 확인 질의 → 23 응답 판정. 긍정이면 확정까지 간다.

        확인 질의는 **오확정을 막는 마지막 관문**이다. 룰이 틀리게 "성공"한 적이
        실제로 있었고(`LOG-40`), 그때도 이 질의가 있었으면 방문자가 "아니요"로 잡을 수 있었다.

        배웅("오늘 하루도 화이팅하세요")은 **여기에 두지 않는다.** B 는 목적지를 정해 주고
        넘기는 역할이고, 방문자와 함께 움직이는 건 C(에스코트)다. 배웅은 여정이 끝나는
        자리에서 나와야 자연스러우므로 C 의 몫이다.
        """
        # 일정으로 풀린 경우에는 전용 멘트가 있다. 없으면 일반 확인 멘트.
        say(f"sched_{self.sched}" if self.sched else f"confirm_{dest}")
        ans = listen(f"ans_{self.attempt}", no_speech_s=7.0)   # CONFIRMING 7초
        q = f"{DESTINATIONS[dest]['name']} 맞으실까요?"
        v = verdict(ans.text, q) if ans else None
        label = {True: "긍정", False: "부정"}.get(v, "판단 불가")
        print(f"  [확인] {dest} ← {label}")

        if v is False:
            say("no_ack")
            return None                    # 17 재질문 경로로
        if v is None:
            # **예도 아니오도 아닌 답을 버리지 않는다.**
            # "어? 여기 1층에 뭐 알려주는 곳 있다던데?" 는 예/아니오가 아니지만
            # 안내데스크를 가리킨다. 예전에는 이걸 무응답과 똑같이 취급해 재질문으로 보냈다 —
            # 쓸 수 있는 답을 버리고 다시 묻는 셈이었다.
            return self._answer_as_utterance(ans, depth)

        # 26 목적지 확정 → 26' **위치를 알려주고 에스코트가 필요한지 묻는다**
        return self._offer_escort(dest, confidence, purpose)

    def _offer_escort(self, dest: str, confidence: float, purpose: str) -> str:
        """위치를 알려준 뒤 **직접 안내가 필요한지** 묻는다. 수락할 때만 C 에게 넘긴다.

        **에스코트를 기본으로 깔지 않는다.** 많은 방문자는 위치만 알면 혼자 간다.
        모두를 데려다주면 C 한 대가 병목이 되고, 방문자도 굳이 로봇을 따라 걷게 된다.

        수락하지 않으면 `dialog.result` 를 **발행하지 않는다.** C 가 움직일 이유가 없고,
        방문자는 이미 위치를 들었다. 거절 자체는 이상 상황이 아니라 `alert.event` 도 안 보낸다.
        """
        say(f"where_{dest}")
        ans = listen(f"escort_{self.attempt}", no_speech_s=7.0)
        # **긍정일 때만 수락이다.** 나머지는 전부 사양으로 본다 —
        # 사양을 따로 분류할 이유가 없다(안 원하면 그냥 가고, 초음파가 잡는다).
        want = verdict(ans.text, "직접 안내해 드릴까요?") is True if ans else False
        print(f"  [에스코트] {dest} ← {'수락' if want else '사양/무응답'}")

        if not want:
            # 위치는 이미 알려줬다. 여기서 대화를 닫되 **문을 완전히 닫지는 않는다** —
            # 더 물어볼 게 있을 수 있으므로 "다시 터치해 주세요" 라고 말하고
            # **실제로 터치 대기로 돌아간다.** 말만 하고 세션을 닫으면 터치해도 아무 일이 안 생긴다.
            print("  → 위치만 안내 (C 인계 없음) · 터치 대기로 복귀")
            self.served = True
            self.opened = False            # 한 판 끝 — 다음 손님은 다시 터치부터
            # **시계를 다시 시작한다.** 한 판을 끝내고 다시 기다리는 것이므로
            # 앞선 대화에 쓴 시간을 다음 질문에 물리면 안 된다. 초기화하지 않으면
            # "더 물어보세요" 라고 해놓고 몇 십 초 뒤에 세션이 만료돼 버린다.
            self.started = time.time()
            say("closing")
            return LOOP_BACK

        return self._handoff(dest, confidence, purpose)

    def _handoff(self, dest: str, confidence: float, purpose: str) -> str:
        """27 발행 → 30 에스코트 시작 (실제 동행은 C)."""
        ok = self.bus.publish_result(self.session_id, dest, purpose,
                                     confidence, self.attempt - 1)
        print(f"  [발행] dialog.result {dest} conf={confidence:.2f} "
              f"{'ok' if ok else '실패(큐 보관)'}")
        say(f"escort_{dest}")
        eye.set_state(eye.IDLE)
        return "confirmed"

    def _answer_as_utterance(self, ans, depth: int) -> str | None:
        """확인 질의에 **예/아니오가 아닌 답**이 왔을 때, 그 답을 새 발화로 다시 본다.

        방문자는 "네/아니요" 로만 답하지 않는다. 틀렸다는 걸 알리면서 **동시에 올바른 목적지를
        말하는 쪽이 오히려 자연스럽다** — "어? 여기 1층에 뭐 알려주는 곳 있다던데?" 처럼.
        이걸 무응답과 같이 취급하면 쓸 수 있는 답을 버리고 재질문하게 된다.

        안전 측면: 새 목적지도 **다시 확인 질의를 거친다.** 확인 없이 확정되는 경로가
        생기는 게 아니다(`BR-B-10`). 다만 한 턴 안에서 무한히 되묻지 않도록 **깊이 1** 로 막는다.
        """
        if ans is None or not ans.text:
            return None                    # 진짜 무응답 — 17 재질문
        if depth >= 1:
            # 확인의 답이 또 예/아니오가 아니었다. 여기서 더 파고들면 같은 턴이 길어지기만 한다.
            print("  [확인] 답이 계속 목적지 얘기 — 재질문으로 넘긴다")
            return None

        m = match(ans.text, ans.p_stt)
        print(f"  [재해석] {m.action} · dest={m.dest} · conf={m.confidence:.2f}")

        if m.action == "disambiguate":     # 15 선택형 재질문 (시도 횟수 미포함)
            fixed = self._resolve_correction(m, ans.text)
            if fixed:
                return self.confirm(fixed, LLM_CONFIDENCE, ans.text, depth + 1)
            self.ambig += 1
            say(self._choose_key(m))
            return None

        dest = m.dest
        conf = m.confidence
        if not m.candidates:               # 14-2 LLM 분류 폴백
            dest = self._llm(ans.text)
            conf = LLM_CONFIDENCE
        if dest is None:
            return None                    # 목적지 얘기가 아니었다 — 17 재질문

        return self.confirm(dest, conf, ans.text, depth + 1)

    # ---- 한 턴 -------------------------------------------------------------
    def turn(self) -> str | None:
        """터치 대기 → 청취 → 매핑 → 확인. 세션이 끝나면 결과 문자열을 돌려준다."""
        # 6-2 터치 대기
        #
        # **멘트를 터치로 끊고 온 경우에는 기다리지 않는다.** 그 터치가 곧 "말하겠다" 는
        # 신호였는데 여기서 `wait_touch()` 가 이벤트를 비우고 다시 15초를 세면,
        # 방문자는 터치했는데도 아무 일이 안 일어나는 것처럼 느낀다.
        global _cut_by_touch
        eye.set_state(eye.IDLE)
        if _cut_by_touch:
            _cut_by_touch = False
            self.opened = True
            print("  [대기] 생략 — 안내 도중 터치로 이미 시작 신호를 받았다")
            return self._after_touch()

        # **터치는 대화를 여는 신호다.** 한 번 열린 세션에서 재질문마다 또 터치하게 하면,
        # 방문자는 "다시 말씀해 주세요" 를 듣고도 로봇을 만져야 한다. 확인 질의·에스코트
        # 제안은 이미 터치 없이 바로 듣고 있어서 재질문만 규칙이 달랐다.
        if self.opened:
            print("  [대기] 생략 — 이미 열린 대화 (터치는 처음 한 번)")
            return self._after_touch()

        print(f"  [대기] 터치를 기다린다 (최대 {TOUCH_WAIT_S:.0f}초) — 눈 노란색")
        if not self.bus.wait_touch(TOUCH_WAIT_S):
            # 6-3 무터치 → 8-2 재실 확인
            if not self.present():
                return self.leave()
            say("nudge")                                  # 9 M-04 재촉 1회
            if not self.bus.wait_touch(TOUCH_WAIT_S):     # 10
                return self.leave("재촉 후에도 무터치")

        self.opened = True
        return self._after_touch()

    def _after_touch(self) -> str | None:
        """터치를 받은 다음 — 7 청취부터."""
        res = listen(f"utt_{self.attempt}")
        self.started = time.time()     # 방문자가 말했다 — 상한 시계를 되돌린다
        if res is None:
            if not self.present():
                return self.leave()
            return self._reask("무발화")
        if not res.text:
            self.stt_fail += 1
            if self.stt_fail >= MAX_STT_FAIL:
                return self.escalate("dialog_failed")
            return self._reask()
        self.stt_fail = 0

        # 13' 말로만 알려주는 장소(화장실·계단 …)가 섞여 있으면 **먼저** 알려준다.
        #
        # 목적지 8종과 함께 나오는 일이 흔하다 —
        #   "출고로 갈게요. 그전에 화장실 어디에요?"
        # 여기서 화장실을 무시하면 방문자는 물어본 걸 못 듣는다. 반대로 화장실만 답하고
        # 끝내면 정작 목적지를 놓친다. **알려주고 나서 목적지 흐름을 그대로 이어 간다.**
        self.said_info = False
        info = info_places.find(res.text)
        if info:
            print(f"  [안내] 말로만 알려주는 장소: {info}")
            say(f"info_{info}")
            self.said_info = True

        # 13 매핑 — **룰은 폴백용으로 먼저 계산해 둔다** (모호 판정은 룰만 할 수 있다)
        m = match(res.text, res.p_stt)
        print(f"  [룰  ] {m.action} · dest={m.dest} · conf={m.confidence:.2f}"
              + (f" · {m.note}" if m.note else ""))

        # 13-2 **LLM 우선** (v3.2)
        #
        # 원래는 룰이 먼저였는데, 룰이 틀리는 지점이 전부 한 종류였다 —
        # **말의 의미를 모른다**. 짧은 키워드가 엉뚱한 음절을 잡는 사고가
        # `LOG-40`·`48`·`51` 에 이어 `올라가`↔`나가` 까지 **네 번** 반복됐다.
        # 키워드를 고칠 때마다 다른 곳이 터져서, 순서를 뒤집었다.
        #
        # 룰을 버리는 게 아니다 — **LLM 이 판단하지 못하거나 네트워크가 끊겼을 때 받는다.**
        # 그래야 인터넷 없이도 "입고요" 같은 직접 발화는 계속 동작한다.
        dest, conf = self._llm(res.text), LLM_CONFIDENCE

        if dest is None:
            # LLM 이 답을 못 냈다 → 룰로 내려간다
            if m.action == "disambiguate":        # 15 선택형 재질문
                fixed = self._resolve_correction(m, res.text)
                if fixed:
                    return self._confirmed(self.confirm(fixed, LLM_CONFIDENCE, res.text))
                self.ambig += 1
                if self.ambig >= MAX_AMBIG:       # 15-2 가드 (BR-B-13)
                    print("  선택형 3회 도달 → 시도 횟수로 합산")
                    return self._reask()
                say(self._choose_key(m))
                return None                       # 선택형은 시도 횟수에 미포함

            if m.dest is not None:                # 16 룰이 확신하면 그걸 쓴다
                print(f"  [폴백] LLM 판단 없음 → 룰 결과({m.dest}) 사용")
                dest, conf = m.dest, m.confidence
            else:
                if self.said_info:
                    # 물어본 곳을 방금 알려줬다. 목적지가 없다고 또 되묻는 건 눈치가 없다.
                    print("  → 안내만 하고 터치 대기로 복귀")
                    self.served = True
                    # 한 판이 끝났다 — 다음 손님은 **다시 터치부터**다.
                    # 이걸 안 닫으면 "터치해 주세요" 라고 말해 놓고 곧바로 녹음을 연다.
                    self.opened = False
                    self.started = time.time()
                    say("closing")
                    return None
                return self._reask()

        return self._confirmed(self.confirm(dest, conf, res.text))

    @staticmethod
    def _choose_key(m) -> str:
        """선택형 재질문 멘트 고르기. 실제로 갈리는 쌍은 입고/출고 도크뿐이다."""
        dests = {c.dest for c in m.candidates}
        return ("choose_dock" if dests <= {"inbound_dock", "outbound_dock"}
                else "choose")

    def _correcting(self, text: str) -> bool:
        return any(k in text for k in CORRECTION)

    def _resolve_correction(self, m, text: str) -> str | None:
        """후보가 갈렸을 때 **LLM 에게 먼저 물어본다.** 되묻는 건 그다음이다.

        *"입고 도크가 어딨어요? 아 아니다 출고 도크가 어디에요?"* 는 목적지가 둘 나오지만
        **사람은 이미 답을 말했다.** 그대로 되물으면 방문자는 방금 한 말을 또 해야 한다.

        그렇다고 "마지막에 말한 쪽" 으로 규칙을 잡을 수는 없다 —
        *"입고 도크요, 출고 아니고"* 에서는 마지막이 **부정된 쪽**이다.

        **처음에는 "아니/말고" 같은 정정 표지가 있을 때만 불렀는데, 그게 틀렸다.**
        *"입고도크요. 아 출고도크다 출고도크요"* 에는 표지가 하나도 없다("아니" 가 아니라 "아").
        사람이 말을 고치는 방식을 낱말 목록으로 가둘 수 없다.

        그래서 조건을 바꿨다 — **후보가 갈렸다는 것 자체가 "룰이 모른다" 는 뜻**이므로,
        표지를 따지지 말고 그냥 묻는다. 어차피 되물으면 5초가 걸릴 자리라 LLM 1초는
        순이득이고(`LOG-38` 과 같은 논리), 후보가 갈리는 일 자체가 드물어 평소 지연은 그대로다.
        결과는 여전히 **확인 질의를 거치므로** 확인 없이 확정되는 경로가 생기지 않는다.
        """
        dests = {c.dest for c in m.candidates}
        dest = self._llm(text)
        if dest is None:
            return None
        if dest not in dests:
            # 후보에 없던 곳을 골랐다 — 정정을 읽은 게 아니라 딴 얘기를 한 것이다.
            print(f"  [정정] LLM 이 후보 밖({dest})을 골라 무시 — 선택형 재질문으로")
            return None
        print(f"  [정정] 자기정정으로 판단 → {dest}")
        return dest

    def _confirmed(self, r: str | None) -> str | None:
        """`confirm()` 결과를 턴 결과로 옮긴다.

        `LOOP_BACK` 은 **사양**이다 — 재질문이 아니라 그냥 터치 대기로 돌아간다.
        `None` 만 확인 실패이므로 재질문으로 보낸다.
        """
        if r == LOOP_BACK:
            return None                    # 턴 종료, 시도 횟수 그대로
        return r or self._reask()

    def _llm(self, text: str) -> str | None:
        """8종 목적지 분류. 덤으로 **말로만 알려주는 곳**을 찾으면 그것도 재생한다."""
        if not llm_fallback.available():
            print("  [LLM ] 키 없음 — 건너뜀")
            return None
        t0 = time.time()
        r = llm_fallback.ask(text)
        dest = r.destination if r else None
        info = r.info_place if r else None
        # 일정으로 풀렸으면 **그 일정 전용 멘트**를 쓴다 —
        # "오후 두 시 반에 협력사 정기 미팅이 있으시네요. 회의실 1로 안내해 드릴까요?"
        # 일반 확인 멘트("회의실 1 맞으실까요?")보다 **알아봐 줬다는 게 드러나** 방문자가 납득한다.
        self.sched = r.schedule if r else None
        print(f"  [LLM ] {time.time()-t0:.2f}초 → dest={dest or 'null'} info={info or 'null'}"
              f" sched={self.sched or 'null'}"
              + (f" ({r.reason})" if r and r.reason else ""))
        if info and not self.said_info:
            # 키워드로는 못 잡았지만 의미로는 그 얘기였다 ("똥 마려운데 어디로 가요").
            # 키워드를 계속 늘리는 대신 여기서 받는다 — 8종에 쓰는 방식과 같다.
            print(f"  [안내] LLM 이 찾은 장소: {info}")
            say(f"info_{info}")
            self.said_info = True
        return dest if dest in DESTINATIONS else None

    def _reask(self, why: str = "인식 실패") -> str | None:
        """17 시도 검사 → 17-2 재실 확인 → 18 재질문."""
        print(f"  → 재질문 ({why}, 시도 {self.attempt} → {self.attempt + 1})")
        self.attempt += 1
        if self.attempt > MAX_ATTEMPTS:
            return self.escalate("dialog_failed")
        if not self.present():
            return self.leave()
        say("reprompt" if self.attempt == 2 else "reprompt_2")
        return None                            # 연결자 A — 6-2 터치 대기로 복귀

    # ---- 세션 -------------------------------------------------------------
    def run(self) -> str:
        global _bus, _cut_by_touch
        _bus = self.bus                        # 재생 중 터치를 감시하려면 필요하다
        _cut_by_touch = False
        self.bus.touch_edge.clear()            # 세션 전에 쌓인 터치는 버린다
        self.opened = False                    # 이 세션에서 터치를 한 번이라도 받았나
        print(f"\n=== 세션 {self.session_id} ===")
        say("greet")                           # 6 M-01
        while True:
            if self.expired():
                # **세션 상한은 "아무 일도 없을 때" 의 안전장치**다. 대화가 오가는 동안에는
            # 시계가 흐르면 안 된다 — 재질문을 두어 번 주고받으면 60초는 금방 차고,
            # 앞에서 말하고 있는 방문자를 끊게 된다. `listen()` 이 발화를 잡을 때마다
            # 되돌리므로(아래 `self.started` 갱신), 여기 걸린다는 건 정말 조용했다는 뜻이다.
            #
            # **세션 상한은 안전장치지 실패 판정이 아니다.** 무한정 열려 있는 걸
                # 막으려고 두는 것이고, 실패는 이미 재질문 3회에서 `dialog_failed` 로
                # 잡는다. 여기서 직원까지 부르면 같은 일을 두 곳에서 하는 셈이고,
                # 그것도 **앞에 사람이 있는지 보지도 않고** 부르게 된다.
                # `leave()` 는 재실·응대 여부를 보고 조용히 닫는다.
                return self.leave("세션 상한 60초 초과")
            out = self.turn()
            if out:
                return out


def main() -> int:
    bus = Bus()
    if not bus.connect():
        print("[경고] MQTT 미연결 — 터치·초음파를 못 받는다. 눈 LED 도 안 바뀐다.")

    if "--demo" in sys.argv:
        sid = f"demo-{int(time.time())}"
        try:
            print(Session(bus, sid).run())
        finally:
            bus.close()
        return 0

    print("gate.session 대기 중... (Ctrl+C 로 종료)")
    try:
        while True:
            if not bus.sessions:
                time.sleep(0.2)
                continue
            msg = bus.sessions.popleft()
            p = msg.get("payload", {})
            # 2 개시 조건 재검증 — 미인가·PPE 불합격이면 대화를 열지 않는다 (BR-B-14)
            if p.get("handoff_to") != "mechdog_b":
                continue
            if p.get("face_result") != "authorized" or p.get("ppe_result") != "pass":
                print(f"  3 대화 미개시 (face={p.get('face_result')} "
                      f"ppe={p.get('ppe_result')})")
                continue
            print(Session(bus, msg.get("session_id", "unknown")).run())
    except KeyboardInterrupt:
        eye.set_state(eye.IDLE)
        print("\n종료")
    except Exception as e:
        # 대화 루프가 통째로 죽는 경우 — 대시보드에 이유를 남기고 나간다.
        # 04 §4.6 의 error 3조건(오디오 단절·STT 연속 실패·세션 60초)은 아직 미구현이다.
        bus.publish_health("error", f"{type(e).__name__}: {e}"[:200])
        raise
    finally:
        bus.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
