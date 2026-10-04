# MechDog D 로봇 MicroPython `main.py` (실물 적용 버전)

D 로봇(ESP32, Hiwonder MechDog MicroPython 펌웨어)의 `/main.py`에 **실제로 적용된** 소스다.
옆 폴더 `firmware/mechdog_d_uart/`는 Arduino C++ 패치 제안(실물 미적용)이고 이 폴더와는 별개다.
Arduino 예제나 패치를 이 MicroPython 펌웨어에 업로드하지 않는다.

## 적용 버전

| 항목 | 값 |
|---|---|
| 버전 | 눈 LED 버전 (부저 3회 버전 + WiFi `CMD|4|3|R|G|B|$` 눈 RGB) |
| 적용 일시 | 2026-10-03 23:17 (USB 시리얼 friendly REPL로 전송 → readback → rename 교체) |
| 적용 파일 크기 | 11,451 bytes, 줄바꿈 CR(`\r`)만 사용 |
| 적용 파일 SHA-256 | `8e043e61bdcd99a1a06d26e5b2732597da922a614463b9208d47fbbae51db49a` |
| 로봇 쪽 확인 | 교체 직후 로봇에서 계산한 `/main.py` SHA-256이 위 값과 일치 (2026-10-03).<br>2026-10-04에는 REPL로 크기 11,451 bytes만 재확인(해시는 재확인 안 함) |

### 이 저장소 사본과 적용 파일의 차이 — WiFi 비밀번호 한 줄
- 이 폴더의 `main.py`는 13행 `WIFI_PASSWORD = "CHANGE_ME"`만 다르다. 비밀번호는 Git에 넣지 않는다.
- 저장소 사본: 11,452 bytes, SHA-256 `e2360820e59df2157a5064d2a075010e69ef24ec54239e4a124fc997a36fc25f`
- `CHANGE_ME`를 현장 핫스팟 비밀번호로 바꾸면 적용 파일과 바이트 단위로 같아진다(위 11,451 bytes / `8e043e61…`로 검증).
  비밀번호를 넣은 파일은 커밋하지 않는다.
- CR 줄바꿈을 그대로 보존하려고 `.gitattributes`에 `main.py -text`를 둔다(Git이 줄바꿈을 바꾸면 해시가 달라진다).

## WiFi(UDP 9027) 명령 처리 — 원본 대비 추가된 부분

| 명령 | 동작 | 비고 |
|---|---|---|
| `CMD|0|$` | `wifi.send_ID()` | 원본 그대로. 눈·자세·부저와 무관 |
| `CMD|2|1|6|$` | 두 발 서기 (`stand_two_legs`) | 원본 그대로. 실행 전 `set_default_pose` |
| `CMD|2|1|99|$` | 기본 자세만 (`set_default_pose`) | 원본 그대로(99는 동작 목록에 없어 동작은 생략) |
| `CMD|7|1|$` | 부저 짧게 3회 (800 Hz, 100 ms, 간격 0.2 s) | **추가**. 경고 상태가 0일 때만 울리고 1로 바꿈 |
| `CMD|7|0|$` | 부저 경고 상태 해제 (소리 없음) | **추가** |
| `CMD|4|3|R|G|B|$` | 초음파 모듈 RGB 눈 색 `i2csonar.setRGB(0,R,G,B)` | **추가**. BLE 쪽에는 원래 있던 기능을 WiFi에도 연결 |

대시보드가 쓰는 눈 색 RGB(실물 보고 조정): 파랑 `0,0,255` / 빨강 `255,0,0` / 주황 `255,20,0` / 노랑 `255,130,0`.
이 펌웨어는 UDP 응답을 보내지 않는다. 대시보드의 "전송 성공"은 로봇이 받았다는 증거가 아니다.

## 로봇 안의 백업 파일 (2026-10-03 기준)

| 로봇 파일 | 내용 | 확인된 값 |
|---|---|---|
| `/main.py` | 눈 LED 버전 (현재 적용) | 11,451 B, `8e043e61…` |
| `/main_three_beep_backup.py` | 직전 버전: 부저 3회, 눈 LED 없음 | 11,152 B, SHA-256 `a1dbaf5c46a00be8971d21e316770e6df83e41ef6c99414c18dcc86a22e04f07` (교체 직후 로봇에서 확인) |
| `/main_single_beep_backup.py` | 그 이전: 부저 1회 버전 | 이 문서에서는 해시 미기재 |
| `/main_factory_original.py` | 제조사 원본 | 이 문서에서는 해시 미기재 |

## 복원 방법 (눈 LED 버전 → 부저 3회 버전)

로봇 동작이 이상할 때만 하고, 진행 전 팀/담당자 승인을 받는다.

1. 다리를 바닥에서 띄워 고정하고 USB 시리얼(CH340)로 friendly REPL에 접속한다.
   raw REPL, mpremote, soft reset, `machine.reset()`, Ctrl-C는 쓰지 않는다(실행 중인 루프를 깨뜨림).
2. 한 줄씩 짧게 입력하고, 에코가 입력과 정확히 같을 때만 Enter를 누른다(긴 줄은 끝부분이 유실된 적 있음).
3. 백업이 있고 해시가 맞는지 먼저 확인한다:
   ```python
   import os, uhashlib, ubinascii
   os.listdir('/')
   h = uhashlib.sha256(); f = open('/main_three_beep_backup.py', 'rb'); h.update(f.read()); f.close()
   ubinascii.hexlify(h.digest())        # a1dbaf5c46a00be8... 이어야 함
   ```
4. 교체한다(현재 버전은 지우지 않고 이름만 바꿔 둔다):
   ```python
   os.rename('/main.py', '/main_eye_failed.py')
   os.rename('/main_three_beep_backup.py', '/main.py')
   os.listdir('/')
   ```
5. 로봇 전원을 껐다 켠다(리셋 명령 대신 사용자가 직접 전원 조작). 부팅 후 WiFi IP가 바뀔 수 있으니 REPL로 다시 확인한다.
6. 대시보드는 그대로 써도 되지만 눈 색 명령(`CMD|4|…`)은 무시된다(부저 3회 버전에는 WiFi 눈 처리 없음).

다시 눈 LED 버전으로 올릴 때는 이 폴더 `main.py`의 `CHANGE_ME`를 현장 비밀번호로 바꾼 사본을 만들고,
크기 11,451 B / SHA-256 `8e043e61…`인지 확인한 뒤 같은 방식(전송 → readback 해시 확인 → rename)으로 교체한다.
