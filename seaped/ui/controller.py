"""Application controller: single source of truth between UI and engines.

All heavy work (load engine thread, coordinator thread, proxy checks) lives
behind this object. The UI only polls thread-safe snapshots and drains events.
"""

from __future__ import annotations

import json
import queue
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional

from ..core.config import (
    AuthorizationError,
    TestConfig,
    list_presets,
    load_preset,
    project_dir,
    save_preset,
)
from ..core.engine import EngineEvent, EngineState, LoadEngine
from ..core.metrics import IntervalSample, MetricsCollector, MetricsSnapshot, SeriesAggregator
from ..core.result import TestResult, build_result, save_result
from ..dist.coordinator import Coordinator
from ..net.proxy import ProxyManager

SESSION_FILE = "session.json"


class AppController:
    def __init__(self) -> None:
        self.events: "queue.Queue[EngineEvent]" = queue.Queue(maxsize=5000)
        self.collector = MetricsCollector()
        self.aggregator = SeriesAggregator()
        self.proxy_manager = ProxyManager()
        self.engine: Optional[LoadEngine] = None
        self.coordinator: Optional[Coordinator] = None
        self.config: TestConfig = self._load_session()
        self.last_result: Optional[TestResult] = None
        self.last_error: str = ""
        self.distributed_active: bool = False
        self.local_included: bool = True
        self._lock = threading.Lock()
        self._finish_reason: str = ""
        self.started_at: float = 0.0

    # ----------------------------- session ----------------------------- #
    def _session_path(self) -> Path:
        return project_dir() / SESSION_FILE

    def _load_session(self) -> TestConfig:
        path = self._session_path()
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                cfg = TestConfig.from_dict(data.get("config", {}))
                cfg.authorized = False  # never persist the consent flag
                return cfg
            except Exception:
                pass
        return TestConfig(name="New test", target="", authorized=False)

    def save_session(self) -> None:
        try:
            payload = {"config": self.config.to_dict(), "saved_at": time.time()}
            self._session_path().write_text(
                json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
            )
        except Exception:
            pass

    # ----------------------------- events ----------------------------- #
    def post(self, kind: str, message: str, **data) -> None:
        try:
            self.events.put_nowait(EngineEvent(kind=kind, message=message, data=data))
        except queue.Full:
            pass

    def drain_events(self, limit: int = 200) -> List[EngineEvent]:
        out: List[EngineEvent] = []
        for _ in range(limit):
            try:
                out.append(self.events.get_nowait())
            except queue.Empty:
                break
        return out

    # ----------------------------- engine ----------------------------- #
    @property
    def state(self) -> EngineState:
        if self.engine and self.engine.state in (
            EngineState.STARTING,
            EngineState.RUNNING,
            EngineState.STOPPING,
        ):
            return self.engine.state
        if self.distributed_active and self._agents_running() > 0:
            return EngineState.RUNNING
        if self.engine:
            return self.engine.state
        return EngineState.IDLE

    @property
    def running(self) -> bool:
        return self.state in (EngineState.STARTING, EngineState.RUNNING, EngineState.STOPPING)

    def _agents_running(self) -> int:
        if not self.coordinator:
            return 0
        return len([a for a in self.coordinator.agents() if a.state in ("running", "stopping")])

    def snapshot(self) -> MetricsSnapshot:
        if self.engine:
            return self.engine.collector.snapshot()
        return MetricsSnapshot()

    def merged_series(self) -> List[IntervalSample]:
        return self.aggregator.samples()

    def _on_engine_event(self, event: EngineEvent) -> None:
        self.post(event.kind, event.message, **event.data)
        if event.kind == "finished":
            snapshot = event.data.get("snapshot") or self.collector.snapshot()
            try:
                result = build_result(
                    self.config,
                    snapshot,
                    event.message,
                    agents=self._agent_summaries(),
                    started_at=self.started_at or None,
                )
                save_result(result)
                self.last_result = result
                self.post("result", f"Report saved: {result.id}", result=result)
            except Exception as exc:  # noqa: BLE001
                self.post("error", f"Failed to save report: {exc}")

    def _agent_summaries(self) -> List[dict]:
        if not self.coordinator:
            return []
        return [a.to_dict() for a in self.coordinator.agents()]

    def start_test(self, config: Optional[TestConfig] = None) -> None:
        """Validate, authorize and launch a test (local and/or distributed)."""
        from ..i18n import tr

        cfg = config or self.config
        cfg.require_authorization()
        problems = cfg.validate()
        if problems:
            raise ValueError("; ".join(problems))
        if self.running:
            raise ValueError(tr("val.engine_running"))

        self.config = cfg
        self.last_error = ""
        self.collector.reset()
        self.aggregator = SeriesAggregator()
        if self.coordinator:
            self.coordinator.aggregator = self.aggregator
        self.started_at = time.time()

        proxies = []
        if cfg.proxy_profile:
            proxies = self.proxy_manager.urls_for_profile(cfg.proxy_profile)
            if not proxies:
                raise ValueError(tr("val.proxy_offline", name=cfg.proxy_profile))

        remote_count = 0
        if self.distributed_active and self.coordinator and self.coordinator.listening:
            remote_count = self.coordinator.send_spec(cfg.to_dict())
            if remote_count:
                self.post("log", f"Specification sent to {remote_count} agent(s).")

        start_local = self.local_included or remote_count == 0
        if not start_local and remote_count == 0:
            raise ValueError("No agents available and local machine is excluded.")

        if start_local:
            engine = LoadEngine(
                cfg,
                collector=self.collector,
                on_event=self._on_engine_event,
                on_sample=self.aggregator.add,
                proxies=proxies,
                label="local",
            )
            self.engine = engine
            engine.start()
        elif remote_count:
            self.post(
                "log",
                f"Distributed test running on {remote_count} agent(s); "
                "local machine excluded.",
            )

    def stop_test(self, reason: str = "") -> None:
        from ..i18n import tr

        self._finish_reason = reason or tr("stop.manual")
        if self.engine and self.engine.running:
            self.engine.stop(reason)
        if self.coordinator and self.coordinator.listening:
            try:
                n = self.coordinator.stop_test()
                if n:
                    self.post("log", f"Stop command sent to {n} agent(s).")
            except RuntimeError:
                pass
        if not (self.engine and self.engine.running):
            self.distributed_active = False

    def wait_idle(self, timeout: float = 15.0) -> bool:
        if self.engine:
            return self.engine.join(timeout)
        return True

    # ----------------------------- results ----------------------------- #
    def save_distributed_result(self, stop_reason: str = "") -> TestResult:
        """Build + persist a report from merged distributed samples."""
        from ..i18n import tr

        series = self.aggregator.samples()
        if not series:
            raise ValueError(tr("val.no_samples_dist"))
        snapshot = snapshot_from_series(series, self.started_at)
        result = build_result(
            self.config, snapshot, stop_reason or tr("stop.manual"),
            agents=self._agent_summaries(),
            started_at=self.started_at or None,
        )
        save_result(result)
        self.last_result = result
        self.post("result", f"Distributed report saved: {result.id}", result=result)
        return result

    # ----------------------------- coordinator ----------------------------- #
    def coordinator_start(self, host: str, port: int, token: str) -> None:
        if self.coordinator and self.coordinator.listening:
            raise RuntimeError("Coordinator is already running.")
        coord = Coordinator(token=token, host=host, port=port, aggregator=self.aggregator)
        coord.start()
        if not coord.listening:
            raise RuntimeError(coord.last_error or "Coordinator failed to start.")
        self.coordinator = coord
        self.post("log", f"Coordinator listening on {host}:{coord.port}")

    def coordinator_stop(self) -> None:
        if not self.coordinator:
            return
        self.coordinator.stop()
        self.coordinator = None
        self.distributed_active = False
        self.post("log", "Coordinator stopped.")

    def require_coordinator(self) -> Coordinator:
        if not self.coordinator or not self.coordinator.listening:
            raise RuntimeError("Coordinator is not running.")
        return self.coordinator

    def require_coordinator_safe(self) -> Optional[Coordinator]:
        """Return the coordinator only when it is actually listening."""
        if self.coordinator and self.coordinator.listening:
            return self.coordinator
        return None

    # ----------------------------- presets ----------------------------- #
    def save_preset(self, name: str) -> Path:
        return save_preset(self.config, name)

    def load_preset(self, name: str) -> TestConfig:
        cfg = load_preset(name)
        cfg.authorized = False
        self.config = cfg
        return cfg

    def list_presets(self) -> List[str]:
        return list_presets()


def snapshot_from_series(series: List[IntervalSample], started_at: float = 0.0) -> MetricsSnapshot:
    """Rebuild a summary snapshot from merged (distributed) interval samples."""
    if not series:
        return MetricsSnapshot()
    ok = sum(s.ok for s in series)
    failed = sum(s.errors for s in series)
    total = ok + failed
    with_counts = [s for s in series if s.count > 0]
    recent = with_counts[-5:]
    errors: Dict[str, int] = {}
    statuses: Dict[str, int] = {}
    for s in series:
        for kind, count in s.error_kinds.items():
            errors[kind] = errors.get(kind, 0) + count
    bytes_in = int(sum(s.bytes_per_s for s in series))
    return MetricsSnapshot(
        elapsed=(time.time() - started_at) if started_at else float(len(series)),
        total=total,
        ok=ok,
        failed=failed,
        rps=round(sum(s.rps for s in recent) / len(recent), 2) if recent else 0.0,
        peak_rps=round(max((s.rps for s in series), default=0.0), 2),
        avg_latency=round(sum(s.avg for s in with_counts) / len(with_counts), 2)
        if with_counts
        else 0.0,
        min_latency=0.0,
        max_latency=round(max((s.max_lat for s in series), default=0.0), 2),
        p50=round(sum(s.p50 for s in with_counts) / len(with_counts), 2) if with_counts else 0.0,
        p75=round(sum(s.p75 for s in with_counts) / len(with_counts), 2) if with_counts else 0.0,
        p90=round(sum(s.p90 for s in with_counts) / len(with_counts), 2) if with_counts else 0.0,
        p95=round(sum(s.p95 for s in with_counts) / len(with_counts), 2) if with_counts else 0.0,
        p99=round(sum(s.p99 for s in with_counts) / len(with_counts), 2) if with_counts else 0.0,
        error_rate=round(failed / total * 100.0, 2) if total else 0.0,
        availability=round(ok / total * 100.0, 2) if total else 100.0,
        active=max((s.active for s in series), default=0),
        bytes_in=bytes_in,
        bytes_out=0,
        status_classes=statuses,
        error_kinds=errors,
        series=series,
    )


__all__ = ["AppController", "snapshot_from_series"]
