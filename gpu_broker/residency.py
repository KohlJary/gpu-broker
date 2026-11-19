"""GPU residency: make exactly the model a job needs resident, evicting whatever is in the way.

Three kinds of tenant share the card. LLM servers are units the driver starts and stops
whole; at most one is resident. ComfyUI stays running (its idle footprint is small) and
loads models per job, releasing them on POST /free. A service (a non-LLM server: music, speech,
anything with a unit and a health check) is also a unit started whole, but only for a session,
and it is stopped as soon as anything else needs the card.

Only the scheduler's GPU thread calls `ensure`, and only between jobs, so there is no
locking here. State is re-checked rather than trusted: other operators may stop an LLM or
ComfyUI behind the broker's back, and `last_comfy` does not survive a restart.
"""
from __future__ import annotations

import time
from collections.abc import Callable

from .backends import Backends
from .catalog import Catalog
from .constants import ERR_SHORT, Event, Runner, Verb
from .drivers import DRIVER_ERRORS, Driver
from .settings import Intervals, Timeouts
from .store import Store
from .units import UnitRef, unit_ref

DECIMALS = 1


class Residency:
    def __init__(self, catalog: Catalog, driver: Driver, backends: Backends, store: Store, timeouts: Timeouts,
                 intervals: Intervals, comfy_unit: UnitRef | None = None,
                 clock: Callable[[], float] = time.monotonic, sleep: Callable[[float], None] = time.sleep) -> None:
        self.catalog, self.driver, self.backends, self.store = catalog, driver, backends, store
        self.t, self.i, self.comfy_unit = timeouts, intervals, comfy_unit
        self.clock, self.sleep = clock, sleep
        self.current: str | None = None      # catalog key of the resident LLM, if any
        self.service: str | None = None      # catalog key of the resident service, if any (never an LLM)
        self.last_comfy: str | None = None   # last ComfyUI model that ran (its weights may still be loaded)
        # The GPU sampler's latest reading if fresh and taken after the given wall-clock time,
        # else None (then the driver is asked). `wall` stamps that time; samples use time.time.
        self.cached_gpu: Callable[[float], tuple[int, int, int | None] | None] = lambda after: None
        self.wall: Callable[[], float] = time.time

    def detect(self) -> str | None:
        """At startup: adopt whichever LLM unit is already running. A broken driver is logged,
        not raised, so the API still comes up."""
        self.current = None
        for key, m in self.catalog.llm_units():
            try:
                if self.driver.unit(m["unit"], Verb.IS_ACTIVE):
                    self.current = key
                    break
            except DRIVER_ERRORS as e:
                self.store.event(Event.RES_DETECT_FAILED, model=key, error=str(e)[:ERR_SHORT])
        self.service = None
        for key, m in self.catalog.services():   # a service left running holds VRAM: track it to stop it
            try:
                if self.driver.unit(m["unit"], Verb.IS_ACTIVE):
                    self.service = key
                    break
            except DRIVER_ERRORS as e:
                self.store.event(Event.RES_DETECT_FAILED, model=key, error=str(e)[:ERR_SHORT])
        return self.current

    def healthy(self, key: str) -> bool:
        return self.backends.llm_healthy(self.catalog.models[key])

    def _wait(self, ready: Callable[[], bool], timeout_s: float) -> float | None:
        """Poll `ready` until it holds; seconds waited, or None on timeout."""
        start = self.clock()
        while self.clock() - start < timeout_s:
            if ready():
                return self.clock() - start
            self.sleep(self.i.health_poll_s)
        return None

    def _stop_unit(self, key: str, jid: str | None) -> None:
        self.store.event(Event.RES_STOP, jid, model=key)
        self.driver.unit(self.catalog.models[key]["unit"], Verb.STOP)

    def _start_unit(self, key: str, jid: str | None) -> None:
        unit = self.catalog.models[key]["unit"]
        self.store.event(Event.RES_START, jid, model=key)
        if not self.driver.unit(unit, Verb.START):
            raise RuntimeError(f"could not start {unit_ref(unit).name}")
        waited = self._wait(lambda: self.healthy(key), self.t.llm_start_s)
        if waited is None:
            raise RuntimeError(f"{key} did not become healthy within {self.t.llm_start_s}s")
        self.store.event(Event.RES_READY, jid, model=key, load_s=round(waited, DECIMALS))

    def _comfy_up(self, jid: str | None) -> None:
        """ComfyUI is meant to stay up, but it can be stopped from outside; start it if we may."""
        if self.backends.comfy_alive():
            return
        self.store.event(Event.RES_COMFY_DOWN, jid)
        if self.comfy_unit is None:
            raise RuntimeError("ComfyUI is down and no comfy.unit is configured to start it")
        if not self.driver.unit(self.comfy_unit, Verb.START):
            raise RuntimeError("ComfyUI is down and could not be started")
        if self._wait(self.backends.comfy_alive, self.t.comfy_start_s) is None:
            raise RuntimeError(f"ComfyUI did not come up within {self.t.comfy_start_s}s")
        self.store.event(Event.RES_COMFY_STARTED, jid)

    def ensure(self, key: str, jid: str | None = None) -> None:
        """Make `key` runnable now."""
        runner = self.catalog.models[key]["runner"]
        if self.service and self.service != key:   # whatever comes next needs the card the service holds
            self._stop_unit(self.service, jid)
            self.service = None
        if runner == Runner.SERVICE:
            self._service_up(key, jid)
        elif runner == Runner.LLM_UNIT:
            if self.current == key and self.healthy(key):
                return
            if self.current == key:  # stopped from outside since we last looked
                self.store.event(Event.RES_LOST, jid, model=key)
                self.current = None
            # Free ComfyUI unconditionally: it may have been used directly, outside the broker.
            self.backends.comfy_free()
            self.last_comfy = None
            if self.current:
                self._stop_unit(self.current, jid)
            self._start_unit(key, jid)
            self.current = key
        else:
            if self.current:
                self._stop_unit(self.current, jid)
                self.current = None
            if self.catalog.models[key]["runner"] == Runner.EXEC:
                # A program outside ComfyUI needs the card to itself: drop ComfyUI's weights too
                # (best effort — a ComfyUI that is down holds no VRAM).
                self.backends.comfy_free()
                self.last_comfy = None
                self._wait_vram(key, self.wall())   # the LLM stop and the free have returned
            else:
                self._comfy_up(jid)
                if self.last_comfy and self.last_comfy != key:
                    self.backends.comfy_free()
                self.last_comfy = key
        self.store.event(Event.RES_RESIDENT, jid, model=key)

    def _service_up(self, key: str, jid: str | None) -> None:
        """A service gets the card to itself: stop the LLM, free ComfyUI, wait for its VRAM, start it.
        The LLM is stopped even when the service is already up (one left running at startup)."""
        if self.current:
            self._stop_unit(self.current, jid)
            self.current = None
        self.backends.comfy_free()
        self.last_comfy = None
        if self.service == key and self.healthy(key):
            return
        if self.service == key:  # stopped from outside since we last looked
            self.store.event(Event.RES_LOST, jid, model=key)
            self.service = None
        self._wait_vram(key, self.wall())
        self._start_unit(key, jid)
        self.service = key

    def _wait_vram(self, key: str, freed_at: float) -> None:
        """Freed VRAM is returned asynchronously (a stopped server's process exits, ComfyUI's
        /free unloads in the background): poll the GPU until the model's `vram_mib` fits, within
        timeouts.exec_vram_s. Nothing to wait for if the catalog gives no size. Uses the GPU
        sampler's reading only if it was taken after `freed_at` (when the evictions returned) —
        an older one says nothing about the card now — else asks the driver."""
        need = int(self.catalog.models[key].get("vram_mib") or 0)
        if not need:
            return
        end = self.clock() + self.t.exec_vram_s
        while True:
            used, total, _ = self.cached_gpu(freed_at) or self.driver.gpu()
            if total - used >= need:
                return
            if self.clock() >= end:
                raise RuntimeError(f"{key} needs {need} MiB of VRAM; only {total - used} MiB free after "
                                   f"{self.t.exec_vram_s:g}s (something else holds the GPU)")
            self.sleep(self.i.health_poll_s)

    def release_comfy(self) -> None:
        """Unload ComfyUI's weights after an image/video run so the default LLM fits again."""
        if self.last_comfy:
            self.backends.comfy_free()
            self.last_comfy = None
