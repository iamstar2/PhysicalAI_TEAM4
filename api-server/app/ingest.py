"""메시지 → 테이블 적재 규칙.

**협의로 바뀔 가능성이 가장 큰 파일이다.** msg_type 하나당 함수 하나이고,
HANDLERS 표에 등록돼 있다. 규칙을 바꾸려면 해당 함수만 고치면 된다.
새 msg_type 이 스키마에 생기면 함수를 만들어 HANDLERS 에 한 줄 추가한다
(추가 전까지는 원본이 event_logs 에 남아 데이터가 사라지지 않는다).

`TODO(협의)` 표시가 붙은 곳이 팀과 정해야 하는 부분이다.

공통 원칙
- **같은 메시지를 두 번 받아도 결과가 같아야** 한다 (QoS 1 중복, retain 재수신, 수집서버 재전송).
  store() 가 msg_id 로 한 번 거르고(ingest_log), 각 함수도 가능한 한 스스로 안전하게 짠다.
- 판정은 하지 않는다. 받은 값을 테이블 모양으로 옮기기만 한다.
- 규칙상 넣을 수 없는 메시지는 ValueError — 422 로 돌아가 수집서버가 버린다.
"""
from __future__ import annotations

import json
import threading
from collections import OrderedDict
from typing import Callable

import psycopg

from . import config

# --- 값 매핑 (TODO(협의)) ----------------------------------------------------

# alert_logs.level 은 스키마 주석상 'WARNING' | 'ALERT' 2값인데, 메시지 level 은 info | warn | critical 3값.
# info 는 경고가 아니라 참고 알림이다 (B 가 응대 없이 떠난 방문자를 알릴 때만 씀 — dialog_timeout).
# WARNING 에 섞으면 관리자가 해제할 일 없는 행이 '미해제 경고' 로 쌓이므로 INFO 로 따로 두고
# 처음부터 해제된 것으로 넣는다. 칸이 TEXT 라 스키마 변경은 없고, 허용값 주석에 INFO 추가만 필요 (최현수).
ALERT_LEVEL = {"info": "INFO", "warn": "WARNING", "critical": "ALERT"}
AUTO_RESOLVED = {"info"}

# access_decisions.helmet 은 '착용' | '미착용' | '판정불가'
HELMET = {"pass": "착용", "fail": "미착용", "undetermined": "판정불가"}

# escort_logs.robot_id / event_logs.robot_id 가 INTEGER — 노드 이름을 번호로.
# 번호는 HW 설계도의 로봇 이름(mechdog-01 A · 02 B · 03 C · 04 D)과 같다.
# escort_logs · event_logs 는 C 의 기존 테이블이라 스키마에서 "그대로 유지" 로 돼 있다.
ROBOT_NO = {"mechdog_a": 1, "mechdog_b": 2, "mechdog_c": 3, "mechdog_d": 4}


# --- 중복 거르기 ---------------------------------------------------------------
# ingest_log 테이블(HW 설계도의 DB 항목)이 있으면 DB 에, 없으면 메모리에 기록한다.
# 메모리는 서버를 재시작하면 비지만, 그때도 각 규칙 함수의 ON CONFLICT 가 받쳐 준다.

_SEEN_MAX = 50_000
_seen: OrderedDict[str, None] = OrderedDict()
_seen_lock = threading.Lock()
_has_log_table: bool | None = None


def dedupe_key(msg: dict) -> str:
    # 팀 스키마 주석은 "경고 해제도 같은 msg_id" — 그러면 발생과 해제가 같은 키라 구분한다
    p = msg["payload"]
    if p.get("msg_type") == "alert.event" and p.get("resolved"):
        return msg["msg_id"] + "#resolved"
    return msg["msg_id"]


def _log_table(c: psycopg.Cursor) -> bool:
    global _has_log_table
    if _has_log_table is None:
        c.execute("SELECT to_regclass('ingest_log') IS NOT NULL AS ok")
        _has_log_table = bool(c.fetchone()["ok"])
    return _has_log_table


def _claim(c: psycopg.Cursor, msg: dict) -> bool:
    """처음 보는 메시지면 True. DB 기록은 같은 트랜잭션이라 적재가 실패하면 함께 취소된다."""
    key = dedupe_key(msg)
    if _log_table(c):
        c.execute("""INSERT INTO ingest_log (msg_key, msg_type, src, ts)
                     VALUES (%s, %s, %s, %s) ON CONFLICT (msg_key) DO NOTHING RETURNING msg_key""",
                  (key, msg["payload"]["msg_type"], msg["src"], msg["ts"]))
        return c.fetchone() is not None
    with _seen_lock:
        return key not in _seen


def remember(msg: dict) -> None:
    """커밋이 끝난 뒤에만 부른다 — 실패한 메시지를 '본 것' 으로 치면 재전송이 버려진다."""
    if _has_log_table:
        return
    with _seen_lock:
        _seen[dedupe_key(msg)] = None
        while len(_seen) > _SEEN_MAX:
            _seen.popitem(last=False)


def reset_cache() -> None:        # 테스트용
    global _has_log_table
    _has_log_table = None
    with _seen_lock:
        _seen.clear()


# --- 공통 -----------------------------------------------------------------

def ensure_session(c: psycopg.Cursor, session_id: str, visitor_id: str | None = None) -> bool:
    """sessions 행 보장. 다른 테이블이 FK 로 참조하므로 먼저 있어야 한다."""
    if session_id in config.NO_SESSION_IDS:
        return False
    if config.AUTO_CREATE_SESSION or visitor_id is not None:
        c.execute("""INSERT INTO sessions (session_id, visitor_id) VALUES (%s, %s)
                     ON CONFLICT (session_id) DO UPDATE
                       SET visitor_id = COALESCE(sessions.visitor_id, EXCLUDED.visitor_id)""",
                  (session_id, visitor_id))
        return True
    c.execute("SELECT 1 FROM sessions WHERE session_id = %s", (session_id,))
    return c.fetchone() is not None


def _known_person(c: psycopg.Cursor, person_id: str | None) -> str | None:
    """등록된 사람일 때만 돌려준다. access_decisions.person_id 가 persons 를 FK 로 참조해서,
    A 쪽 동기화가 늦어 DB 에 아직 없는 사람이면 판정 기록 자체가 실패하기 때문 — 그때는 비워 둔다."""
    if not person_id:
        return None
    c.execute("SELECT 1 FROM persons WHERE person_id = %s", (person_id,))
    return person_id if c.fetchone() else None


def _event_log(c: psycopg.Cursor, robot: str | None, event_type: str, ts: str, detail: dict) -> None:
    c.execute("""INSERT INTO event_logs (robot_id, event_type, timestamp, detail)
                 VALUES (%s, %s, %s, %s)""",
              (ROBOT_NO.get(robot or ""), event_type, ts, json.dumps(detail, ensure_ascii=False)))


# --- msg_type 별 규칙 --------------------------------------------------------

def gate_session(c, m, p) -> str:
    # 팀 스키마 0번(A안): "A 파트가 방문자 감지 시 sessions 에 1행 INSERT". 0929 부터 DB 쓰기는
    # API 경유라, A 가 보내는 gate.session 을 여기서 받아 그 1행을 만든다 — 같은 약속이다.
    if not ensure_session(c, m["session_id"], p["visitor_id"]):
        raise ValueError(f"방문자 세션이 아닌 session_id: {m['session_id']}")
    return "sessions"


# 출입 판정 사유 코드 — 팀 AlertReason(unauthorized · no_helmet · no_vest)에 맞춘다.
# 판정불가는 AlertReason 에 없어서 따로 둔다 (FaceResult · PpeResult 의 undetermined).
FACE_REASON = {"unauthorized": "unauthorized", "undetermined": "face_undetermined"}
PPE_REASON = {"helmet": "no_helmet", "vest": "no_vest"}


def _merge_decision(c, m, *, reasons: set[str], snapshot_path: str | None, **cols) -> str:
    """access_decisions 에 **출입 판정 1회 = 1행** 으로 넣는다.

    A 내부에서는 사진 1장에서 얼굴 · PPE 를 함께 판정해 policy.decide() 로 한 번 결정하지만
    (A 판정 흐름도), MQTT 로는 vision.face · vision.ppe 두 메시지로 나뉘어 온다. 그래서
    **같은 session_id 의 두 메시지를 한 행으로 합친다** — A 는 판정에 실패하면 새 세션으로
    다시 시작하므로 세션 하나에 판정은 한 번이다 (09-29 김별이).
    TODO(협의): 한 세션에서 판정을 여러 번 하게 바뀌면 이 합치기 기준을 바꿔야 한다 (여도훈).

    - event_id = session_id (방문자 세션이 아니면 msg_id — 합칠 짝이 없다)
    - 하나라도 차단 사유가 있으면 deny, 사유는 합집합
    - 사진 경로는 차단일 때만 (정상 통과는 저장하지 않는다 — A 요구)
    - 한쪽만 도착한 동안은 그쪽 결과만으로 판정돼 있다가, 나머지가 오면 다시 계산된다
    """
    key = m["msg_id"] if m["session_id"] in config.NO_SESSION_IDS else m["session_id"]
    # 두 메시지가 동시에 와도 한 행만 생기게: 먼저 자리를 잡고, 잠근 뒤 합친다
    c.execute("""INSERT INTO access_decisions (event_id, ts, node_id, decision)
                 VALUES (%s, %s, %s, 'allow') ON CONFLICT (event_id) DO NOTHING""",
              (key, m["ts"], m["src"]))
    c.execute("SELECT * FROM access_decisions WHERE event_id = %s FOR UPDATE", (key,))
    row = c.fetchone()
    merged = set(filter(None, (row["reasons"] or "").split(","))) | reasons
    decision = "deny" if merged else "allow"
    c.execute("""UPDATE access_decisions SET
                   ts            = LEAST(ts, %s),
                   decision      = %s,
                   reasons       = %s,
                   person_id     = COALESCE(%s, person_id),
                   match_score   = COALESCE(%s, match_score),
                   helmet        = COALESCE(%s, helmet),
                   latency_ms    = GREATEST(latency_ms, %s),
                   snapshot_path = CASE WHEN %s = 'deny'
                                        THEN COALESCE(snapshot_path, %s) END
                 WHERE event_id = %s""",
              (m["ts"], decision, ",".join(sorted(merged)) or None,
               cols.get("person_id"), cols.get("match_score"), cols.get("helmet"),
               cols.get("latency_ms"), decision, snapshot_path, key))
    return "access_decisions"


def vision_face(c, m, p) -> str:
    reason = FACE_REASON.get(p["result"])          # authorized 면 None
    return _merge_decision(
        c, m, reasons={reason} if reason else set(),
        snapshot_path=p.get("snapshot_path") if reason else None,
        person_id=_known_person(c, p.get("person_id")),
        match_score=p.get("similarity"), latency_ms=p.get("latency_ms"))


def vision_ppe(c, m, p) -> str:
    items = p.get("items", {})
    reasons = {PPE_REASON.get(k, f"no_{k}") for k, v in items.items() if v == "fail"}
    if p["overall"] == "undetermined" or "undetermined" in items.values():
        reasons.add("ppe_undetermined")
    if p["overall"] == "fail" and not reasons:       # 항목 없이 전체만 fail 인 경우
        reasons.add("ppe_fail")
    return _merge_decision(
        c, m, reasons=reasons,
        snapshot_path=p.get("snapshot_path") if reasons else None,
        helmet=HELMET.get(items.get("helmet", "")), latency_ms=p.get("latency_ms"))


def dialog_result(c, m, p) -> str:
    # MQTT 에는 최종 결과만 온다. 턴 기록 · 실제 시작 · 종료 시각은 B 로그 일괄 적재(/dialog/import)가
    # 덮어쓴다. 여기서 started_at 에 넣는 ts 는 "결과가 나온 시각" 이라 임시값이다.
    # TODO(협의): outcome 코드 — 결과 메시지가 왔다는 건 목적지가 확정됐다는 뜻이라 'handoff' 로 둔다.
    if not ensure_session(c, m["session_id"]):
        raise ValueError(f"방문자 세션이 아닌 session_id: {m['session_id']}")
    c.execute("""INSERT INTO dialog_sessions
                   (session_id, started_at, outcome, destination, purpose, confidence, retry_count)
                 VALUES (%s, %s, 'handoff', %s, %s, %s, %s)
                 ON CONFLICT (session_id) DO UPDATE SET
                   destination = EXCLUDED.destination,
                   purpose     = EXCLUDED.purpose,
                   confidence  = EXCLUDED.confidence,
                   retry_count = GREATEST(dialog_sessions.retry_count, EXCLUDED.retry_count),
                   outcome     = COALESCE(dialog_sessions.outcome, EXCLUDED.outcome)""",
              (m["session_id"], m["ts"], p["destination"], p["purpose"],
               p["confidence"], p.get("retry_count", 0)))
    return "dialog_sessions"


def alert_event(c, m, p) -> str:
    # 발생은 INSERT, 해제는 UPDATE. 해제 메시지를 원래 경고와 맞추는 방법이 두 가지라 둘 다 받는다.
    #   ① 같은 msg_id — 팀 스키마 SQL 주석의 방식
    #   ② 새 msg_id + (session_id, reason) — D 대시보드 실제 코드 (clear_active_alert, 09-15~)
    # TODO(협의): 한 가지로 통일되면 나머지 분기는 지워도 된다
    sid = m["session_id"] if ensure_session(c, m["session_id"]) else None
    resolved = bool(p.get("resolved", False))
    if p["level"] in AUTO_RESOLVED and not resolved:        # 참고 알림 — 해제할 대상이 아니다
        c.execute("""INSERT INTO alert_logs
                       (msg_id, session_id, robot_id, occurred_at, level, reason,
                        resolved, resolved_at, snapshot_path)
                     VALUES (%s, %s, %s, %s, %s, %s, true, %s, %s)
                     ON CONFLICT (msg_id) DO NOTHING""",
                  (m["msg_id"], sid, m["src"], m["ts"], ALERT_LEVEL[p["level"]], p["reason"],
                   m["ts"], p.get("snapshot_path")))
        return "alert_logs(참고 알림)"
    if resolved:
        c.execute("""UPDATE alert_logs SET resolved = true, resolved_at = COALESCE(resolved_at, %s)
                     WHERE msg_id = %s RETURNING alert_id""", (m["ts"], m["msg_id"]))
        if c.fetchone():
            return "alert_logs(해제)"
        c.execute("""UPDATE alert_logs SET resolved = true, resolved_at = %s
                     WHERE alert_id = (SELECT alert_id FROM alert_logs
                                       WHERE session_id IS NOT DISTINCT FROM %s AND reason = %s
                                         AND NOT resolved
                                       ORDER BY occurred_at DESC LIMIT 1)
                     RETURNING alert_id""", (m["ts"], sid, p["reason"]))
        if c.fetchone():
            return "alert_logs(해제)"
        # 이미 해제돼 있는 경고의 해제 — info(처음부터 해제로 저장)를 대시보드가 해제 버튼으로 닫은 경우 등
        c.execute("""SELECT 1 FROM alert_logs WHERE session_id IS NOT DISTINCT FROM %s AND reason = %s
                     LIMIT 1""", (sid, p["reason"]))
        if c.fetchone():
            return "alert_logs(이미 해제)"
        # 맞는 경고가 없으면(API 가 발생 메시지를 못 받은 경우) 해제된 경고로 한 줄 남긴다
    c.execute("""INSERT INTO alert_logs
                   (msg_id, session_id, robot_id, occurred_at, level, reason,
                    resolved, resolved_at, snapshot_path)
                 VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                 ON CONFLICT (msg_id) DO NOTHING""",
              (m["msg_id"], sid, m["src"], m["ts"], ALERT_LEVEL[p["level"]], p["reason"],
               resolved, m["ts"] if resolved else None, p.get("snapshot_path")))
    return "alert_logs"


def system_health(c, m, p) -> str:
    # 테이블은 "상태가 바뀔 때만 1행" — 주기 발행 · retain 재수신은 버린다.
    # '최근' 은 받은 순서(health_id)로 본다 — LWT 의 ts 는 접속 시각이라 믿을 수 없다
    # (dialog/bus.py 주석: "state=offline 인 행의 ts 를 믿지 말고 받은 시각을 써야 한다").
    c.execute("""SELECT status, detail FROM system_health WHERE node = %s
                 ORDER BY health_id DESC LIMIT 1""", (p["node"],))
    last = c.fetchone()
    if last and last["status"] == p["state"] and last["detail"] == p.get("detail"):
        return "system_health(변화 없음)"
    if p["state"] == "offline":
        c.execute("""INSERT INTO system_health (node, status, occurred_at, detail)
                     VALUES (%s, %s, now(), %s)""", (p["node"], p["state"], p.get("detail")))
    else:
        c.execute("""INSERT INTO system_health (node, status, occurred_at, detail)
                     VALUES (%s, %s, %s, %s)""", (p["node"], p["state"], m["ts"], p.get("detail")))
    return "system_health"


def escort_status(c, m, p) -> str:
    # 메시지는 상태가 계속 오고, escort_logs 는 "안내 1회 = 1행" — 상태가 바뀌는 순간만 기록.
    # 직전 상태를 메모리에 두지 않고 DB 의 '열린 행(도착 · 중단 전)' 만 보고 판단한다 —
    # 그래야 재전송 · 서버 재시작에도 결과가 같다. C 가 1초 주기든 '바뀔 때만' 이든 그대로 동작.
    # TODO(협의): escort_logs 에 session_id 칸이 없고 robot_id 가 INTEGER (sql/proposed_changes.sql)
    # TODO(협의): 복귀 중에 C 가 어떤 state · destination 을 보내는지 (moving 이면 복귀도 안내 1회로 셈)
    robot = ROBOT_NO.get(m["src"])
    if robot is None:
        raise ValueError(f"robot_id 번호가 정해지지 않은 노드: {m['src']}")
    state, dest = p["state"], p["destination"]
    c.execute("""SELECT id, destination FROM escort_logs
                 WHERE robot_id = %s AND arrival_time IS NULL AND motion_played IS NULL
                 ORDER BY id DESC LIMIT 1""", (robot,))
    open_row = c.fetchone()

    if state == "moving":
        if open_row and open_row["destination"] == dest:
            return "escort_logs(이동 중)"
        if open_row:            # 도착 · 중단 소식 없이 목적지가 바뀌었다 — 이전 안내는 중단으로 닫는다
            c.execute("UPDATE escort_logs SET success = 0, motion_played = 'aborted' WHERE id = %s",
                      (open_row["id"],))
        c.execute("INSERT INTO escort_logs (robot_id, destination, start_time) VALUES (%s, %s, %s)",
                  (robot, dest, m["ts"]))
        return "escort_logs(출발)"
    if state == "arrived" and open_row:
        c.execute("UPDATE escort_logs SET arrival_time = %s, success = 1 WHERE id = %s",
                  (m["ts"], open_row["id"]))
        return "escort_logs(도착)"
    if state == "aborted" and open_row:
        # 실패 표시 칸이 success 뿐이라, 닫힌 행임을 motion_played 에 남긴다
        c.execute("UPDATE escort_logs SET success = 0, motion_played = 'aborted' WHERE id = %s",
                  (open_row["id"],))
        return "escort_logs(중단)"
    return "escort_logs(기록 안 함)"         # idle · paused, 또는 열린 행 없이 온 도착 · 중단


def robot_command(c, m, p) -> str:
    _event_log(c, p["dst"], f"robot.command:{p['action']}", m["ts"],
               {"msg_id": m["msg_id"], "src": m["src"], "reason": p.get("reason"),
                "session_id": m["session_id"]})
    return "event_logs"


HANDLERS: dict[str, Callable[[psycopg.Cursor, dict, dict], str]] = {
    "gate.session":  gate_session,
    "vision.face":   vision_face,
    "vision.ppe":    vision_ppe,
    "dialog.result": dialog_result,
    "alert.event":   alert_event,
    "system.health": system_health,
    "escort.status": escort_status,
    "robot.command": robot_command,
}


def store(c: psycopg.Cursor, msg: dict) -> str:
    """검사를 통과한 메시지 하나를 적재하고, 어디에 넣었는지 돌려준다."""
    p = msg["payload"]
    if not _claim(c, msg):
        return "중복(건너뜀)"
    handler = HANDLERS.get(p["msg_type"])
    if handler is None:         # 스키마에는 있는데 적재 규칙이 아직 없는 종류 — 원본을 남긴다
        _event_log(c, msg["src"], p["msg_type"], msg["ts"], msg)
        return "event_logs(규칙 없음)"
    where = handler(c, msg, p)
    if config.EVENT_LOG_ALL and p["msg_type"] != "robot.command":
        _event_log(c, msg["src"], p["msg_type"], msg["ts"], msg)
    return where
