# security-dashboard (MechDog D)

팀 저장소(`schema/mechdog_messages.schema.json`, `schema/topics.json`)를 유일한
스펙으로 삼는 D(보안관제) 서비스. MQTT 수신 -> 보안 상태 판단 -> 웹 대시보드
실시간 표시 -> 관리자 경고 해제 / 긴급 정지 까지 동작하는 최소 구현이다.

## 구조

```
security-dashboard/
├─ Dockerfile                # 팀 규칙: python:3.11-slim, 포트 3000 (저장소 루트를 빌드 컨텍스트로 사용)
├─ requirements.txt          # paho-mqtt, jsonschema, Flask
├─ app/
│  ├─ main.py                 # 진입점 - MQTT(백그라운드 스레드) + 웹서버(메인 스레드) 함께 실행
│  ├─ mqtt_client.py          # MQTT 구독/발행 + schema 검증 + 관리자 액션(해제/긴급정지)
│  ├─ security_state.py       # session_id별 NORMAL/WARNING/ALERT/PENDING 판단
│  ├─ dashboard_state.py      # 웹서버와 MQTT 스레드가 공유하는 상태(Lock으로 보호)
│  ├─ robot_commands.py       # D 로봇 명령 인터페이스 (콘솔 출력 스텁, SDK는 나중에 교체)
│  ├─ web_server.py           # Flask 라우트 (/api/state, /api/actions/*, /api/snapshot)
│  ├─ templates/index.html    # 대시보드 화면
│  └─ static/{style.css,app.js}
└─ README.md
```

## 실행 방법

### 로컬 (venv)

```bash
cd security-dashboard
pip install -r requirements.txt
python app/main.py
```

환경변수: `MQTT_HOST`(기본 localhost), `MQTT_PORT`(기본 1883), `PORT`(기본 3000),
`MECHDOG_SNAPSHOT_ROOT`(기본 /data/snap), 필요 시 `MQTT_USER`/`MQTT_PASS`.

### Docker

```bash
# 저장소 루트에서 실행 (컨텍스트가 security-dashboard/ 가 아니라 루트여야 함 - 아래 참고)
docker build -f security-dashboard/Dockerfile -t security-dashboard .
docker run -d --name security-dashboard --network <mosquitto와 같은 네트워크> \
  -p 3000:3000 -e MQTT_HOST=mosquitto -e MQTT_PORT=1883 \
  -v <snapshot 볼륨>:/data/snap:ro security-dashboard
```

**왜 빌드 컨텍스트가 저장소 루트인가**: `mqtt_client.py`가 `schema/mechdog_messages.schema.json`,
`schema/topics.json`을 유일한 스펙으로 읽는데, 그 파일들이 `security-dashboard/`
바깥(저장소 루트의 `schema/`)에 있다. 그래서 이미지 안에서도 로컬 개발 폴더와
똑같은 상대 위치(`<root>/schema/`, `<root>/security-dashboard/app/...`)를
재현했다. 팀 `docker-compose.yml`에 그대로 통합하려면 `security-dashboard`
서비스의 `build.context`를 `.`(저장소 루트)로, `dockerfile`을
`security-dashboard/Dockerfile`로 바꿔야 한다 - 공용 파일이라 지금은 임의로
고치지 않았다.

## 보안 상태 판단 규칙

| 조건 | 상태 |
|---|---|
| face=authorized + ppe=pass | NORMAL |
| ppe=fail | WARNING (얼굴 판정과 무관하게 독립적으로 발동) |
| face=unauthorized | ALERT (WARNING보다 우선) |
| face 또는 ppe가 undetermined / 아직 둘 다 안 받음 | PENDING |

`PENDING`은 팀 공식 스펙에 없는 이 서비스 내부 전용 상태다 (재시도 횟수·자동
해제 조건이 DECISIONS.md에서 아직 미확정이라 undetermined를 ALERT로 단정하지
않으려는 임시 처리). PENDING은 MQTT로 아무것도 발행하지 않는다.

같은 `session_id`에서 상태가 실제로 바뀔 때만 `alert.event`를 발행한다(중복
방지). 관리자가 "경고 해제"를 누르면 그 세션의 상태를 초기화해서, 같은 위반이
다시 감지되면 재경보가 가능하도록 했다.

## 웹 대시보드

### 화면 갱신 방식: 1초 폴링

브라우저 JS가 `/api/state`를 1초 간격으로 `fetch(..., {cache: "no-store"})`
한다. WebSocket이나 SSE도 검토했지만:
- 이 화면은 서버 -> 브라우저 단방향 정보 전달만 필요하다.
- 사람 눈에는 1초 지연과 즉시 반영이 사실상 구분되지 않는다.
- WebSocket/SSE는 연결을 계속 열어두고 스레드 간 큐/이벤트로 데이터를 흘려보내야
  해서 구현이 한 단계 더 복잡해진다.

이 프로젝트 규모에서는 폴링이 "가장 단순하고 안정적인" 선택이라고 판단했다.

### 관리자 액션

- **경고 해제**: 현재 활성 경고를 찾아 `robot_commands.clear_alert()` 호출(콘솔
  출력) + 같은 필드(level/reason/track_id/session_id)를 재사용해서
  `resolved: true`인 `alert.event`를 MQTT로 재발행한다. 새 topic이나 필드를
  만들지 않았다 - 팀 예시(`schema/examples/alert_event.json`)에도 이미 같은
  이벤트가 resolved만 바뀌어 다시 오는 패턴이 있다.
- **긴급 정지**: 브라우저에서 `confirm()` 확인 절차를 거친 뒤
  `robot_commands.emergency_stop()`을 호출(콘솔 출력)하고 화면에 "EMERGENCY
  STOP ACTIVE" 배너를 띄운다. MQTT로 나가는 공식 메시지는 아니다(schema에
  해당 msg_type 없음). 배너 옆 "해제" 버튼은 순수 UI 상태 초기화용으로, 이것도
  MQTT 메시지를 만들지 않는다.

### system.health 구독

`mechdog/v1/system/health/{node}`의 `{node}` 자리를 MQTT 표준 와일드카드
`+`로 바꿔 `mechdog/v1/system/health/+`를 구독한다 - 새 topic을 만드는 게
아니라 이미 문서화된 자리표시자를 표준 문법으로 구독하는 것뿐이다. 데이터가
없는 노드는 화면에 `UNKNOWN`으로 표시하고, 가짜로 `ONLINE`이라고 표시하지
않는다.

## 알려진 단순화 / 아직 안 한 것

- PPE `helmet`과 `vest`가 동시에 fail이면 `alert.event.reason`은 `no_helmet`을
  우선 선택한다 (schema에 "둘 다 미착용" 단일 reason 값이 없어서).
- 최근 경고 20개는 메모리에만 저장한다(프로세스 재시작 시 사라짐) - DB는 최현수
  담당 서비스가 준비되면 교체.
- 실제 MechDog SDK 연동 없음 (`robot_commands.py`는 콘솔 출력 스텁).
- `escort.status`(에스코트 이탈)는 아직 처리하지 않는다 - vision.face/ppe만 다룸.
- 대시보드 자체 테스트 패널은 만들지 않았다 - 팀 공식 `tools/mock_publisher.py`를
  터미널에서 직접 실행하는 쪽이 메시지 규약을 새로 만들 위험이 없어 더 안전하다고
  판단했다.
