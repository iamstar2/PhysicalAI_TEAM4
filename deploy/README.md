# 노트북 4대 배치

별도 서버 PC 없이 **각자 노트북에서 자기 역할을 띄운다** (0929 회의).
`docker-compose.host1.yml` · `host2.yml` 은 처음 설계(서버 2대) 기준이라, 실제 배치는 이 폴더의 파일을 쓴다.

| 노트북 | 담당 | 띄우는 것 | 파일 | 열어야 할 포트 |
|---|---|---|---|---|
| **A** | 여도훈 | MQTT 브로커 · 수집서버 | `a-broker.yml` | 1883 (MQTT), 9001 |
| **B** | 김별이 | API 서버 (대화 서비스는 라즈베리파이5) | `b-api.yml` | 8080 |
| **C** | 최현수 | PostgreSQL | `c-db.yml` | 5432 |
| **D** | 백경률 | 보안 대시보드 | `d-dashboard.yml` | 3000 |

```
로봇 4대 · B 파이 ─MQTT→ [A 브로커] → [A 수집서버] ─HTTP→ [B API 서버] ─SQL→ [C DB]
                          │                                   ↑
                          └─MQTT→ [D 대시보드] ─HTTP(이력 · 사진 · 얼굴 등록)┘
                                        └─UDP 9027→ D 로봇
```

## 준비 (각자 한 번)

```bash
cp deploy/.env.example deploy/.env        # 시연 망에서 고정한 IP 를 채운다 — 네 명 모두 같은 값
```

- B 는 추가로 `api-server/.env` (DB 주소 · 토큰 · 암호화 키) — `api-server/README.md`
- C 는 `deploy/.env` 에 `DB_PASSWORD` · `TEAM_SCHEMA_SQL`(팀 스키마 파일 경로)
- A 는 `deploy/.env` 에 `COLLECTOR_TOKEN` (김별이에게 받음)
- `.env` 는 전부 커밋하지 않는다 (`.gitignore` 에 있음)

## 띄우는 순서

| 순서 | 누가 | 명령 | 확인 |
|---|---|---|---|
| 1 | 공유기 · 핫스팟 | 켜고 4대 접속 | 각자 `ipconfig` 로 IP 가 `deploy/.env` 값과 같은지 |
| 2 | C | `docker compose -f deploy/c-db.yml up -d` | `docker logs postgres` 에 `ready to accept connections` |
| 3 | A | `docker compose -f deploy/a-broker.yml up -d` | 다른 노트북에서 `mosquitto_sub -h <A IP> -t 'mechdog/v1/#' -v` |
| 4 | B | `docker compose -f deploy/b-api.yml up -d --build` | 브라우저 `http://<B IP>:8080/healthz` → `"db": true` |
| 5 | A | `docker compose -f deploy/a-broker.yml --profile collector up -d` | 수집서버 코드가 생긴 뒤 |
| 6 | D | `docker compose -f deploy/d-dashboard.yml up -d --build` (또는 직접 실행) | `http://<D IP>:3000` |
| 7 | 로봇 | A · B · C · D 전원 | 대시보드에 4대 `online` |

## 자주 막히는 것

- **윈도우 방화벽** — 다른 노트북에서 포트에 못 붙으면 거의 이것이다. 핫스팟 · 새 WiFi 는
  "공용 네트워크" 로 잡혀 들어오는 연결을 막는다. 네트워크 설정에서 **개인 네트워크**로 바꾸거나,
  Docker Desktop 이 처음 물을 때 허용한다.
- **IP 가 바뀜** — 로봇 ESP32 의 `secrets.h`, B 파이의 `MQTT_HOST`, D 대시보드의 `D_ROBOT_IP` 가 전부
  고정 IP 를 보고 있다. 바뀌면 다시 올려야 하니 **시연 전날 같은 망으로 한 번 확인**한다.
- **C 스키마가 안 들어감** — 초기화 스크립트는 DB 볼륨이 **비어 있을 때 한 번만** 돈다.
  이미 띄운 적이 있으면 `down -v` 로 지우고 다시 띄우거나, `psql` 로 직접 적용한다.
- **브로커 위치가 바뀜** — 지금까지는 김별이 PC 에서 브로커를 돌렸다. A 노트북으로 옮기면
  **B 파이(`~/run_demo.sh` 의 `MQTT_HOST`)와 B 본체 ESP32 의 브로커 주소도 A IP 로** 바꿔야 한다.
