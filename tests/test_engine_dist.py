"""Engine + distributed subsystem integration tests (loopback only)."""

import asyncio
import os
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from aiohttp import web

from seaped.core.config import RequestProfile, TestConfig
from seaped.core.engine import EngineState, LoadEngine
from seaped.core.limits import SafetyLimits
from seaped.core.scenarios import ScenarioSpec
from seaped.dist.coordinator import Coordinator
from seaped.dist.agent import AgentNode
from seaped.i18n import set_language

set_language("en")  # assertions below match English messages


class LocalServer:
    """aiohttp server running on its own thread + event loop."""

    def __init__(self):
        self.loop = None
        self.runner = None
        self.port = None
        self.thread = None

    async def _setup(self, ready):
        async def handler(request):
            if request.path == "/slow":
                await asyncio.sleep(0.4)
                return web.Response(text="slow")
            if request.path == "/error":
                return web.Response(status=503, text="unavailable")
            return web.Response(text="ok", headers={"X-Test": "seaped"})

        app = web.Application()
        app.router.add_route("*", "/{tail:.*}", handler)
        self.runner = web.AppRunner(app)
        await self.runner.setup()
        await web.TCPSite(self.runner, "127.0.0.1", 0).start()
        self.port = self.runner.addresses[0][1]
        ready.set()

    def start(self):
        ready = threading.Event()

        def run():
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)
            self.loop.run_until_complete(self._setup(ready))
            self.loop.run_forever()

        self.thread = threading.Thread(target=run, name="test-server", daemon=True)
        self.thread.start()
        if not ready.wait(10):
            raise RuntimeError("local server failed to start")
        return self.port

    def stop(self):
        if self.loop and self.runner:
            try:
                asyncio.run_coroutine_threadsafe(self.runner.cleanup(), self.loop).result(5)
            except Exception:
                pass
            self.loop.call_soon_threadsafe(self.loop.stop)
            self.thread.join(5)
            self.loop.close()


def free_limits(**kw):
    base = dict(
        max_vus=20,
        max_duration=60,
        max_rps=5000,
        error_rate_stop=95.0,
        latency_stop_ms=0,
        consecutive_failures_stop=10 ** 9,
        error_rate_window=10 ** 9,
    )
    base.update(kw)
    return SafetyLimits(**base)


def make_config(port, **spec_kw):
    spec = dict(start_vus=2, max_vus=5, duration=4, ramp_up=1, ramp_down=1)
    spec.update(spec_kw)
    return TestConfig(
        name="itest",
        target=f"http://127.0.0.1:{port}",
        profile=RequestProfile(method="GET", path="/", timeout=5),
        scenario_id="constant",
        spec=ScenarioSpec(**spec),
        limits=free_limits(),
        authorized=True,
    )


def test_engine_runs_against_local_server():
    server = LocalServer()
    try:
        port = server.start()
        engine = LoadEngine(make_config(port))
        engine.start()
        assert engine.join(30), "engine did not finish in time"
        snap = engine.collector.snapshot()
        assert engine.state == EngineState.FINISHED, engine.state
        assert snap.total > 50, f"only {snap.total} requests"
        assert snap.ok == snap.total, f"failures: {snap.error_kinds}"
        assert snap.availability == 100.0
        assert snap.rps > 5
        assert len(snap.series) >= 4, len(snap.series)
        assert engine.stop_reason
        assert snap.bytes_in > 0
    finally:
        server.stop()


def test_engine_respects_rate_limit():
    server = LocalServer()
    try:
        port = server.start()
        cfg = make_config(port, duration=6)
        cfg.limits = free_limits(max_rps=60, max_duration=30)
        engine = LoadEngine(cfg)
        engine.start()
        assert engine.join(30)
        snap = engine.collector.snapshot()
        assert snap.total > 20
        # token bucket must keep the average well below a free-running rate
        avg = snap.total / max(0.1, snap.elapsed)
        assert avg <= 150, f"rate limit not enforced: {avg:.0f} req/s"
    finally:
        server.stop()


def test_engine_detects_errors_and_stops():
    server = LocalServer()
    try:
        port = server.start()
        cfg = make_config(port, duration=60)
        cfg.profile.path = "/error"
        cfg.profile.expect_status = 200
        cfg.limits = free_limits(
            error_rate_stop=50.0, error_rate_window=1.0,
            consecutive_failures_stop=25, max_duration=60,
        )
        engine = LoadEngine(cfg)
        engine.start()
        assert engine.join(40)
        snap = engine.collector.snapshot()
        assert snap.failed > 0
        assert engine.breach is not None, "expected an automatic stop"
        assert "Error rate" in engine.breach.reason or "Consecutive" in engine.breach.reason
        assert engine.breach.detail
    finally:
        server.stop()


def test_engine_manual_stop():
    server = LocalServer()
    try:
        port = server.start()
        cfg = make_config(port, duration=300)
        engine = LoadEngine(cfg)
        engine.start()
        time.sleep(3)
        engine.stop("manual")
        assert engine.join(20)
        assert engine.state == EngineState.FINISHED
        assert "manual" in engine.stop_reason
        snap = engine.collector.snapshot()
        assert snap.total > 5
    finally:
        server.stop()


def test_engine_refuses_unauthorized():
    cfg = make_config(80)
    cfg.authorized = False
    try:
        LoadEngine(cfg)
        raise AssertionError("should refuse unauthorized config")
    except Exception as exc:
        assert "authorized" in str(exc).lower()


def test_distributed_full_cycle():
    server = LocalServer()
    port = server.start()
    coord = None
    agent = None
    observer = None
    bad = None
    try:
        coord = Coordinator(token="unit-test-token", host="127.0.0.1", port=0)
        coord.start()
        assert coord.listening, coord.last_error

        # wrong token must be rejected
        bad = AgentNode("127.0.0.1", coord.port, "wrong-token-abc", name="bad",
                        consent=True, reconnect=False)
        bad.start()
        time.sleep(2.0)
        assert not bad.connected, "bad token was accepted"
        bad.stop()

        agent = AgentNode(
            "127.0.0.1", coord.port, "unit-test-token", name="worker-1", consent=True,
            limits=free_limits(max_vus=4, max_duration=30, max_rps=500),
            reconnect=False,
        )
        agent.start()
        deadline = time.time() + 8
        while time.time() < deadline and not coord.agents():
            time.sleep(0.1)
        agents = coord.agents()
        assert len(agents) == 1, f"agents={agents}"
        rec = agents[0]
        assert rec.name == "worker-1"
        assert rec.consent is True
        assert rec.max_vus == 4
        assert rec.state == "idle"

        # observer (no consent) must not be targeted
        observer = AgentNode("127.0.0.1", coord.port, "unit-test-token", name="watcher",
                             consent=False, reconnect=False)
        observer.start()
        time.sleep(2.0)
        assert coord.send_spec(make_config(port).to_dict(), agent_ids=[observer.id]) == 0

        # dispatch to the consenting agent
        cfg = make_config(port, duration=4)
        cfg.name = "distributed-run"
        assert coord.send_spec(cfg.to_dict()) == 1

        deadline = time.time() + 30
        samples = []
        events = []
        while time.time() < deadline:
            events.extend(coord.drain_events())
            samples = coord.series()
            if len(samples) >= 3:
                break
            time.sleep(0.5)
        if len(samples) < 3:
            diag = "; ".join(
                f"{e.get('type')}:{str(e.get('message'))[:80]}" for e in events[-8:]
            )
            raise AssertionError(
                f"aggregated samples={len(samples)} agent_state={agent.state} "
                f"agent_connected={agent.connected} err={agent.last_error} events=[{diag}]"
            )
        assert sum(s.ok for s in samples) > 0, "no successful remote requests"

        # stop + kick
        assert coord.stop_test() >= 1
        time.sleep(1.0)
        assert coord.kick(agent.id) is True
        time.sleep(1.5)
        assert agent.kicked, "agent did not honour kick"
    finally:
        for node in (agent, observer, bad):
            if node:
                node.stop()
        if coord:
            coord.stop()
        server.stop()


def main():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    if len(sys.argv) > 1:
        tests = [t for t in tests if sys.argv[1] in t.__name__]
    failed = 0
    for fn in tests:
        try:
            fn()
            print(f"  PASS  {fn.__name__}", flush=True)
        except Exception as exc:  # noqa: BLE001
            failed += 1
            import traceback

            print(f"  FAIL  {fn.__name__}: {exc}", flush=True)
            traceback.print_exc()
    print(f"\n{len(tests) - failed}/{len(tests)} passed", flush=True)
    return 1 if failed else 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    raise SystemExit(main())
