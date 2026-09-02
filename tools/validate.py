#!/usr/bin/env python3
"""브로커 없이 mechdog_common 스키마 자체를 검증하는 스크립트.

pytest 없이 단독 실행 가능. 각 테스트의 통과/실패를 출력하고 마지막에
통과/실패 개수를 요약한다. 실패가 있으면 종료 코드 1을 반환한다.

사용법:
    python tools/validate.py
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pydantic import ValidationError

from mechdog_common import (
    AlertEventPayload,
    AlertLevel,
    AlertReason,
    Destination,
    DialogResultPayload,
    Envelope,
    EscortState,
    EscortStatusPayload,
    FaceResult,
    GateSessionPayload,
    MsgType,
    Node,
    NodeState,
    Point,
    PpeItem,
    PpeResult,
    QOS_POLICY,
    SystemHealthPayload,
    VisionFacePayload,
    VisionPpePayload,
    make_envelope,
    new_session_id,
)

KST = timezone(timedelta(hours=9))
SESSION = "sess-test-0000"


def sample_envelopes() -> dict[MsgType, Envelope]:
    return {
        MsgType.VISION_FACE: make_envelope(
            src=Node.MECHDOG_A,
            session_id=SESSION,
            payload=VisionFacePayload(
                visitor_id="v1",
                result=FaceResult.AUTHORIZED,
                confidence=0.9,
                similarity=0.8,
                snapshot_path="/data/snap/x/face.jpg",
            ),
        ),
        MsgType.VISION_PPE: make_envelope(
            src=Node.MECHDOG_A,
            session_id=SESSION,
            payload=VisionPpePayload(
                visitor_id="v1",
                items={PpeItem.HELMET: PpeResult.PASS, PpeItem.VEST: PpeResult.PASS},
                overall=PpeResult.PASS,
                confidence=0.9,
                snapshot_path="/data/snap/x/ppe.jpg",
            ),
        ),
        MsgType.GATE_SESSION: make_envelope(
            src=Node.MECHDOG_A,
            session_id=SESSION,
            payload=GateSessionPayload(
                visitor_id="v1",
                face_result=FaceResult.AUTHORIZED,
                ppe_result=PpeResult.PASS,
                handoff_to=Node.MECHDOG_B,
            ),
        ),
        MsgType.DIALOG_RESULT: make_envelope(
            src=Node.MECHDOG_B,
            session_id=SESSION,
            payload=DialogResultPayload(
                destination=Destination.LOBBY,
                purpose="방문",
                confidence=0.85,
                retry_count=0,
            ),
        ),
        MsgType.ESCORT_STATUS: make_envelope(
            src=Node.MECHDOG_C,
            session_id=SESSION,
            payload=EscortStatusPayload(
                state=EscortState.MOVING,
                destination=Destination.LOBBY,
                position=Point(x=1.0, y=2.0),
                heading_deg=90.0,
                distance_to_target_m=3.0,
            ),
        ),
        MsgType.ALERT_EVENT: make_envelope(
            src=Node.MECHDOG_D,
            session_id=SESSION,
            payload=AlertEventPayload(
                level=AlertLevel.WARN,
                reason=AlertReason.NO_HELMET,
                resolved=False,
            ),
        ),
        MsgType.SYSTEM_HEALTH: make_envelope(
            src=Node.MECHDOG_A,
            session_id="system",
            payload=SystemHealthPayload(node=Node.MECHDOG_A, state=NodeState.READY),
        ),
    }


# --- 테스트 케이스 ----------------------------------------------------------

def test_round_trip_all_msg_types():
    for msg_type, env in sample_envelopes().items():
        raw = env.model_dump_json()
        restored = Envelope.model_validate_json(raw)
        assert restored.payload.msg_type == msg_type, f"{msg_type} round-trip 실패"
        assert restored.model_dump() == env.model_dump(), f"{msg_type} round-trip 값 불일치"


def test_extra_field_rejected():
    payload = {
        "msg_type": "vision.face",
        "visitor_id": "v1",
        "result": "authorized",
        "confidence": 0.9,
        "snapshot_path": "/data/snap/x/face.jpg",
        "unexpected_field": "should be rejected",
    }
    try:
        VisionFacePayload.model_validate(payload)
    except ValidationError:
        return
    raise AssertionError("정의되지 않은 필드(unexpected_field)가 거부되지 않았다")


def test_confidence_out_of_range_rejected():
    try:
        VisionFacePayload(
            visitor_id="v1",
            result=FaceResult.AUTHORIZED,
            confidence=1.5,
            snapshot_path="/data/snap/x/face.jpg",
        )
    except ValidationError:
        return
    raise AssertionError("confidence=1.5 (범위 초과)가 거부되지 않았다")


def test_angle_out_of_range_rejected():
    try:
        EscortStatusPayload(
            state=EscortState.MOVING,
            destination=Destination.LOBBY,
            position=Point(x=0.0, y=0.0),
            heading_deg=361.0,
            distance_to_target_m=1.0,
        )
    except ValidationError:
        return
    raise AssertionError("heading_deg=361 (범위 초과)가 거부되지 않았다")


def test_undefined_enum_rejected():
    try:
        VisionFacePayload(
            visitor_id="v1",
            result="maybe",
            confidence=0.9,
            snapshot_path="/data/snap/x/face.jpg",
        )
    except ValidationError:
        return
    raise AssertionError("정의되지 않은 FaceResult 값('maybe')이 거부되지 않았다")


def test_naive_timestamp_rejected():
    try:
        Envelope(
            src=Node.MECHDOG_A,
            session_id=SESSION,
            ts=datetime(2026, 9, 2, 12, 0, 0),  # 타임존 없음
            payload=SystemHealthPayload(node=Node.MECHDOG_A, state=NodeState.READY),
        )
    except ValidationError:
        return
    raise AssertionError("타임존 없는 ts가 거부되지 않았다")


def test_authorized_and_undetermined_are_distinct():
    authorized = VisionFacePayload(
        visitor_id="v1",
        result=FaceResult.AUTHORIZED,
        confidence=0.9,
        snapshot_path="/data/snap/x/a.jpg",
    )
    undetermined = VisionFacePayload(
        visitor_id="v1",
        result=FaceResult.UNDETERMINED,
        confidence=0.9,
        snapshot_path="/data/snap/x/u.jpg",
    )
    assert authorized.result != undetermined.result, "authorized와 undetermined가 같은 값으로 합쳐졌다"
    assert authorized.result == FaceResult.AUTHORIZED
    assert undetermined.result == FaceResult.UNDETERMINED
    assert FaceResult.UNAUTHORIZED not in (authorized.result, undetermined.result)


def test_session_id_uniqueness_under_burst():
    ids = {new_session_id(Node.MECHDOG_A) for _ in range(500)}
    assert len(ids) == 500, "짧은 시간 안에 발급한 session_id 500개 중 중복이 발생했다"


def test_qos_policy_covers_lossless_message_types():
    lossless = {
        MsgType.VISION_FACE,
        MsgType.VISION_PPE,
        MsgType.GATE_SESSION,
        MsgType.DIALOG_RESULT,
        MsgType.ALERT_EVENT,
    }
    for msg_type in lossless:
        assert QOS_POLICY[msg_type] == 1, f"{msg_type}는 유실되면 안 되는데 QoS 1이 아니다"
    for msg_type in (MsgType.ESCORT_STATUS, MsgType.SYSTEM_HEALTH):
        assert QOS_POLICY[msg_type] == 0, f"{msg_type}는 스트림성 메시지인데 QoS 0이 아니다"


TESTS = [
    test_round_trip_all_msg_types,
    test_extra_field_rejected,
    test_confidence_out_of_range_rejected,
    test_angle_out_of_range_rejected,
    test_undefined_enum_rejected,
    test_naive_timestamp_rejected,
    test_authorized_and_undetermined_are_distinct,
    test_session_id_uniqueness_under_burst,
    test_qos_policy_covers_lossless_message_types,
]


def main() -> int:
    passed, failed = 0, 0
    for test in TESTS:
        name = test.__name__
        try:
            test()
        except Exception as exc:  # noqa: BLE001 - 실패 이유를 그대로 출력하기 위해 광범위하게 잡음
            failed += 1
            print(f"FAIL  {name}: {exc}")
        else:
            passed += 1
            print(f"PASS  {name}")

    print(f"\n{passed} passed, {failed} failed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
