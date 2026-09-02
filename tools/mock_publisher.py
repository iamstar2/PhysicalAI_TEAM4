#!/usr/bin/env python3
"""schema/ 스펙에 맞는 시나리오별 샘플 메시지를 발행하는 참고 구현.

공용 Python 패키지는 없앴으므로, 이 스크립트는 schema/topics.json을 읽어서
직접 topic/QoS/retain을 정하고 raw paho-mqtt로 발행한다. 팀원이 다른 언어로
구현할 때 "이런 모양의 JSON을 이런 topic/QoS로 보내면 된다"는 참고용.

사용법:
    python tools/mock_publisher.py --list
    python tools/mock_publisher.py normal --dry-run
    python tools/mock_publisher.py escort_lost --speed 3
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import paho.mqtt.client as mqtt

from _common import make_envelope, new_session_id, topic_qos_retain


class Publisher:
    def __init__(self, dry_run: bool):
        self.dry_run = dry_run
        self._client = None
        if not dry_run:
            self._client = mqtt.Client(client_id="mock_publisher")
            user = os.environ.get("MQTT_USER")
            if user:
                self._client.username_pw_set(user, os.environ.get("MQTT_PASS"))
            host = os.environ.get("MQTT_HOST", "localhost")
            port = int(os.environ.get("MQTT_PORT", "1883"))
            self._client.connect(host, port)
            self._client.loop_start()

    def publish(self, *, src: str, session_id: str, payload: dict) -> None:
        env = make_envelope(src=src, session_id=session_id, payload=payload)
        node = payload.get("node")  # system.health 토픽에만 쓰임
        topic, qos, retain = topic_qos_retain(payload["msg_type"], node=node)

        if self.dry_run:
            print(f"[dry-run] PUB {topic} (qos={qos}, retain={retain})")
            import json

            print(f"          {json.dumps(env, ensure_ascii=False)}")
            return

        import json

        self._client.publish(topic, json.dumps(env), qos=qos, retain=retain)

    def close(self) -> None:
        if self._client is not None:
            self._client.loop_stop()
            self._client.disconnect()


def _sleep(seconds: float, speed: float) -> None:
    time.sleep(seconds / speed)


def scenario_normal(dry_run: bool, speed: float) -> None:
    """인가 + 복장통과 -> 대화 -> 에스코트 -> 도착."""
    pub = Publisher(dry_run)
    session_id = new_session_id("mechdog_a")
    visitor_id = "visitor-001"

    pub.publish(
        src="mechdog_a",
        session_id=session_id,
        payload={
            "msg_type": "vision.face",
            "visitor_id": visitor_id,
            "result": "authorized",
            "confidence": 0.93,
            "similarity": 0.81,
            "snapshot_path": f"/data/snap/{session_id}/face.jpg",
        },
    )
    _sleep(0.5, speed)

    pub.publish(
        src="mechdog_a",
        session_id=session_id,
        payload={
            "msg_type": "vision.ppe",
            "visitor_id": visitor_id,
            "items": {"helmet": "pass", "vest": "pass"},
            "overall": "pass",
            "confidence": 0.90,
            "snapshot_path": f"/data/snap/{session_id}/ppe.jpg",
        },
    )
    _sleep(0.5, speed)

    pub.publish(
        src="mechdog_a",
        session_id=session_id,
        payload={
            "msg_type": "gate.session",
            "visitor_id": visitor_id,
            "face_result": "authorized",
            "ppe_result": "pass",
            "handoff_to": "mechdog_b",
        },
    )
    _sleep(1.0, speed)

    pub.publish(
        src="mechdog_b",
        session_id=session_id,
        payload={
            "msg_type": "dialog.result",
            "destination": "meeting_room_1",
            "purpose": "방문 미팅",
            "confidence": 0.88,
            "retry_count": 0,
        },
    )
    _sleep(1.0, speed)

    for state, x in [("moving", 2.0), ("moving", 5.0), ("arrived", 8.0)]:
        pub.publish(
            src="mechdog_c",
            session_id=session_id,
            payload={
                "msg_type": "escort.status",
                "state": state,
                "destination": "meeting_room_1",
                "position": {"x": x, "y": 1.0, "z": 0.0},
                "heading_deg": 90.0,
                "distance_to_target_m": max(0.0, 8.0 - x),
            },
        )
        _sleep(1.0, speed)

    pub.close()


def scenario_unauthorized(dry_run: bool, speed: float) -> None:
    """미인가 -> 경고 -> 관리자 수동 해제."""
    pub = Publisher(dry_run)
    session_id = new_session_id("mechdog_a")
    visitor_id = "visitor-002"

    pub.publish(
        src="mechdog_a",
        session_id=session_id,
        payload={
            "msg_type": "vision.face",
            "visitor_id": visitor_id,
            "result": "unauthorized",
            "confidence": 0.95,
            "similarity": 0.21,
            "snapshot_path": f"/data/snap/{session_id}/face.jpg",
        },
    )
    _sleep(0.5, speed)

    pub.publish(
        src="mechdog_d",
        session_id=session_id,
        payload={
            "msg_type": "alert.event",
            "level": "critical",
            "reason": "unauthorized",
            "track_id": visitor_id,
            "snapshot_path": f"/data/snap/{session_id}/alert.jpg",
            "resolved": False,
        },
    )
    _sleep(2.0, speed)

    pub.publish(
        src="mechdog_d",
        session_id=session_id,
        payload={
            "msg_type": "alert.event",
            "level": "critical",
            "reason": "unauthorized",
            "track_id": visitor_id,
            "resolved": True,
        },
    )
    pub.close()


def scenario_no_helmet(dry_run: bool, speed: float) -> None:
    """안전모 미착용 -> 경고 -> 재착용 -> 자동 해제."""
    pub = Publisher(dry_run)
    session_id = new_session_id("mechdog_a")
    visitor_id = "visitor-003"

    pub.publish(
        src="mechdog_a",
        session_id=session_id,
        payload={
            "msg_type": "vision.ppe",
            "visitor_id": visitor_id,
            "items": {"helmet": "fail", "vest": "pass"},
            "overall": "fail",
            "confidence": 0.90,
            "snapshot_path": f"/data/snap/{session_id}/ppe_1.jpg",
        },
    )
    _sleep(0.5, speed)

    pub.publish(
        src="mechdog_d",
        session_id=session_id,
        payload={
            "msg_type": "alert.event",
            "level": "warn",
            "reason": "no_helmet",
            "track_id": visitor_id,
            "snapshot_path": f"/data/snap/{session_id}/alert.jpg",
            "resolved": False,
        },
    )
    _sleep(2.0, speed)

    pub.publish(
        src="mechdog_a",
        session_id=session_id,
        payload={
            "msg_type": "vision.ppe",
            "visitor_id": visitor_id,
            "items": {"helmet": "pass", "vest": "pass"},
            "overall": "pass",
            "confidence": 0.92,
            "snapshot_path": f"/data/snap/{session_id}/ppe_2.jpg",
        },
    )
    _sleep(0.5, speed)

    pub.publish(
        src="mechdog_d",
        session_id=session_id,
        payload={
            "msg_type": "alert.event",
            "level": "warn",
            "reason": "no_helmet",
            "track_id": visitor_id,
            "resolved": True,
        },
    )
    pub.close()


def scenario_undetermined(dry_run: bool, speed: float) -> None:
    """얼굴 판정 불가 3회 -> D 이관."""
    pub = Publisher(dry_run)
    session_id = new_session_id("mechdog_a")
    visitor_id = "visitor-004"

    for attempt in range(1, 4):
        pub.publish(
            src="mechdog_a",
            session_id=session_id,
            payload={
                "msg_type": "vision.face",
                "visitor_id": visitor_id,
                "result": "undetermined",
                "confidence": 0.30,
                "similarity": None,
                "snapshot_path": f"/data/snap/{session_id}/face_{attempt}.jpg",
            },
        )
        _sleep(1.0, speed)

    pub.publish(
        src="mechdog_d",
        session_id=session_id,
        payload={
            "msg_type": "alert.event",
            "level": "warn",
            "reason": "face_timeout",
            "track_id": visitor_id,
            "resolved": False,
        },
    )
    pub.close()


def scenario_escort_lost(dry_run: bool, speed: float) -> None:
    """에스코트 중 이탈 -> D 호출."""
    pub = Publisher(dry_run)
    session_id = new_session_id("mechdog_a")

    pub.publish(
        src="mechdog_c",
        session_id=session_id,
        payload={
            "msg_type": "escort.status",
            "state": "moving",
            "destination": "office_2f",
            "position": {"x": 1.0, "y": 0.0, "z": 0.0},
            "heading_deg": 45.0,
            "distance_to_target_m": 6.0,
        },
    )
    _sleep(1.0, speed)

    pub.publish(
        src="mechdog_c",
        session_id=session_id,
        payload={
            "msg_type": "escort.status",
            "state": "paused",
            "destination": "office_2f",
            "position": {"x": 2.0, "y": 0.5, "z": 0.0},
            "heading_deg": 45.0,
            "distance_to_target_m": 5.0,
        },
    )
    _sleep(0.5, speed)

    pub.publish(
        src="mechdog_d",
        session_id=session_id,
        payload={"msg_type": "alert.event", "level": "warn", "reason": "escort_lost", "resolved": False},
    )
    pub.close()


def scenario_health(dry_run: bool, speed: float) -> None:
    """전 노드 헬스체크."""
    pub = Publisher(dry_run)
    for node in ["mechdog_a", "mechdog_b", "mechdog_c", "mechdog_d", "rpi", "pc", "db", "dashboard"]:
        pub.publish(
            src=node,
            session_id="system",
            payload={"msg_type": "system.health", "node": node, "state": "ready"},
        )
        _sleep(0.2, speed)
    pub.close()


SCENARIOS = {
    "normal": scenario_normal,
    "unauthorized": scenario_unauthorized,
    "no_helmet": scenario_no_helmet,
    "undetermined": scenario_undetermined,
    "escort_lost": scenario_escort_lost,
    "health": scenario_health,
}


def main() -> None:
    parser = argparse.ArgumentParser(description="MechDog 시나리오 샘플 메시지 발행기")
    parser.add_argument("scenario", nargs="?", choices=sorted(SCENARIOS), help="실행할 시나리오 이름")
    parser.add_argument("--dry-run", action="store_true", help="브로커 연결 없이 콘솔에만 출력")
    parser.add_argument("--speed", type=float, default=1.0, help="배속 (기본 1.0, 클수록 빨리 진행)")
    parser.add_argument("--list", action="store_true", help="사용 가능한 시나리오 목록 출력")
    args = parser.parse_args()

    if args.list or not args.scenario:
        print("사용 가능한 시나리오:")
        for name in sorted(SCENARIOS):
            print(f"  - {name}")
        return

    if args.speed <= 0:
        parser.error("--speed 는 0보다 커야 합니다.")

    SCENARIOS[args.scenario](dry_run=args.dry_run, speed=args.speed)


if __name__ == "__main__":
    main()
