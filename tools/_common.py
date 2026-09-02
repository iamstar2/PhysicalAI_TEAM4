"""mock_publisher.py / echo_subscriber.py 가 같이 쓰는 작은 헬퍼.

주의: 이건 팀원이 import해서 쓰는 공용 패키지가 아니다 (그건 없앴다 - schema/ 의
JSON Schema가 유일한 스펙이다). 이 파일은 tools/ 안의 두 데모 스크립트가 코드
중복을 피하려고 쓰는 로컬 유틸일 뿐이다.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

KST = timezone(timedelta(hours=9))

ROOT = Path(__file__).resolve().parent.parent
TOPICS_PATH = ROOT / "schema" / "topics.json"

with open(TOPICS_PATH, encoding="utf-8") as f:
    _TOPICS = json.load(f)

SUBSCRIBE_ALL = _TOPICS["subscribe_all"]
_TOPIC_BY_MSG_TYPE = {t["msg_type"]: t for t in _TOPICS["topics"]}


def topic_qos_retain(msg_type: str, node: str | None = None) -> tuple[str, int, bool]:
    """schema/topics.json 기준으로 (topic, qos, retain)을 반환.

    system.health 는 topic에 {node} 자리가 있어서 실제 노드 값으로 치환해야 한다.
    """
    entry = _TOPIC_BY_MSG_TYPE[msg_type]
    topic = entry["topic"].format(node=node) if "{node}" in entry["topic"] else entry["topic"]
    return topic, entry["qos"], entry["retain"]


def new_session_id(node: str) -> str:
    """방문자 세션 ID 발급.

    같은 초에 여러 방문자가 동시에 게이트에 접근해도 충돌하지 않도록, 타임스탬프
    (가독성/정렬용) 뒤에 uuid4 8자리(고유성 보장)를 덧붙인다. 순번(카운터) 방식은
    프로세스 재시작 시 0으로 리셋되어 이전 세션과 겹칠 수 있어 채택하지 않았다.
    """
    ts = datetime.now(KST).strftime("%Y%m%d%H%M%S")
    return f"sess-{ts}-{node}-{uuid.uuid4().hex[:8]}"


def make_envelope(*, src: str, session_id: str, payload: dict) -> dict:
    """schema/mechdog_messages.schema.json 을 만족하는 Envelope dict 생성."""
    return {
        "ver": 1,
        "msg_id": uuid.uuid4().hex,
        "ts": datetime.now(KST).isoformat(),
        "src": src,
        "session_id": session_id,
        "payload": payload,
    }
