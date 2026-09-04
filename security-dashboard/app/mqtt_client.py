#!/usr/bin/env python3
"""security-dashboard(mechdog_d)의 MQTT 진입점.

흐름:
    mechdog/v1/vision/face, mechdog/v1/vision/ppe, mechdog/v1/system/health/+ 구독
    -> schema/mechdog_messages.schema.json 으로 검증
    -> security_state.SecurityStateStore 로 상태 판단 (얼굴/PPE)
       + dashboard_state.DashboardState 갱신 (웹 화면이 읽는 공유 상태)
    -> 상태가 바뀌었을 때만 robot_commands 호출 + alert.event 발행

topic 문자열, QoS, retain은 전부 schema/topics.json에서 그대로 읽어온다 -
이 파일 안에 topic을 새로 만들거나 하드코딩하지 않는다. system.health의
{node} 부분만 MQTT 표준 와일드카드 "+"로 바꿔서 구독한다 (topics.json에
이미 "topic 끝에 {node}를 실제 노드 값으로 치환" 이라고 문서화되어 있고,
"+"는 그 자리에 어떤 값이 와도 다 받겠다는 MQTT 표준 문법일 뿐, 새 topic을
만드는 게 아니다). tools/mock_publisher.py, tools/echo_subscriber.py와 동일한
schema 로딩 방식을 그대로 따른다.

사용법 (security-dashboard 폴더 기준, 단독 실행 - 콘솔 확인용):
    python app/mqtt_client.py
    MQTT_HOST=localhost MQTT_PORT=1883 python app/mqtt_client.py

웹 대시보드와 함께 실행할 때는 main.py를 통해서 실행한다 (이 파일을 직접
실행하면 웹 서버 없이 콘솔 로그만 본다).
"""

from __future__ import annotations

import json
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import paho.mqtt.client as mqtt
from jsonschema import Draft202012Validator

from robot_commands import alert_action, clear_alert, emergency_stop as robot_emergency_stop, warning_action
from security_state import ALERT, NORMAL, PENDING, WARNING, SecurityStateStore, Transition

# security-dashboard/app/mqtt_client.py -> security-dashboard -> 저장소 루트
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCHEMA_PATH = REPO_ROOT / "schema" / "mechdog_messages.schema.json"
TOPICS_PATH = REPO_ROOT / "schema" / "topics.json"

if not SCHEMA_PATH.exists() or not TOPICS_PATH.exists():
    raise FileNotFoundError(
        f"팀 스펙 파일을 찾을 수 없습니다: {SCHEMA_PATH} / {TOPICS_PATH}\n"
        "security-dashboard 폴더가 팀 저장소(schema/ 포함) 안에 있는지 확인하세요."
    )

with open(SCHEMA_PATH, encoding="utf-8") as f:
    _SCHEMA = json.load(f)
VALIDATOR = Draft202012Validator(_SCHEMA)

with open(TOPICS_PATH, encoding="utf-8") as f:
    _TOPICS = json.load(f)
_TOPIC_BY_MSG_TYPE = {t["msg_type"]: t for t in _TOPICS["topics"]}

KST = timezone(timedelta(hours=9))
SRC_NODE = "mechdog_d"  # schema Node enum + docker-compose container_name과 일치


def topic_qos_retain(msg_type: str) -> tuple[str, int, bool]:
    entry = _TOPIC_BY_MSG_TYPE[msg_type]
    return entry["topic"], entry["qos"], entry["retain"]


def make_envelope(*, session_id: str, payload: dict) -> dict:
    """schema/mechdog_messages.schema.json Envelope 규격에 맞는 dict 생성."""
    return {
        "ver": 1,
        "msg_id": uuid.uuid4().hex,
        "ts": datetime.now(KST).isoformat(),
        "src": SRC_NODE,
        "session_id": session_id,
        "payload": payload,
    }


def _alert_reason_for_ppe(items: dict) -> str:
    """items 안에서 어떤 항목이 실패했는지로 AlertReason을 정한다.

    helmet/vest가 둘 다 fail이면 helmet을 우선한다 - schema의 AlertReason은
    한 번에 하나의 사유만 표현할 수 있고(no_helmet_and_vest 같은 값이 없음),
    팀에서 우선순위를 정한 적이 없어 임의로 helmet을 먼저 고른 것뿐이다.
    """
    if items.get("helmet") == "fail":
        return "no_helmet"
    if items.get("vest") == "fail":
        return "no_vest"
    return "no_helmet"  # overall=fail인데 items에 구체 항목이 없을 때의 방어적 기본값


def _print_transition(transition: Transition) -> None:
    print(
        f"[state] session={transition.session_id} visitor={transition.visitor_id} "
        f"trigger={transition.trigger} face={transition.face_result} "
        f"ppe={transition.ppe_overall} -> {transition.new_status}"
        + (f" (이전: {transition.old_status})" if transition.old_status else " (신규)")
    )
    if transition.new_status == PENDING:
        if transition.face_result == "undetermined" or transition.ppe_overall == "undetermined":
            print(f"  [보류] session={transition.session_id} 판정 보류 / 재검사 필요 (undetermined)")
        else:
            print(f"  [대기] session={transition.session_id} 얼굴/PPE 판정 중 아직 도착하지 않은 게 있음")


class SecurityDashboardClient:
    def __init__(self, dashboard_state=None) -> None:
        self.store = SecurityStateStore()
        self.state = dashboard_state  # dashboard_state.DashboardState | None (단독 실행 시 None)
        self.client = mqtt.Client(client_id=SRC_NODE)

        user = os.environ.get("MQTT_USER")
        if user:
            self.client.username_pw_set(user, os.environ.get("MQTT_PASS"))

        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.on_message = self._on_message

    # --- MQTT 콜백 -----------------------------------------------------

    def _on_connect(self, client, userdata, flags, rc) -> None:
        print(f"[mqtt] connected (rc={rc})")
        if self.state is not None:
            self.state.set_mqtt_connected(rc == 0)
        for msg_type in ("vision.face", "vision.ppe"):
            topic, qos, _retain = topic_qos_retain(msg_type)
            client.subscribe(topic, qos=qos)
            print(f"[mqtt] subscribed: {topic} (qos={qos})")

        health_topic, health_qos, _retain = topic_qos_retain("system.health")
        health_pattern = health_topic.replace("{node}", "+")
        client.subscribe(health_pattern, qos=health_qos)
        print(f"[mqtt] subscribed: {health_pattern} (qos={health_qos})")

    def _on_disconnect(self, client, userdata, rc) -> None:
        print(f"[mqtt] disconnected (rc={rc})")
        if self.state is not None:
            self.state.set_mqtt_connected(False)

    def _on_message(self, client, userdata, msg) -> None:
        try:
            data = json.loads(msg.payload)
        except json.JSONDecodeError as exc:
            print(f"[mqtt] {msg.topic}: invalid JSON ({exc})")
            return

        errors = list(VALIDATOR.iter_errors(data))
        if errors:
            print(f"[mqtt] {msg.topic}: schema 위반 - {errors[0].message}")
            return

        payload = data["payload"]
        session_id = data["session_id"]
        msg_type = payload["msg_type"]

        if msg_type == "vision.face":
            transition = self.store.apply_face(
                session_id=session_id,
                visitor_id=payload["visitor_id"],
                result=payload["result"],
                snapshot_path=payload.get("snapshot_path"),
            )
        elif msg_type == "vision.ppe":
            transition = self.store.apply_ppe(
                session_id=session_id,
                visitor_id=payload["visitor_id"],
                overall=payload["overall"],
                items=payload.get("items", {}),
                snapshot_path=payload.get("snapshot_path"),
            )
        elif msg_type == "system.health":
            print(f"[health] {payload['node']} -> {payload['state']}")
            if self.state is not None:
                self.state.update_node_health(
                    payload["node"], payload["state"], payload.get("detail"), data["ts"]
                )
            return
        else:
            return  # 이 서비스는 vision.face / vision.ppe / system.health만 처리한다

        _print_transition(transition)
        self._handle_transition(transition)

    # --- 판정 -> 액션 ----------------------------------------------------

    def _handle_transition(self, transition: Transition) -> None:
        if not transition.changed:
            return  # 같은 상태 반복 -> 중복 경고 방지, 아무것도 안 함

        if transition.new_status == WARNING:
            warning_action()
            self._publish_alert(
                session_id=transition.session_id,
                track_id=transition.visitor_id,
                level="warn",
                reason=_alert_reason_for_ppe(transition.ppe_items),
                snapshot_path=transition.snapshot_path,
            )
        elif transition.new_status == ALERT:
            alert_action()
            self._publish_alert(
                session_id=transition.session_id,
                track_id=transition.visitor_id,
                level="critical",
                reason="unauthorized",
                snapshot_path=transition.snapshot_path,
            )
        elif transition.new_status == NORMAL and transition.old_status in (WARNING, ALERT):
            clear_alert()  # 콘솔 표시만 함 - resolved=true 자동 발행은 안 함(해제 조건 미정, 관리자 수동 해제만 발행)

    # --- alert.event 발행 (자동 판정 + 관리자 수동 해제 공용) -----------------

    def _publish_alert(
        self,
        *,
        session_id: str,
        track_id: str | None,
        level: str,
        reason: str,
        snapshot_path: str | None,
        resolved: bool = False,
    ) -> dict | None:
        payload = {
            "msg_type": "alert.event",
            "level": level,
            "reason": reason,
            "track_id": track_id,
            "snapshot_path": snapshot_path,
            "resolved": resolved,
        }
        envelope = make_envelope(session_id=session_id, payload=payload)

        errors = list(VALIDATOR.iter_errors(envelope))
        if errors:
            print(f"[mqtt] 발행 취소 - 우리가 만든 alert.event가 schema 위반: {errors[0].message}")
            return None

        topic, qos, retain = topic_qos_retain("alert.event")
        self.client.publish(topic, json.dumps(envelope, ensure_ascii=False), qos=qos, retain=retain)
        print(f"[mqtt] PUB {topic} (qos={qos}) {json.dumps(envelope, ensure_ascii=False)}")

        if self.state is not None:
            self.state.record_alert({**payload, "session_id": session_id, "ts": envelope["ts"]})
        return envelope

    # --- 대시보드 버튼에서 호출하는 관리자 액션 ------------------------------

    def clear_active_alert(self) -> bool:
        """[경고 해제] 버튼: 현재 활성 경고를 resolved=true로 재발행하고 D를 CLEAR_ALERT 시킨다.

        새 topic이나 필드를 만들지 않고, 기존 alert.event를 resolved=true로 다시
        보내는 것으로 처리한다 (팀 예시 schema/examples/alert_event.json에도 이미
        같은 이벤트가 resolved만 바뀌어 다시 오는 패턴이 나와 있다).
        """
        if self.state is None:
            return False
        active = self.state.get_active_alert()
        if active is None:
            return False

        clear_alert()  # [D ROBOT] CLEAR_ALERT 콘솔 출력
        self._publish_alert(
            session_id=active["session_id"],
            track_id=active.get("track_id"),
            level=active["level"],
            reason=active["reason"],
            snapshot_path=None,
            resolved=True,
        )
        # 이 세션의 판정 상태를 초기화 - 같은 위반이 다시 감지되면 재경보 가능해야 함
        self.store.reset_status(active["session_id"])
        return True

    def trigger_emergency_stop(self) -> None:
        robot_emergency_stop()  # [D ROBOT] EMERGENCY_STOP 콘솔 출력
        if self.state is not None:
            self.state.set_emergency_stop(True)

    def reset_emergency_stop(self) -> None:
        """긴급정지 배너를 끄는 대시보드 전용 버튼 - MQTT로 나가는 공식 메시지는 아니다."""
        if self.state is not None:
            self.state.set_emergency_stop(False)

    # --- 실행 -------------------------------------------------------------

    def connect(self) -> None:
        host = os.environ.get("MQTT_HOST", "localhost")
        port = int(os.environ.get("MQTT_PORT", "1883"))
        print(f"[mqtt] connecting to {host}:{port} ...")
        self.client.connect(host, port)

    def start(self) -> None:
        """웹 서버(main.py)와 같은 프로세스에서 백그라운드로 돌릴 때 사용."""
        self.connect()
        self.client.loop_start()

    def stop(self) -> None:
        self.client.loop_stop()
        self.client.disconnect()

    def run_forever(self) -> None:
        """이 파일을 단독 스크립트로 실행할 때(콘솔 확인용) 사용."""
        self.connect()
        self.client.loop_forever()


def main() -> None:
    SecurityDashboardClient().run_forever()


if __name__ == "__main__":
    main()
