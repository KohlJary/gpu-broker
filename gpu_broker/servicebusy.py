"""What a service's busy_path answer means, as a pure function: how much work it says it has."""
from __future__ import annotations

from typing import Any

BUSY_FIELD = "busy"   # where the answer says how busy it is, unless the catalog's busy_fields names others


def busy_count(got: Any, fields: list[str]) -> int | None:
    """Sum the numbers (or bools) at dotted `fields` in a service's answer; a bare number counts as
    itself. None if any field is missing or not a number: the service can't say."""
    if isinstance(got, (bool, int, float)):
        return int(got)
    total = 0
    for field in fields:
        v = got
        for part in field.split("."):
            v = v.get(part) if isinstance(v, dict) else None
        if not isinstance(v, (bool, int, float)):
            return None
        total += int(v)
    return total
