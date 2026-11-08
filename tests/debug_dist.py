import asyncio, sys, time, os, threading, asyncio
sys.stdout.reconfigure(encoding="utf-8", errors="replace") if hasattr(sys.stdout, "reconfigure") else None
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from aiohttp import web
from seaped.core.config import TestConfig, RequestProfile
from seaped.core.scenarios import ScenarioSpec
from seaped.core.limits import SafetyLimits
from seaped.dist.coordinator import Coordinator
from seaped.dist.agent import AgentNode

class Server:
    def __init__(self):
        self.loop = None; self.runner = None; self.port = None; self.thread = None
    async def _setup(self, ready):
        app = web.Application()
        async def h(r): return web.Response(text="ok")
        app.router.add_route("*", "/{t:.*}", h)
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
        self.thread = threading.Thread(target=run, daemon=True)
        self.thread.start()
        ready.wait(5)
        return self.port
    def stop(self):
        if self.loop:
            asyncio.run_coroutine_threadsafe(self.runner.cleanup(), self.loop)
            time.sleep(0.3)
            self.loop.call_soon_threadsafe(self.loop.stop)
            self.thread.join(3)

srv = Server()
port = srv.start()
print("target port", port)

def cfg():
    return TestConfig(
        name="dist-dbg", target=f"http://127.0.0.1:{port}",
        profile=RequestProfile(timeout=5),
        scenario_id="constant",
        spec=ScenarioSpec(start_vus=2, max_vus=4, duration=5, ramp_up=1),
        limits=SafetyLimits(max_vus=20, max_duration=60, max_rps=5000,
                            error_rate_stop=95, latency_stop_ms=0,
                            consecutive_failures_stop=10**9, error_rate_window=10**9),
        authorized=True,
    )

coord = Coordinator(token="dbg-token-123", host="127.0.0.1", port=0)
coord.start()
print("coordinator port", coord.port, "listening", coord.listening, "err", coord.last_error)

agent = AgentNode("127.0.0.1", coord.port, "dbg-token-123", name="w1", consent=True,
                  limits=SafetyLimits(max_vus=4, max_duration=30, max_rps=500,
                                      error_rate_stop=95, latency_stop_ms=0,
                                      consecutive_failures_stop=10**9, error_rate_window=10**9),
                  reconnect=False,
                  on_log=lambda lv, m: print(f"   AGENT[{lv}] {m}"))
agent.start()

t0 = time.time()
while time.time() - t0 < 6 and not coord.agents():
    time.sleep(0.1)
print("agents:", [(a.name, a.state, a.consent, a.max_vus) for a in coord.agents()])

n = coord.send_spec(cfg().to_dict())
print("send_spec ->", n)

t0 = time.time()
while time.time() - t0 < 16:
    for e in coord.drain_events():
        print("   EVENT", e.get("type"), "|", str(e.get("message"))[:160])
    time.sleep(0.5)

samples = coord.series()
print("samples:", len(samples), "peak", coord.aggregator.peak_rps)
for s in samples[:6]:
    print(f"   rps={s.rps} ok={s.ok} err={s.errors} active={s.active} p95={s.p95}")
print("agent state:", agent.state, "connected", agent.connected, "last_err", agent.last_error)
agent.stop(); coord.stop(); srv.stop()
