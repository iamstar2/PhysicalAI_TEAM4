#!/usr/bin/env python3
"""시나리오별 샘플 메시지 발행 스크립트.

사용법:
    python tools/mock_publisher.py --list
    python tools/mock_publisher.py normal --dry-run
    python tools/mock_publisher.py escort_lost --speed 3
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mechdog_common import (
    AlertEventPayload,
    AlertLevel,
    AlertReason,
    Destination,
    DialogResultPayload,
    EscortState,
    EscortStatusPayload,
    FaceResult,
    GateSessionPayload,
    MechDogBus,
    Node,
    NodeState,
    Point,
    PpeItem,
    PpeResult,
    SystemHealthPayload,
    VisionFacePayload,
    VisionPpePayload,
    new_session_id,
)


def _sleep(seconds: float, speed: float) -> None:
    time.sleep(seconds / speed)


def _make_buses(dry_run: bool) -> dict[Node, MechDogBus]:
    nodes = [Node.MECHDOG_A, Node.MECHDOG_B, Node.MECHDOG_C, Node.MECHDOG_D]
    buses = {n: MechDogBus(n, dry_run=dry_run) for n in nodes}
    for b in buses.values():
        b.connect()
    return buses


def _teardown(buses: dict[Node, MechDogBus]) -> None:
    for b in buses.values():
        b.disconnect()


def scenario_normal(dry_run: bool, speed: float) -> None:
    """인가 + 복장통과 -> 대화 -> 에스코트 -> 도착."""
    buses = _make_buses(dry_run)
    session_id = new_session_id(Node.MECHDOG_A)
    visitor_id = "visitor-001"

    buses[Node.MECHDOG_A].publish(
        VisionFacePayload(
            visitor_id=visitor_id,
            result=FaceResult.AUTHORIZED,
            confidence=0.93,
            similarity=0.81,
            snapshot_path=f"/data/snap/{session_id}/face.jpg",
        ),
        session_id=session_id,
    )
    _sleep(0.5, speed)

    buses[Node.MECHDOG_A].publish(
        VisionPpePayload(
            visitor_id=visitor_id,
            items={PpeItem.HELMET: PpeResult.PASS, PpeItem.VEST: PpeResult.PASS},
            overall=PpeResult.PASS,
            confidence=0.90,
            snapshot_path=f"/data/snap/{session_id}/ppe.jpg",
        ),
        session_id=session_id,
    )
    _sleep(0.5, speed)

    buses[Node.MECHDOG_A].publish(
        GateSessionPayload(
            visitor_id=visitor_id,
            face_result=FaceResult.AUTHORIZED,
            ppe_result=PpeResult.PASS,
            handoff_to=Node.MECHDOG_B,
        ),
        session_id=session_id,
    )
    _sleep(1.0, speed)

    buses[Node.MECHDOG_B].publish(
        DialogResultPayload(
            destination=Destination.MEETING_ROOM_1,
            purpose="방문 미팅",
            confidence=0.88,
            retry_count=0,
        ),
        session_id=session_id,
    )
    _sleep(1.0, speed)

    for state, x in [
        (EscortState.MOVING, 2.0),
        (EscortState.MOVING, 5.0),
        (EscortState.ARRIVED, 8.0),
    ]:
        buses[Node.MECHDOG_C].publish(
            EscortStatusPayload(
                state=state,
                destination=Destination.MEETING_ROOM_1,
                position=Point(x=x, y=1.0),
                heading_deg=90.0,
                distance_to_target_m=max(0.0, 8.0 - x),
            ),
            session_id=session_id,
        )
        _sleep(1.0, speed)

    _teardown(buses)


def scenario_unauthorized(dry_run: bool, speed: float) -> None:
    """미인가 -> 경고 -> 관리자 수동 해제."""
    buses = _make_buses(dry_run)
    session_id = new_session_id(Node.MECHDOG_A)
    visitor_id = "visitor-002"

    buses[Node.MECHDOG_A].publish(
        VisionFacePayload(
            visitor_id=visitor_id,
            result=FaceResult.UNAUTHORIZED,
            confidence=0.95,
            similarity=0.21,
            snapshot_path=f"/data/snap/{session_id}/face.jpg",
        ),
        session_id=session_id,
    )
    _sleep(0.5, speed)

    buses[Node.MECHDOG_D].publish(
        AlertEventPayload(
            level=AlertLevel.CRITICAL,
            reason=AlertReason.UNAUTHORIZED,
            track_id=visitor_id,
            snapshot_path=f"/data/snap/{session_id}/alert.jpg",
            resolved=False,
        ),
        session_id=session_id,
    )
    _sleep(2.0, speed)

    # 대시보드에서 관리자가 수동으로 해제
    buses[Node.MECHDOG_D].publish(
        AlertEventPayload(
            level=AlertLevel.CRITICAL,
            reason=AlertReason.UNAUTHORIZED,
            track_id=visitor_id,
            resolved=True,
        ),
        session_id=session_id,
    )

    _teardown(buses)


def scenario_no_helmet(dry_run: bool, speed: float) -> None:
    """안전모 미착용 -> 경고 -> 재착용 -> 자동 해제."""
    buses = _make_buses(dry_run)
    session_id = new_session_id(Node.MECHDOG_A)
    visitor_id = "visitor-003"

    buses[Node.MECHDOG_A].publish(
        VisionPpePayload(
            visitor_id=visitor_id,
            items={PpeItem.HELMET: PpeResult.FAIL, PpeItem.VEST: PpeResult.PASS},
            overall=PpeResult.FAIL,
            confidence=0.90,
            snapshot_path=f"/data/snap/{session_id}/ppe_1.jpg",
        ),
        session_id=session_id,
    )
    _sleep(0.5, speed)

    buses[Node.MECHDOG_D].publish(
        AlertEventPayload(
            level=AlertLevel.WARN,
            reason=AlertReason.NO_HELMET,
            track_id=visitor_id,
            snapshot_path=f"/data/snap/{session_id}/alert.jpg",
            resolved=False,
        ),
        session_id=session_id,
    )
    _sleep(2.0, speed)

    # 재착용 후 재검사 통과
    buses[Node.MECHDOG_A].publish(
        VisionPpePayload(
            visitor_id=visitor_id,
            items={PpeItem.HELMET: PpeResult.PASS, PpeItem.VEST: PpeResult.PASS},
            overall=PpeResult.PASS,
            confidence=0.92,
            snapshot_path=f"/data/snap/{session_id}/ppe_2.jpg",
        ),
        session_id=session_id,
    )
    _sleep(0.5, speed)

    # 재검사 통과 -> 자동 해제
    buses[Node.MECHDOG_D].publish(
        AlertEventPayload(
            level=AlertLevel.WARN,
            reason=AlertReason.NO_HELMET,
            track_id=visitor_id,
            resolved=True,
        ),
        session_id=session_id,
    )

    _teardown(buses)


def scenario_undetermined(dry_run: bool, speed: float) -> None:
    """얼굴 판정 불가 3회 -> D 이관."""
    buses = _make_buses(dry_run)
    session_id = new_session_id(Node.MECHDOG_A)
    visitor_id = "visitor-004"

    for attempt in range(1, 4):
        buses[Node.MECHDOG_A].publish(
            VisionFacePayload(
                visitor_id=visitor_id,
                result=FaceResult.UNDETERMINED,
                confidence=0.30,
                similarity=None,
                snapshot_path=f"/data/snap/{session_id}/face_{attempt}.jpg",
            ),
            session_id=session_id,
        )
        _sleep(1.0, speed)

    buses[Node.MECHDOG_D].publish(
        AlertEventPayload(
            level=AlertLevel.WARN,
            reason=AlertReason.FACE_TIMEOUT,
            track_id=visitor_id,
            resolved=False,
        ),
        session_id=session_id,
    )

    _teardown(buses)


def scenario_escort_lost(dry_run: bool, speed: float) -> None:
    """에스코트 중 이탈 -> D 호출."""
    buses = _make_buses(dry_run)
    session_id = new_session_id(Node.MECHDOG_A)

    buses[Node.MECHDOG_C].publish(
        EscortStatusPayload(
            state=EscortState.MOVING,
            destination=Destination.OFFICE_2F,
            position=Point(x=1.0, y=0.0),
            heading_deg=45.0,
            distance_to_target_m=6.0,
        ),
        session_id=session_id,
    )
    _sleep(1.0, speed)

    buses[Node.MECHDOG_C].publish(
        EscortStatusPayload(
            state=EscortState.PAUSED,
            destination=Destination.OFFICE_2F,
            position=Point(x=2.0, y=0.5),
            heading_deg=45.0,
            distance_to_target_m=5.0,
        ),
        session_id=session_id,
    )
    _sleep(0.5, speed)

    buses[Node.MECHDOG_D].publish(
        AlertEventPayload(
            level=AlertLevel.WARN,
            reason=AlertReason.ESCORT_LOST,
            resolved=False,
        ),
        session_id=session_id,
    )

    _teardown(buses)


def scenario_health(dry_run: bool, speed: float) -> None:
    """전 노드 헬스체크."""
    buses = {n: MechDogBus(n, dry_run=dry_run) for n in Node}
    for b in buses.values():
        b.connect()
        b.publish(SystemHealthPayload(node=b.node, state=NodeState.READY), session_id="system")
        _sleep(0.2, speed)
    _teardown(buses)


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
