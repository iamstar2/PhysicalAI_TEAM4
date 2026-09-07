# MechDog MQTT 메시지 스펙

MechDog 출입 통제 프로젝트에서 A(비전/게이트) · B(대화) · C(에스코트) · D(보안경고)
4명이 주고받는 MQTT 메시지 형식을 정의한 저장소.

**이 저장소는 설치하는 패키지가 아니라 스펙 문서다.** 유일한 소스는
`schema/mechdog_messages.schema.json` (JSON Schema)이고, 각자 자기 서비스가
쓰는 언어에서 이 스펙에 맞는 JSON을 만들고 검증하면 된다. Python 전용 공용
라이브러리를 만들지 않은 이유는, 대시보드가 React/JS라 Python 클래스를 못
쓰기 때문이다 — JSON Schema는 언어에 상관없이 다 쓸 수 있다.

## MechDog 온보드 기본 제공 SDK (참고)

`references/`에는 제조사(Hiwonder)가 MechDog 본체에 기본 제공하는 오픈소스
예제/라이브러리가 들어있다. 이 저장소의 `schema/`는 RPi/PC 사이에서 MQTT로
오가는 메시지 형식이고, 아래는 MechDog 본체(ESP32)가 온보드에서 바로 쓸 수 있는
**별도 계층의 SDK**다 — 서로 다른 계층이니 혼동하지 말 것.

- **지원 플랫폼**: Scratch(WonderCode, 블록코딩) · Python(MicroPython) · Arduino(C/C++) · 모바일 앱(BLE)
- **컨트롤러**: 메인 컨트롤러 ESP32(모션·역기구학 담당), 별도 ESP32-S3 Cam 모듈(비전, I2C로 연결)
- **온보드 Python(MicroPython) 모듈** (펌웨어에 이미 포함되어 import만 하면 됨):
  - `HW_MechDog.MechDog` — 모션 제어 (`action_run()`으로 동작그룹 실행, 보행 속도·자세 조절)
  - `Hiwonder` — 초음파/조도/터치 센서, ASR(음성인식)+MP3 재생 등 부가 기능
  - `Hiwonder_IIC` — I2C 주변장치 접근. `Hiwonder_IIC.ESP32S3Cam`에 **`face_recognition()`이 이미 내장**되어 있음
  - `Hiwonder_BLE.BLE` — 블루투스로 모바일 앱과 통신
  - `machine` — MicroPython 표준 하드웨어 제어(GPIO/I2C/타이머 등)
- **Arduino(C++) 쪽**: `HW_MechDog.h`, `mech_base_types.h` 헤더로 동일한 모션 API 제공,
  다른 보드와 UART로 시리얼 통신하는 예제(`MechDog_uart`)도 포함
- **공식 자료**: [Hiwonder MechDog 문서](https://docs.hiwonder.com/projects/MechDog/en/latest/) ·
  [제품 페이지](https://www.hiwonder.com/products/mechdog) · [GitHub](https://github.com/Hiwonder/MechDog)

> **참고**: `Hiwonder_IIC.ESP32S3Cam.face_recognition()`이 이미 온보드에 있으므로, A(여도훈)가
> InsightFace/ArcFace로 직접 구현하기 전에 이 내장 기능만으로 충분한지 먼저 확인해볼 만하다.

## 구조

```
schema/
  mechdog_messages.schema.json  - 메시지 스펙 (Envelope + 메시지 타입별 payload)
  topics.json                   - MQTT 토픽 이름 + QoS/Retain 정책 + 근거
  examples/                     - 메시지 타입별 실제 JSON 예시
tools/
  validate_schema.py    - schema 자체와 examples가 서로 맞는지 검증 (브로커 불필요)
  mock_publisher.py     - 시나리오별 샘플 메시지 발행 (참고 구현, Python)
  echo_subscriber.py    - 전 토픽 구독 + 스펙 검증하며 출력 (참고 구현, Python)
  cleanup_snapshots.py  - 보관 기간 초과 스냅샷/오디오 정리
references/
  01~04                  - Hiwonder 공식 MechDog 예제 (Scratch/Python/Arduino/모바일 앱)
```

## 스펙 읽는 법

1. **`schema/mechdog_messages.schema.json`** — 모든 메시지는 공통 Envelope
   (`ver`, `msg_id`, `ts`, `src`, `session_id`, `payload`)으로 감싸여 있고,
   `payload`는 `msg_type` 값에 따라 7가지 중 하나의 모양을 가진다
   (`vision.face`, `vision.ppe`, `gate.session`, `dialog.result`,
   `escort.status`, `alert.event`, `system.health`). 정의 안 된 필드는
   `additionalProperties: false`로 전부 거부된다.
2. **`schema/topics.json`** — 메시지 타입별 MQTT 토픽 문자열, QoS(0/1), retain
   여부와 그 이유가 데이터로 들어있다.
3. **`schema/examples/*.json`** — 실제로 이런 모양의 JSON이 오간다는 예시.
   코드 안 읽고 이 파일들만 보면 감이 온다.

## 검증하는 법

### Python (이 저장소에 포함된 방식)

```bash
pip install -r requirements.txt
python tools/validate_schema.py
```

각자 서비스 코드에서도 같은 방식으로 검증하면 된다:

```python
import json
from jsonschema import Draft202012Validator

schema = json.load(open("schema/mechdog_messages.schema.json"))
validator = Draft202012Validator(schema)
validator.validate(my_message_dict)  # 스펙과 다르면 여기서 예외 발생
```

### 다른 언어

JSON Schema는 표준이라 어떤 언어든 구현체가 있다 (JS는 `ajv`, 등등). 브라우저에서
mqtt.js로 붙는 대시보드도 `ajv`로 동일한 `mechdog_messages.schema.json`을 그대로
가져다 쓰면 된다.

### 브로커 없이 확인해보기

```bash
python tools/mock_publisher.py --list
python tools/mock_publisher.py normal --dry-run
```

## MQTT 보안 설정

### 로컬/사내망 데모 (기본값)

`mosquitto/mosquitto.conf`가 기본값으로 `allow_anonymous true`라 인증 없이 붙는다.

```bash
export MQTT_HOST=localhost
export MQTT_PORT=1883
```

### 외부 네트워크에 노출할 때

1. 브로커에 계정을 만든다:
   ```bash
   docker exec mosquitto mosquitto_passwd -c /mosquitto/config/passwd <MQTT_USER>
   ```
2. `mosquitto.conf`에서 `allow_anonymous false` + `password_file` 주석을 해제한다.
3. 각자 클라이언트 코드에서 `MQTT_USER`/`MQTT_PASS` 환경변수가 있으면
   `username_pw_set()`(또는 각 언어의 동일 기능)을 호출하도록 구현한다.
   `tools/mock_publisher.py`, `tools/echo_subscriber.py`에 이미 그렇게 되어 있으니
   참고하면 된다.

### 목표 아키텍처: TLS + ACL (2-호스트 배포 시)

로컬 데모를 넘어 실제로 브로커/수집 호스트와 메인서버 호스트를 분리 배포할 때는
TLS(:8883)와 토픽별 ACL까지 켠다. `mosquitto/mosquitto.conf` 하단의 "목표
아키텍처" 블록 주석을 해제하고, 인증서(`mosquitto/certs/`)와
`mosquitto/acl.conf`(예시: [acl.conf.example](mosquitto/acl.conf.example) —
`schema/topics.json` 기준으로 노드별 발행/구독 권한을 정의해 뒀다)를 준비하면 된다.

## Docker 통합

스펙이 코드가 아니라 JSON 문서이므로, 컨테이너에 설치할 게 없다. 각자 서비스
저장소에서 이 저장소를 클론(또는 `schema/` 디렉터리만 복사)해서 개발 중에
참고하고, 자기 언어의 JSON Schema validator로 발행 전에 검증하면 된다.
실행 중 컨테이너가 이 저장소 자체를 마운트해야 하는 것도 아니다 — JSON 스펙은
빌드/개발 시점 참고 자료이지 런타임 의존성이 아니다.

배포 토폴로지는 두 가지로 나뉜다.

- **로컬 단일 호스트 데모** (개발 중 기본): [docker-compose.yml](docker-compose.yml).
  브로커·4대 로봇·DB를 전부 한 대에서 같이 띄운다.
- **목표 아키텍처 — 2-호스트 분리 배포** (`work_docs`의 `Hw설계도.png` 기준):
  [docker-compose.host1.yml](docker-compose.host1.yml)(브로커 + 수집서버) /
  [docker-compose.host2.yml](docker-compose.host2.yml)(API 서버 + 시나리오
  A~D + DB). API 서버가 스냅샷·오디오·상태 업로드(REST)와 DB 접근의 유일한
  관문이고, 시나리오 A~D는 기존 vision/dialog/escort/security 서비스가 그대로
  MQTT로 호스트1의 브로커에 붙는 구조다. 호스트2는 `HOST1_MQTT_HOST` 환경변수로
  호스트1의 브로커 주소를 가리킨다.

베이스 이미지는 `python:3.11-slim`으로 통일 (회의록 합의 사항, Python
서비스에 한정).

## 얼굴 이미지 보관 정책

스냅샷은 개인정보이므로 무기한 보관하지 않는다. `tools/cleanup_snapshots.py`가
`MECHDOG_RETENTION_DAYS`(기본 7일)가 지난 날짜 디렉터리를 통째로 삭제한다.

```bash
python tools/cleanup_snapshots.py --dry-run   # 삭제 대상만 미리 보기
python tools/cleanup_snapshots.py             # 실제 삭제
MECHDOG_RETENTION_DAYS=14 python tools/cleanup_snapshots.py  # 보관 기간 변경
```

주기 실행은 cron에 등록: `0 0 * * * cd /path/to/project && python tools/cleanup_snapshots.py >> /var/log/mechdog_cleanup.log 2>&1`

## 스펙이 바뀌어야 할 때

1. 새 필드/메시지 타입이 필요한 사람이 스키마 소유자에게 요청
2. `schema/mechdog_messages.schema.json` (+ 필요 시 `schema/topics.json`,
   `schema/examples/`) 수정
3. `python tools/validate_schema.py` 돌려서 기존 예시가 안 깨지는지 확인
4. PR로 머지 → 팀 채널에 공지 → 각자 자기 검증 코드가 최신 스키마를 보고 있는지 확인

로컬에서 각자 스펙에 없는 필드를 임의로 얹으면 안 된다 —
`additionalProperties: false`가 다른 사람 쪽에서 그걸 거부하도록 만들어져 있다.

미확정 값과 팀원별 확인 체크리스트는 [DECISIONS.md](DECISIONS.md) 참고.
