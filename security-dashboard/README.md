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
├─ tests/
│  └─ test_alert_forwarding.py  # alert.event 구독/표시/해제 로직 회귀 테스트 (Mock, 브로커 불필요)
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

### alert.event 구독 - D 자신뿐 아니라 A/B/C가 낸 경고도 표시 (2026-09-14)

`schema/README.md` 기준 `alert.event`는 D만 내는 메시지가 아니라 `unauthorized`
등은 A, `dialog_timeout`/`dialog_failed`는 B, `escort_lost`는 C가 발행 주체다.
이 서비스는 `mechdog/v1/alert/event`를 구독해서 다른 노드가 낸 경고도 화면에
반영한다.

- **중복/재발행 루프 방지**: 수신한 `alert.event`의 `src`가 `mechdog_d`(자기
  자신)면 그냥 버린다. D가 직접 낸 경고는 발행하는 순간 이미 화면 상태에
  동기적으로 반영했으므로, 구독으로 되돌아온 자기 메시지를 또 처리할 필요가 없다.
  관리자 해제로 나가는 `resolved:true` 재발행도 같은 방식으로 안전하다.
- **동시 다발 경고**: 활성 경고를 하나의 슬롯이 아니라 `session_id`별로 따로
  들고 있는다(`dashboard_state.active_alerts`). D 자신이 세션 X에 대해 낸 경고와
  B가 세션 Y에 대해 낸 경고가 동시에 화면에 표시될 수 있다.
- **B/C 경고 수신 시 D의 물리 동작(경고 자세 등)은 호출하지 않는다** - 표시만
  한다. 표시 외에 D가 자동으로 반응할지는 팀 확인 필요(아래 "확인 필요" 참고).

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

- **경고 해제**: 활성 경고가 세션별로 여러 개 있을 수 있어(위 alert.event 구독
  참고), 화면의 각 경고 카드에 있는 "이 경고 해제" 버튼이 `session_id`를 지정해서
  `/api/actions/clear_alert`를 호출한다. 해당 세션에 대해 `robot_commands.clear_alert()`
  호출(콘솔 출력) + 같은 필드(level/reason/track_id/session_id)를 재사용해서
  `resolved: true`인 `alert.event`를 MQTT로 재발행한다. 새 topic이나 필드를
  만들지 않았다 - 팀 예시(`schema/examples/alert_event.json`)에도 이미 같은
  이벤트가 resolved만 바뀌어 다시 오는 패턴이 있다. B/C가 낸 경고를 해제해도
  재발행은 D 명의(`src: mechdog_d`)로 나간다 - B/C가 이 신호를 자기 상태 초기화에
  실제로 참고할지는 B/C 코드가 아직 없어 확인되지 않았다.
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
- 실제 MechDog SDK 연동 없음 (`robot_commands.py`는 콘솔 출력 스텁). "2족 기립",
  "내장 부저" 등 실물 동작은 아직 어디에도 구현돼 있지 않다 - 지금 검증된 것은
  `tests/test_alert_forwarding.py`의 Mock MQTT 테스트뿐이며, 이를 실물 연동
  완료로 혼동하면 안 된다.
- `escort.status`(위치 스트림) 자체는 아직 구독/처리하지 않는다 - 다만 C가 그
  이탈을 `alert.event`(`reason: escort_lost`)로 발행하면 2026-09-14부터는 그
  경고 자체는 구독해서 화면에 표시한다.
- 대시보드 자체 테스트 패널은 만들지 않았다 - 팀 공식 `tools/mock_publisher.py`를
  터미널에서 직접 실행하는 쪽이 메시지 규약을 새로 만들 위험이 없어 더 안전하다고
  판단했다.
- **방문 횟수 표시는 아직 구현하지 않았다.** 최현수님의 DB(`access_decisions` 등)
  조회 API가 이 저장소에 아직 정의돼 있지 않아, 가짜 숫자나 임의의 DB 연결을
  만들지 않고 필요한 API 계약만 정리해 별도로 공유했다(팀 채널/이슈 참고, 아래
  "확인 필요" 항목).

## 확인 필요 (팀 확인 전까지 보류)

- `schema/README.md`의 AlertReason 발행 주체표는 `unauthorized`/`no_helmet`/
  `no_vest`/`face_timeout`을 **A가 직접 발행**하는 것으로 정의한다. 지금 이
  서비스는 A 대신 vision.face/vision.ppe를 스스로 판정해서 같은 reason으로
  D가 alert.event를 발행하는 방식으로 되어 있다(A 코드가 아직 없어 그 자리를
  메우는 임시 구현). **A가 실제로 구현되면 A와 D가 같은 경고를 중복 발행하지
  않도록 역할을 다시 정리해야 한다.**
- B/C가 낸 alert.event(예: `dialog_timeout`, `escort_lost`)를 화면에 표시할 때
  D가 자동으로 물리 동작(경고 자세 등)을 걸어야 하는지, 표시만 하면 되는지
  아직 정해지지 않았다 - 지금은 표시만 한다.
- 관리자가 B/C발 경고를 대시보드에서 해제하면 D 명의로 `resolved:true`를
  재발행하는데, B/C가 이 신호를 실제로 참고해서 자기 상태를 초기화할지는
  B/C 코드가 없어 확인 불가.
