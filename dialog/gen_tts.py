# -*- coding: utf-8 -*-
"""안내 음성 생성기 — 문구를 고치면 다시 돌려서 음성을 갱신한다.

    python3 gen_tts.py                 # 전체(26개) 재생성
    TTS_GAP_S=1 python3 gen_tts.py     # 결제 티어 — 간격 없이 빠르게(약 30초)
    python3 gen_tts.py greet reprompt  # 일부만
    python3 gen_tts.py --list          # 문구 목록만 보기(생성 안 함)

문구·말투·음성은 전부 `phrases.json` 에 있다. **코드를 고칠 일이 거의 없도록** 분리해 뒀다 —
멘트는 사람이 말하듯 계속 다듬게 되므로, 그때마다 이 파일을 건드리지 않아도 되게 하려는 것이다.

왜 Gemini TTS 인가
------------------
Piper(`ko_KR-kss-medium`)는 기계음 티가 나서 기각됐다(`LOG-42`). Gemini TTS 는
**말투를 자연어로 지시**할 수 있어서("상냥하고 전문적인 안내원 톤으로") 결과가 확연히 낫다.

모델은 **`gemini-3.1-flash-tts-preview`** 를 쓴다. 같은 Gemini TTS 라도 모델마다 한도가 다른데,
구 `gemini-2.5-flash-preview-tts` 는 **하루 10회**라 26개 생성이 불가능한 반면
이 모델은 **분당 3회**여서 간격만 두면 무료로도 전부 만들 수 있다.
결제를 붙였다면 `TTS_GAP_S=1` 로 간격을 없앤다.

주의: 실시간 합성용이 아니다. 클라우드 왕복이 필요하므로 **미리 만들어 두고 재생만** 한다.
런타임에는 인터넷이 필요 없다.
"""
from __future__ import annotations

import base64
import json
import os
import sys
import time
import urllib.error
import urllib.request
import wave
from pathlib import Path

import numpy as np

HERE = Path(__file__).parent
CONF = json.loads((HERE / "phrases.json").read_text(encoding="utf-8"))
OUT = Path(os.environ.get("TTS_OUT", Path.home() / "tts_cache"))

# 엔진 선택. `TTS_ENGINE=edge` 로 바꾸면 Edge 를 쓴다.
#   gemini — 말투 지시가 먹어서 품질이 낫지만 **무료 한도가 모델당 하루 10회**라
#            26개를 한 번에 못 만든다(결제를 붙이면 풀린다).
#   edge   — 완전 무료·무제한이지만 한국어에 말투(스타일) 옵션이 없다.
# 둘 다 같은 문구·같은 파일명으로 출력하므로 **나중에 덮어쓰기만 하면 교체된다.**
ENGINE = os.environ.get("TTS_ENGINE", "gemini")

MODEL = os.environ.get("GEMINI_TTS_MODEL", "gemini-3.1-flash-tts-preview")
URL = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent"
EDGE_VOICE = os.environ.get("EDGE_VOICE", "ko-KR-SunHiNeural")

SR = 24000
# 요청 간격. **무료 한도(분당 3회) 때문에 넣었던 것**이라, 결제를 붙이면 필요 없다.
#   TTS_GAP_S=1  → 26개를 30초 안에 생성 (결제 티어)
#   미지정       → 무료 티어 기준 21초 (26개 약 9분)
# 429 가 나면 아래 synth() 가 알아서 기다렸다 재시도하므로, 짧게 잡아도 실패하지는 않는다.
GAP_S = float(os.environ.get(
    "TTS_GAP_S", 21 if ENGINE == "gemini" else 0))
TAIL_S = 0.15       # 끝부분 이만큼을 보고 잘림을 판정한다
TAIL_MAX = 0.02
RETRY = 3


def build_phrases() -> dict[str, str]:
    """`phrases.json` 한 파일에서 {파일이름: 문구} 를 만든다.

    문구가 **리스트면 변형별로 파일을 하나씩** 만든다 (`greet_1.wav`, `greet_2.wav` ...).
    재생할 때 그중 하나를 무작위로 고르므로, 같은 상황에서 매번 같은 말이 나오지 않는다 —
    시연에서 같은 문장이 반복되면 그것만으로 기계 티가 난다.

    예전에는 목적지 문구가 `destinations.py` 에 있고 안내 멘트를 확인 멘트에서
    **문자열 치환으로 만들어** 냈다. 그러면 두 파일을 봐야 하고, 확인과 안내가
    서로 묶여 있어 다른 말투를 쓸 수 없었다. 이제 둘 다 이 파일에 따로 적는다.
    """
    out: dict[str, str] = {}

    def add(key: str, value) -> None:
        if isinstance(value, str):
            out[key] = value
        else:
            for i, text in enumerate(value, 1):
                out[f"{key}_{i}"] = text

    for key, spec in CONF["목적지"].items():
        add(f"confirm_{key}", spec["확인"])       # 목적지가 맞는지 되묻기
        add(f"where_{key}", spec["위치"])         # 위치 알려주기 + "직접 안내해 드릴까요?"
        add(f"escort_{key}", spec["에스코트"])    # 에스코트 수락 시에만
    for key, spec in CONF["공통"].items():
        add(key, spec["문구"])
    # 말로만 알려주는 장소(화장실·계단 …). 문구가 비어 있으면 건너뛴다 —
    # 시연장 배치가 정해지기 전에는 위치를 쓸 수 없고, 지어내면 안 된다.
    for key, spec in CONF.get("음성안내", {}).items():
        if spec.get("문구"):
            add(f"info_{key}", spec["문구"])
    # 일정 전용 확인 멘트. 시각·용건이 들어가 있어 일정마다 따로 만든다.
    try:
        sched = json.loads((HERE / "schedule.json").read_text(encoding="utf-8"))
        for it in sched.get("items", []):
            if it.get("키") and it.get("멘트"):
                add(f"sched_{it['키']}", it["멘트"])
    except (OSError, json.JSONDecodeError):
        pass
    return out


def unused_keys() -> set[str]:
    """현재 코드가 재생하지 않는 멘트. 다시 만들 때 건너뛴다.

    변형이 있으면 `error_1` 처럼 접미사가 붙으므로 **접두사로** 판정한다.
    """
    return {k for k, v in CONF["공통"].items() if v.get("사용") == "미사용"}


def _is_unused(key: str, skip: set[str]) -> bool:
    base = key.rsplit("_", 1)[0] if key.rsplit("_", 1)[-1].isdigit() else key
    return base in skip


def _request(text: str) -> bytes:
    prompt = f'{CONF["style"]}\n"{text}"'
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "speechConfig": {"voiceConfig": {
                "prebuiltVoiceConfig": {"voiceName": CONF["voice"]}}},
        },
    }
    req = urllib.request.Request(
        URL, data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json",
                 "x-goog-api-key": os.environ["GEMINI_API_KEY"]},
        method="POST")
    with urllib.request.urlopen(req, timeout=120) as r:
        payload = json.load(r)
    parts = payload["candidates"][0]["content"]["parts"]
    return b"".join(base64.b64decode(p["inlineData"]["data"])
                    for p in parts if "inlineData" in p)


def _request_edge(text: str) -> bytes:
    """Edge TTS. mp3 로만 받을 수 있어 ffmpeg 로 PCM 변환한다.

    말투 지시는 무시된다 — Edge 한국어 음성에는 스타일 옵션이 없다(`LOG-42`).
    그래서 문장만 읽는다. 대신 무료·무제한이라 26개를 한 번에 만들 수 있다.
    """
    import asyncio
    import subprocess
    import tempfile

    import edge_tts

    async def _save(path: str) -> None:
        await edge_tts.Communicate(text, EDGE_VOICE).save(path)

    with tempfile.TemporaryDirectory() as td:
        mp3 = str(Path(td) / "a.mp3")
        asyncio.run(_save(mp3))
        r = subprocess.run(
            ["ffmpeg", "-y", "-i", mp3, "-f", "s16le", "-ar", str(SR), "-ac", "1", "-"],
            capture_output=True)
        if r.returncode != 0:
            raise RuntimeError(f"ffmpeg 실패: {r.stderr.decode()[:200]}")
        return r.stdout


def _tail_peak(pcm: bytes) -> float:
    """끝부분 음량. 정상 종료면 말끝에 무음이 남아 0 에 가깝다."""
    d = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768
    return float(np.abs(d[-int(SR * TAIL_S):]).max()) if len(d) else 1.0


def synth(text: str, path: Path) -> dict:
    """생성 후 잘림을 검사하고, 잘렸으면 다시 받는다.

    Gemini TTS 는 `finishReason: STOP` 으로 응답해도 **음성이 중간에서 끊겨 오는 일이 있다**
    (같은 문장이 2.25초/2.73초로 달랐고, 실제로 "안내해 드릴까..." 에서 끊겼다).
    응답 메타로는 구분할 수 없어서 파형 끝을 직접 본다.
    """
    fetch = _request if ENGINE == "gemini" else _request_edge
    best: bytes | None = None
    best_peak = 1.0
    last_err = ""
    for attempt in range(RETRY):
        try:
            pcm = fetch(text)
        except urllib.error.HTTPError as e:
            # **무엇 때문에 실패했는지 남긴다.** 예전엔 그냥 "생성 실패" 만 떠서
            # 한도 초과인지 인증 문제인지 구분이 안 됐다(16개째에서 멈췄을 때 실제로 겪었다).
            body = e.read().decode("utf-8", "replace")[:300]
            last_err = f"HTTP {e.code} · {body}"
            print(f"      시도 {attempt + 1}/{RETRY} 실패 — {last_err}", file=sys.stderr)
            if e.code == 429:                  # 한도 초과 — 점점 길게 기다렸다 재시도
                # GAP_S 를 짧게 잡았을 때(결제 티어) 한도에 부딪히면 고정 대기로는
                # 같은 벽에 계속 부딪힌다. 시도마다 배로 늘린다.
                time.sleep(max(GAP_S, 2.0) * (2 ** attempt))
                continue
            raise
        peak = _tail_peak(pcm)
        if best is None or len(pcm) > len(best):
            best, best_peak = pcm, peak
        if peak <= TAIL_MAX:                   # 깨끗하게 끝났으면 확정
            best, best_peak = pcm, peak
            break
        time.sleep(GAP_S)

    if best is None:
        raise RuntimeError(f"생성 실패 — {last_err or '원인 불명'}")

    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SR)
        wf.writeframes(best)
    return {"sec": round(len(best) / (SR * 2), 2),
            "tail": round(best_peak, 4),
            "ok": best_peak <= TAIL_MAX}


def main() -> int:
    phrases = build_phrases()
    args = [a for a in sys.argv[1:] if not a.startswith("--")]

    if "--list" in sys.argv:
        unused = unused_keys()
        for k, v in phrases.items():
            mark = "  (미사용)" if _is_unused(k, unused) else ""
            print(f"  {k:24} {v}{mark}")
        voice = CONF["voice"] if ENGINE == "gemini" else EDGE_VOICE
        print(f"\n총 {len(phrases)}개 · 엔진 {ENGINE} · 음성 {voice}")
        if ENGINE == "gemini":
            print(f"말투: {CONF['style']}")
        return 0

    if args:
        items = [(k, v) for k, v in phrases.items() if k in args]
    else:
        # 전체 생성 시에는 **미사용 멘트를 뺀다.** 5개가 여기 해당하고,
        # 만들어 봐야 재생되지 않으므로 요청·시간·요금만 든다.
        skip = unused_keys()
        items = [(k, v) for k, v in phrases.items() if not _is_unused(k, skip)]
    if not items:
        print(f"해당 키 없음: {' '.join(args)}")
        return 1

    OUT.mkdir(parents=True, exist_ok=True)
    if ENGINE == "gemini":
        print(f"[gemini] {MODEL} / 음성 {CONF['voice']} / {len(items)}개 (간격 {GAP_S}초)")
        print(f"말투: {CONF['style']}\n")
    else:
        print(f"[edge] {EDGE_VOICE} / {len(items)}개")
        print("※ Edge 는 말투 지시를 지원하지 않아 문장만 읽는다 — "
              "나중에 gemini 로 덮어쓰면 교체된다\n")

    bad = []
    for i, (key, text) in enumerate(items, 1):
        r = synth(text, OUT / f"{key}.wav")
        mark = "" if r["ok"] else "  ⚠잘림의심"
        print(f"  [{i:2d}/{len(items)}] {key:24} {r['sec']:5.2f}초{mark}  {text[:30]}",
              flush=True)
        if not r["ok"]:
            bad.append(key)
        if i < len(items):
            time.sleep(GAP_S)

    print(f"\n완료 — {len(items)}개" + (f", 잘림 의심 {len(bad)}건: {' '.join(bad)}" if bad else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
