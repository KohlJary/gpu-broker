"""Services: non-LLM servers (music, speech, ...) the broker starts for a session and stops after.

A service is a unit with an endpoint, borrowed whole through a session like ComfyUI. Its busy_path
says when it is still working; anything else that needs the card stops it.
"""
import pathlib

import pytest
import yaml

from gpu_broker import settings
from gpu_broker.backends import HttpBackends
from gpu_broker.broker import Broker
from gpu_broker.catalog import Catalog
from gpu_broker.catalogschema import validate
from gpu_broker.constants import JobState
from gpu_broker.residency import Residency
from gpu_broker.servicebusy import busy_count
from gpu_broker.sessions import End, Sessions
from gpu_broker.store import Store
from gpu_broker.units import unit_ref
from tests.helpers import FIX, TOKEN, FakeBackends, FakeDriver, done, make_settings
from tests.test_backends import COMFY, http  # noqa: F401 — the fake-urlopen fixture

SERVICE = {"kind": "ui", "runner": "service", "status": "ready", "unit": "music-gen",
           "endpoint": "http://127.0.0.1:8001", "busy_path": "/busy", "session_only": True, "vram_mib": 6000}


def catalog_with_service(tmp_path: pathlib.Path, **over) -> pathlib.Path:
    data = yaml.safe_load((FIX / "catalog.yaml").read_text())
    data["models"]["music"] = {**SERVICE, **over}
    out = tmp_path / "catalog-service.yaml"
    out.write_text(yaml.safe_dump(data))
    return out


# ---- the catalog ---------------------------------------------------------------------------

def test_a_service_needs_a_unit_an_endpoint_and_session_only(tmp_path):
    data = yaml.safe_load(catalog_with_service(tmp_path).read_text())
    validate(data)
    for drop, msg in (("unit", "needs a unit and an endpoint"), ("endpoint", "needs a unit and an endpoint"),
                      ("session_only", "sessions only")):
        bad = {**data, "models": {**data["models"], "music": {k: v for k, v in SERVICE.items() if k != drop}}}
        with pytest.raises(ValueError, match=msg):
            validate(bad)


def test_busy_path_is_a_path_and_a_service_is_never_the_default_resident(tmp_path):
    data = yaml.safe_load(catalog_with_service(tmp_path, busy_path="http://elsewhere/busy").read_text())
    with pytest.raises(ValueError, match="busy_path must be a path"):
        validate(data)
    data = yaml.safe_load(catalog_with_service(tmp_path).read_text())
    data["defaults"]["resident"] = "music"
    with pytest.raises(ValueError, match="cannot be a service"):
        validate(data)


def test_a_service_unit_is_allowlisted_like_any_catalog_unit(tmp_path):
    assert unit_ref("music-gen") in Catalog(str(catalog_with_service(tmp_path))).units()


# ---- residency -----------------------------------------------------------------------------

@pytest.fixture
def res(tmp_path):
    driver = FakeDriver({"llama-8b"})
    ticks = iter(range(10**6))
    r = Residency(Catalog(str(catalog_with_service(tmp_path))), driver, FakeBackends(driver), Store(str(tmp_path / "b.db")),
                  settings.Timeouts(llm_start_s=5, comfy_start_s=5), settings.Intervals(), unit_ref("comfyui"),
                  clock=lambda: next(ticks), sleep=lambda _: None)
    r.detect()
    return r


def test_a_service_gets_the_card_the_llm_stops_and_comfy_is_freed(res):
    res.ensure("music")
    assert res.driver.active == {"music-gen"} and res.service == "music" and res.current is None
    assert res.backends.frees == 1


def test_anything_else_stops_the_service(res):
    for nxt in ("llama-8b", "sdxl-base", "sharp"):
        res.ensure("music")
        res.ensure(nxt)
        assert res.service is None and "music-gen" not in res.driver.active, nxt


def test_a_resident_healthy_service_is_a_no_op_and_a_lost_one_restarts(res):
    res.ensure("music")
    calls = len(res.driver.calls)
    res.ensure("music")
    assert len(res.driver.calls) == calls
    res.driver.active.discard("music-gen")   # stopped behind the broker's back
    res.ensure("music")
    assert "music-gen" in res.driver.active and res.service == "music"


def test_detect_finds_a_service_left_running(tmp_path):
    driver = FakeDriver({"llama-8b", "music-gen"})
    r = Residency(Catalog(str(catalog_with_service(tmp_path))), driver, FakeBackends(driver), Store(str(tmp_path / "b.db")),
                  settings.Timeouts(), settings.Intervals(), unit_ref("comfyui"), sleep=lambda _: None)
    assert r.detect() == "llama-8b" and r.service == "music"
    r.ensure("llama-8b")   # the next switch stops it, so its VRAM comes back
    assert r.service is None and "music-gen" not in driver.active


def test_a_session_on_a_service_left_running_still_stops_the_llm(tmp_path):
    """Regression (found on a real card): a service adopted at startup was 'already up', and the
    session returned before stopping the LLM, so both sat on the card."""
    driver = FakeDriver({"llama-8b", "music-gen"})
    r = Residency(Catalog(str(catalog_with_service(tmp_path))), driver, FakeBackends(driver), Store(str(tmp_path / "b.db")),
                  settings.Timeouts(), settings.Intervals(), unit_ref("comfyui"), sleep=lambda _: None)
    r.detect()
    starts = [c for c in driver.calls if c[0] == "start"]
    r.ensure("music")
    assert r.current is None and driver.active == {"music-gen"} and r.service == "music"
    assert [c for c in driver.calls if c[0] == "start"] == starts   # already up: not restarted


def test_a_service_waits_for_its_vram(res):
    res.driver.vram = (20000, 24564)   # 4.5 GB free; music needs 6
    with pytest.raises(RuntimeError, match="needs 6000 MiB"):
        res.ensure("music")


# ---- sessions --------------------------------------------------------------------------------

def test_a_session_asks_its_own_model_whether_it_is_busy():
    t = [0.0]
    s = Sessions({"session_idle_s": 100, "session_yield_s": 10, "session_max_s": 1000}, lambda: 0, poll_s=5,
                 clock=lambda: t[0], sleep=lambda d: t.__setitem__(0, t[0] + d))
    answers = iter([2, 1, None] + [0] * 1000)   # working, working, can't say (counts as busy), then idle
    asked: list[str] = []
    s.busy_for = lambda key: asked.append(key) or next(answers)
    out = s.hold("j", "music", {})
    assert out["ended"] == End.IDLE and out["held_s"] == 110 and set(asked) == {"music"}


def test_http_service_busy_reads_a_number_a_bool_or_an_object(http):
    _, routes = http
    b = HttpBackends(COMFY, settings.Timeouts(), settings.Intervals(), {}, sleep=lambda _: None)
    assert b.service_busy({k: v for k, v in SERVICE.items() if k != "busy_path"}) is None   # nothing to ask
    assert b.service_busy(SERVICE) is None                                               # refused: can't say
    for answer, want in ((3, 3), (0, 0), (True, 1), (False, 0), ({"busy": 2}, 2), ({"busy": False}, 0),
                         ("yes", None), ({"other": 1}, None)):
        routes["/busy"] = answer
        assert b.service_busy(SERVICE) == want, answer


def test_busy_fields_sum_dotted_paths_in_the_services_own_shape(http):
    # ACE-Step's /v1/stats, as it answers
    stats = {"data": {"jobs": {"total": 3, "queued": 1, "running": 1}, "queue_size": 1}, "code": 200}
    fields = ["data.queue_size", "data.jobs.running"]
    assert busy_count(stats, fields) == 2
    assert busy_count({"data": {"jobs": {"running": 0}, "queue_size": 0}}, fields) == 0
    assert busy_count({"data": {}}, fields) is None   # a field it doesn't answer: can't say
    _, routes = http
    routes["/v1/stats"] = stats
    b = HttpBackends(COMFY, settings.Timeouts(), settings.Intervals(), {}, sleep=lambda _: None)
    assert b.service_busy({**SERVICE, "busy_path": "/v1/stats", "busy_fields": fields}) == 2


def test_busy_fields_must_be_dotted_paths(tmp_path):
    data = yaml.safe_load(catalog_with_service(tmp_path, busy_fields="data.running").read_text())
    with pytest.raises(ValueError, match="busy_fields must be a list"):
        validate(data)


# ---- through the broker and the API -------------------------------------------------------------

@pytest.fixture
def service_broker(tmp_path):
    driver = FakeDriver({"llama-8b"})
    b = Broker(make_settings(tmp_path, catalog=catalog_with_service(tmp_path)), env={}, driver=driver,
               backends=FakeBackends(driver))
    b.start()
    yield b
    b.stop()


def test_restoring_the_default_llm_stops_a_resident_service(tmp_path):
    """Regression (found on a real card): idle restore saw the default LLM already resident and
    returned, leaving the service on the card after its session ended."""
    driver = FakeDriver({"llama-8b", "music-gen"})
    b = Broker(make_settings(tmp_path, catalog=catalog_with_service(tmp_path)), env={}, driver=driver,
               backends=FakeBackends(driver))
    b.start()
    try:
        assert b.residency.current == "llama-8b" and b.residency.service == "music"
        b.scheduler._restore_now = True
        b.scheduler.maybe_restore()
        assert b.residency.service is None and "music-gen" not in driver.active and b.residency.current == "llama-8b"
    finally:
        b.stop()


def test_a_service_session_starts_it_holds_the_card_and_gives_it_back(service_broker):
    from fastapi.testclient import TestClient

    from gpu_broker.web.app import create_app
    b = service_broker
    with TestClient(create_app(b, TOKEN, start=False)) as c:
        c.headers["Authorization"] = f"Bearer {TOKEN}"
        r = c.post("/v1/sessions", json={"model": "music", "idle_min": 0.0001}).json()
        j = done(b, r["id"])
        assert j["state"] == JobState.DONE and j["result"]["ended"] == End.IDLE
        assert "music-gen" in b.backends.busy_asked   # it asked the service, not ComfyUI
        assert c.post("/v1/jobs", json={"model": "music", "prompt": "x"}).json()["job"]["state"] == JobState.REJECTED
    b.scheduler.maybe_restore()   # the session ended: the default LLM comes back and the service stops
    assert b.residency.current == "llama-8b" and b.residency.service is None
    assert "music-gen" not in b.driver.active
