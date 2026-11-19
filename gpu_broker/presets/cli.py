"""`gpu-broker preset`: list the presets, or print one as a catalog entry ready to paste.

    gpu-broker preset
    gpu-broker preset acestep --unit acestep.service
    gpu-broker preset ollama --unit ollama.service --served-name llama3.1:8b --key llama31

Needs no config, token or host access. The printed entry is checked by the catalog's own rules first.
"""
from __future__ import annotations

import argparse
import sys
from typing import Any

import yaml

from ..catalogschema import validate
from ..constants import Kind, Runner
from . import entry, find
from .table import PRESETS

COMMAND = "preset"
PLACEHOLDER_LLM = "_resident"   # validate() wants a default LLM; the printed entry never includes it


def _checked(key: str, m: dict[str, Any]) -> None:
    models: dict[str, Any] = {key: m}
    resident = key
    if m.get("runner") != Runner.LLM_UNIT:
        resident = PLACEHOLDER_LLM
        models[resident] = {"kind": Kind.LLM, "runner": Runner.LLM_UNIT, "status": "ready", "unit": "x",
                            "endpoint": "http://127.0.0.1:1", "served_name": "x"}
    validate({"defaults": {"resident": resident}, "models": models})  # type: ignore[typeddict-item]


def _listing() -> str:
    rows = [f"{'name':16} {'runner':9} {'port':>5}  {'busy signal':12} verified  program"]
    for p in PRESETS:
        busy = "metrics" if p.busy_metrics else "json" if p.busy_path else "none"
        rows.append(f"{p.name:16} {p.runner:9} {p.port:>5}  {busy:12} {'yes' if p.verified else 'no':8}  {p.label}")
    return "\n".join(rows)


def main(args: list[str]) -> int:
    ap = argparse.ArgumentParser(prog=f"gpu-broker {COMMAND}", description="Catalog entries for common GPU programs.")
    ap.add_argument("name", nargs="?", help="a preset (omit to list them)")
    ap.add_argument("--unit", help="the systemd unit or container that runs it (default: the preset's name)")
    ap.add_argument("--port", type=int, help="where it listens, if not its default")
    ap.add_argument("--served-name", help="LLM servers: the model it serves")
    ap.add_argument("--key", help="the catalog key (default: the preset's name)")
    a = ap.parse_args(args)
    if not a.name:
        print(_listing())
        return 0
    try:
        p = find(a.name)
        m = entry(p, a.unit, a.port, a.served_name)
        _checked(a.key or p.name, m)
    except (KeyError, ValueError) as e:
        print(f"gpu-broker {COMMAND}: {e.args[0] if e.args else e}", file=sys.stderr)
        return 2
    head = [f"# {p.label}: {'verified on a real card' if p.verified else 'from its docs, not yet run against a broker'}"]
    head += [f"# needs: {p.needs}"] if p.needs else []
    head += [f"# {p.notes}"] if p.notes else []
    head += [f"# source: {s}" for s in p.sources]
    print("\n".join(head))
    print(yaml.safe_dump({a.key or p.name: m}, sort_keys=False).rstrip())
    return 0
