# mechdog_common

MechDog 출입 통제 프로젝트의 공용 MQTT 메시지 규약 패키지.
A(비전/게이트) · B(대화) · C(에스코트) · D(보안경고) 4명이 각자 Docker 컨테이너로
개발하고, 이 패키지를 import해서 메시지 스키마/토픽/QoS를 통일한다.

## 설치

로컬에서 바로 개발할 때 (editable install):

```bash
pip install -r requirements.txt
pip install -e .
```

또는 각자 서비스 컨테이너에서 설치할 때는 "Docker 통합" 절 참고.

## 5분 사용 예제

### 발행하는 쪽 (예: A가 얼굴 판정 결과를 보냄)

```python
from mechdog_common import (
    MechDogBus, Node, VisionFacePayload, FaceResult, new_session_id,
)

bus = MechDogBus(Node.MECHDOG_A)
bus.connect()

session_id = new_session_id(Node.MECHDOG_A)  # 방문자 최초 감지 시 A가 발급

bus.publish(
    VisionFacePayload(
        visitor_id="visitor-001",
        result=FaceResult.AUTHORIZED,
        confidence=0.93,
        similarity=0.81,
        snapshot_path="/data/snap/20260902/sessxxx/face.jpg",
    ),
    session_id=session_id,
)
# 토픽(mechdog/v1/vision/face), QoS(1), retain 여부는 bus가 자동으로 결정한다.
# 이 session_id를 B/C/D에게 계속 물려주면 같은 방문자의 메시지를 추적할 수 있다.
```

### 구독하는 쪽 (예: D가 판정 결과를 받아 경고 로직을 돌림)

```python
from mechdog_common import MechDogBus, Node, MsgType, Envelope

bus = MechDogBus(Node.MECHDOG_D)

def on_face_result(env: Envelope) -> None:
    payload = env.payload  # VisionFacePayload
    print(env.session_id, payload.result)

bus.on(MsgType.VISION_FACE, on_face_result)
bus.connect()
```

### 브로커 없이 확인해보기

```bash
python tools/mock_publisher.py --list
python tools/mock_publisher.py normal --dry-run
python tools/validate.py
```

## MQTT 보안 설정

`bus.py`는 환경변수만으로 두 모드를 전환한다. 코드를 고칠 필요는 없다.

### 로컬/사내망 데모 (기본값)

`MQTT_USER`를 설정하지 않으면 인증 없이 그대로 연결한다.

```bash
export MQTT_HOST=localhost
export MQTT_PORT=1883
```

`mosquitto/mosquitto.conf`도 기본값이 `allow_anonymous true`로 되어 있어 바로 붙는다.

### 외부 네트워크에 노출할 때

1. 브로커에 계정을 만든다 (Mosquitto 예시):
   ```bash
   docker exec mosquitto mosquitto_passwd -c /mosquitto/config/passwd <MQTT_USER>
   ```
2. `mosquitto.conf`에서 `allow_anonymous false` + `password_file` 주석을 해제한다.
3. 각 서비스 컨테이너에 `MQTT_USER` / `MQTT_PASS` 환경변수를 넣는다:
   ```bash
   export MQTT_USER=mechdog
   export MQTT_PASS=<비밀번호>
   ```
   `MQTT_USER`가 설정된 순간 `MechDogBus`가 자동으로 `username_pw_set()`을 호출해
   인증 모드로 붙는다.

## Docker 통합 방법

4명이 각자 컨테이너로 개발하고 최종 통합(최현수 노트북)하는 이 프로젝트 규모(팀 4명,
기간 짧음)에서 공용 패키지를 공유하는 방법 3가지를 비교했다.

| 방식 | 장점 | 단점 | 이 프로젝트 적합도 |
|---|---|---|---|
| **pip 로컬 패키지** (COPY + `pip install`) | Dockerfile 한 줄로 통합, 버전(`pyproject.toml`) 고정 가능, import 문법이 실제 배포된 패키지처럼 동작해 로컬 개발/컨테이너 차이 없음 | 스키마 변경 시 각자 이미지 재빌드 필요 | ★★★ (채택) |
| git submodule | 별도 저장소로 버전 관리, 여러 프로젝트에 재사용하기 좋음 | 팀원 전원이 submodule 사용법(초기화, 업데이트, detached HEAD)에 익숙해야 함 - 안 그러면 "서브모듈이 옛 버전"인 채로 통합 때 터짐. 4명·짧은 기간에는 러닝커브가 리스크 | ★ |
| 단순 파일 복사 (수동 동기화) | 당장 제일 빠름, 도구 학습 불필요 | 누군가 로컬에서 고치고 안 옮기면 즉시 드리프트. "각자 로컬에서 필드 추가하면 통합 때 반드시 깨진다"는 회의록 우려가 그대로 재현됨 | ✗ |

**결론**: pip 로컬 패키지 방식을 채택. `pyproject.toml`로 버전이 명시되고,
Dockerfile에 `COPY mechdog_common/ ...` + `pip install`만 넣으면 되어 팀원 4명이
새 도구를 배울 필요가 없다. 스키마는 PR로만 바꾸고(회의록 방침), 바뀌면 각자
이미지를 재빌드하는 것으로 "동기화 깨짐" 문제를 구조적으로 막는다.

실제 예시는 [Dockerfile.example](Dockerfile.example), [docker-compose.yml](docker-compose.yml) 참고.
공용 패키지는 팀 공용 저장소(Git)에 두고, 각자 서비스 저장소에서 그 저장소를
clone 하거나 CI에서 sdist를 받아 COPY 하는 식으로 가져온다.

베이스 이미지는 `python:3.11-slim`으로 통일 (회의록 합의 사항).

## 얼굴 이미지 보관 정책

`paths.py`의 `snapshot_path()`로 저장된 이미지는 개인정보이므로 무기한 보관하지 않는다.
`tools/cleanup_snapshots.py`가 `MECHDOG_RETENTION_DAYS`(기본 7일)가 지난 날짜
디렉터리를 통째로 삭제한다.

```bash
python tools/cleanup_snapshots.py --dry-run   # 삭제 대상만 미리 보기
python tools/cleanup_snapshots.py             # 실제 삭제
MECHDOG_RETENTION_DAYS=14 python tools/cleanup_snapshots.py  # 보관 기간 변경
```

주기 실행은 cron에 등록해서 매일 자정에 돌리면 된다: `0 0 * * * cd /path/to/project && python tools/cleanup_snapshots.py >> /var/log/mechdog_cleanup.log 2>&1`

## 패키지 구조

```
mechdog_common/
  enums.py     - 고정 상수 (Node, MsgType, FaceResult, ... )
  messages.py  - Pydantic 메시지 스키마 (Envelope + discriminated union payload)
  topics.py    - MQTT 토픽 생성 규칙 + QoS/Retain 정책
  paths.py     - 이미지/오디오 저장 경로 규칙
  bus.py       - paho-mqtt 발행/구독 래퍼
tools/
  mock_publisher.py     - 시나리오별 샘플 메시지 발행
  echo_subscriber.py    - 전 토픽 구독 디버그 도구
  validate.py            - 브로커 없이 스키마 자체 검증
  cleanup_snapshots.py   - 보관 기간 초과 스냅샷/오디오 정리
```

미확정 값과 팀원별 확인 체크리스트는 [DECISIONS.md](DECISIONS.md) 참고.
