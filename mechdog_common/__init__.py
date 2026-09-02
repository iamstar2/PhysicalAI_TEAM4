"""MechDog 공용 MQTT 메시지 규약 패키지.

팀 전체가 이 패키지를 import해서 메시지를 만들고, 발행/구독한다.

    from mechdog_common import MechDogBus, Node, MsgType, new_session_id
    from mechdog_common import VisionFacePayload, FaceResult
"""

from .enums import (
    AlertLevel,
    AlertReason,
    Destination,
    EscortState,
    FACE_SIMILARITY_THRESHOLD,
    FaceResult,
    MsgType,
    Node,
    NodeState,
    PpeItem,
    PpeResult,
)
from .messages import (
    AlertEventPayload,
    DialogResultPayload,
    Envelope,
    EscortStatusPayload,
    GateSessionPayload,
    Point,
    PayloadBase,
    SystemHealthPayload,
    VisionFacePayload,
    VisionPpePayload,
    make_envelope,
    new_session_id,
    now_iso,
)
from .topics import QOS_POLICY, RETAIN_POLICY, SUBSCRIBE_ALL, TOPIC_PREFIX, qos_for, retain_for, topic_for
from .paths import AUDIO_ROOT, DEFAULT_RETENTION_DAYS, SNAPSHOT_ROOT, audio_path, snapshot_path
from .bus import MechDogBus

__all__ = [
    # enums
    "AlertLevel",
    "AlertReason",
    "Destination",
    "EscortState",
    "FACE_SIMILARITY_THRESHOLD",
    "FaceResult",
    "MsgType",
    "Node",
    "NodeState",
    "PpeItem",
    "PpeResult",
    # messages
    "AlertEventPayload",
    "DialogResultPayload",
    "Envelope",
    "EscortStatusPayload",
    "GateSessionPayload",
    "Point",
    "PayloadBase",
    "SystemHealthPayload",
    "VisionFacePayload",
    "VisionPpePayload",
    "make_envelope",
    "new_session_id",
    "now_iso",
    # topics
    "QOS_POLICY",
    "RETAIN_POLICY",
    "SUBSCRIBE_ALL",
    "TOPIC_PREFIX",
    "qos_for",
    "retain_for",
    "topic_for",
    # paths
    "AUDIO_ROOT",
    "DEFAULT_RETENTION_DAYS",
    "SNAPSHOT_ROOT",
    "audio_path",
    "snapshot_path",
    # bus
    "MechDogBus",
]
