"""팀 메시지 스키마(`schema/mechdog_messages.schema.json`) 검사."""
from __future__ import annotations

import json
from functools import lru_cache

from jsonschema import Draft202012Validator, FormatChecker

from . import config


@lru_cache(maxsize=1)
def _validator() -> Draft202012Validator:
    schema = json.loads(config.SCHEMA_PATH.read_text(encoding="utf-8"))
    return Draft202012Validator(schema, format_checker=FormatChecker())


def errors(msg: dict) -> list[str]:
    """틀린 곳 목록. 빈 리스트면 통과."""
    out = []
    for e in sorted(_validator().iter_errors(msg), key=lambda e: list(e.path)):
        where = "/".join(str(p) for p in e.path) or "(root)"
        out.append(f"{where}: {e.message}")
    return out
