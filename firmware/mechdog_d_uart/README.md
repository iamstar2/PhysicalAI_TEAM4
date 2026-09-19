# mechdog_d_uart 펌웨어 패치 제안 (미적용 · 미업로드)

이 폴더는 **`references/`의 원본 Hiwonder 공식 예제를 절대 수정하지 않기 위해** 분리한
패치 제안 공간이다. `references/03 Arduino Programming Projects/05 Serial Communication
Practical Lessons/MechDog_Slave_Program/MechDog_uart/` 원본은 그대로 두고, 여기에만
변경안을 둔다.

## 현재 상태: 로컬 컴파일 성공, 실물에는 아직 적용된 적 없음

- ESP32에 업로드한 적 없음, 실물 시리얼 포트로 명령을 보낸 적도 없음.
- `esptool`의 `erase-flash`/`write-flash`를 실행한 적 없음.
- 실물 명령을 보낸 적 없음(테스트는 전부 `security-dashboard/tests/`의 Mock/Fake로만 진행).
- 2026-09-18~19에 로컬 컴파일을 진행했고, **2026-09-19에 원본·패치본 모두 링크까지
  성공**했다(아래 "2026-09-19 빌드 검증" 참고). **컴파일/링크 성공과 실물 하드웨어
  동작 검증은 별개다 - 빌드 성공이 곧 업로드/실물 적용 승인이 아니다.**
- 아래 "적용 전 필수 확인"을 팀이 확인하기 전까지 업로드하지 않는다.

## 확인된 실제 하드웨어 (2026-09-18)

팀이 직접 확인한 값 - 아래 보드 설정은 전부 이 값을 근거로 한다.

| 항목 | 값 |
|---|---|
| Chip | ESP32-D0WD, revision v1.1 (고전적인 듀얼코어 ESP32 - S2/S3/C3 계열 아님) |
| Flash | 4MB, 3.3V |
| USB-Serial 브리지 | CH340 |
| Windows 포트 | <PORT> |
| 전체 플래시 백업 | `mechdog_d_factory_backup_A.bin`, 4,194,304 bytes (이 저장소에는 포함하지 않음 - 아래 "백업 파일 취급" 참고) |

**교차 검증**: PlatformIO `espressif32` 플랫폼의 `esp32dev`(Espressif ESP32 Dev
Module) 보드 정의 파일(`esp32dev.json`)의 `upload.maximum_size`가 정확히
**4194304**(byte)로, 팀이 실측한 백업 파일 크기와 정확히 일치한다 - `esp32dev`
보드 선택이 이 칩과 맞다는 근거로 삼았다.

### 백업 파일 실제 분석 결과 (2026-09-18, 읽기 전용)

개인 백업 폴더의 `mechdog_d_factory_backup_A.bin`(경로: `<MECHDOG_LIBRARY_PATH>`와
같은 개인 작업 폴더, 저장소 밖)을 **`rb`(읽기 전용) 모드로만 열어** 헤더/파티션
테이블을 파싱했다. 파일을 쓰거나
옮기거나 저장소에 복사한 적 없음 - 분석 전후로 크기(4,194,304 bytes)와
수정 시각이 그대로임을 확인했다.

- **파일 SHA256**: `6d3b19ab20876fe0539e118864478ca72a87af69e898dabc4edfc552d53fa4fe`
  (백업 원본 전체 기준 - 향후 같은 백업인지 재확인할 때 이 값과 비교하면 됨)
- **부트로더 이미지 헤더**(offset 0x1000): magic 0xe9(정상), flash_mode=**DIO**,
  flash_freq=**40MHz**, flash_size=**4MB** — 위 "올바른 보드 설정"에서 제안한
  값과 **정확히 일치**함을 실제 백업으로 확인했다.
- **App(factory) 이미지 헤더**(offset 0x10000): magic 0xe9(정상), flash_mode=DIO,
  flash_freq=40MHz, flash_size=4MB, 8 segments — 부트로더 헤더와 일치.
- 두 헤더 모두 `esptool.py image_info`로 별도 추출(0x1000~0x8000 부트로더
  구간, 0x10000~0x1FFFFF factory 파티션 전체)해 **독립적으로 재검증**했고,
  체크섬(Checksum)과 SHA256 검증 해시(Validation Hash) 둘 다 "valid"로
  나왔다 - 백업 파일이 손상되지 않았고 위 파싱이 정확함을 뒷받침한다. 추출한
  임시 파일은 세션 스크래치 폴더에만 있고 저장소/커밋 대상이 아니다.
- **파티션 테이블**(offset 0x8000, MD5 체크섬 엔트리로 정상 종료됨 확인):

  | label | type | subtype | offset | size |
  |---|---|---|---|---|
  | `nvs` | data | nvs | 0x009000 | 24,576 bytes |
  | `phy_init` | data | phy | 0x00f000 | 4,096 bytes |
  | `factory` | app | factory | 0x010000 | 2,031,616 bytes |
  | `vfs` | data | fat | 0x200000 | 2,097,152 bytes |

  OTA 파티션(`ota_0`/`ota_1`/`otadata`)이 없는 **단일 factory 앱** 구성이고,
  데이터 파티션이 SPIFFS가 아니라 **FAT(subtype `fat`)**이다. ~~이는 Arduino-ESP32
  코어의 표준 파티션 스킴 중 "Default 4MB with ffat"와 정확히 일치한다~~ —
  **2026-09-19 정정**: Arduino-ESP32가 기본 제공하는 `default_ffat.csv` 등을
  직접 열어 비교해보니 전부 `otadata`+`ota_0`+`ota_1`(이중 OTA) 구조라 실제
  백업(OTA 없는 단일 `factory`)과 정확히 일치하지 않았다. 표준 스킴 이름을
  쓰지 않고, 이 표에 나온 값 그대로 커스텀 CSV를 만들어 썼다 - 아래
  "2026-09-19 빌드 검증"의 "D. 파티션 구조" 참고.

**참고**: `Hiwonder.cpp`/`Hiwonder.h`에 나오는 `ESP32S3Cam` 클래스(`ESP32S3_init()`,
`face_recognition()` 등, I2C로 통신)는 MechDog 본체의 메인 컨트롤러가 아니라
**별도의 AI 비전 카메라 모듈에 달린 별개의 ESP32-S3 칩**을 가리킨다. 우리가
패치하는 대상(`MechDog_uart.ino`가 도는 메인 바디 컨트롤러)은 어디까지나
ESP32-D0WD이고, 이 둘을 혼동하면 안 된다.

## 올바른 보드 설정

| 도구 | 설정 |
|---|---|
| Arduino IDE | 보드: **"ESP32 Dev Module"**(esp32 by Espressif Systems 패키지) / Flash Size: **4MB (32Mb)** / Flash Mode: **DIO** / Flash Frequency: **40MHz** / Partition Scheme: 표준 이름과 일치하는 게 없어 **커스텀 CSV**(`firmware/mechdog_d_uart/partitions/partitions_mechdog_d.csv`) 사용 - 아래 "2026-09-19 빌드 검증 D" 참고 / Upload Speed: CH340이라 921600보다 **460800 또는 115200**을 권장(실제 값은 업로드 시 안정성 보고 조정) / Port: 실물 USB-Serial 포트(환경마다 다름, 장치관리자에서 확인) |
| PlatformIO | `platform = espressif32`, `board = esp32dev`, `framework = arduino` (보드 JSON이 `flash_mode: dio`, `f_flash: 40000000L`, `upload.flash_size: 4MB`, `upload.speed: 460800`을 이미 담고 있어 별도 오버라이드 불필요) |

ESP32-D0WD **rev v1.1**이라는 실리콘 리비전 자체는 별도 보드 프로파일이 필요
없다 - Arduino-ESP32 코어가 업로드/부팅 시 칩 리비전을 자동으로 인식해서 필요한
보정을 알아서 적용한다(리비전별로 "esp32dev" 외에 다른 보드를 고를 필요 없음).

## 대상 파일과 변경 내용

대상: `references/03 Arduino Programming Projects/05 Serial Communication Practical
Lessons/MechDog_Slave_Program/MechDog_uart/MechDog_uart.ino`

`switch(rec_data[0])`의 기존 `case 6`(배터리 잔량, 169-173행) 바로 뒤에 `case 7`
하나만 추가한다. 다른 파일(`HW_MechDog.*`, `Hiwonder.*` 등)은 건드리지 않는다 -
`MechDog` 클래스가 이미 `PowerBuzzer`를 public 상속하고 있어(`HW_MechDog.h:28`)
`mechdog.playTone(...)`을 이 파일 안에서 바로 호출할 수 있기 때문이다
(`Hiwonder.cpp:148` `void PowerBuzzer::playTone(int duty, int btime, bool state)`).

패치 내용은 `0001-add-buzzer-case7.patch`(unified diff, `references/` 원본 대비)에
있다. 적용 예시(팀이 실제로 적용하기로 결정했을 때):

```bash
git apply firmware/mechdog_d_uart/0001-add-buzzer-case7.patch
```

이 패치는 **2026-09-19에 검증**됐다: 깨끗한 원본 사본에 `git apply`로 적용한
결과가 실제 컴파일에 쓰인 파일과 SHA256까지 바이트 단위로 완전히 일치했다 -
자세한 빌드 절차와 결과는 아래 "2026-09-19 빌드 검증" 참고.

## 새 명령 형식

- 부저 1회 트리거(200ms, 논블로킹): `"CMD|7|1|$"`
- 별도 "끄기" 명령은 만들지 않았다 - 펌웨어가 200ms 뒤 자동으로 꺼지므로(`Buzzer_Task`의
  `userTone` 원샷 동작, `Hiwonder.cpp:119-146` 참고), PC 쪽에서 반복 전송을 멈추면
  그걸로 충분하다고 판단했다(`security-dashboard/app/robot_commands.py`의
  `_buzzer_loop`가 반복 전송을 담당).

## duty=500 값의 근거

임의로 정한 값이 아니라, 같은 파일의 저전압 경보 로직(`Hiwonder.cpp:129`
`ledcWrite(self->Buzzer_channel, 500)`)에서 실제로 소리가 나는 것으로 보이는 값을
그대로 재사용했다. **다만 경보음으로서 크기/음색이 적절한지는 실물에서 들어봐야
확정된다** - 추측하지 않는다.

## 충돌 검토 (2026-09-18)

- **기존 UART 명령과의 충돌**: `references/`의 `switch(rec_data[0])`은 `case
  1`~`6`까지만 쓴다(자세조정/동작그룹/이동제어/초음파/IMU/배터리). `case 7`은
  새 번호라 기존 case와 겹치지 않는다 - `diff -u`로 원본과 비교해도 `case 7`
  블록 추가 외에는 어떤 줄도 바뀌지 않았음을 확인했다(패치 파일 내용과 동일).
- **`"CMD|7|1|$"` 수신 시 실제로 `playTone(500, 200, false)`가 실행되는지 코드
  추적**: 파싱 규칙(`MechDog_uart.ino:63-69`)대로 따라가면 `"CMD|7|1|$"` →
  `cmd.indexOf('|')`=3, `cmd.indexOf('$')`=8 → 중간 문자열 `"7|1|"` 추출 →
  `while` 루프가 `rec_data[0]=7`, `rec_data[1]=1`, `index=2`로 채운다. 새로 추가한
  `case 7`의 조건 `index == 2 && rec_data[1] == 1`이 정확히 이 값과 일치해
  `mechdog.playTone(500, 200, false)`가 실행된다 - 코드만으로 재현 가능하며
  추측이 아니다.
- **기존 저전압 경고음과의 충돌 여부**: 핀/함수/전역변수 어느 것도 새로 만들지
  않았고 기존 `PowerBuzzer`의 것을 그대로 쓴다 - **자원 충돌은 없다.** 다만
  동작 우선순위상 상호작용은 있다: `Buzzer_Task`(`Hiwonder.cpp:119-146`)는
  매 루프마다 `if(bt_state){...저전압 경보...} else if(userTone){...케이스7
  요청...} else{정지}` 순서로 검사한다. 즉 **저전압 경보가 활성(`bt_state=true`)인
  동안에는 `case 7`이 호출한 `playTone()`의 요청이 즉시 소리 나지 않고 대기하다가,
  저전압 상태가 풀리면 그제서야 한 번 울린다.** 크래시나 핀 충돌은 없지만, 배터리가
  낮은 상태에서는 보안 경고음이 늦게(또는 저전압 경보 소리에 묻혀) 들릴 수 있다는
  점은 팀이 알고 있어야 한다.
- **`stand_two_legs`(`"CMD|2|1|6|$"`)/`normal_attitude`(`"CMD|2|1|16|$"`) 보존
  여부**: 패치는 `case 6`(배터리) 뒤, `case 2`의 `switch(actions)`와는 완전히
  분리된 위치에 `case 7`만 추가했다 - `diff -u` 결과 `case 2`/`actions_flg==1`
  블록은 한 글자도 바뀌지 않았다. 두 명령 모두 그대로 유지된다.

## 공식 라이브러리 확보 시도 (2026-09-18, 2026-09-19에 해결됨)

**2026-09-19 업데이트**: 아래 절차대로 팀이 라이브러리를 확보했고, 실제로
컴파일·링크까지 성공했다 - 결과는 "2026-09-19 빌드 검증" 절 참고. 이 절은
"어떻게/왜 이 라이브러리가 필요했는지"의 기록으로 남겨둔다.

Hiwonder 공식 문서([5. Arduino Programming Projects](https://docs.hiwonder.com/projects/MechDog/en/latest/docs/5.Arduino_Programming_Projects.html),
"5.1.3 Arduino IDE Introduction" 절)를 직접 확인했다 - 문서 원문:
"To run the program in this section, you need the MPU6050 driver library."이고,
설치 방법은 Arduino IDE의 `Sketch → Include Library → Add .ZIP Library`, 필요한
파일은 **`MechDog_Arduino.zip`**(quad_kinematics.h/mech_base_types.h가 여기
포함될 것으로 추정) + **MPU6050** 드라이버 라이브러리다. 두 파일 모두 문서가
직접 링크하는 곳은 하나의 Google Drive 공유 폴더뿐이다:

```
https://drive.google.com/drive/folders/1wJZCIvGLD6YQFeU7hys8D1eYQOjPmz6O?usp=sharing
```

- 이 링크는 공식 문서 본문에서 직접 인용한 것이고(추측/서드파티 검색 결과가
  아님), 접속 확인 결과 **HTTP 200으로 살아있다**(2026-09-18 기준).
- 문서에는 zip 파일의 정확한 파일명 목록·크기·버전·체크섬이 나와 있지 않고,
  "이 폴더 안에서 필요한 zip을 찾아 받으라"는 형태의 안내다.
- **이번 조사에서 다운로드하지 않았다.** Google Drive 폴더는 브라우저 UI
  기반 탐색이 필요해서(개별 파일의 직접 다운로드 링크·API 접근 권한이 없어)
  이 환경에서 자동으로 목록을 받아오거나 내려받을 수 없었다 - 그리고 설령
  받을 수 있었더라도, 공식 링크에서 나온 자료라 해도 **내용물을 열어보기
  전까지는 검증되지 않은 서드파티 아카이브**이므로 로봇 펌웨어 빌드에 임의로
  끼워 넣지 않았다.

**직접 받아야 할 절차(팀 확인 필요)**:
1. 위 Google Drive 링크를 브라우저로 연다.
2. 폴더 안에서 `MechDog_Arduino.zip`과 `MPU6050` 라이브러리(zip 또는 폴더)를
   찾아 다운로드한다.
3. 압축을 풀기 **전에** 먼저 zip 내부 파일 목록만 확인한다(예: 탐색기 미리보기,
   또는 `Expand-Archive -List`가 없는 구버전 PowerShell이면 7-Zip 등으로 목록만
   확인) - `quad_kinematics.h`/`mech_base_types.h`가 들어있는지, 실행파일(.exe)
   같은 의심스러운 내용물이 없는지 먼저 본다.
4. 확인되면 **Arduino IDE의 라이브러리 폴더 또는 이 저장소 밖의 별도 로컬 빌드
   환경에만** 설치한다(이 저장소 안에 커밋하지 않는다).
5. 저에게 파일명·크기·(가능하면 `certutil -hashfile <파일> SHA256`로 얻은)
   SHA256을 알려주시면, 그 값을 이 문서에 기록하고 실제 컴파일을 이어서
   시도하겠습니다.

## 원본 vs 패치본 컴파일 비교 (2026-09-18, 최종 결과는 2026-09-19 절 참고)

**이 절은 라이브러리 확보 전(컴파일조차 안 되던 시점)의 기록이다.** 실제로
성공한 최종 빌드 결과·수치는 아래 "2026-09-19 빌드 검증"을 봐야 한다.

**환경**: PlatformIO Core 6.1.19(이미 설치돼 있던 것) + 새로 설치한
`espressif32` 플랫폼(7.1.3), `framework-arduinoespressif32`, `toolchain-xtensa-esp32`.
`firmware/mechdog_d_uart/build/`(신규, `.pio/`는 `.gitignore`에 이미 등록돼
있어 커밋되지 않음) 아래 **두 개의 독립된 PlatformIO 프로젝트**를 만들어
순서대로(원본 먼저, 패치본 다음) 빌드했다:

- `pio_project_original/` - `references/`의 `MechDog_uart` **원본을 한 글자도
  안 바꾸고** 그대로 복사한 스케치(`diff -q`로 원본과 동일 확인)
- `pio_project/` - `case 7`이 추가된 패치본 스케치

**1) 원본 컴파일 결과 — 실패** (`pio_project_original/build_original.log`,
untracked):
```
src/HW_MechDog.h:3:10: fatal error: quad_kinematics.h: No such file or directory
src/MechDog_uart.ino:1:10: fatal error: mech_base_types.h: No such file or directory
```
**이 두 헤더는 `references/03 Arduino Programming Projects/` 안의 모든 예제가
공통으로 `#include`하지만 이 저장소 어디에도 실제 파일이 없다**(`find`/`grep`로
저장소 전체 확인) - 즉 **원본 예제부터가 위 "공식 라이브러리" 없이는 컴파일이
안 되는 상태**임을 패치 이전에 먼저 확인했다.

**2) 패치본 컴파일 결과 — 동일한 지점에서 동일한 이유로 실패**
(`pio_project/build_patched.log`, untracked): 완전히 같은 두 줄의
`fatal error`가 그대로 재현됐다 - **`case 7` 패치가 새로운 오류를 만들지
않았다.**

**3) 바이너리 크기·경고 비교**: 두 빌드 모두 링크 단계 전에 멈춰서
**`.elf`/`.bin`이 하나도 생성되지 않았다** - 따라서 최종 바이너리 크기
비교는 이번 단계에서 할 수 없다(위 라이브러리 확보 후 재시도 필요).
다만 부분적으로 컴파일된 개별 오브젝트 파일로 봤을 때:
- 두 프로젝트 모두 `Hiwonder.cpp.o`, `Servo.cpp.o`는 정상적으로 컴파일 완료됨
  (이 두 파일은 문제의 헤더를 직접 include하지 않음).
- 패치본 빌드에서만 추가로 `pwm_servo.cpp.o`, `WMMatrixLed.cpp.o`까지
  컴파일이 진행돼 `-Wreturn-type` 경고 3건이 로그에 나타났다(`pwm_servo.cpp`의
  일부 함수가 모든 경로에서 값을 반환하지 않음) - 이 경고는 **`case 7` 패치와
  무관하다**: `pwm_servo.cpp`는 두 프로젝트에서 `diff -q`로 100% 동일한 파일임을
  이미 확인했고, SCons가 여러 파일을 병렬 컴파일하다 어느 파일까지 끝내고
  오류로 멈추는지가 매번 달라지는(비결정적) 스케줄링 때문에 원본 빌드에서는
  이 경고가 나올 기회조차 없었을 뿐이다 - 같은 파일이므로 원본에서도 끝까지
  가면 동일하게 나타난다.

**결론**: `case 7` 패치는 원본 대비 **새로운 컴파일 오류나 경고를 추가하지
않았다.** 다만 실제 "빌드 성공" 확인은 Hiwonder 기반 라이브러리 확보 후로
남아있다.

## 2026-09-19 빌드 검증 — 라이브러리 확보 및 링크 성공

### A. 변경 목적

- UART로 `"CMD|7|1|$"`를 받으면(조건: 필드 2개, 두 번째 필드가 `1`) 조건에
  따라 `mechdog.playTone(500, 200, false)`를 실행하는 패치다(위 "대상 파일과
  변경 내용" 참고, 원본 대비 6줄 추가뿐).
- **빌드 성공과 실제 하드웨어 동작 검증은 다르다.** 아래는 전부 로컬
  컴파일·링크 결과이며, **실물 업로드·부저 실제 동작 시험은 아직 하지
  않았다.**

### B. 검증된 빌드 환경

| 구성요소 | 버전 |
|---|---|
| PlatformIO Core | 6.1.19 |
| espressif32 플랫폼 | 7.1.3 |
| framework-arduinoespressif32 | 4.20017.260907+sha.dcc1105b |
| toolchain-xtensa-esp32 | 8.4.0+2021r2-patch5 |
| 보드 | `esp32dev` (Espressif ESP32 Dev Module) |
| Flash | DIO / 40MHz / 4MB |
| 파티션 | 표준 스킴이 아닌 커스텀 단일 factory 파티션 구조(아래 D 참고) |

### C. 라이브러리 준비

라이브러리 원본(`MechDog_Arduino.zip`/`MPU6050.zip` 및 그 압축 해제물)은
**이 저장소에 포함하지 않는다** - Hiwonder 공식 배포물이고 저장소 밖(팀
공유 폴더 등)에 각자 받아서 로컬에만 둔다.

빌드 전에 환경변수 하나를 설정해야 한다(PowerShell 예시, 실제 경로는
각자 라이브러리를 받은 위치로 교체):

```powershell
$env:MECHDOG_ARDUINO_ARCHIVE="C:/path/to/MechDog_Arduino/src/esp32/MechDog_Arduino.a"
```

`firmware/mechdog_d_uart/tools/link_mechdog_archive.py`(아래 E 참고)가 이
환경변수를 읽어서:
- 설정 안 돼 있으면 → 빌드 중단 + 위 설정 방법 출력
- 경로의 파일이 없으면 → 중단
- 파일명이 정확히 `MechDog_Arduino.a`가 아니면 → 중단
- SHA256이 아래 값과 다르면 → 중단

**요구되는 `MechDog_Arduino.a` SHA256**: `1fdad476172eebf62bdc554bf3d240e0579011a88d4563ba5f1cceeb47c09a0e`

**라이브러리 원본은 이 스크립트에서 읽기만 한다 - 복사·이동·수정하지 않는다.**

### D. 파티션 구조

실제 백업(`mechdog_d_factory_backup_A.bin`)에서 읽기 전용으로 파싱한 값
그대로 `firmware/mechdog_d_uart/partitions/partitions_mechdog_d.csv`에
커스텀 파티션 테이블로 저장돼 있다(표준 Arduino-ESP32 스킴 중 정확히
일치하는 게 없어서 - 위 "확인된 실제 하드웨어"의 정정 참고):

| 이름 | offset | size |
|---|---|---|
| `nvs` | `0x9000` | `24K`(`0x6000`) |
| `phy_init` | `0xF000` | `4K`(`0x1000`) |
| `factory` | `0x10000` | `0x1F0000`(1984K, 2,031,616 bytes) |
| `vfs` | `0x200000` | `2M`(`0x200000`) |

`gen_esp32part.py`로 빌드가 생성한 `partitions.bin`을 다시 CSV로
역디코딩해서 이 값과 완전히 일치함을 확인했다(2026-09-19).

### E. 빌드 절차

1. 원본에 패치 적용(팀이 실제로 적용하기로 결정했을 때만):
   ```bash
   git apply firmware/mechdog_d_uart/0001-add-buzzer-case7.patch
   ```
2. PlatformIO 프로젝트의 `platformio.ini`에서 다음 두 정식 경로를 참조한다
   (레포 루트 기준 상대경로 - 개인 PC 절대경로 없음):
   ```ini
   board_build.partitions = firmware/mechdog_d_uart/partitions/partitions_mechdog_d.csv
   extra_scripts = firmware/mechdog_d_uart/tools/link_mechdog_archive.py
   ```
   (실제 프로젝트 위치에 따라 상대경로 깊이는 조정)
3. 위 C의 환경변수를 설정한 뒤:
   ```bash
   pio run -t clean
   pio run -v
   ```
4. **업로드 명령(`pio run -t upload`, `esptool.py ... write_flash` 등)은
   여기 실행 절차로 넣지 않는다 - 별도 승인 전까지 업로드 금지.**

### F. 검증 결과 (2026-09-19, 환경변수 방식으로 재현성까지 재확인)

- 원본·패치본 **둘 다 링크 성공**, `firmware.elf`/`firmware.bin` 생성됨
- **undefined reference 0건**(둘 다) — 이전에 `quad_kinematics::*` 심볼이
  없어서 실패하던 문제 해결
- **multiple definition / ABI 오류 0건**
- 최종 링크 명령에 `MechDog_Arduino.a`(whole-archive) **정확히 1회** 포함
- 원본 `firmware.bin`: **339,824 bytes**
- 패치본 `firmware.bin`: **339,904 bytes**
- **Flash 차이: +80 bytes**(패치본이 큼 - `case 7` 블록 하나 분량, 예상 범위)
- RAM 사용량: **25,460 / 327,680 bytes**(7.8%, 원본·패치본 동일)
- Flash 사용량: 16.7%(원본 339,461 / 2,031,616B, 패치본 339,541 / 2,031,616B)
- `case 7` 외 소스 차이 없음(`HW_MechDog.*`, `Hiwonder.*`, `Servo.*`,
  `WMMatrixLed.*`, `action.h`, `pwm_servo.*` 전부 바이트 단위 동일 재확인)
- `bootloader.bin`·`partitions.bin`은 원본·패치본이 **SHA256까지 완전히 동일**
  (`case 7`이 이 영역에 영향을 주지 않는다는 근거)
- 환경변수 방식으로 전환한 뒤 재빌드해도 `firmware.bin` SHA256이 이전
  성공 빌드와 **완전히 동일**(바이트 단위 재현성 확인)

### G. 알려진 기존 경고 (패치와 무관, 원본에도 있던 것)

- `PI` 매크로 재정의 2건(ESP32 코어 vs 라이브러리 헤더)
- `typedef` 무시 경고 1건
- `pwm_servo.cpp`의 `-Wreturn-type` 3건
- 위 6건 전부 원본·패치본에 동일하게 존재 - `case 7`이 추가한 경고는 없다.

## UART 연결 경로 비교: 외부 USB-TTL(옵션 A) vs <PORT>/UART0 확장(옵션 B) — 2026-09-18

로봇이 A 옆에 고정 배치라 "추가 하드웨어 없이 <PORT>"를 우선 검토했지만, 아래
근거로 **옵션 A(외부 USB-TTL을 GPIO32/33에 직결)를 권장**한다.

### 코드로 확인한 사실

- `MechDog_uart.ino`는 `HardwareSerial mySerial(1)`(UART1, GPIO32/33)만 만들고,
  이 스케치 전체에서 기본 `Serial`(UART0) 객체는 **단 한 번도 쓰지 않는다**
  (`grep`으로 `Serial.`(mySerial 제외) 사용처가 전무함을 확인 - `#include
  "HardwareSerial.h"`만 있고 실제 `Serial.begin()`/`Serial.print()` 호출이
  없다). 즉 **이 참고 예제 기준으로는** UART0가 완전히 비어있어, 새로 하나
  더 여는 것 자체는 이 파일과 충돌하지 않는다.
- 하지만 이건 "참고 예제" 기준이다. 실제 로봇에 올라간 출고 펌웨어가 이 예제와
  정확히 같은지는 **아직 확인되지 않았다**(체크리스트 3번, 아래에서도 다시
  강조). 다른 예제(`offset_setting.ino` 등)는 `Serial.begin(115200)`으로 UART0를
  디버그 로그용으로 쓴다 - 출고 펌웨어가 그런 코드를 포함하고 있다면 얘기가
  달라진다.
- `mechdog.action_run()`은 `run_status()==0`일 때만 실행되고 이미 실행 중이면
  조용히 무시한다(`HW_MechDog.cpp:227-231`) - 즉 UART0/UART1 양쪽에서 거의
  동시에 같은 동작 명령이 들어와도 펌웨어 차원에서 중복 실행을 막아주는
  안전판이 이미 있다. 다만 이건 "동작"에만 해당하고, **부저는 이런 보호가
  없다**(매번 새로 `playTone()`을 트리거함).

### 각 옵션 평가

| 항목 | A. 외부 USB-TTL → GPIO32/33 | B. 펌웨어에 UART0(<PORT>) 파서 추가 |
|---|---|---|
| 추가 하드웨어 | 3.3V USB-TTL 어댑터 1개 + 점퍼선 3가닥(RX/TX/GND) 필요 | 없음(기존 <PORT> 재사용) |
| 펌웨어 변경 범위 | **없음**(이미 검토한 `case 7` 부저 패치가 전부) | `rec_data`/`index` 등 파싱 상태를 UART0/UART1 **별도로** 둬야 함(두 포트에서 동시에 프레임이 들어올 수 있어 하나의 전역 버퍼를 공유하면 깨짐) - 최소 부저 패치보다 변경 범위가 커짐 |
| DTR/RTS 자동 리셋 위험 | GPIO32/33은 EN/IO0(자동 리셋 회로)와 무관한 일반 GPIO라 **이 경로로는 리셋이 걸리지 않는다** | <PORT>는 CH340 기반 자동 리셋 회로가 물려 있는 바로 그 포트다. 팀이 이미 `esptool` 사용 시 리셋→자세 풀림을 실측했는데, **`security-dashboard`가 평상시(업로드가 아닌 일반 통신) <PORT>를 열 때도 같은 회로 때문에 리셋이 걸릴 수 있는지는 이번에 실물로 검증하지 못했다** - 만약 걸린다면 대시보드가 시리얼을 열 때마다(또는 재연결마다) 로봇이 넘어질 위험이 있어 훨씬 심각하다 |
| 기존 출고 펌웨어와의 관계 | 기존 펌웨어를 몰라도(체크리스트 3번 미해결이어도) UART1 CMD 파서가 이미 있다는 전제만 맞으면 그대로 활용 가능 | 출고 펌웨어의 실제 소스를 모르는 상태에서 UART0 파서를 "추가"해야 해서, 우리가 갖고 있지 않은 코드에 손을 대는 셈 - 위험이 더 크다 |
| 개발/디버깅 편의 | <PORT>는 Arduino IDE 시리얼 모니터/재플래싱용으로 자유롭게 남겨둘 수 있음(대시보드는 별도 포트 사용) | <PORT> 하나를 대시보드와 개발자가 동시에 못 씀(포트 점유 충돌) |

### 결론 및 남은 확인

**현재 근거로는 옵션 A(외부 USB-TTL)를 권장한다** - 펌웨어 변경 범위가
`case 7` 부저 패치 하나로 끝나고, 팀이 이미 실측한 DTR/RTS 리셋 문제를
원천적으로 피할 수 있기 때문이다. 다만 이건 "구현"이 아니라 "권장"이며,
아래가 확인돼야 실제로 채택할 수 있다:
- GPIO32/33이 물리적으로 접근 가능한 커넥터/핀헤더로 나와 있는지 (체크리스트 2번)
- 실제 출고 펌웨어가 UART1 CMD 파서를 포함하는지 (체크리스트 3번)
- (옵션 B를 계속 고려한다면) <PORT>를 일반 통신으로 열었을 때도 DTR/RTS 리셋이
  걸리는지 실물로 확인 - 이건 이번 조사에서 <PORT>로 아무것도 보내지 말라는
  제한 때문에 검증하지 못했다.

옵션 B의 펌웨어 확장 코드는 이번 단계에서 작성하지 않았다 - "근거 없이
구현하지 말라"는 지시에 따라, 위 위험(자동 리셋, 버퍼 분리 필요성)이 해소되지
않은 채로 코드부터 만들지 않았다.

## 백업 파일 취급

`mechdog_d_factory_backup_A.bin`은 이 저장소에 포함하지 않았다(포함한 적도
없음) - 로봇 개체별 고유 캘리브레이션/시리얼 데이터가 들어있는 바이너리라
Git에 올릴 대상이 아니라고 판단했다. 로컬에 안전하게 별도 보관(예: 팀 공유
드라이브의 비공개 폴더)을 권장한다.

## 적용 전 필수 확인 (팀 확인 사항)

1. ~~백업~~ — **완료**: `mechdog_d_factory_backup_A.bin`(4,194,304 bytes) 확보됨.
2. **핀 배선 확인**: 이 프로토콜은 `HardwareSerial mySerial(1)`로 GPIO32(RX)/33(TX)를
   쓴다(`MechDog_uart.ino:3-4,17`) - 동봉 USB 케이블(CH340, <PORT>)이 연결되는
   UART0(플래싱/기본 시리얼용)과 다른 물리 핀일 가능성이 높다. 실제로 GPIO32/33이
   어떤 커넥터로 나와 있는지 실물을 보고 확인해야 한다.
3. **현재 로봇에 올라간 펌웨어가 이 참고 예제와 동일한지 확인**: 출고 펌웨어가 GitHub
   공개 예제와 정확히 같다는 보장이 없으므로, 이 패치를 그대로 적용하기 전에 실제
   설치된 소스와 비교할 것.
4. ~~누락된 Hiwonder 기반 라이브러리 확보~~ — **완료(2026-09-19)**: 팀이
   `MechDog_Arduino`/`MPU6050`을 확보했고, 원본·패치본 모두 컴파일·링크까지
   성공했다. 자세한 내용은 "2026-09-19 빌드 검증" 참고. 남은 건 실물 업로드
   승인 여부(이 문서의 다른 미확인 항목들)뿐이다.
5. **서보 자세 유지 관련 안전 조치**: 팀이 이미 실측 확인한 대로, `esptool`이
   업로드 때마다 DTR/RTS 자동 리셋 시퀀스로 ESP32를 재시작시키는 순간 서보 PWM
   출력이 끊겨 다리 자세 유지가 풀린다. **업로드/리셋을 시도하는 매 순간마다
   (이번 부저 패치든 다른 어떤 펌웨어 작업이든) 로봇을 세워두지 말고, 사람이
   몸통을 손으로 받치거나 스탠드/거치대로 다리에 체중이 실리지 않게 지지한 뒤에만
   진행한다.** 시리얼 모니터를 여는 것만으로도 자동 리셋 회로가 걸리는 보드가
   있으므로, 업로드가 아니더라도 <PORT>로 처음 연결할 때는 항상 몸통을 지지한
   상태로 시작한다.
6. **UART 연결 경로 확정**: 위 "UART 연결 경로 비교" 결과 옵션 A(외부 3.3V
   USB-TTL을 GPIO32/33에 직결)를 권장하지만, 최종 확정 전에 GPIO32/33 실물
   접근성(2번 항목)과 실제 출고 펌웨어 일치 여부(3번 항목)를 먼저 봐야 한다.
   옵션 B(<PORT> 재사용)를 계속 검토한다면, **<PORT>를 일반 통신으로 열었을 때도
   DTR/RTS 자동 리셋이 걸리는지**를 5번 항목과 같은 방식으로 몸통을 지지한
   채 먼저 실물로 확인해야 한다(이번 조사에서는 "<PORT>로 아무것도 보내지
   말라"는 제한 때문에 검증하지 못했다).

이 여섯 가지가 확인되기 전까지는 패치를 만들기만 하고 적용/업로드하지 않는다.
