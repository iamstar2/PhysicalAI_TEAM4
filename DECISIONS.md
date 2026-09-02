# DECISIONS.md — 미확정 값 & 확인 체크리스트

이 문서는 `schema/` 의 메시지 스펙 중 팀 합의 없이 임시로 정한 것, 그리고 이미
검토·해결된 항목을 추적한다. 회의(2026-09-02) 결정 사항을 기반으로 작성.

---

## 아직 못 정한 것 (검토 필요)

### 1. 목적지 ID 목록 — `schema/mechdog_messages.schema.json: $defs.Destination`
- 현재 `lobby`, `meeting_room_1`, `meeting_room_2`, `office_2f`, `warehouse` 5개를 임시로 넣어둠.
- 실제 건물 목적지 ID ↔ 좌표 매핑표가 아직 없음 (회의록 4-C "할 일" 항목).
- **담당자**: 최현수(맵/에스코트) / 여도훈(게이트에서도 목적지 후보를 알아야 함)
- **확인할 것**: 실제 목적지 개수·이름, 좌표 테이블, 마커 배치 계획 확정 후 `Destination` enum 값 교체.
- 스키마에 `description`으로 `TODO` 주석을 달아둬서 검토 없이 그대로 배포되지 않도록 해둠.

### 2. 얼굴 유사도 임계값
- 회의록 권장 범위(0.5~0.6) 중 임시로 중간값 0.55를 참고값으로 씀.
- 이 값은 A(vision-service)가 자기 코드 안에서 쓰는 임계값이라 공용 스펙(`schema/`)에는
  안 들어있음 — MQTT로 오가는 건 이미 판정된 `result`(authorized/unauthorized/undetermined)뿐이고,
  임계값 자체는 A 내부 구현 값이기 때문.
- **담당자**: 여도훈(vision-service 정확도) / 최현수(오탐 시 보안 리스크 협의)
- **확인할 것**: 등록자 10인 이상 데이터셋으로 오탐율(FAR)·거부율(FRR) 실측 후 확정.

### 3. 재시도 횟수 / 경고 해제 조건
- `undetermined` 시나리오에서 "3회 실패 시 D로 이관"은 회의록 예시 값을 그대로
  `mock_publisher.py`에 넣은 것이며, 공용 스펙에 상수로 고정되어 있지 않음 (임계값과
  같은 이유로 A/D 내부 구현 값).
- 안전모 미착용 경고의 "자동 해제" 조건(재검사 1회 통과로 충분한지, N회 연속 통과가
  필요한지)도 미정.
- **담당자**: 백경률(D 상태 머신 설계) / 여도훈(재촬영 로직)
- **확인할 것**: 값이 확정되면 각자 서비스 코드에 상수로 반영. 이 값이 다른 노드도
  알아야 하는 값으로 바뀌면(예: 대시보드에 "N회 중 몇 번째 재시도" 표시) 그때는
  MQTT 페이로드 필드로 추가하고 스키마도 같이 고친다.

---

## 이번 라운드에서 해결된 것

### ~~공용 Python 패키지 유지 여부~~ — 결정됨: 없앰
`mechdog_common` Pydantic 패키지를 전부 제거하고 `schema/mechdog_messages.schema.json`
(JSON Schema) 하나로 스펙을 통일했다. 이유:
- 대시보드(백경률)가 React/JS라 Python 패키지를 쓸 수 없어서, 애초에 Python 3인
  A/B/C만 쓸 수 있는 스펙이었음.
- JSON Schema는 언어 무관 표준이라 Python은 `jsonschema`, JS는 `ajv` 등 각자
  언어에서 동일한 파일을 그대로 검증에 쓸 수 있음.
- 팀 규모(4명)·기간(짧음) 상, 공용 패키지의 버전 관리·재빌드 부담보다 "스펙 파일
  하나 보고 각자 구현"이 더 단순하다고 판단.
- 트레이드오프: Python 쪽에서 누리던 "필드 잘못 보내면 import 시점에 바로 에러"
  같은 강제성은 약해짐. 대신 `tools/validate_schema.py`로 스펙과 예시가
  어긋나지 않는지는 계속 확인 가능.

### ~~세션 ID 동시 접근 충돌~~ — 해결됨
같은 초에 두 방문자가 게이트에 동시 접근하면 타임스탬프만으로는 `session_id`가
충돌할 수 있다는 문제를 검토함. `tools/_common.py`의 `new_session_id()`에 uuid4
8자리를 섞어 프로세스 재시작·다중 인스턴스와 무관하게 유일성을 보장하도록 구현
(선택 이유는 함수 docstring에 기록). 각자 언어로 구현할 때도 같은 방식(타임스탬프
+ 충분히 긴 난수) 권장.

### ~~QoS 정책 근거 미문서화~~ — 해결됨
`schema/topics.json`에 메시지 타입별 QoS/Retain 선택 이유를 데이터로 기록. 판정 결과
(`vision.face`, `vision.ppe`, `gate.session`, `dialog.result`)와 경고(`alert.event`)는
QoS 1로 재확인/수정 완료. 스트림성 메시지(`escort.status`, `system.health`)만 QoS 0.

### ~~Docker 통합 방식 미정~~ — 해결됨(재검토)
공용 패키지가 없어졌으므로 "pip vs submodule vs 파일 복사" 논의 자체가 없어짐 —
JSON 스펙은 런타임에 컨테이너가 설치할 대상이 아니라 개발 시점 참고 문서라서,
그냥 이 저장소를 각자 클론해서 보면 된다. 배포 토폴로지(포트/볼륨)는
`docker-compose.yml` 참고.

### ~~MQTT 인증 없음~~ — 해결됨
로컬 데모(기본값, 인증 없음)와 외부 노출(인증 필수) 두 케이스를 README.md에
분리 정리. `tools/mock_publisher.py`/`echo_subscriber.py`가 `MQTT_USER`/`MQTT_PASS`
있으면 자동으로 인증 붙는 참고 구현이고, 각자 서비스 코드도 같은 패턴으로 구현하면 됨.

### ~~얼굴 이미지 보관 정책 없음~~ — 해결됨
`tools/cleanup_snapshots.py` 추가 (외부 의존성 없는 독립 스크립트). `MECHDOG_RETENTION_DAYS`
(기본 7일) 경과한 날짜 디렉터리를 정리. cron 등록 방법은 README.md 참고.

---

## 확인 체크리스트 (담당자별)

- [ ] **여도훈**: 얼굴 유사도 임계값 실측 튜닝 값 확정 (자기 서비스 내부 값)
- [ ] **최현수 / 여도훈**: `Destination` 목적지 ID·좌표 확정 → `schema/` 값 교체
- [ ] **백경률 / 여도훈**: 재시도 횟수, 경고 자동 해제 조건 확정
- [ ] **여도훈**: 외부 네트워크 노출 여부에 따라 Mosquitto `allow_anonymous` 설정 및
      `MQTT_USER`/`MQTT_PASS` 배포용 값 발급
- [ ] **전원**: `schema/mechdog_messages.schema.json`이 바뀌면(PR 머지되면) 각자
      서비스의 검증 코드가 최신 스키마를 보고 있는지 확인
