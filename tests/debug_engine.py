import asyncio, sys, time, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from aiohttp import web
from seaped.core.config import TestConfig, RequestProfile
from seaped.core.engine import LoadEngine
from seaped.core.limits import SafetyLimits
from seaped.core.scenarios import ScenarioSpec

async def h(request):
    return web.Response(text="ok")

async def start():
    app = web.Application(); app.router.add_route("*", "/{t:.*}", h)
    r = web.AppRunner(app); await r.setup()
    await web.TCPSite(r, "127.0.0.1", 0).start()
    return r, r.addresses[0][1]

def main():
    loop = asyncio.new_event_loop()
    runner, port = loop.run_until_complete(start())
    print("server port", port)
    cfg = TestConfig(
        name="dbg", target=f"http://127.0.0.1:{port}",
        profile=RequestProfile(timeout=5),
        scenario_id="constant",
        spec=ScenarioSpec(start_vus=2, max_vus=5, duration=4, ramp_up=1),
        limits=SafetyLimits(max_vus=20, max_duration=60, max_rps=5000,
                            error_rate_stop=95, latency_stop_ms=0,
                            consecutive_failures_stop=10**9, error_rate_window=10**9),
        authorized=True,
    )
    def ev(e):
        if e.kind != "sample":
            print(f"  [{e.kind}] {e.message} {e.data if e.kind in ('error','limit') else ''}")
    eng = LoadEngine(cfg, on_event=ev)
    eng.start(); eng.join(30)
    snap = eng.collector.snapshot()
    print("state", eng.state, "total", snap.total, "ok", snap.ok, "failed", snap.failed,
          "rps", snap.rps, "series", len(snap.series), "reason", eng.stop_reason)
    if snap.error_kinds: print("errors", snap.error_kinds)
    for s in snap.series[:8]:
        print(f"   sample rps={s.rps} ok={s.ok} err={s.errors} active={s.active} p95={s.p95}")
    loop.run_until_complete(runner.cleanup()); loop.close()

main()
