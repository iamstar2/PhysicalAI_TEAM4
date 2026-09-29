from __future__ import annotations

import copy
import uuid

from conftest import H, rows

COL, DASH, A, B, D = "t-col", "t-dash", "t-a", "t-b", "t-d"
JPEG = b"\xff\xd8\xff\xe0" + b"fake-jpeg" * 20


def _msg(ex, msg_type, **payload):
    m = copy.deepcopy(ex[msg_type])
    m["msg_id"] = uuid.uuid4().hex
    m["payload"].update(payload)
    return m


# --- 인증 · 권한 ---------------------------------------------------------------

def test_no_token_401(client, examples):
    assert client.post("/events", json=examples["gate.session"]).status_code == 401


def test_wrong_client_403(client, examples):
    assert client.post("/events", json=examples["gate.session"], headers=H(DASH)).status_code == 403


def test_healthz(client):
    r = client.get("/healthz").json()
    assert r["db"] and r["encryption"]


# --- 적재 -----------------------------------------------------------------------

def test_all_examples_store(client, examples):
    # 예시 8종이 전부 스키마를 통과하고 어딘가에 들어가야 한다
    order = ["gate.session", "vision.face", "vision.ppe", "dialog.result", "escort.status",
             "alert.event", "system.health", "robot.command"]
    for t in order:
        r = client.post("/events", json=examples[t], headers=H(COL))
        assert r.status_code == 200, (t, r.json())
    assert rows("SELECT visitor_id FROM sessions WHERE session_id = %s",
                examples["gate.session"]["session_id"])[0]["visitor_id"] == "visitor-001"
    assert len(rows("SELECT * FROM access_decisions")) == 1      # 같은 세션의 얼굴 · PPE → 1행
    assert rows("SELECT destination FROM dialog_sessions")[0]["destination"] == "meeting_room_1"
    assert rows("SELECT level FROM alert_logs")[0]["level"] == "ALERT"
    assert len(rows("SELECT * FROM escort_logs")) == 1
    assert len(rows("SELECT * FROM event_logs")) == 1


def test_duplicate_is_idempotent(client, examples):
    for _ in range(3):
        for t in ("gate.session", "vision.face", "dialog.result", "alert.event", "system.health"):
            assert client.post("/events", json=examples[t], headers=H(COL)).status_code == 200
    assert len(rows("SELECT * FROM access_decisions")) == 1
    assert len(rows("SELECT * FROM alert_logs")) == 1
    assert len(rows("SELECT * FROM system_health")) == 1


def test_schema_violation_rejected(client, examples):
    bad = copy.deepcopy(examples["dialog.result"])
    bad["payload"]["destination"] = "rooftop"
    bad["ts"] = "2026-09-02T14:25:40"                  # 시간대 없음
    r = client.post("/events", json=bad, headers=H(COL))
    assert r.status_code == 422
    assert len(r.json()["detail"]["errors"]) == 2
    assert rows("SELECT * FROM dialog_sessions") == []


def test_alert_resolve_same_msg_id(client, examples):
    m = examples["alert.event"]
    client.post("/events", json=m, headers=H(COL))
    done = copy.deepcopy(m)
    done["payload"]["resolved"] = True
    assert client.post("/events", json=done, headers=H(COL)).status_code == 200
    r = rows("SELECT resolved, resolved_at FROM alert_logs")
    assert len(r) == 1 and r[0]["resolved"] and r[0]["resolved_at"] is not None


def test_alert_resolve_dashboard_style(client, examples):
    # D 대시보드는 해제 때 msg_id 를 새로 만들고 (session_id, reason) 으로 가리킨다
    m = examples["alert.event"]
    client.post("/events", json=m, headers=H(COL))
    other = _msg(examples, "alert.event", reason="no_helmet", level="warn")
    client.post("/events", json=other, headers=H(COL))              # 같은 세션, 다른 사유
    done = _msg(examples, "alert.event", resolved=True, snapshot_path=None)
    assert client.post("/events", json=done, headers=H(COL)).status_code == 200
    r = {x["reason"]: x["resolved"] for x in rows("SELECT reason, resolved FROM alert_logs")}
    assert r == {"unauthorized": True, "no_helmet": False}          # 해당 사유만, 새 행 없이


def test_alert_without_gate_session_creates_session(client, examples):
    # 미인가자는 gate.session 없이 D 경고만 올 수 있다 — FK 때문에 실패하면 안 된다
    r = client.post("/events", json=examples["alert.event"], headers=H(COL))
    assert r.status_code == 200
    assert len(rows("SELECT * FROM sessions")) == 1


def test_health_only_on_change(client, examples):
    for state in ("ready", "ready", "busy", "busy", "ready"):
        client.post("/events", json=_msg(examples, "system.health", state=state), headers=H(COL))
    assert [r["status"] for r in rows("SELECT status FROM system_health ORDER BY health_id")] \
        == ["ready", "busy", "ready"]


def test_escort_trip(client, examples):
    for state in ("idle", "moving", "moving", "paused", "moving", "arrived", "idle", "moving", "aborted"):
        client.post("/events", json=_msg(examples, "escort.status", state=state), headers=H(COL))
    r = rows("SELECT success, arrival_time, motion_played FROM escort_logs ORDER BY id")
    assert len(r) == 2
    assert r[0]["success"] == 1 and r[0]["arrival_time"] is not None
    assert r[1]["success"] == 0 and r[1]["motion_played"] == "aborted"


def test_batch_partial_failure(client, examples):
    bad = copy.deepcopy(examples["vision.face"])
    del bad["payload"]["result"]
    r = client.post("/events/batch", json=[examples["gate.session"], bad], headers=H(COL)).json()
    assert r["ok"] == 1 and r["failed"] == 1


# --- 얼굴 등록 -------------------------------------------------------------------

def test_person_photo_encrypted_roundtrip(client):
    p = client.post("/persons", json={"name": "홍길동"}, headers=H(DASH)).json()
    r = client.post(f"/persons/{p['person_id']}/photos", headers=H(DASH),
                    files={"file": ("a.jpg", JPEG, "image/jpeg")}, data={"consent": "true"})
    assert r.status_code == 201, r.text
    stored = rows("SELECT image FROM person_photos")[0]["image"]
    assert bytes(stored) != JPEG                                  # DB 에는 암호문
    listed = client.get("/persons", headers=H(A)).json()
    assert listed[0]["photos"][0]["sha256"]
    got = client.get(f"/persons/{p['person_id']}/photos/{r.json()['photo_id']}", headers=H(A))
    assert got.content == JPEG                                    # A 는 원본을 받는다


def test_person_photo_needs_consent(client):
    p = client.post("/persons", json={"name": "홍길동"}, headers=H(DASH)).json()
    r = client.post(f"/persons/{p['person_id']}/photos", headers=H(DASH),
                    files={"file": ("a.jpg", JPEG, "image/jpeg")}, data={"consent": "false"})
    assert r.status_code == 400


def test_a_cannot_register(client):
    assert client.post("/persons", json={"name": "x"}, headers=H(A)).status_code == 403


def test_persons_updated_since(client):
    p = client.post("/persons", json={"name": "a"}, headers=H(DASH)).json()
    later = client.get("/persons", params={"updated_since": p["updated_at"]}, headers=H(A)).json()
    assert later == []
    client.patch(f"/persons/{p['person_id']}", json={"active": False}, headers=H(DASH))
    later = client.get("/persons", params={"updated_since": p["updated_at"]}, headers=H(A)).json()
    assert later[0]["active"] is False


# --- 경고 사진 -------------------------------------------------------------------

def test_snapshot_upload_and_get(client):
    r = client.post("/snapshots", headers=H(A), data={"session_id": "sess-1", "kind": "face"},
                    files={"file": ("f.jpg", JPEG, "image/jpeg")})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["snapshot_path"].startswith("/data/snap/sess-1/face-")
    assert client.get(body["url"], headers=H(DASH)).content == JPEG


def test_snapshot_path_traversal(client):
    r = client.post("/snapshots", headers=H(A), data={"session_id": "../etc", "kind": "x"},
                    files={"file": ("f.jpg", JPEG, "image/jpeg")})
    assert r.status_code == 400


# --- 조회 · B 로그 -----------------------------------------------------------------

def test_query_endpoints(client, examples):
    for t in ("gate.session", "dialog.result", "alert.event", "system.health"):
        client.post("/events", json=examples[t], headers=H(COL))
    sid = examples["gate.session"]["session_id"]
    s = client.get(f"/sessions/{sid}", headers=H(DASH)).json()
    assert s["dialog"]["destination"] == "meeting_room_1"
    assert client.get("/alerts", params={"resolved": False}, headers=H(DASH)).json()
    msg_id = examples["alert.event"]["msg_id"]
    assert client.patch(f"/alerts/{msg_id}/resolve", headers=H(DASH)).json()["resolved"]
    assert client.get("/health/latest", headers=H(DASH)).json()[0]["status"] == "ready"
    assert "visitors" in client.get("/stats/today", headers=H(DASH)).json()


def test_dialog_import_twice(client, examples):
    sid = "sess-20260929-b-demo"
    recs = [
        {"rec": "session", "session_id": sid, "visitor_id": None,
         "started_at": "2026-09-29T10:00:00+09:00", "ended_at": "2026-09-29T10:01:00+09:00",
         "outcome": "handoff", "destination": "safety_training_room", "purpose": "교육",
         "confidence": 0.9, "retry_count": 0, "escalation_reason": None},
        {"rec": "turn", "session_id": sid, "turn_no": 1, "ts": "2026-09-29T10:00:10+09:00",
         "stt_raw": "교육 받으러 왔어요", "candidates": [{"dest": "safety_training_room"}],
         "decision": "skip_confirm", "total_ms": 3900},
    ]
    for _ in range(2):
        r = client.post("/dialog/import", json=recs, headers=H(B))
        assert r.status_code == 200, r.text
    assert len(rows("SELECT * FROM dialog_turns")) == 1
    assert rows("SELECT candidates FROM dialog_turns")[0]["candidates"][0]["dest"] \
        == "safety_training_room"


def test_db_down_returns_503(client, examples, monkeypatch):
    # DB 장애는 422(메시지 탓)가 아니라 503 — 수집서버가 버리지 않고 다시 보내게
    import psycopg
    from app import db

    monkeypatch.setattr(db, "tx", lambda: (_ for _ in ()).throw(psycopg.OperationalError("down")))
    r = client.post("/events", json=examples["gate.session"], headers=H(COL))
    assert r.status_code == 503


# --- 점검(0929)에서 고친 것 — 재발 방지 ------------------------------------------

def _fail_once(monkeypatch, exc):
    from app import db
    real = db.tx
    state = {"n": 0}

    def tx():
        if state["n"] == 0:
            state["n"] += 1
            raise exc
        return real()
    monkeypatch.setattr(db, "tx", tx)


def test_duplicate_resolve_does_not_touch_new_alert(client, examples):
    # 해제 메시지가 QoS 1 로 두 번 와도, 그 사이 새로 난 같은 사유 경고를 해제하면 안 된다
    first = examples["alert.event"]
    client.post("/events", json=first, headers=H(COL))
    done = _msg(examples, "alert.event", resolved=True, snapshot_path=None)
    client.post("/events", json=done, headers=H(COL))
    again = _msg(examples, "alert.event")                            # 재경보
    client.post("/events", json=again, headers=H(COL))
    assert client.post("/events", json=done, headers=H(COL)).json()["stored"] == "중복(건너뜀)"
    r = {x["msg_id"]: x["resolved"] for x in rows("SELECT msg_id, resolved FROM alert_logs")}
    assert r == {first["msg_id"]: True, again["msg_id"]: False}


def test_robot_command_duplicate(client, examples):
    for _ in range(3):
        client.post("/events", json=examples["robot.command"], headers=H(COL))
    assert len(rows("SELECT * FROM event_logs")) == 1


def test_retry_after_db_failure_is_not_skipped(client, examples, monkeypatch):
    # 실패한 메시지를 '본 것' 으로 기억하면 수집서버의 재전송이 버려진다
    import psycopg
    m = _msg(examples, "escort.status", state="moving")
    _fail_once(monkeypatch, psycopg.OperationalError("down"))
    assert client.post("/events", json=m, headers=H(COL)).status_code == 503
    assert client.post("/events", json=m, headers=H(COL)).json()["stored"] == "escort_logs(출발)"
    assert len(rows("SELECT * FROM escort_logs")) == 1


def test_server_bug_is_500_not_422(client, examples, monkeypatch):
    # 서버 버그를 422(메시지 탓)로 돌려주면 수집서버가 버린다
    from app import ingest

    def broken(c, m, p):
        raise KeyError("oops")
    monkeypatch.setitem(ingest.HANDLERS, "gate.session", broken)
    assert client.post("/events", json=examples["gate.session"], headers=H(COL)).status_code == 500
    monkeypatch.undo()
    r = client.post("/events", json=examples["gate.session"], headers=H(COL))
    assert r.json()["stored"] == "sessions"                         # 고친 뒤 재전송하면 들어간다


def test_type_without_rule_is_kept(client, examples, monkeypatch):
    from app import ingest
    monkeypatch.delitem(ingest.HANDLERS, "robot.command")
    r = client.post("/events", json=examples["robot.command"], headers=H(COL)).json()
    assert r["stored"] == "event_logs(규칙 없음)"
    assert rows("SELECT event_type FROM event_logs")[0]["event_type"] == "robot.command"


def test_lwt_offline_uses_receive_time(client, examples):
    client.post("/events", json=_msg(examples, "system.health", state="busy"), headers=H(COL))
    lwt = _msg(examples, "system.health", state="offline", detail="LWT")
    lwt["ts"] = "2026-09-01T09:00:00+09:00"                          # 접속했던 시각
    client.post("/events", json=lwt, headers=H(COL))
    latest = client.get("/health/latest", headers=H(DASH)).json()[0]
    assert latest["status"] == "offline" and not latest["occurred_at"].startswith("2026-09-01")


def test_escort_destination_change_closes_open_trip(client, examples):
    client.post("/events", json=_msg(examples, "escort.status", state="moving"), headers=H(COL))
    client.post("/events", json=_msg(examples, "escort.status", state="moving",
                                     destination="exit_gate"), headers=H(COL))
    r = rows("SELECT destination, motion_played FROM escort_logs ORDER BY id")
    assert [x["motion_played"] for x in r] == ["aborted", None]


def test_stats_today_uses_local_timezone(client):
    from datetime import datetime
    from zoneinfo import ZoneInfo
    since = client.get("/stats/today", headers=H(DASH)).json()["since"]
    t = datetime.fromisoformat(since).astimezone(ZoneInfo("Asia/Seoul"))
    assert (t.hour, t.minute) == (0, 0)


def test_snapshot_refused_without_key(client, monkeypatch):
    from app import config
    monkeypatch.setattr(config, "PHOTO_KEY", "")
    r = client.post("/snapshots", headers=H(A), data={"session_id": "s1", "kind": "face"},
                    files={"file": ("f.jpg", JPEG, "image/jpeg")})
    assert r.status_code == 503


def test_snapshot_enc_name_blocked(client):
    body = client.post("/snapshots", headers=H(A), data={"session_id": "s1", "kind": "face"},
                       files={"file": ("f.jpg", JPEG, "image/jpeg")}).json()
    assert client.get(body["url"] + ".enc", headers=H(DASH)).status_code == 400


def test_dialog_import_bad_value_is_422(client):
    recs = [{"rec": "session", "session_id": "sess-x", "started_at": "2026-09-29T10:00:00+09:00"},
            {"rec": "turn", "session_id": "sess-x", "turn_no": "첫번째", "ts": "2026-09-29T10:00:01+09:00"}]
    assert client.post("/dialog/import", json=recs, headers=H(B)).status_code == 422
    assert rows("SELECT * FROM dialog_sessions") == []               # 전체가 취소된다


def test_ingest_log_table_mode(client, examples):
    # 최현수가 ingest_log 를 추가하면 DB 로 중복을 거른다 (재시작 뒤에도 유지)
    from pathlib import Path

    from app import db, ingest
    sql = (Path(__file__).parents[1] / "sql" / "proposed_changes.sql").read_text(encoding="utf-8")
    ddl = sql[sql.index("CREATE TABLE IF NOT EXISTS ingest_log"):]
    with db.tx() as c:
        c.execute(ddl)
    try:
        ingest.reset_cache()
        alert = examples["alert.event"]
        client.post("/events", json=examples["robot.command"], headers=H(COL))
        client.post("/events", json=alert, headers=H(COL))
        ingest.reset_cache()                                         # 서버 재시작 흉내
        client.post("/events", json=examples["robot.command"], headers=H(COL))
        done = copy.deepcopy(alert)
        done["payload"]["resolved"] = True                           # 같은 msg_id 로 해제
        client.post("/events", json=done, headers=H(COL))
        assert len(rows("SELECT * FROM event_logs")) == 1
        assert rows("SELECT resolved FROM alert_logs")[0]["resolved"] is True
        assert len(rows("SELECT * FROM ingest_log")) == 3
    finally:
        with db.tx() as c:
            c.execute("DROP TABLE ingest_log")
        ingest.reset_cache()


def test_vision_face_person_id_and_latency(client, examples):
    # 등록된 사람이면 person_id 가 들어가고, 아니면 FK 로 실패하지 않게 비운다
    client.post("/persons", json={"name": "홍길동", "person_id": "EMP-0001"}, headers=H(DASH))
    client.post("/events", json=examples["vision.face"], headers=H(COL))
    unknown = _msg(examples, "vision.face", person_id="EMP-9999")
    unknown["session_id"] = "sess-20260929-other"                   # 다른 방문
    assert client.post("/events", json=unknown, headers=H(COL)).status_code == 200
    r = rows("SELECT person_id, latency_ms FROM access_decisions ORDER BY decision_id")
    assert r == [{"person_id": "EMP-0001", "latency_ms": 180}, {"person_id": None, "latency_ms": 180}]


def test_old_style_vision_without_new_fields_still_ok(client, examples):
    old = _msg(examples, "vision.face")
    del old["payload"]["person_id"], old["payload"]["latency_ms"]
    assert client.post("/events", json=old, headers=H(COL)).status_code == 200


# --- 출입 판정 1회 = 1행 (A 판정 흐름도: 사진 1장 → 얼굴 · PPE → policy.decide() 한 번) -------

def test_face_and_ppe_merge_into_one_decision(client, examples):
    face = examples["vision.face"]                                      # authorized, 0.81
    ppe = _msg(examples, "vision.ppe", items={"helmet": "fail", "vest": "pass"}, overall="fail")
    for m in (ppe, face):                                               # 순서가 바뀌어 와도
        assert client.post("/events", json=m, headers=H(COL)).status_code == 200
    r = rows("SELECT * FROM access_decisions")
    assert len(r) == 1
    d = r[0]
    assert d["event_id"] == face["session_id"]
    assert (d["decision"], d["reasons"], d["helmet"]) == ("deny", "no_helmet", "미착용")
    assert d["match_score"] == 0.81 and d["latency_ms"] == 180          # 얼굴 180 · PPE 95 중 큰 값
    assert d["snapshot_path"] == ppe["payload"]["snapshot_path"]        # 차단 쪽 사진


def test_both_pass_is_allow_without_photo(client, examples):
    client.post("/events", json=examples["vision.face"], headers=H(COL))
    client.post("/events", json=examples["vision.ppe"], headers=H(COL))
    d = rows("SELECT decision, reasons, helmet, snapshot_path FROM access_decisions")[0]
    assert d == {"decision": "allow", "reasons": None, "helmet": "착용", "snapshot_path": None}


def test_unauthorized_and_no_vest_reasons_union(client, examples):
    face = _msg(examples, "vision.face", result="unauthorized", person_id=None)
    ppe = _msg(examples, "vision.ppe", items={"helmet": "pass", "vest": "fail"}, overall="fail")
    client.post("/events", json=face, headers=H(COL))
    client.post("/events", json=ppe, headers=H(COL))
    d = rows("SELECT decision, reasons, snapshot_path FROM access_decisions")[0]
    assert d["decision"] == "deny" and d["reasons"] == "no_vest,unauthorized"
    assert d["snapshot_path"] == face["payload"]["snapshot_path"]       # 먼저 온 차단 사진 유지


def test_revisit_is_new_row(client, examples):
    # 재방문은 A 가 새 세션을 만든다 → 판정도 새 행
    client.post("/events", json=examples["vision.face"], headers=H(COL))
    again = _msg(examples, "vision.face")
    again["session_id"] = "sess-20260929150000-mechdog_a-00000002"
    client.post("/events", json=again, headers=H(COL))
    assert len(rows("SELECT * FROM access_decisions")) == 2


def test_info_alert_is_not_an_open_warning(client, examples):
    # info 는 참고 알림 (B: 응대 없이 떠난 방문자) — '미해제 경고' 로 쌓이면 안 된다
    m = _msg(examples, "alert.event", level="info", reason="dialog_timeout", snapshot_path=None)
    assert client.post("/events", json=m, headers=H(COL)).json()["stored"] == "alert_logs(참고 알림)"
    d = rows("SELECT level, resolved, resolved_at FROM alert_logs")[0]
    assert d["level"] == "INFO" and d["resolved"] and d["resolved_at"] is not None
    assert client.get("/alerts", params={"resolved": False}, headers=H(DASH)).json() == []


def test_dashboard_clearing_info_does_not_add_row(client, examples):
    # D 는 info 도 활성 카드로 띄우고, 관리자가 누르면 새 msg_id 로 resolved=true 를 보낸다
    m = _msg(examples, "alert.event", level="info", reason="dialog_timeout", snapshot_path=None)
    client.post("/events", json=m, headers=H(COL))
    clear = _msg(examples, "alert.event", level="info", reason="dialog_timeout",
                 snapshot_path=None, resolved=True)
    assert client.post("/events", json=clear, headers=H(COL)).json()["stored"] == "alert_logs(이미 해제)"
    assert len(rows("SELECT * FROM alert_logs")) == 1
