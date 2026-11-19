"""What a service's busy_path answer means, as pure functions: how much work it says it has.

Two shapes: JSON (`busy_fields`, dotted paths, summed) and Prometheus text (`busy_metrics`, metric
names, every sample of each summed whatever its labels), for servers that only count work in
/metrics (vLLM, llama.cpp with --metrics, text-embeddings-inference).
"""
from __future__ import annotations

import json
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


def busy_from(raw: bytes, fields: list[str], metrics: list[str]) -> int | None:
    """A busy_path answer: Prometheus text when `metrics` names metrics, else JSON."""
    if metrics:
        return metric_sum(raw.decode("utf-8", "replace"), metrics)
    return busy_count(json.loads(raw), fields)


def metric_sum(text: str, names: list[str]) -> int | None:
    """Sum every sample of the named metrics in Prometheus text exposition; None if one is absent."""
    totals: dict[str, float] = {}
    for line in text.splitlines():
        if not line or line.startswith("#"):
            continue
        head, _, value = line.rpartition(" ")
        name = head.split("{", 1)[0].strip()
        if name in names:
            try:
                totals[name] = totals.get(name, 0.0) + float(value)
            except ValueError:
                return None
    if any(n not in totals for n in names):
        return None
    return int(sum(totals.values()))
