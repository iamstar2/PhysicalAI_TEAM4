-- API 서버가 제안하는 팀 스키마 변경 — 최현수(DB) 확인 전에는 적용하지 않는다.
-- 적용되면 app/ingest.py 의 TODO(협의) 부분을 같이 고친다.

-- 1) escort_logs — 메시지는 노드 이름(mechdog_c)을 쓰는데 robot_id 가 INTEGER,
--    방문자와 묶을 session_id 칸이 없음. 중단(aborted)을 표시할 칸이 없어 motion_played 를 빌려 쓰는 중.
ALTER TABLE escort_logs ALTER COLUMN robot_id TYPE TEXT USING robot_id::text;
ALTER TABLE escort_logs ADD COLUMN session_id TEXT REFERENCES sessions(session_id);
ALTER TABLE escort_logs ADD COLUMN result TEXT;          -- 'arrived' | 'aborted'

-- 2) access_decisions — 방문자 한 명의 기록을 묶을 session_id 가 없음
ALTER TABLE access_decisions ADD COLUMN session_id TEXT REFERENCES sessions(session_id);

-- 3) event_logs — 중복 수신을 거를 키가 없음
ALTER TABLE event_logs ADD COLUMN msg_id TEXT UNIQUE;

-- 4) 감사 로그 — 지금은 파일(api-server/logs/audit_*.jsonl). DB 로 옮길 때
CREATE TABLE IF NOT EXISTS audit_logs (
    id         BIGSERIAL   PRIMARY KEY,
    at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    client     TEXT        NOT NULL,      -- 토큰 이름 (collector, dashboard, ...)
    method     TEXT        NOT NULL,
    path       TEXT        NOT NULL,
    status     SMALLINT    NOT NULL,
    ms         REAL
);

-- 5) 받은 메시지 기록 (HW 설계도 DB 의 ingest_log) — 중복 수신을 서버 재시작 뒤에도 거르기 위해.
--    없으면 API 서버가 메모리로 대신한다 (재시작하면 잊지만 각 테이블의 ON CONFLICT 가 받쳐 줌).
--    msg_key 는 보통 msg_id, 같은 msg_id 로 오는 경고 해제는 '<msg_id>#resolved'.
CREATE TABLE IF NOT EXISTS ingest_log (
    msg_key      TEXT        PRIMARY KEY,
    msg_type     TEXT        NOT NULL,
    src          TEXT        NOT NULL,
    ts           TIMESTAMPTZ NOT NULL,      -- 발행 측 시각
    received_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
