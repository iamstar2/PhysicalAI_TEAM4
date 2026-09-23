# -*- coding: utf-8 -*-
"""USB 스피커 로터리 볼륨 놉 → ALSA PCM 연결.

    python tools/vol_daemon.py                 # 이름으로 자동 탐색
    python tools/vol_daemon.py /dev/input/event1 0    # 직접 지정

놉이 **엔드리스 인코더**라 물리적으로 음량을 바꾸지 않는다. 돌리면 `KEY_VOLUMEUP` /
`KEY_VOLUMEDOWN` 키 이벤트만 나오고, 이 데몬이 그걸 `amixer` 로 옮겨야 실제로 커진다.
**데몬이 안 떠 있으면 다이얼이 아무 반응도 안 한다**(`09_작업기록 LOG-61`).

**장치를 이름으로 찾는다.** `/dev/input/eventN` 의 N 은 고정이 아니다 — USB 를 다시
꽂거나 다른 입력 장치가 붙으면 번호가 밀린다. 마이크·스피커를 이름으로 찾는
`dialog/audio.py` 와 같은 방식이다.
"""
import re
import struct
import subprocess
import sys
import time
from pathlib import Path

SPK_HINT = "TITAN"          # 스피커 이름에 들어가는 조각 (대소문자 무시)
STEP = "2%"

KEY_VOLUMEDOWN = 114
KEY_VOLUMEUP = 115
KEY_MUTE = 113


def find_event(hint: str = SPK_HINT) -> str | None:
    """이름으로 입력 장치를 찾는다. 없으면 `None`."""
    for dev in sorted(Path("/dev/input").glob("event*")):
        name_file = Path(f"/sys/class/input/{dev.name}/device/name")
        try:
            name = name_file.read_text().strip()
        except OSError:
            continue
        if hint.lower() in name.lower():
            print(f"[vol] 입력 장치: {dev}  ({name})")
            return str(dev)
    return None


def find_card(hint: str = SPK_HINT) -> str:
    """이름으로 사운드 카드 번호를 찾는다. 못 찾으면 0."""
    try:
        text = Path("/proc/asound/cards").read_text()
    except OSError:
        return "0"
    for line in text.splitlines():
        m = re.match(r"\s*(\d+)\s+\[", line)
        if m and hint.lower() in line.lower():
            print(f"[vol] 사운드 카드: {m.group(1)}  ({line.strip()[:50]})")
            return m.group(1)
    return "0"


def current_pct(card: str) -> str:
    out = subprocess.run(["amixer", "-c", card, "sget", "PCM"],
                         capture_output=True, text=True).stdout
    m = re.search(r"\[(\d+)%\]", out)
    return m.group(1) + "%" if m else "?"


def main() -> int:
    if len(sys.argv) > 1:
        dev, card = sys.argv[1], (sys.argv[2] if len(sys.argv) > 2 else "0")
    else:
        # 부팅 직후에는 USB 인식이 늦을 수 있어 잠깐 기다려 본다
        dev = None
        for _ in range(20):
            dev = find_event()
            if dev:
                break
            time.sleep(1.0)
        if not dev:
            print(f"[vol] '{SPK_HINT}' 입력 장치를 못 찾았다 — 스피커가 꽂혀 있나?")
            return 1
        card = find_card()

    print(f"볼륨 놉 데몬 시작 — {dev} 감시, card {card}, 스텝 {STEP}, "
          f"현재 {current_pct(card)}")

    def bump(arg: str, label: str) -> None:
        subprocess.run(["amixer", "-c", card, "sset", "PCM", arg], capture_output=True)
        print(f"{label}  →  {current_pct(card)}", flush=True)

    with open(dev, "rb") as f:
        while True:
            data = f.read(24)
            if len(data) < 24:
                continue
            typ, code, val = struct.unpack("HHi", data[16:24])
            if typ != 1 or val != 1:
                continue
            if code == KEY_VOLUMEDOWN:
                bump(f"{STEP}-", "볼륨 -")
            elif code == KEY_VOLUMEUP:
                bump(f"{STEP}+", "볼륨 +")
            elif code == KEY_MUTE:
                bump("toggle", "음소거 토글")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
