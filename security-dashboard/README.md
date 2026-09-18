# security-dashboard (MechDog D)

팀 저장소(`schema/mechdog_messages.schema.json`, `schema/topics.json`)를 유일한
스펙으로 삼는 D(보안관제) 서비스. MQTT 수신 -> 보안 상태 판단 -> 웹 대시보드
실시간 표시 -> 관리자 경고 해제 / 긴급 정지 까지 동작하는 최소 구현이다.

## 구조

```
security-dashboard/
├─ Dockerfile                # 팀 규칙: python:3.11-slim, 포트 3000 (저장소 루트를 빌드 컨텍스트로 사용)
├─ requirements.txt          # paho-mqtt, jsonschema, Flask, pyserial(serial 모드 전용, 지연 import)
├─ app/
│  ├─ main.py                 # 진입점 - MQTT(백그라운드 스레드) + 웹서버(메인 스레드) 함께 실행
│  ├─ mqtt_client.py          # MQTT 구독/발행 + schema 검증 + 관리자 액션(해제/긴급정지)
│  ├─ security_state.py       # session_id별 NORMAL/WARNING/ALERT/PENDING 판단
│  ├─ dashboard_state.py      # 웹서버와 MQTT 스레드가 공유하는 상태(Lock으로 보호)
│  ├─ robot_commands.py       # D 로봇 명령 인터페이스 - mock(콘솔) / serial(실물 UART) 드라이버
│  ├─ web_server.py           # Flask 라우트 (/api/state, /api/actions/*, /api/snapshot)
│  ├─ templates/index.html    # 대시보드 화면
│  └─ static/{style.css,app.js}
├─ tests/
│  ├─ test_alert_forwarding.py      # alert.event 구독/표시/해제 로직 회귀 테스트 (Mock, 브로커 불필요)
│  ├─ test_same_session_alerts.py  # 같은 session_id에서 사유가 다른/같은 경고가 겹치는 경우 회귀 테스트
│  └─ test_robot_dispatch.py       # 실물 연동(고정 배치) 회귀 테스트 - Fake 시리얼만 사용, 실물 없음
└─ README.md
```

실물 D 로봇 펌웨어 변경 제안은 이 폴더가 아니라 저장소 루트의 `firmware/mechdog_d_uart/`에
따로 있다(원본 `references/`는 건드리지 않는다 - 아래 "실물 D 로봇 연동" 절 참고).

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

### alert.event 구독 - D 자신뿐 아니라 A/B/C가 낸 경고도 표시 (2026-09-14, 식별 기준은 2026-09-15 수정)

`schema/README.md` 기준 `alert.event`는 D만 내는 메시지가 아니라 `unauthorized`
등은 A, `dialog_timeout`/`dialog_failed`는 B, `escort_lost`는 C가 발행 주체다.
이 서비스는 `mechdog/v1/alert/event`를 구독해서 다른 노드가 낸 경고도 화면에
반영한다.

- **중복/재발행 루프 방지**: 수신한 `alert.event`의 `src`가 `mechdog_d`(자기
  자신)면 그냥 버린다. D가 직접 낸 경고는 발행하는 순간 이미 화면 상태에
  동기적으로 반영했으므로, 구독으로 되돌아온 자기 메시지를 또 처리할 필요가 없다.
  관리자 해제로 나가는 `resolved:true` 재발행도 같은 방식으로 안전하다.
- **활성 경고 식별 기준 = `(session_id, reason)`**: 처음에는 `session_id`만으로
  활성 경고를 구분했는데, 같은 세션에서 D(예: `unauthorized`)와 B/C(예:
  `dialog_timeout`)가 서로 다른 사유로 동시에 경고를 내면 서로 덮어써서 하나가
  화면에서 통째로 사라지는 문제가 있었다(2026-09-14 재검토에서 발견,
  `tests/test_same_session_alerts.py` 참고). `schema/README.md`의 AlertReason별
  발행 주체표에서 각 reason이 노드 하나에 대응하도록 설계돼 있어, `session_id` +
  `reason` 조합이면 "이 세션에서 벌어진 이 종류의 위반"을 안전하게 가리킬 수 있다.
  이 값이 다르면(D의 판정 vs B/C의 경고) 동시에 표시되고 각각 개별 해제된다.
- **관리자 해제 시 D 내부 판정 상태(security_state) 초기화 범위**: 해제한 경고의
  `src`가 `mechdog_d`일 때만 그 세션의 판정 상태(`security_state.reset_status`)를
  초기화한다. B/C가 낸 경고를 해제할 때도 무조건 초기화하면, D 자신의 활성 경고가
  같은 세션에 아직 남아있는 상태에서 그 판정 상태가 부당하게 지워져 다음에 같은
  판정이 들어와도 "바뀐 것"으로 오인해 중복 재발행하는 부작용이 있었다.
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
  `robot_commands.emergency_stop()`을 호출하고 화면에 "EMERGENCY STOP ACTIVE"
  배너를 띄운다. MQTT로 나가는 공식 메시지는 아니다(schema에 해당 msg_type
  없음). 배너 옆 "해제" 버튼은 순수 UI 상태 초기화용으로, 이것도 MQTT 메시지를
  만들지 않는다. **주의**: 이 단계의 EMERGENCY_STOP은 실제 전원 차단이 아니다 -
  로봇이 이동하지 않는 고정 배치라서, 할 수 있는 건 부저 반복 중지 +
  `normal_attitude` 요청뿐이다(화면에도 동일하게 표시, 아래 "실물 D 로봇 연동"
  참고).

### system.health 구독

`mechdog/v1/system/health/{node}`의 `{node}` 자리를 MQTT 표준 와일드카드
`+`로 바꿔 `mechdog/v1/system/health/+`를 구독한다 - 새 topic을 만드는 게
아니라 이미 문서화된 자리표시자를 표준 문법으로 구독하는 것뿐이다. 데이터가
없는 노드는 화면에 `UNKNOWN`으로 표시하고, 가짜로 `ONLINE`이라고 표시하지
않는다.

## 실물 D 로봇 연동 (고정 배치, Serial) — 2026-09-17

**시나리오**: D는 A 바로 옆에 고정 배치되고 이동하지 않는다. A는 vision.face/
vision.ppe 판정 결과만 발행하고, 이 서비스가 그걸로 NORMAL/WARNING/ALERT/PENDING을
판정해 `alert.event`를 낸다(1단계 통합시험 기준 - A는 아직 alert.event를 직접
발행하지 않는다). 미인가/PPE 미착용이면 실물 MechDog D가 `stand_two_legs` 자세와
내장 부저 경고를 실행한다.

### 드라이버: `MECHDOG_D_DRIVER=mock|serial`

`robot_commands.py`는 두 드라이버만 지원한다. 실물이 없는 팀원 환경에서도 아무
환경변수 없이 그대로 실행하면 지금까지와 똑같이 **mock(콘솔 출력)**으로 동작한다.

| 환경변수 | 기본값 | 설명 |
|---|---|---|
| `MECHDOG_D_DRIVER` | `mock` | `mock`(콘솔만) 또는 `serial`(실제 UART로 CMD 전송) |
| `MECHDOG_D_SERIAL_PORT` | (없음) | `serial` 모드일 때 **필수**. 임의 기본값(COM3 등)을 두지 않는다 - 잘못된 포트로 실수 전송하는 사고를 피하기 위해서다. 없으면 시작 시 에러. |
| `MECHDOG_D_SERIAL_BAUD` | `9600` | `MechDog_uart.ino`의 `mySerial.begin(9600, ...)`과 일치시켜야 함 |
| `MECHDOG_D_BUZZER_INTERVAL_S` | `1.0` | 부저 원샷(200ms) 재전송 간격(초) |

### 물리 상태: 세션이 아니라 로봇 전체 기준(전역)

로봇이 1대뿐이고 이동하지 않으므로, "경고 자세+부저"는 세션별이 아니라 **로봇
전체에 걸린 물리 상태 하나**다.

- **최초 진입(1회만)**: 어떤 세션이든 처음 WARNING/ALERT로 전이해서 D 소유
  활성 경고가 생기면 `stand_two_legs`(`"CMD|2|1|6|$"`)를 보내고 부저 반복
  스레드를 시작한다. `robot_commands.start_buzzer_and_posture()`가 부저 스레드가
  이미 살아있으면 아무 것도 하지 않고 즉시 반환하므로, 같은 세션에 사유가
  추가되거나(예: no_helmet 이후 unauthorized 추가) 다른 세션이 겹쳐도(예: 서로
  다른 방문자가 동시에 미인가로 감지) `stand_two_legs`는 다시 전송되지 않는다.
- **복귀는 전역 카운트 기준**: 관리자가 (session_id, reason) 하나를 해제해도,
  `dashboard_state.count_d_owned_active_alerts("mechdog_d")`가 0이 될 때만
  `stop_buzzer_and_return_posture()`(부저 중지 + `"CMD|2|1|16|$"` normal_attitude)를
  부른다. 다른 세션에 D 소유 경고가 남아있으면 그대로 경고 상태를 유지한다 -
  세션 하나만 보고 판단하면 다른 세션의 위반을 무시하고 복귀해버리는 오판이
  생기기 때문이다.
- **A의 자동 NORMAL 재판정으로는 절대 종료되지 않는다**: 재검사를 통과해서
  `security_state`가 다시 NORMAL이 되어도 물리 경고는 그대로 유지된다. 오직
  관리자의 수동 해제(`/api/actions/clear_alert`)만이 종료 조건이다.
- **B/C가 낸 alert.event는 표시만 하고 물리 동작을 걸지 않는다** - 이전에는
  "확인 필요" 항목이었는데 이번 정책으로 확정됐다(아래 참고).

### CMD 프로토콜 문자열의 근거

추측하지 않고 `references/03 Arduino Programming Projects/05 Serial
Communication Practical Lessons/MechDog_Slave_Program/MechDog_uart/MechDog_uart.ino`의
실제 파싱 로직만 근거로 삼았다:

- `stand_two_legs`: `"CMD|2|1|6|$"` (case 2 "동작 그룹 호출" + actions_flg==1의
  case 6이 `action_run("stand_two_legs")`)
- `normal_attitude`: `"CMD|2|1|16|$"` (같은 경로의 case 16)
- 부저: **이 펌웨어에는 아직 부저 명령이 없다.** `MechDog` 클래스가 `PowerBuzzer`를
  이미 상속하고 있어(`HW_MechDog.h:28`) `mechdog.playTone(duty, btime, state)`
  (`Hiwonder.cpp:148`)를 바로 호출할 수 있지만, 시리얼 프로토콜에 그 호출을
  연결하는 case가 빠져 있다. `firmware/mechdog_d_uart/`에 `case 7`을 추가하는
  패치를 제안해 뒀다(`"CMD|7|1|$"` = 200ms 논블로킹 원샷) - **원본
  `references/`는 수정하지 않았고, 이 패치는 아직 ESP32에 적용/업로드되지
  않았다.** 부저는 원샷이라(`Buzzer_Task`가 200ms 뒤 자동으로 끔) "계속
  울리기"는 PC 쪽에서 반복 전송으로 구현한다(`robot_commands._buzzer_loop`).

### 안전장치

- **Lock**: 자세 명령(`_send`)과 부저 반복 스레드가 같은 시리얼 포트에 동시에
  쓰지 않도록 `robot_commands._write_lock` 하나를 공유한다.
- **Serial 실패 격리**: `_send()`는 어떤 예외든 밖으로 던지지 않고 로그만
  남긴다(`robot_commands.last_error()`로 조회 가능, 화면에도 표시). MQTT 콜백
  스레드나 대시보드 프로세스가 시리얼 오류로 죽지 않는다.
- **적용 전 필수 확인**: `firmware/mechdog_d_uart/README.md`에 정리한 3가지
  (플래시 백업, GPIO32/33 핀 배선 확인, 실제 로봇 펌웨어와 참고 예제 일치
  여부)가 확인되기 전까지 패치를 업로드하지 않는다.

## 알려진 단순화 / 아직 안 한 것

- PPE `helmet`과 `vest`가 동시에 fail이면 `alert.event.reason`은 `no_helmet`을
  우선 선택한다 (schema에 "둘 다 미착용" 단일 reason 값이 없어서).
- 최근 경고 20개는 메모리에만 저장한다(프로세스 재시작 시 사라짐) - DB는 최현수
  담당 서비스가 준비되면 교체.
- **실물 MechDog SDK 연동은 아직 검증되지 않았다.** `robot_commands.py`가
  `MECHDOG_D_DRIVER=serial`일 때 실제 시리얼 명령을 만들어 보내는 코드는
  생겼지만(위 "실물 D 로봇 연동" 참고), ESP32에 부저 패치를 업로드한 적도,
  실제 로봇에 명령을 보낸 적도 없다 - 지금 검증된 것은 `tests/test_alert_forwarding.py`,
  `tests/test_same_session_alerts.py`, `tests/test_robot_dispatch.py`의 Mock/Fake
  테스트뿐이며, 이를 실물 연동 완료로 혼동하면 안 된다.
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
- ~~B/C가 낸 alert.event를 화면에 표시할 때 D가 자동으로 물리 동작을 걸어야
  하는지~~ — **2026-09-17 정책으로 확정**: 표시만 하고 물리 동작(자세/부저)은
  걸지 않는다.
- 관리자가 B/C발 경고를 대시보드에서 해제하면 D 명의로 `resolved:true`를
  재발행하는데, B/C가 이 신호를 실제로 참고해서 자기 상태를 초기화할지는
  B/C 코드가 없어 확인 불가.
- `firmware/mechdog_d_uart/`의 부저 case 7 패치를 실제로 ESP32에 적용할지,
  적용한다면 언제/누가 백업·업로드를 진행할지 팀 확인 필요.
