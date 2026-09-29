# api-server (김별이)

MechDog 팀의 **DB 쓰기 · 조회 창구**. 0929 회의에서 "각 파트는 DB 에 직접 쓰지 않고 API 를 거친다" 로 정했다.

```
로봇 ─MQTT→ 브로커 → 수집서버(여도훈) ─ POST /events ────────┐
D 대시보드 ─ 얼굴 등록 · 이력 조회 · 경고 해제 ────────────────┤
A 노트북   ─ 등록 사진 가져가기 · 경고 사진 올리기 ────────────┼→ api-server → PostgreSQL(최현수)
B 파이     ─ 대화 로그 일괄 적재 (tools/dialog_log_upload.py) ─┘
```

판정은 하지 않는다. 받은 값을 검사하고 테이블 모양으로 옮기기만 한다.
HW 설계도의 "시나리오 A~D 라우팅" 은 09-17 에 각자 로컬 실행으로 바꾸면서 전달할 대상이 없어져 **넣지 않았다.**

---

## 실행

노트북 4대 배치(A 브로커 · 수집서버 / B API 서버 / C DB / D 대시보드)는 [`deploy/README.md`](../deploy/README.md).
B 노트북에서는:

```bash
cp api-server/.env.example api-server/.env      # DB 주소(C 노트북) · 토큰 · 암호화 키 채우기
docker compose -f deploy/b-api.yml up -d --build
```

로컬 (도커 없이):

```bash
cd api-server
python -m venv .venv && .venv/Scripts/pip install -r requirements.txt   # 리눅스·맥은 .venv/bin/pip
.venv/Scripts/uvicorn app.main:app --host 0.0.0.0 --port 8080 --env-file .env
```

- **`--host 0.0.0.0`** 이어야 다른 노트북에서 접속된다.
- `http://<서버 IP>:8080/docs` — 모든 엔드포인트를 브라우저에서 바로 시험할 수 있다 (오른쪽 위 Authorize 에 토큰).
- `http://<서버 IP>:8080/healthz` — DB 연결 · 암호화 키 · 토큰 수 확인.

## 인증

모든 요청에 `Authorization: Bearer <토큰>`. 토큰은 김별이가 파트별로 하나씩 발급한다 (`.env` 의 `API_TOKENS`).
누가 무엇을 부를 수 있는지는 [`app/security.py`](app/security.py) 의 `PERMISSIONS` 표.

| 토큰 이름 | 쓰는 곳 | 호출할 수 있는 것 |
|---|---|---|
| `collector` | 수집서버 | `POST /events`, `/events/batch` |
| `dashboard` | D 대시보드 | 얼굴 등록, 경고 사진 보기, 조회 · 통계, 경고 해제 기록 |
| `mechdog_a` | A 노트북 | 등록 목록 · 사진 받기, 경고 사진 올리기 |
| `mechdog_d` | D 로봇 · 노트북 | 경고 사진 올리기 |
| `mechdog_b` | B 파이 | 대화 로그 일괄 적재 |

---

## 파트별로 쓰는 법

### 수집서버 (여도훈) — `POST /events`

MQTT 로 받은 메시지를 **바꾸지 말고 그대로** JSON 본문으로 보낸다.

```bash
curl -X POST http://<서버>:8080/events -H "Authorization: Bearer <collector 토큰>" \
     -H "Content-Type: application/json" -d @schema/examples/gate_session.json
```

- `schema/mechdog_messages.schema.json` 으로 검사 → 틀리면 **422** 와 틀린 곳 목록. 버리지 않고 `logs/rejected_*.jsonl` 에 남는다.
- **응답 코드로 재전송을 판단한다**

  | 코드 | 뜻 | 수집서버가 할 일 |
  |---|---|---|
  | 200 | 적재됨 (이미 있으면 건너뜀) | 다음 메시지 |
  | 422 | 메시지가 틀림 (스키마 · 제약 위반) | **버린다** — 다시 보내도 같다. 서버가 `logs/rejected_*.jsonl` 에 남김 |
  | 401 · 403 | 토큰 문제 | 설정 확인 (재전송 무의미) |
  | 503 · 연결 실패 · 타임아웃 | DB 나 API 서버 장애 | **쌓아 두고 나중에 다시** |
  | 500 | API 서버 버그 | **쌓아 두고 나중에 다시** — 김별이가 고친 뒤 재전송하면 들어간다 |
- **같은 메시지를 여러 번 보내도 된다** (QoS 1 중복 · retain 재수신 · 재전송 모두 안전). 실패하면 그냥 다시 보내면 된다.
- 끊겼다가 다시 붙었을 때 몰린 메시지는 `POST /events/batch` 로 배열째. 한 건이 422 여도 나머지는 들어간다.
  503 · 500 이 오면 배열 **전체를 다시** 보내면 된다 (이미 들어간 건 중복으로 건너뜀).
- 규칙이 아직 없는 새 msg_type 도 버리지 않고 `event_logs` 에 원본으로 남는다.
- `health` 는 상태가 바뀔 때만, `escort.status` 는 출발 · 도착 · 중단 순간만 기록된다 — 걸러서 보낼 필요 없이 전부 보내면 된다.

메시지 → 테이블 (규칙은 [`app/ingest.py`](app/ingest.py) 한 파일에 있다)

| msg_type | 테이블 | 방식 |
|---|---|---|
| `gate.session` | `sessions` | 행 생성 · visitor_id |
| `vision.face` / `vision.ppe` | `access_decisions` | **같은 session_id 의 두 메시지를 1행으로** (출입 판정 1회 = 1행). 하나라도 차단이면 deny, 사유는 `unauthorized` · `no_helmet` · `no_vest` · `face_undetermined` · `ppe_undetermined`. 차단일 때만 snapshot_path |
| `dialog.result` | `dialog_sessions` | 목적지 · 목적 · 신뢰도 |
| `alert.event` | `alert_logs` | 발생 INSERT. 해제는 **같은 msg_id** 또는 **(session_id, reason)** 으로 찾아 UPDATE — D 대시보드는 후자 |
| `system.health` | `system_health` | 직전 상태와 다를 때만 |
| `escort.status` | `escort_logs` | moving → 출발 행, arrived → 도착, aborted → 실패 |
| `robot.command` | `event_logs` | 명령 기록 |

`sessions` 행이 없으면 자동으로 만든다 (`AUTO_CREATE_SESSION=1`) — 미인가자처럼 `gate.session` 없이 경고만 오는 경우 FK 로 실패하지 않게.
단 `session_id` 가 `system` · `unknown` · `none` 이면 방문자 세션이 아니라서 만들지 않는다 (`NO_SESSION_IDS`).

**중복 거르기** — `ingest_log` 테이블(HW 설계도의 DB 항목, [`sql/proposed_changes.sql`](sql/proposed_changes.sql))이
DB 에 있으면 거기에 받은 msg_id 를 남겨 **서버를 재시작해도** 거른다. 없으면 메모리로 대신한다.
실패한 메시지는 '받은 것' 으로 치지 않는다 — 재전송이 버려지지 않게.

**health 의 '최근 상태'** 는 받은 순서로 본다. LWT(offline)의 `ts` 는 접속했던 시각이라 믿을 수 없어서,
offline 은 받은 시각으로 기록한다 (`dialog/bus.py` 주석과 같은 약속).

### 대시보드 (백경률)

| 할 일 | 호출 |
|---|---|
| 사람 등록 | `POST /persons` `{"name": "..."}` |
| 등록 사진 (1인당 3장 이상 권장) | `POST /persons/{id}/photos` — multipart `file`, `consent=true` (**동의 없으면 400**) |
| 비활성화 (퇴사 등) | `PATCH /persons/{id}` `{"active": false}` |
| 경고 이력 | `GET /alerts?resolved=false` |
| 경고 해제 | **지금처럼 MQTT 로 resolved=true 발행** → 수집서버를 거쳐 자동 반영. `PATCH /alerts/{msg_id}/resolve` 는 DB 만 바로 고쳐야 할 때 |
| 방문자 한 명 기록 | `GET /sessions/{session_id}` |
| 노드 최근 상태 · 오늘 통계 | `GET /health/latest`, `GET /stats/today` ("오늘" 은 한국 시간 0시부터, `LOCAL_TZ`) |
| 경고 사진 | `GET /snapshots/{session_id}/{파일}` — 메시지의 `snapshot_path` 가 `/data/snap/<session>/<파일>` 이면 앞의 `/data/snap` 을 `/snapshots` 로 바꿔 부르면 된다 |

토큰은 **대시보드 서버(Flask)가 들고 대신 부르는 것**을 권한다 — 브라우저 JS 에 토큰을 두면 누구나 볼 수 있다.
브라우저가 직접 불러야 하면 `.env` 의 `CORS_ORIGINS` 에 대시보드 주소를 넣는다.

### A 노트북 (여도훈)

| 할 일 | 호출 |
|---|---|
| 새로 등록 · 바뀐 사람 | `GET /persons?updated_since=<마지막 확인 시각>` — 사진마다 `sha256` 이 있어 바뀐 사진만 받으면 된다 |
| 등록 사진 원본 | `GET /persons/{id}/photos/{photo_id}` — 서버가 복호화해서 준다 |
| 경고 사진 올리기 | `POST /snapshots` — multipart `file`, `session_id`, `kind`(face · ppe · alert) → 응답의 `snapshot_path` 를 메시지에 넣는다 |

얼굴 특징값(임베딩)은 스키마 주석대로 **DB 에 넣지 않고 A 안에 둔다.** API 는 사진만 다룬다.

### B 파이 (김별이)

```bash
API_URL=http://<서버>:8080 API_TOKEN=<mechdog_b 토큰> python3 tools/dialog_log_upload.py ~/dialog_logs/*.jsonl
```

---

## 보안

- **등록 사진 · 경고 사진은 암호화해서 저장** (Fernet, `PHOTO_KEY`). 키는 API 서버만 가진다 — A · 대시보드는 API 를 거쳐서만 원본을 본다. 키가 없으면 **둘 다 업로드를 거부**한다 (평문으로 몰래 저장하지 않는다).
- **`PHOTO_KEY` 를 잃어버리면 저장된 사진을 못 연다.** 따로 백업해 둔다.
- 경고 사진은 **7일 뒤 자동 삭제** (`SNAPSHOT_RETENTION_DAYS`, access_decisions 주석 기준).
- 모든 요청은 **감사 로그**(`logs/audit_*.jsonl`)에 누가 · 언제 · 무엇을 · 결과가 남는다.
- `.env` (토큰 · DB 비밀번호 · 암호화 키)는 커밋하지 않는다.

## 정해야 할 것 — `TODO(협의)`

코드에서 `TODO(협의)` 로 검색하면 전부 나온다. 결정이 나면 표시된 곳만 고치면 된다.

| 무엇 | 누구와 | 지금은 |
|---|---|---|
| `alert_logs.level` 허용값에 `INFO` 추가 | 최현수 | info → **INFO**(참고 알림, 처음부터 해제됨) · warn → WARNING · critical → ALERT. 지금 info 를 보내는 노드는 없다 (B 이탈 알림은 09-29 삭제) — 나중에 누가 보내도 경고에 섞이지 않게 둔 것. 칸이 TEXT 라 스키마 변경 없이 동작하고, 주석의 허용값만 고치면 된다 |
| 한 세션에 판정이 한 번뿐인지 | 여도훈 | **1회 1행으로 합침 (09-29)** — A 판정 흐름도(사진 1장 → 얼굴 · PPE → `policy.decide()`)와 A 의 표 설계에 맞춘 것. 판정 실패 시 새 세션으로 다시 시작한다는 전제라 **같은 세션 = 판정 1회** 로 합친다. 재방문도 새 세션이라 새 행. 한 세션에서 여러 번 판정하게 되면 합치기 기준을 바꿔야 한다 |
| `escort_logs` session_id 없음 · 중단 표시 | 최현수 | robot_id 숫자는 HW 설계도 이름(mechdog-01~04)과 같아 **그대로 둬도 된다**. 중단은 motion_played='aborted' |
| `access_decisions` · `event_logs` 에 session_id · msg_id | 최현수 | 없음 — [`sql/proposed_changes.sql`](sql/proposed_changes.sql) |
| 감사 로그를 DB 로 | 최현수 | 파일 |
| 경고 해제를 무엇으로 맞출지 | 백경률 · 최현수 | 스키마 주석은 같은 msg_id, 대시보드 코드는 새 msg_id + (session_id, reason) → 둘 다 받음 |
| 토큰 · 권한 표 | 전원 | 위 표 |
| C 쪽 "MQTT-DB 브릿지" 가 지금 동작하는지 | 최현수 | **확인 필요** — `DogC_Flow` 문서 · host2 compose 주석에 escort/status 를 브릿지로 `event_logs` 에 저장한다고 적혀 있다(코드는 미확인). 동작 중이면 끄지 않을 경우 API 경로와 중복 저장된다 |

## 시험

```bash
docker run -d --name mechdog_api_testdb -e POSTGRES_USER=mechdog -e POSTGRES_PASSWORD=mechdog \
    -e POSTGRES_DB=mechdog -p 55432:5432 postgres:16
docker exec -i mechdog_api_testdb psql -U mechdog -d mechdog < <팀 스키마 SQL>
cd api-server && .venv/Scripts/pip install -r requirements-dev.txt && .venv/Scripts/python -m pytest -q
```

39개 — 얼굴 · PPE 1행 합치기(순서 무관 · 사유 합집합 · 재방문), person_id · latency_ms, 인증 · 권한, DB 장애 시 503 · 서버 버그 시 500, 실패 후 재전송, 규칙 없는 새 종류 보존, ingest_log 모드,
LWT 시각, 해제 중복 수신, 목적지 바뀐 에스코트, 오늘 기준 시간대, 암호화 키 없음 · .enc 직접 요청 차단, 예시 메시지 8종 적재, 중복 수신, 스키마 위반, 경고 해제(두 방식), health 변화 감지,
에스코트 출발 · 도착 · 중단, 일괄 적재 부분 실패, 등록 사진 암호화 왕복 · 동의 · 권한, 경고 사진 · 경로 조작 차단,
조회 엔드포인트, 대화 로그 이중 적재.
