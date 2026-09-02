#!/usr/bin/env python3
"""schema/mechdog_messages.schema.json 자체와 schema/examples/*.json이 서로 맞는지 검증.

공용 Python 패키지 없이, JSON Schema + jsonschema 라이브러리만으로 검증한다.
pytest 없이 단독 실행 가능. 통과/실패 개수를 마지막에 출력하고, 실패가 있으면
종료 코드 1을 반환한다.

사용법:
    pip install jsonschema
    python tools/validate_schema.py
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parent.parent
SCHEMA_PATH = ROOT / "schema" / "mechdog_messages.schema.json"
EXAMPLES_DIR = ROOT / "schema" / "examples"

with open(SCHEMA_PATH, encoding="utf-8") as f:
    SCHEMA = json.load(f)

VALIDATOR = Draft202012Validator(SCHEMA)


def load_examples() -> dict[str, dict]:
    examples = {}
    for path in sorted(EXAMPLES_DIR.glob("*.json")):
        with open(path, encoding="utf-8") as f:
            examples[path.stem] = json.load(f)
    return examples


# --- 테스트 케이스 ----------------------------------------------------------

def test_schema_itself_is_valid():
    Draft202012Validator.check_schema(SCHEMA)


def test_all_examples_pass():
    examples = load_examples()
    assert examples, "schema/examples 에 예시 파일이 하나도 없다"
    for name, data in examples.items():
        errors = list(VALIDATOR.iter_errors(data))
        assert not errors, f"{name}.json 이 스키마를 통과하지 못했다: {errors[0].message}"


def test_extra_field_rejected():
    data = copy.deepcopy(load_examples()["vision_face"])
    data["payload"]["unexpected_field"] = "should be rejected"
    errors = list(VALIDATOR.iter_errors(data))
    assert errors, "정의되지 않은 필드(unexpected_field)가 거부되지 않았다"


def test_confidence_out_of_range_rejected():
    data = copy.deepcopy(load_examples()["vision_face"])
    data["payload"]["confidence"] = 1.5
    errors = list(VALIDATOR.iter_errors(data))
    assert errors, "confidence=1.5 (범위 초과)가 거부되지 않았다"


def test_angle_out_of_range_rejected():
    data = copy.deepcopy(load_examples()["escort_status"])
    data["payload"]["heading_deg"] = 361
    errors = list(VALIDATOR.iter_errors(data))
    assert errors, "heading_deg=361 (범위 초과)가 거부되지 않았다"


def test_undefined_enum_rejected():
    data = copy.deepcopy(load_examples()["vision_face"])
    data["payload"]["result"] = "maybe"
    errors = list(VALIDATOR.iter_errors(data))
    assert errors, "정의되지 않은 FaceResult 값('maybe')이 거부되지 않았다"


def test_naive_timestamp_rejected():
    data = copy.deepcopy(load_examples()["vision_face"])
    data["ts"] = "2026-09-02T12:00:00"  # 타임존 없음
    errors = list(VALIDATOR.iter_errors(data))
    assert errors, "타임존 없는 ts가 거부되지 않았다"


def test_authorized_and_undetermined_are_distinct():
    base = load_examples()["vision_face"]
    authorized = copy.deepcopy(base)
    authorized["payload"]["result"] = "authorized"
    undetermined = copy.deepcopy(base)
    undetermined["payload"]["result"] = "undetermined"
    assert not list(VALIDATOR.iter_errors(authorized)), "authorized 예시가 스키마를 통과하지 못했다"
    assert not list(VALIDATOR.iter_errors(undetermined)), "undetermined 예시가 스키마를 통과하지 못했다"
    assert authorized["payload"]["result"] != undetermined["payload"]["result"], (
        "authorized와 undetermined가 같은 값으로 합쳐졌다"
    )


def test_qos_policy_covers_lossless_message_types():
    with open(ROOT / "schema" / "topics.json", encoding="utf-8") as f:
        topics = {t["msg_type"]: t for t in json.load(f)["topics"]}

    lossless = {"vision.face", "vision.ppe", "gate.session", "dialog.result", "alert.event"}
    for msg_type in lossless:
        assert topics[msg_type]["qos"] == 1, f"{msg_type}는 유실되면 안 되는데 QoS 1이 아니다"
    for msg_type in ("escort.status", "system.health"):
        assert topics[msg_type]["qos"] == 0, f"{msg_type}는 스트림성 메시지인데 QoS 0이 아니다"


TESTS = [
    test_schema_itself_is_valid,
    test_all_examples_pass,
    test_extra_field_rejected,
    test_confidence_out_of_range_rejected,
    test_angle_out_of_range_rejected,
    test_undefined_enum_rejected,
    test_naive_timestamp_rejected,
    test_authorized_and_undetermined_are_distinct,
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
