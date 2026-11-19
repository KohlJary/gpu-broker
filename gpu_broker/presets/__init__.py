"""Presets: catalog entries for the programs that most often share a home GPU.

Each preset says how the program is usually run (default port, a health path, where it reports
being busy, the words its units and containers carry) and where those facts come from. `verified`
is true only for programs that have been run against a broker on a real card; the rest come from
their own docs and source, and say so. `gpu-broker preset NAME --unit UNIT` prints the entry.

Pure data and pure functions: nothing here contacts anything.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..constants import Kind, ModelStatus, Runner

LOCAL = "http://127.0.0.1"


@dataclass(frozen=True)
class Preset:
    name: str
    label: str
    runner: str                       # llm_unit | comfy | service
    port: int                         # the program's own default
    health_path: str = "/health"
    busy_path: str | None = None
    busy_fields: tuple[str, ...] = ()
    busy_metrics: tuple[str, ...] = ()
    words: tuple[str, ...] = ()       # in its systemd units, container names or images
    needs: str = ""                   # what it must be started with for this to work
    notes: str = ""
    sources: tuple[str, ...] = ()
    verified: bool = False            # run against a broker on a real card
    kind: str = field(default=Kind.UI)


def entry(p: Preset, unit: str | None = None, port: int | None = None,
          served_name: str | None = None) -> dict[str, Any]:
    """The catalog entry for preset `p`. LLM servers need `served_name` (the model the server
    loads); units default to the preset's name."""
    endpoint = f"{LOCAL}:{port or p.port}"
    if p.runner == Runner.COMFY:   # ComfyUI itself is configured under `comfy:`; this lends it the card
        return {"kind": Kind.UI.value, "runner": Runner.COMFY.value, "session_only": True,
                "status": ModelStatus.READY.value}
    m: dict[str, Any] = {"kind": str(p.kind), "runner": str(p.runner), "unit": unit or p.name, "endpoint": endpoint,
                         "health_path": p.health_path, "status": ModelStatus.READY.value}
    if p.runner == Runner.LLM_UNIT:
        if not served_name:
            raise ValueError(f"{p.name} serves models: say which one (--served-name)")
        m["served_name"] = served_name
        return m
    m["session_only"] = True
    if p.busy_path:
        m["busy_path"] = p.busy_path
        if p.busy_fields:
            m["busy_fields"] = list(p.busy_fields)
        if p.busy_metrics:
            m["busy_metrics"] = list(p.busy_metrics)
    return m


def find(name: str) -> Preset:
    from .table import PRESETS
    for p in PRESETS:
        if p.name == name:
            return p
    raise KeyError(f"no preset {name!r}; `gpu-broker preset` lists them")
