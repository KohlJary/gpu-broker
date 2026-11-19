"""Presets: catalog entries for common GPU programs, and Prometheus busy signals."""
import pytest

from gpu_broker import settings
from gpu_broker.backends import HttpBackends
from gpu_broker.catalogschema import validate
from gpu_broker.presets import entry, find
from gpu_broker.presets.cli import main as preset_main
from gpu_broker.presets.table import PRESETS
from gpu_broker.servicebusy import busy_from, metric_sum
from tests.test_backends import COMFY, http  # noqa: F401 — the fake-urlopen fixture

VERIFIED = {"ollama", "comfyui", "acestep"}   # run against a broker on a real 16 GB card

VLLM_METRICS = """# HELP vllm:num_requests_running Number of requests in model execution batches.
# TYPE vllm:num_requests_running gauge
vllm:num_requests_running{engine="0",model_name="m"} 2.0
vllm:num_requests_waiting{engine="0",model_name="m"} 3.0
vllm:other_thing 9
"""


def test_every_preset_makes_a_valid_entry_with_a_source():
    names = [p.name for p in PRESETS]
    assert len(names) == len(set(names))
    for p in PRESETS:
        m = entry(p, served_name="some-model")
        llm = {"kind": "llm", "runner": "llm_unit", "status": "ready", "unit": "x",
               "endpoint": "http://127.0.0.1:1", "served_name": "x"}
        validate({"defaults": {"resident": "_r"}, "models": {p.name: m, "_r": llm}})
        assert p.sources and all(s.startswith("https://") for s in p.sources), p.name


def test_only_what_ran_on_a_real_card_says_verified():
    assert {p.name for p in PRESETS if p.verified} == VERIFIED


def test_an_llm_server_needs_its_model_and_options_override_defaults():
    with pytest.raises(ValueError, match="served-name"):
        entry(find("vllm"))
    m = entry(find("acestep"), unit="acestep.service", port=9001)
    assert m["unit"] == "acestep.service" and m["endpoint"] == "http://127.0.0.1:9001" and m["session_only"]
    assert entry(find("comfyui")) == {"kind": "ui", "runner": "comfy", "session_only": True, "status": "ready"}
    with pytest.raises(KeyError):
        find("nope")


def test_metric_sum_adds_every_sample_whatever_its_labels():
    assert metric_sum(VLLM_METRICS, ["vllm:num_requests_running", "vllm:num_requests_waiting"]) == 5
    assert metric_sum(VLLM_METRICS, ["vllm:num_requests_running"]) == 2
    assert metric_sum(VLLM_METRICS, ["missing_metric"]) is None   # can't say, not idle
    assert busy_from(b'{"data": {"n": 1}}', ["data.n"], []) == 1
    assert busy_from(VLLM_METRICS.encode(), [], ["vllm:num_requests_waiting"]) == 3


def test_a_service_can_report_busy_through_metrics(http):
    _, routes = http

    class Text:
        def __init__(self, body):
            self.body = body.encode()

        def read(self, n=-1):
            return self.body

        def __enter__(self):
            return self

        def __exit__(self, *a):
            pass
    routes["/metrics"] = lambda req: Text("te_queue_size 4\n")
    b = HttpBackends(COMFY, settings.Timeouts(), settings.Intervals(), {}, sleep=lambda _: None)
    assert b.service_busy(entry(find("tei"), port=8080)) == 4


def test_the_cli_lists_and_prints_checked_entries(capsys):
    assert preset_main([]) == 0
    listing = capsys.readouterr().out
    assert all(p.name in listing for p in PRESETS)
    assert preset_main(["kokoro-fastapi", "--unit", "kokoro"]) == 0
    out = capsys.readouterr().out
    assert "from its docs, not yet run against a broker" in out and "ALLOW_DEV_UNLOAD" in out
    assert "kokoro-fastapi:\n  kind: ui\n  runner: service\n  unit: kokoro" in out
    assert preset_main(["ollama"]) == 2 and "served-name" in capsys.readouterr().err
