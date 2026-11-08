"""Built-in self test.

Used both in development (``python -m seaped --smoke``) and to verify a
packaged build (``SEAPED.exe --smoke``) — it exercises the critical subsystems
without any network access.
"""

from __future__ import annotations

import asyncio
import sys
import traceback


def _check(results, name: str, fn) -> None:
    try:
        fn()
    except Exception as exc:  # noqa: BLE001
        results.append((name, False, str(exc)))
        traceback.print_exc()
    else:
        results.append((name, True, ""))


# --------------------------- subsystem checks --------------------------- #

def _metrics() -> None:
    from seaped.core.metrics import MetricsCollector, percentile

    data = sorted(float(i) for i in range(1, 101))
    assert abs(percentile(data, 95) - 95.05) < 1e-6
    c = MetricsCollector()
    c.start()
    for i in range(200):
        c.record(10 + i, status=200, ok=True, bytes_in=10)
    for _ in range(10):
        c.record(999, status=500, ok=False, error_kind="http_500")
    sample = c.tick(4)
    snap = c.snapshot()
    assert snap.total == 210 and snap.ok == 200 and snap.failed == 10
    assert sample.count == 210
    assert snap.availability > 95.0


def _scenarios() -> None:
    from seaped.core.scenarios import SCENARIOS, ScenarioSpec, schedule_preview

    spec = ScenarioSpec(start_vus=5, max_vus=100, duration=60, ramp_up=20)
    for sid, sc in SCENARIOS.items():
        for t in (0, 10, 30, 59, 61):
            value = sc.target_vus(spec, t)
            assert 0 <= value <= spec.max_vus, f"{sid}@{t}"
    assert len(schedule_preview(spec, "ramp", points=40)) == 40


def _config_and_limits() -> None:
    from seaped.core.config import AuthorizationError, RequestProfile, TestConfig
    from seaped.core.limits import SafetyLimits, LimitBreach

    cfg = TestConfig(target="https://example.com", authorized=True)
    assert cfg.validate() == []
    unauth = TestConfig(target="https://example.com")
    try:
        unauth.require_authorization()
        raise AssertionError("authorization gate missing")
    except AuthorizationError:
        pass
    bad = TestConfig(target="ftp://x", authorized=True)
    assert bad.validate(), "non-http target must be rejected"

    lim = SafetyLimits(max_vus=10, max_duration=60, error_rate_stop=20,
                       latency_stop_ms=1000, consecutive_failures_stop=5,
                       error_rate_window=5)
    lim.validate()
    assert lim.check(10, 100, 0, 100, 0, 5) is None
    assert isinstance(lim.check(61, 100, 0, 100, 0, 5), LimitBreach)
    assert isinstance(lim.check(10, 100, 50, 100, 0, 5), LimitBreach)

    profile = RequestProfile(method="POST", headers="X-Test: 1\n# comment", body="{}")
    assert profile.header_dict() == {"X-Test": "1"}


def _proxy_layer() -> None:
    from seaped.net.proxy import ProxyEntry, ProxyManager, _extract_ip

    entry = ProxyManager.parse_line("socks5://u:p@host:1080")
    assert entry.scheme == "socks5" and entry.username == "u"
    assert ProxyManager.parse_line("# comment") is None
    assert _extract_ip('{"origin": "203.0.113.9"}') == "203.0.113.9"
    e = ProxyEntry(host="h", port=8080, city="Berlin", country="DE")
    assert e.location == "Berlin, DE"


def _crypto() -> None:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    from seaped.dist.protocol import auth_signature, derive_key

    token = "self-test-token"
    client_nonce, server_nonce = b"c" * 16, b"s" * 16
    key = derive_key(token, client_nonce, server_nonce)
    assert key == derive_key(token, client_nonce, server_nonce)
    assert key != derive_key(token + "x", client_nonce, server_nonce)

    sig = auth_signature(token, "agent-1", client_nonce)
    assert sig == auth_signature(token, "agent-1", client_nonce)
    assert sig != auth_signature("other-token", "agent-1", client_nonce)

    cipher = AESGCM(key)
    nonce = b"\xC1" + (1).to_bytes(11, "big")
    blob = cipher.encrypt(nonce, b'{"t":"ping"}', None)
    assert cipher.decrypt(nonce, blob, None) == b'{"t":"ping"}'


def _reports() -> None:
    from seaped.core.config import TestConfig
    from seaped.core.metrics import MetricsSnapshot
    from seaped.core.result import build_result, export_csv, export_html

    cfg = TestConfig(name="self-test", target="https://example.com", authorized=True)
    snap = MetricsSnapshot(elapsed=5.0, total=100, ok=99, failed=1, rps=20.0,
                           availability=99.0, error_rate=1.0, p95=120.0)
    result = build_result(cfg, snap, "Duration limit reached")
    assert result.summary["total"] == 100
    html_path = export_html(result)
    csv_path = export_csv(result)
    assert html_path.exists() and csv_path.exists()
    assert "SEAPED" in html_path.read_text(encoding="utf-8")


# --------------------------- UI check --------------------------- #

async def _ui_navigation() -> None:
    from seaped.ui.app import SeapedApp

    app = SeapedApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause(0.5)
        for key in ("configure", "results", "proxies", "agents", "manual",
                    "about", "dashboard"):
            await pilot.click(f"#nav-{key}")
            await pilot.pause(0.3)
            assert app.sections[key].display, f"section {key} did not open"
        assert app.query_one("#chart-rps") is not None
        assert app.query_one("#tile-state") is not None


def _ui() -> None:
    asyncio.run(_ui_navigation())


# --------------------------- entry point --------------------------- #

def run_selftest() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    from seaped import __version__

    print(f"SEAPED v{__version__} — self test")
    print("-" * 52)
    results = []
    checks = [
        ("metrics engine", _metrics),
        ("load scenarios", _scenarios),
        ("config & safety limits", _config_and_limits),
        ("proxy layer", _proxy_layer),
        ("crypto (AES-GCM/HKDF)", _crypto),
        ("report export", _reports),
        ("interface (headless)", _ui),
    ]
    for name, fn in checks:
        _check(results, name, fn)
        status, ok, detail = results[-1]
        mark = "OK  " if ok else "FAIL"
        print(f" [{mark}] {name}" + (f"  — {detail}" if not ok else ""))

    failed = [r for r in results if not r[1]]
    print("-" * 52)
    if failed:
        print(f"{len(failed)} of {len(results)} checks FAILED")
        return 1
    print(f"all {len(results)} checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(run_selftest())
