# MechDog B 본체 — 센서 브리지 펌웨어

본체(ESP32-WROOM-32D)의 **터치 센서**와 **초음파 센서** 값을 Wi-Fi/MQTT로 발행한다.
게이트 스탠드의 RPi5(대화 유닛)가 이걸 구독해서 PTT 청취 창과 재실 판정에 쓴다.

| 센서 | 용도 | 요구사항 |
|---|---|---|
| 터치 (GPIO 33) | 대화 개시 PTT 트리거 | `FR-B-1003` (**M**, 대화 개시의 유일한 경로) |
| 초음파 (I2C) | 발화 없을 때 방문자 재실 확인 | `FR-B-1001` (S) |

이동·동작 그룹 코드는 **없다**. B는 걷지 않고(`LOG-09`), 제스처·눈 색깔은 5주 범위에서
제외됐다(`LOG-20`).

---

## 왜 UART가 아니라 무선인가

본체의 외부 확장 포트가 **GPIO 32/33**인데, **터치 센서도 GPIO 33**을 쓴다.

| 근거 파일 | 내용 |
|---|---|
| `Hiwonder.h` | `#define Touch_Pin 33` |
| `MechDog_uart.ino` | `#define txPin 33` (UART 송신) |
| `ultrasonic_ranging.ino` | `WMMatrixLed tm(32,33)` (도트매트릭스도 같은 포트) |

즉 UART로 배선하면 **터치 PTT와 핀이 물리적으로 겹친다.** 무선으로 가면 이 충돌이
사라지고, "물리 커넥터가 어디인지 모르겠다"는 문제도 같이 없어진다. (`LOG-21`, `LOG-22`)

---

## 0. 보드 식별 — **벤더 자료를 믿지 말 것**

| | |
|---|---|
| 실제 칩 | **ESP32-WROOM-32D** (일반 ESP32) |
| Arduino 보드 선택 | **ESP32 Dev Module** — `esp32:esp32:esp32` |
| ESP32 코어 버전 | **2.0.17 고정** (3.x 는 `ledcSetup` 제거로 Hiwonder 라이브러리가 안 빌드됨) |
| Wi-Fi | **2.4 GHz 전용** — 5 GHz SSID 로는 무한 재시도만 한다 (LOG-28 에서 며칠 소요) |
| USB | 네이티브 USB 없음 → 보드에 **USB-시리얼 브릿지**(CP2102/CH340)가 따로 있다.<br>파이·PC 에 꽂으면 **`/dev/ttyUSB0`** 으로 잡힌다 (`ttyACM0` 아님) |

> ⚠️ **벤더 소개 자료에는 "ESP32-S3 dual-mode SoC" 라고 적혀 있는데 이 실물과 다르다.**
> 최신 개정판 기준 문서로 보인다. S3 로 알고 Arduino IDE 에서 보드를 잘못 고르면
> **빌드는 통과하는데 실행이 안 되는** 상태가 되니 주의. 근거: `esp32:esp32:esp32` 로 빌드한
> 펌웨어가 실물에서 정상 동작 중(LOG-28) — S3 였다면 바이너리가 돌지 않는다.

---

## 1. 준비

1. **Arduino IDE** + **ESP32 보드 패키지** 설치
2. 라이브러리 매니저에서 **`PubSubClient`** (Nick O'Leary) 설치
3. 나머지 Hiwonder 라이브러리(`Hiwonder.*`, `HW_MechDog.*`, `Servo.*`, `WMMatrixLed.*`,
   `pwm_servo.*`, `action.h`)는 이 폴더에 이미 같이 들어있다 — 벤더 예제에서 그대로 복사한 것

## 2. 접속 정보 채우기 (`secrets.h`)

Wi-Fi 비밀번호·브로커 주소는 **`secrets.h`** 에 따로 둔다. 이 파일은 `.gitignore` 에 등록돼
있어 **깃허브에 올라가지 않는다.** 저장소를 새로 받았다면:

```bash
cd firmware/mechdog_b_body
cp secrets.example.h secrets.h   # 그리고 본인 값으로 채운다
```

```cpp
#define SECRET_WIFI_SSID "..."   // ⚠ 반드시 2.4GHz SSID
#define SECRET_WIFI_PASS "..."
#define SECRET_MQTT_HOST "..."   // 브로커(host1) IP
#define SECRET_MQTT_PORT 1883
```

> **중요 1**: 본체와 RPi5가 **같은 네트워크(같은 브로커)** 에 붙어야 한다.
>
> **중요 2**: 본체 ESP32-WROOM-32D 는 **2.4GHz 전용**이다. 5GHz SSID(`..._5G_...`)를 넣으면
> 시리얼에 `[wifi] connecting...` 만 무한 반복된다 (`09_작업기록 LOG-28`).

## 3. 업로드

- 보드: **ESP32 Dev Module**
- 속도: 115200
- 업로드 후 **시리얼 모니터(115200)** 를 열면 연결 상태 로그가 찍힌다

```
=== MechDog B body sensor bridge (b-body-1.0) ===
[init] sensors ready
[wifi] connecting to ... 
[mqtt] connected
[touch] {"seq":1,"uptime_ms":8123,"touch":false}
```

---

## 4. 발행 토픽 (RPi5 쪽 구독 대상)

> 공용 스키마 네임스페이스(`mechdog/v1/#`)를 **쓰지 않는다.** 공용 메시지는
> `additionalProperties:false` 로 엄격 검증되므로, 스키마에 없는 센서값을 v1에 끼워 넣으면
> 다른 노드의 검증을 깨뜨린다. 그래서 `mechdog/internal/...` 로 분리했다.

| 토픽 | 시점 | retain | 페이로드 |
|---|---|:--:|---|
| `mechdog/internal/b/touch` | **상태 변화 시에만** | ✅ | `{"seq":12,"uptime_ms":34567,"touch":true}` |
| `mechdog/internal/b/ultrasonic` | 300ms 주기 | ✅ | `{"seq":120,"uptime_ms":34567,"distance_cm":142,"valid":true}` |
| `mechdog/internal/b/status` | 접속 시 + LWT | ✅ | `{"online":true,"fw":"b-body-1.1","uptime_ms":8000}` |

## 4-b. 구독 토픽 — 눈 LED (v1.1 신설)

| 토픽 | 방향 | 페이로드 |
|---|---|---|
| `mechdog/internal/b/eye` | **RPi5 → 본체** | `{"state":"listening"}` 또는 `{"r":255,"g":200,"b":0}` |

방문자가 "지금 말해도 되는지"를 알 방법이 음성밖에 없으면 시끄러운 정문에서는 알 수 없다.
눈 색이 그 역할을 한다. **배선 추가는 없다** — 눈 RGB 2개는 초음파 센서 모듈에 달려 있어
이미 쓰던 `UltrasoundSonar` 객체의 `setRGB()` 로 제어된다.

| state | 색 | 의미 | 전이 시간 |
|---|---|---|---|
| `idle` | 🟡 노랑 `255,200,0` | 대기 | 400ms |
| `listening` | 🟢 초록 `0,255,0` | **지금 말하세요** | 200ms (즉각 반응) |
| `thinking` | 🟢🟠 **초록 ↔ 주황 왕복** | 처리 중 | 왕복 1회 2,000ms (계속 반복) |
| `speaking` | 🔵 파랑 `0,0,255` | 안내 중 | 300ms |
| `error` | 🔴 빨강 `255,0,0` | 재질문/오류 | 120ms |

- 전이는 **논블로킹 선형 페이드**다. `delay()` 로 돌리면 그 사이 `mqtt.loop()` 가 멈춰
  터치 발행이 밀리고 keepalive(5초)를 놓쳐 LWT 가 잘못 뜬다.
- **처리 중(`thinking`)만 색이 고정되지 않고 초록↔주황을 계속 오간다.** 고정색이면 멈춘 것처럼
  보이는데 실제로는 STT 가 도는 구간이라, 방문자에게 "기다리는 중"임을 보여야 한다.
  `cos` 보간이라 양 끝(초록·주황)에서 변화가 느려져 숨 쉬듯 흐른다. 듣는중(초록)에서
  넘어오면 왕복이 초록에서 시작하므로 이음매가 보이지 않는다.
  주기는 `EYE_THINK_CYCLE_MS`(기본 2,000ms) — 너무 빠르면 초조해 보이고 느리면 멈춘 것 같다.
- LED 기록은 **25ms 로 제한**한다. 눈 RGB 가 초음파와 **같은 I2C 버스**라, 매 루프 쓰면
  거리 측정이 밀린다.
- `{"r":..,"g":..,"b":..}` 는 **재업로드 없이 실물 색을 맞추기 위한** 경로다.
  노랑(대기)과 주황(처리중)이 인접색이라 실물에서 구분이 안 될 수 있다.
- RPi5 쪽 발행은 `dialog/eye.py` — `python3 eye.py demo` 로 전체 시퀀스를 한 바퀴 돌린다.

> **부저는 쓰지 않는다.** 저전력 "삐" 알람을 끄려고 `PowerBuzzer` 를 쓰려 했으나
> `Buzzer_init()` 이 `protected` 라 `MechDog_init()` 으로만 초기화된다. 서보 발열 때문에
> 그걸 부르지 않으므로(LOG-30) **부저 태스크가 아예 뜨지 않는다 → 이 펌웨어는 삐 소리를
> 낼 수 없다.** 효과음(띠링)은 전부 RPi5 의 USB 스피커로 낸다.

### 터치

- `touch:true` = 지금 만지고 있음 / `false` = 뗐음
- **변화가 있을 때만** 보낸다. `retain`을 켜둬서 RPi5가 재시작해도 현재 상태를 즉시 알 수 있다
- 디바운스는 벤더 `Button` 클래스가 처리 (20ms 폴링, 3틱 이상 눌림에서 true)

### 초음파

- 단위는 **cm** (벤더 예제가 15·40 같은 값과 비교하고, `MechDog_uart.ino`가 `getDistance()*10`으로
  mm 변환해 보내는 것에서 역산) → **실물로 한 번 더 검증할 것**
- `FR-B-1001`의 임계 1.5m = **150 cm**
- `valid:false`면 측정 실패(범위 밖)이므로 **재실 판정에 쓰지 말 것** — `BR-B-15`의
  "연속 3회 미감지" 카운트에 넣을지 여부는 RPi5 쪽에서 정책적으로 결정

### status / LWT

본체가 죽거나 Wi-Fi가 끊기면 브로커가 **자동으로** `{"online":false}` 를 발행한다(LWT).
`FR-B-1005`(본체 링크 감시)를 별도 하트비트 구현 없이 이걸로 대체한다 —
RPi5는 `online:false`를 받으면 **PTT 모드 → VAD 모드로 폴백**하면 된다 (`AC-1005-2`).
keepalive 5초라 대략 **7.5초 안에** 감지된다.

---

## 5. 동작 확인 (RPi5나 PC에서)

```bash
mosquitto_sub -h <브로커IP> -t 'mechdog/internal/b/#' -v
```

- 손으로 로봇 등을 만졌다 뗐다 하면 `touch` 메시지가 true/false로 번갈아 떠야 한다
- 손을 센서 앞에 가까이 대면 `distance_cm` 값이 줄어야 한다
- 본체 전원을 뽑으면 7~8초 뒤 `status` 가 `online:false` 로 바뀌어야 한다

---

## 6. 실물에서 확인해야 할 것 (미검증)

| # | 항목 | 왜 |
|---|---|---|
| 1 | `getDistance()` 단위가 정말 cm인지 | 코드 근거로 역산한 것이라 실측 확인 필요 |
| 2 | 측정 실패 시 반환값 | 0을 주는지 다른 값을 주는지 미확인. 현재는 1~400cm 밖이면 `valid:false` 처리 |
| 3 | Wi-Fi 켠 상태에서 I2C 초음파 읽기가 안정적인지 | ESP32는 무선과 다른 주변장치가 타이밍을 다툴 수 있음 (카메라+블루투스 충돌과 같은 계열의 문제) |
| 4 | `MechDog_init()` 없이 초음파만 초기화해도 되는지 | 지금은 벤더 예제대로 둘 다 호출. 생략 가능하면 서보 전력 소모를 줄일 수 있음 |
| 5 | 1.5m 거리에서 실제로 감지되는지 | 초음파 지향각이 좁고(약 15°) 두꺼운 의류는 반사가 약함 (`FR-B-1001` 미해결 항목) |
