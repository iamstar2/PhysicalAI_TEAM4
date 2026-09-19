"""project-local extra_script - MechDog_Arduino.a를 GNU ld에 whole-archive로 직접 전달한다.

이 파일을 platformio.ini의 extra_scripts로 지정해서 쓴다(사용법은
firmware/mechdog_d_uart/README.md "빌드 절차" 참고).

## 왜 -l/LIBS가 아니라 이 스크립트인가

2026-09-19 진단 결과: build_flags에 넣은 "-l:MechDog_Arduino.a"는 PlatformIO/SCons의
라이브러리 플래그 처리 과정에서 확장자가 잘려 "-l:MechDog_Arduino"(존재하지 않는
파일명)로 재가공됐다(그 플래그를 완전히 제거해도 "-l:MechDog_Arduino"가 링크 명령에
전혀 남지 않는 것으로 확인 - LDF의 precompiled=true 자동 처리가 아니라 -l 정규화
문제였음). 그래서 -l/LIBS 경로를 아예 쓰지 않고 LINKFLAGS에 아카이브 절대경로를
직접 추가한다(whole-archive로 감싸서, 오브젝트보다 먼저 배치돼도 심볼이 누락되지
않게 한다).

## 개인 PC 경로를 저장소에 넣지 않는 방법

라이브러리 원본(Hiwonder 공식 배포, `MechDog_Arduino.zip` 안의 `.a`)은 이 저장소에
포함하지 않는다 - 그래서 경로를 하드코딩하지 않고 환경변수로만 받는다.

PowerShell 설정 예시(실제 값은 본인 환경에 맞게, 아래는 자리표시자):
    $env:MECHDOG_ARDUINO_ARCHIVE="C:/path/to/MechDog_Arduino/src/esp32/MechDog_Arduino.a"

이 스크립트는 그 경로를 **읽기만** 한다 - 라이브러리 원본을 복사/이동/수정하지 않는다.
"""

from __future__ import annotations

import hashlib
import os
import sys

Import("env")  # noqa: F821 - PlatformIO SConscript 전역

ENV_VAR = "MECHDOG_ARDUINO_ARCHIVE"
EXPECTED_FILENAME = "MechDog_Arduino.a"
# 2026-09-19에 팀이 확보한 사본을 읽기 전용으로 해싱해 기록한 값(Hiwonder의 공식
# 배포 체크섬이 아니라 "이 빌드 설정이 검증됐던 그 파일"과 같은지 확인하는 용도) -
# 다른 검증된 사본으로 교체하면 이 값도 함께 갱신해야 한다.
EXPECTED_SHA256 = "1fdad476172eebf62bdc554bf3d240e0579011a88d4563ba5f1cceeb47c09a0e"


def _abort(message: str) -> None:
    print("=" * 78)
    print("[link_mechdog_archive] 빌드 중단")
    print(message)
    print()
    print(f"빌드 전에 {ENV_VAR} 환경변수를 설정하세요. 예(PowerShell, 본인 경로로 교체):")
    print(f'    $env:{ENV_VAR}="C:/path/to/MechDog_Arduino/src/esp32/MechDog_Arduino.a"')
    print("(경로에 역슬래시/공백이 있어도 이 스크립트가 정규화한다)")
    print("=" * 78)
    sys.exit(1)


raw_path = os.environ.get(ENV_VAR)
if not raw_path:
    _abort(f"환경변수 {ENV_VAR}이(가) 설정되지 않았습니다.")

# Windows 역슬래시 -> 슬래시 정규화, 실수로 붙은 따옴표/공백 제거.
archive_path = raw_path.strip().strip('"').strip("'").replace("\\", "/")

if not os.path.isfile(archive_path):
    _abort(f"{ENV_VAR}이(가) 가리키는 파일이 존재하지 않습니다:\n    {archive_path}")

actual_filename = os.path.basename(archive_path)
if actual_filename != EXPECTED_FILENAME:
    _abort(
        f"{ENV_VAR}이(가) {EXPECTED_FILENAME}을(를) 가리키지 않습니다"
        f"(실제 파일명: '{actual_filename}').\n    path: {archive_path}"
    )

with open(archive_path, "rb") as f:  # 읽기 전용 - 라이브러리 원본은 여기서 열기만 함
    actual_sha256 = hashlib.sha256(f.read()).hexdigest()

if actual_sha256 != EXPECTED_SHA256:
    _abort(
        "MechDog_Arduino.a의 SHA256이 예상값과 다릅니다 - 이 빌드 설정이\n"
        "    검증됐던 파일과 다른 사본일 수 있어 링크를 중단합니다.\n"
        f"    expected: {EXPECTED_SHA256}\n"
        f"    actual:   {actual_sha256}\n"
        f"    path:     {archive_path}"
    )

print(f"[link_mechdog_archive] 사용 경로: {archive_path} (SHA256 검증 통과)")

env.Append(
    LINKFLAGS=[
        f"-Wl,--whole-archive,{archive_path},--no-whole-archive",
    ]
)
