# -*- coding: utf-8 -*-
"""whisper.cpp 호출 래퍼.

`05_B_AI_Flow.md` §3.1-A 기준으로 엔진은 **whisper.cpp** 다.
(faster-whisper 는 이 RPi5 에서 RTF 8.0 이 나와 사실상 못 쓴다 — `09_작업기록 LOG-26`)

CLI 를 subprocess 로 부르고 `--output-json-full` 결과를 파싱한다. JSON 을 쓰는 이유는
**토큰별 확률 `p` 를 그대로 받을 수 있어서** 다 — 신뢰도 산식의 `P_stt` 항에 쓴다.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from destinations import INITIAL_PROMPT

# 환경변수로 덮어쓸 수 있게 둔다 (PC/파이 경로가 다르므로)
WHISPER_BIN = Path(os.environ.get(
    "WHISPER_BIN", Path.home() / "whisper.cpp" / "build" / "bin" / "whisper-cli"))
# 기본값이 `tiny` 로 남아 있어서 실행할 때마다 `WHISPER_MODEL=` 을 넘겨야 했다.
# 모델은 `LOG-41` 에서 **base 로 확정**됐다 — 사람 목소리 12문장에서 tiny 9/12,
# base 12/12 로 갈렸다. 기본값을 확정값에 맞춘다.
WHISPER_MODEL = Path(os.environ.get(
    "WHISPER_MODEL", Path.home() / "whisper.cpp" / "models" / "ggml-base.bin"))

THREADS = int(os.environ.get("WHISPER_THREADS", "4"))

# **인식 한 번의 상한.** 평소 2초 안팎인데, 알아듣기 힘든 소리가 들어오면 whisper 가 온도를 올려 가며
# 다시 디코딩해 17.6초까지 헛돈 적이 있다(`LOG-81` h04 — 그러고도 "도크, 회의실, 도크" 를 지어냈다).
# 재시도는 `-nf` 로 끄고, 그래도 넘치면 **실패로 돌려준다** — 방문자를 20초 세워 두느니 다시 묻는 게 낫다.
STT_TIMEOUT_S = float(os.environ.get("STT_TIMEOUT_S", "8.0"))
NO_FALLBACK = os.environ.get("STT_NO_FALLBACK", "1") == "1"

# 특수 토큰은 확률 평균에서 뺀다. [_BEG_], [_TT_100] 같은 것들로,
# 실제 발화 내용이 아니라 디코더 제어용이라 신뢰도에 섞으면 값이 왜곡된다.
def _is_special(tok_text: str) -> bool:
    t = tok_text.strip()
    return t.startswith("[_") and t.endswith("_]") or t.startswith("[_TT_")


@dataclass
class SttResult:
    text: str          # 인식 텍스트 (앞뒤 공백 제거)
    p_stt: float       # 0.0~1.0, 실제 발화 토큰들의 평균 확률
    n_tokens: int      # 확률 평균에 쓰인 토큰 수 (0이면 사실상 무음)
    raw: dict          # 원본 JSON (디버깅용)


def transcribe(wav_path: str | Path, prompt: str = INITIAL_PROMPT) -> SttResult:
    """wav 파일 하나를 인식한다."""
    wav_path = Path(wav_path)
    if not wav_path.exists():
        raise FileNotFoundError(wav_path)

    with tempfile.TemporaryDirectory() as td:
        out_prefix = Path(td) / "result"
        cmd = [
            str(WHISPER_BIN),
            "-m", str(WHISPER_MODEL),
            "-f", str(wav_path),
            "-l", "ko",                 # 자동감지는 짧은 발화에서 언어 오검출 (FR-B-301 AC-3)
            "-t", str(THREADS),
            "--prompt", prompt,         # 도메인 바이어싱 (LOG-27: 이거 없으면 인식률 급락)
            "--output-json-full",
            "-of", str(out_prefix),
            "--no-prints",
        ] + (["-nf"] if NO_FALLBACK else [])
        # **실패해도 예외를 올리지 않는다** (`FR-B-903`). 예전에는 whisper 가 죽으면
        # `CalledProcessError` 가 대화 루프까지 올라가 **B 프로세스가 통째로 죽었다**(`LOG-80`).
        # 빈 결과를 돌려주면 호출 측이 STT 실패로 세서 재질문 → 3회면 에스컬레이션으로 간다.
        try:
            subprocess.run(cmd, check=True, capture_output=True, timeout=STT_TIMEOUT_S)
            data = json.loads((out_prefix.with_suffix(".json")).read_text(encoding="utf-8"))
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired,
                OSError, json.JSONDecodeError) as e:
            print(f"[stt] 인식 실패 — {type(e).__name__} (빈 결과로 처리)")
            return SttResult(text="", p_stt=0.0, n_tokens=0, raw={})

    texts, probs = [], []
    for seg in data.get("transcription", []):
        texts.append(seg.get("text", ""))
        for tok in seg.get("tokens", []):
            if _is_special(tok.get("text", "")):
                continue
            p = tok.get("p")
            if p is not None:
                probs.append(float(p))

    return SttResult(
        text="".join(texts).strip(),
        p_stt=(sum(probs) / len(probs)) if probs else 0.0,
        n_tokens=len(probs),
        raw=data,
    )
