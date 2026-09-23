# -*- coding: utf-8 -*-
"""마이크 녹음(VAD 엔드포인팅) · 스피커 재생.

`scratchpad/audio_lab.py` 로 실기에서 확인한 것들을 대화 파이프라인이 쓸 수 있게 옮긴 것이다.
lab 쪽은 측정용 하네스라 계속 고쳐 쓰고, 여기는 **대화가 의존하는 안정된 경로**로 둔다.

실기에서 배운 것 — 전부 조용히 잘못 동작하던 것들이라 코드로 못 박아 둔다
------------------------------------------------------------------------
1. **카드 번호는 재부팅마다 바뀐다.** 실제로 마이크 3→0, 스피커 0→3 으로 뒤집혔다.
   그래서 번호를 상수로 두지 않고 **장치 이름으로 찾는다**(`_find_card`).
2. **`hw:` 는 못 쓴다.** 스피커(TITAN V2)가 모노를 거부해 `Channels count non available`
   로 실패한다. `plughw:` 는 ALSA 가 알아서 변환해 준다.
3. **USB 마이크는 스트림을 열 때 클릭음이 난다.** 0ms 지점에 피크 0.94 가 찍힌다.
   이걸 안 자르면 ① 정규화가 "이미 충분히 크다"고 판단해 증폭을 건너뛰고
   ② VAD 가 그 클릭을 발화 시작으로 오판한다. 앞 250ms 를 버린다 (`LOG-35`).
4. **`arecord -d` 는 정수 초만 받는다.** 2.25 를 넘기면 **에러 없이 파일이 안 생긴다.**
   그래서 고정 길이 녹음은 안 쓰고 raw 스트림을 직접 읽는다.
5. 캡처 게인은 이미 100%(0.00dB) 라 게인으로는 더 못 올린다 — 소프트웨어 정규화로 맞춘다.
"""
from __future__ import annotations

import os
import re
import subprocess
import time
import wave
from dataclasses import dataclass
from pathlib import Path

import numpy as np

SR = 16000            # whisper.cpp 가 요구하는 샘플레이트
LEAD_TRIM_S = 0.25    # USB 스트림 개시 클릭 제거 (LOG-35)
CHUNK_S = 0.05        # VAD 판정 주기

# --- 엔드포인팅 파라미터 ---------------------------------------------------
# 700ms. 300ms 는 상시청취 구 설계 값이라 **탭 방식에서는 말이 잘린다** —
# 터치로 시작하면 한 문장을 통째로 받아야 하는데 300ms 는 문장 중간 쉼에서 끊긴다
# (`FR-B-203` v1.7-b, `04` §지연표). 500/900 비교는 아직 안 해봤다.
ENDPOINT_MS = int(os.environ.get("ENDPOINT_MS", "700"))
NO_SPEECH_TIMEOUT_S = float(os.environ.get("NO_SPEECH_TIMEOUT_S", "3.0"))
MAX_UTTER_S = float(os.environ.get("MAX_UTTER_S", "10.0"))

# 무음/발화 경계. 시작할 때 실제 배경 소음을 재서 이 값 위로 올려 잡는다.
VAD_FLOOR = 0.012
VAD_MARGIN = 3.0      # 배경 소음 대비 몇 배를 발화로 볼지

MIC_HINT = os.environ.get("MIC_NAME", "C10")
SPK_HINT = os.environ.get("SPK_NAME", "TITAN")


def _find_card(cmd: str, prefer: str, exclude=("vc4hdmi",)) -> str:
    """`arecord -l` / `aplay -l` 출력에서 이름으로 카드를 고른다.

    번호로 고정하면 재부팅 한 번에 마이크와 스피커가 뒤바뀐다(실제로 겪음).
    HDMI 오디오(`vc4hdmi`)는 항상 잡히지만 우리가 쓸 장치가 아니라 제외한다.
    """
    try:
        out = subprocess.run([cmd, "-l"], capture_output=True, text=True).stdout
    except FileNotFoundError:
        raise RuntimeError(f"{cmd} 없음 — alsa-utils 설치 확인")

    cards = re.findall(r"^card (\d+): (\S+)\s*\[([^\]]*)\]", out, re.M)
    if not cards:
        raise RuntimeError(f"{cmd} -l 에 장치가 없다:\n{out}")

    usable = [(n, nm, lbl) for n, nm, lbl in cards
              if not any(x in nm.lower() for x in exclude)]
    for num, name, label in usable:
        if prefer.lower() in f"{name} {label}".lower():
            return f"plughw:{num},0"
    if usable:                       # 이름이 안 맞으면 첫 번째 비-HDMI 장치
        return f"plughw:{usable[0][0]},0"
    raise RuntimeError(f"쓸 수 있는 장치 없음 ({prefer}):\n{out}")


def mic_device() -> str:
    return os.environ.get("MIC_DEV") or _find_card("arecord", MIC_HINT)


def spk_device() -> str:
    return os.environ.get("SPK_DEV") or _find_card("aplay", SPK_HINT)


HPF_HZ = 80.0        # 이 아래를 깎는다 — 사람 목소리는 100Hz 아래가 거의 없다


def highpass(d: np.ndarray, cutoff: float = HPF_HZ, sr: int = SR) -> np.ndarray:
    """저주파 럼블을 깎는다 (1차 고역통과).

    **왜 필요한가**: 마이크에 11~19 Hz 짜리 신호가 들어온다. 귀로는 "두둥" 하는
    둔탁한 소리로만 들리는데 **진폭은 거대해서** 두 가지를 망친다.

      ① VAD 가 발화 시작으로 오판한다 — 방문자가 말하기도 전에 녹음이 열리고,
         700 ms 무음으로 끝나 버린다. whisper 는 알아들을 게 없으니 없는 말을
         지어낸다(`"도크,"` 가 반복 등장했다).
      ② `normalize()` 가 그 럼블을 기준으로 이득을 잡는다 — 정작 목소리는
         상대적으로 작아져서 뒷말이 통째로 묻힌다.

    책상·로봇을 건드리는 진동이 마이크 몸체로 전달되는 게 주된 원인으로 보인다.
    지향성 마이크도 **구조를 타고 오는 진동은 못 막는다.**

    1차 필터로 충분하다 — 80 Hz 에서 -3 dB, 20 Hz 에서 -12 dB 라 럼블은 죽고
    목소리(100 Hz 이상)는 거의 그대로다.
    """
    if len(d) < 2:
        return d
    rc = 1.0 / (2 * np.pi * cutoff)
    a = rc / (rc + 1.0 / sr)
    x = d.astype(np.float32)
    dx = np.diff(x, prepend=x[0])
    # y[n] = a*(y[n-1] + dx[n]) 를 파이썬 반복문으로 돌면 1초 녹음에 수만 번이다.
    # lfilter 로 한 번에 계산한다 (scipy 가 없으면 반복문으로 물러난다).
    try:
        from scipy.signal import lfilter
        y = lfilter([a], [1.0, -a], dx)
    except ImportError:
        y = np.empty_like(x)
        acc = 0.0
        for i in range(len(x)):
            acc = a * (acc + dx[i])
            y[i] = acc
    return np.clip(y, -32768, 32767).astype(np.int16)


class _HP:
    """블록을 이어서 거르는 고역통과. **VAD 판정에도 같은 필터를 쓰기 위해** 상태를 들고 있다.

    저장 직전에만 거르면 소용이 없다 — `record_until_silence()` 는 **거르지 않은 블록**으로
    발화 여부를 판단하기 때문이다. 럼블이 임계값을 넘겨 "발화 시작" 으로 잡히고,
    방문자가 입을 떼기도 전에 700 ms 무음으로 녹음이 끝난다.
    """

    def __init__(self, cutoff: float = 80.0, sr: int = SR) -> None:
        rc = 1.0 / (2 * np.pi * cutoff)
        self.a = rc / (rc + 1.0 / sr)
        self.y = 0.0
        self.x_prev = 0.0

    def __call__(self, block: np.ndarray) -> np.ndarray:
        x = block.astype(np.float32)
        dx = np.diff(x, prepend=self.x_prev)
        self.x_prev = float(x[-1]) if len(x) else self.x_prev
        y = np.empty_like(x)
        acc = self.y
        for i in range(len(x)):
            acc = self.a * (acc + dx[i])
            y[i] = acc
        self.y = acc
        return np.clip(y, -32768, 32767).astype(np.int16)


def _rms(block: np.ndarray) -> float:
    return float(np.sqrt(np.mean(block.astype(np.float32) ** 2))) / 32768.0


def normalize(d: np.ndarray, target: float = 0.25) -> np.ndarray:
    """조용한 녹음을 STT 가 들을 수 있는 크기로 올린다.

    피크가 아니라 **RMS** 기준이다 — 피크는 클릭음 하나에 휘둘린다(그래서 3번 항목이 생겼다).
    마이크에서 30~50cm 떨어져 말하면 실제로 이 보정이 필요할 만큼 작게 들어온다.
    """
    cur = _rms(d)
    if cur < 1e-6:
        return d
    gain = min(target / cur, 20.0)      # 무음 구간 노이즈를 폭발시키지 않도록 상한
    return np.clip(d.astype(np.float32) * gain, -32768, 32767).astype(np.int16)


@dataclass
class RecResult:
    path: Path
    speech: bool          # 발화를 감지했나 (False 면 STT 로 보낼 필요 없다)
    dur_s: float          # 저장된 오디오 길이
    wait_s: float         # 녹음 시작 ~ 발화 시작까지
    peak: float
    rms: float
    reason: str           # endpoint | max_len | no_speech


def _read_exact(pipe, n: int) -> bytes:
    """`n` 바이트를 **다 채워서** 돌려준다. 진짜 EOF 일 때만 짧게 돌려준다.

    파이프는 요청보다 적게 주는 일이 흔한데, 예전 구현은 그걸 **스트림 끝으로 단정**하고
    녹음을 끊었다. 그래서 **말하는 도중에 잘리는 일**이 생겼다 —
    "엘리베이터는 어디에 있어요" 가 "엘리베이터" 에서 0.75초 만에 끊겼고,
    파형에는 무음이 한 조각도 없었다(전부 발화). 무음 판정이 아니라 읽기 문제였다.
    """
    buf = b""
    while len(buf) < n:
        part = pipe.read(n - len(buf))
        if not part:                 # 진짜 EOF
            break
        buf += part
    return buf


def record_until_silence(path: str | Path, dev: str | None = None,
                         stop=None) -> RecResult:
    """말이 끝날 때까지 녹음한다 (⑫ 엔드포인팅).

    고정 길이로 받지 않는 이유: 짧게 잡으면 말이 잘리고, 길게 잡으면 말이 끝난 뒤
    남은 시간만큼 방문자를 그냥 기다리게 한다. 지연 예산에서 이 구간이 700ms 로
    잡혀 있는 것도 "무음을 확인하는 시간"이지 "녹음 길이"가 아니다.
    """
    path = Path(path)
    dev = dev or mic_device()
    chunk_n = int(SR * CHUNK_S)

    proc = subprocess.Popen(
        ["arecord", "-D", dev, "-f", "S16_LE", "-r", str(SR),
         "-c", "1", "-t", "raw", "-q", "-"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    # **호출할 때마다 환경변수를 다시 읽는다.** 모듈 상수로만 두면 import 시점에 굳어서,
    # 실행 중에 `NO_SPEECH_TIMEOUT_S` 를 바꿔도 아무 일도 안 일어난다 —
    # 확인 질의에 7초를 주려던 것이 계속 3초로 돌고 있었다.
    endpoint_ms = int(os.environ.get("ENDPOINT_MS", ENDPOINT_MS))
    no_speech_s = float(os.environ.get("NO_SPEECH_TIMEOUT_S", NO_SPEECH_TIMEOUT_S))
    max_utter_s = float(os.environ.get("MAX_UTTER_S", MAX_UTTER_S))

    hp = _HP()                 # VAD·저장 모두 같은 필터를 통과한 신호를 본다
    frames: list[np.ndarray] = []
    noise: list[float] = []
    speaking = False
    silence_ms = 0
    elapsed = 0.0
    wait_s = 0.0
    reason = "no_speech"
    thresh = VAD_FLOOR

    try:
        while True:
            # 시작 직후 0.8초는 종료 신호를 무시한다 — 터치 센서는 한 번 만져도
            # **가장자리 신호가 여러 번** 뜬다(0.8초에 6번 측정된 적 있다).
            # 그걸 그대로 받으면 시작 터치의 잔여 신호가 곧바로 녹음을 끝낸다.
            if stop is not None and elapsed > LEAD_TRIM_S + 0.8 and stop():
                # 사람이 직접 끝냈다(테스트 녹음기의 터치 종료). 무음을 기다리지 않는다.
                reason = "stopped"
                break
            raw = _read_exact(proc.stdout, chunk_n * 2)
            if len(raw) < chunk_n * 2:        # 진짜 EOF
                reason = "endpoint" if speaking else "no_speech"
                break
            elapsed += CHUNK_S
            if elapsed <= LEAD_TRIM_S:      # 클릭 구간 — 버린다
                continue

            # **거른 신호로 판단하고 거른 신호를 저장한다.** 예전에는 저장 직전에만
            # 걸러서, VAD 는 럼블이 실린 원본을 보고 "발화" 라고 판정했다.
            block = hp(np.frombuffer(raw, dtype=np.int16))
            level = _rms(block)

            # 클릭을 지난 뒤 처음 0.3초로 배경 소음을 재서 문턱을 잡는다.
            # 고정값 하나로는 조용한 사무실과 시끄러운 물류센터 정문을 같이 못 쓴다.
            if len(noise) < 6 and not speaking:
                noise.append(level)
                thresh = max(VAD_FLOOR, float(np.mean(noise)) * VAD_MARGIN)

            if not speaking:
                if level >= thresh:
                    speaking = True
                    wait_s = elapsed - LEAD_TRIM_S
                    frames.append(block)
                elif elapsed - LEAD_TRIM_S >= no_speech_s:
                    reason = "no_speech"
                    break
                continue

            frames.append(block)
            silence_ms = silence_ms + int(CHUNK_S * 1000) if level < thresh else 0
            # **사람이 끝내기로 한 녹음에서는 무음 판정을 쓰지 않는다.**
            # 둘 다 켜 두면 말을 마치고 손을 뻗는 사이에 700ms 가 먼저 지나가
            # 터치하기도 전에 끝나 버린다. 끝내는 주체는 하나여야 한다.
            if stop is None and silence_ms >= endpoint_ms:
                reason = "endpoint"
                break
            if (elapsed - LEAD_TRIM_S - wait_s) >= max_utter_s:
                reason = "max_len"
                break
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            proc.kill()

    d = np.concatenate(frames) if frames else np.zeros(0, dtype=np.int16)
    # 블록을 읽을 때 이미 걸렀다(`hp`) — 여기서 또 걸지 않는다.
    peak = float(np.abs(d).max()) / 32768.0 if len(d) else 0.0
    rms = _rms(d) if len(d) else 0.0
    if len(d):
        d = normalize(d)

    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SR)
        wf.writeframes(d.tobytes())

    return RecResult(path=path, speech=speaking, dur_s=len(d) / SR,
                     wait_s=round(wait_s, 2), peak=round(peak, 4),
                     rms=round(rms, 4), reason=reason)


def play(path: str | Path, dev: str | None = None,
         stop=None, poll_s: float = 0.05) -> bool:
    """안내 음성을 재생한다. 실패하면 **이유를 드러낸다.**

    예전에 `aplay` 의 반환값을 버리는 바람에 `Channels count non available` 로
    아무 소리도 안 나는데 성공한 줄 알고 넘어간 적이 있다.

    `stop` 을 주면 **재생 도중에 끊을 수 있다.** 인사말이 6초인데 방문자가 2초에
    등을 터치하면, 남은 4초를 다 들려주고 나서 녹음을 시작하는 건 말이 안 된다 —
    터치는 "지금 말하겠다" 는 뜻이라 그 순간 입을 다물어야 한다.
    """
    path = Path(path)
    if not path.exists():
        print(f"[audio] 파일 없음: {path}")
        return False
    dev = dev or spk_device()

    if stop is None:
        r = subprocess.run(["aplay", "-D", dev, "-q", str(path)],
                           capture_output=True, text=True)
        if r.returncode != 0:
            print(f"[audio] 재생 실패 ({dev}): {r.stderr.strip()[:200]}")
            return False
        return True

    proc = subprocess.Popen(["aplay", "-D", dev, "-q", str(path)],
                            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    while proc.poll() is None:
        if stop():
            proc.terminate()
            try:
                proc.wait(timeout=0.5)
            except subprocess.TimeoutExpired:
                proc.kill()
            print("  [재생] 터치로 중단")
            return True
        time.sleep(poll_s)
    if proc.returncode not in (0, -15):     # -15 = SIGTERM (우리가 끊은 것)
        err = (proc.stderr.read() or b"").decode("utf-8", "replace")
        print(f"[audio] 재생 실패 ({dev}): {err.strip()[:200]}")
        return False
    return True


if __name__ == "__main__":       # 수동 점검: python3 audio.py
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "play":
        print(play(sys.argv[2]))
    else:
        print(f"마이크  {mic_device()}")
        print(f"스피커  {spk_device()}")
        print("말씀하세요...")
        r = record_until_silence("/tmp/mic_test.wav")
        print(f"  발화 {r.speech} · {r.dur_s:.2f}초 · 대기 {r.wait_s}초 "
              f"· peak {r.peak} · rms {r.rms} · 종료사유 {r.reason}")
