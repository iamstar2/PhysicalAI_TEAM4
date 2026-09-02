# DECISIONS.md — 미확정 값 & 확인 체크리스트

이 문서는 `mechdog_common` 패키지에 반영된 값 중 팀 합의 없이 임시로 정한 것,
그리고 이미 검토·해결된 항목을 추적한다. 회의(2026-09-02) 결정 사항을 기반으로 작성.

---

## 아직 못 정한 것 (검토 필요)

### 1. 목적지 ID 목록 — `enums.py: Destination`
- 현재 `lobby`, `meeting_room_1`, `meeting_room_2`, `office_2f`, `warehouse` 5개를 임시로 넣어둠.
- 실제 건물 목적지 ID ↔ 좌표 매핑표가 아직 없음 (회의록 4-C "할 일" 항목).
- **담당자**: 최현수(맵/에스코트) / 여도훈(게이트에서도 목적지 후보를 알아야 함)
- **확인할 것**: 실제 목적지 개수·이름, 좌표 테이블, 마커 배치 계획 확정 후 `Destination` enum 값 교체.
- 코드에 `# TODO` 주석으로 표시되어 있어 검토 없이 그대로 배포되지 않도록 해둠.

### 2. 얼굴 유사도 임계값 — `enums.py: FACE_SIMILARITY_THRESHOLD`
- 회의록 권장 범위(0.5~0.6) 중 임시로 중간값 0.55 사용.
- 등록자 데이터셋으로 실측 튜닝 전.
- **담당자**: 여도훈(vision-service 정확도) / 최현수(오탐 시 보안 리스크 협의)
- **확인할 것**: 등록자 10인 이상 데이터셋으로 오탐율(FAR)·거부율(FRR) 실측 후 확정.

### 3. 재시도 횟수 / 경고 해제 조건
- `undetermined` 시나리오에서 "3회 실패 시 D로 이관"은 회의록에 나온 예시 값을 그대로
  `mock_publisher.py`에 넣은 것이며, `enums.py`에 상수로 고정되어 있지 않음.
- 안전모 미착용 경고의 "자동 해제" 조건(재검사 1회 통과로 충분한지, N회 연속 통과가
  필요한지)도 미정.
- **담당자**: 백경률(D 상태 머신 설계) / 여도훈(재촬영 로직)
- **확인할 것**: 값이 확정되면 `enums.py`에 `MAX_FACE_RETRY` 같은 상수로 추가하고
  이 문서에서 항목을 지운다.

---

## 이번 라운드에서 해결된 것

### ~~세션 ID 동시 접근 충돌~~ — 해결됨
같은 초에 두 방문자가 게이트에 동시 접근하면 타임스탬프만으로는 `session_id`가
충돌할 수 있다는 문제를 검토함. `messages.py`의 `new_session_id()`에 uuid4 8자리를
섞어 프로세스 재시작·다중 인스턴스와 무관하게 유일성을 보장하도록 수정 완료
(선택 이유는 함수 docstring에 기록).

### ~~QoS 정책 근거 미문서화~~ — 해결됨
`topics.py`에 메시지 타입별 QoS/Retain 선택 이유를 주석으로 추가. 판정 결과
(`vision.face`, `vision.ppe`, `gate.session`, `dialog.result`)와 경고(`alert.event`)는
QoS 1로 재확인/수정 완료. 스트림성 메시지(`escort.status`, `system.health`)만 QoS 0.

### ~~Docker 통합 방식 미정~~ — 해결됨
pip 로컬 패키지(COPY + `pip install`) 방식으로 결정. 이유와 Dockerfile/compose
예시는 README.md "Docker 통합" 절 참고.

### ~~MQTT 인증 없음~~ — 해결됨
`bus.py`가 `MQTT_USER`/`MQTT_PASS` 환경변수 존재 여부로 인증 모드를 자동 전환하도록
구현 완료. 로컬 데모(기본값, 인증 없음)와 외부 노출(인증 필수) 두 케이스를
README.md에 분리해서 정리.

### ~~얼굴 이미지 보관 정책 없음~~ — 해결됨
`tools/cleanup_snapshots.py` 추가. `MECHDOG_RETENTION_DAYS`(기본 7일) 경과한
날짜 디렉터리를 정리. cron 등록 방법은 README.md 참고.

---

## 확인 체크리스트 (담당자별)

- [ ] **여도훈**: `FACE_SIMILARITY_THRESHOLD` 실측 튜닝 값 확정
- [ ] **최현수 / 여도훈**: `Destination` 목적지 ID·좌표 확정
- [ ] **백경률 / 여도훈**: 재시도 횟수, 경고 자동 해제 조건 확정 → `enums.py` 상수화
- [ ] **여도훈**: 외부 네트워크 노출 여부에 따라 Mosquitto `allow_anonymous` 설정 및
      `MQTT_USER`/`MQTT_PASS` 배포용 값 발급
- [ ] **전원**: `mechdog_common` 버전(`pyproject.toml`)이 바뀌면 각자 컨테이너에서
      재빌드했는지 확인
