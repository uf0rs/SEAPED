"""Unit tests for SEAPED core (run: python -m pytest tests/ -q  or  python tests/test_core.py)."""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from seaped.core.metrics import MetricsCollector, SeriesAggregator, percentile
from seaped.core.scenarios import SCENARIOS, ScenarioSpec, get_scenario, schedule_preview
from seaped.core.limits import SafetyLimits, LimitBreach
from seaped.core.config import TestConfig, RequestProfile, AuthorizationError
from seaped.i18n import set_language

set_language("en")  # assertions below match English messages


def test_percentile():
    data = sorted(float(i) for i in range(1, 101))
    assert percentile(data, 50) == 50.5
    assert percentile(data, 100) == 100
    assert percentile(data, 0) == 1
    assert percentile([], 95) == 0
    assert abs(percentile(data, 95) - 95.05) < 1e-6


def test_collector_records_and_snapshots():
    c = MetricsCollector(series_len=10, reservoir_size=1000)
    c.start()
    for i in range(100):
        c.record(latency_ms=10 + i, status=200, ok=True, bytes_in=100)
    for i in range(10):
        c.record(latency_ms=999, status=500, ok=False, error_kind="http_500")
    c.set_active(5)
    sample = c.tick(5)
    snap = c.snapshot()
    assert snap.total == 110
    assert snap.ok == 100
    assert snap.failed == 10
    assert abs(snap.availability - 100 * 100 / 110) < 0.01
    assert snap.status_classes["2xx"] == 100
    assert snap.status_classes["5xx"] == 10
    assert snap.error_kinds["http_500"] == 10
    assert sample.count == 110
    assert sample.errors == 10
    assert len(snap.series) == 1
    assert snap.p95 > 0


def test_collector_reset():
    c = MetricsCollector()
    c.start()
    c.record(5.0, 200, True)
    c.tick(1)
    c.reset()
    snap = c.snapshot()
    assert snap.total == 0 and snap.series == []


def test_scenarios_monotonic_and_bounded():
    spec = ScenarioSpec(start_vus=5, max_vus=100, duration=60, ramp_up=30)
    for sid, sc in SCENARIOS.items():
        for t in [0, 1, 5, 30, 59, 60, 120]:
            v = sc.target_vus(spec, t)
            assert 0 <= v <= spec.max_vus, f"{sid}@{t}={v}"
    ramp = get_scenario("ramp")
    values = [ramp.target_vus(spec, t) for t in range(0, 60, 5)]
    assert values == sorted(values), values
    assert ramp.target_vus(spec, 61) == 0


def test_schedule_preview_length():
    spec = ScenarioSpec()
    assert len(schedule_preview(spec, "spike", points=40)) == 40


def test_limits():
    lim = SafetyLimits(max_vus=10, max_duration=60, error_rate_stop=20,
                       latency_stop_ms=1000, consecutive_failures_stop=5,
                       error_rate_window=5)
    lim.validate()
    assert lim.check(10, 100, 0, 100, 0, 5) is None
    b = lim.check(61, 100, 0, 100, 0, 5)
    assert isinstance(b, LimitBreach) and "Duration" in b.reason
    assert isinstance(lim.check(10, 100, 25, 100, 0, 5), LimitBreach)
    assert isinstance(lim.check(10, 100, 0, 2000, 0, 5), LimitBreach)
    assert isinstance(lim.check(10, 100, 0, 100, 6, 5), LimitBreach)
    assert lim.check(2, 100, 50, 5000, 10, 5) is None  # warm-up window
    try:
        SafetyLimits(max_vus=0).validate()
        raise AssertionError("should raise")
    except ValueError:
        pass


def test_config_validation_and_auth():
    cfg = TestConfig(target="https://example.com", authorized=True)
    assert cfg.validate() == []
    assert cfg.request_url() == "https://example.com/"
    bad = TestConfig(target="ftp://x", authorized=True)
    assert any("http" in p for p in bad.validate())
    unauth = TestConfig(target="https://example.com")
    try:
        unauth.require_authorization()
        raise AssertionError("should raise")
    except AuthorizationError:
        pass
    cfg2 = TestConfig(target="example.com", authorized=True,
                      profile=RequestProfile(method="POST", body="{}", headers="Content-Type: application/json"))
    assert cfg2.validate() == []
    assert cfg2.request_url().startswith("http://example.com/")
    assert cfg2.profile.header_dict()["Content-Type"] == "application/json"


def test_config_roundtrip():
    cfg = TestConfig(name="roundtrip", target="https://a.b", authorized=True,
                     profile=RequestProfile(method="POST", think_time=1.5),
                     scenario_id="spike")
    data = cfg.to_dict()
    restored = TestConfig.from_dict(data)
    assert restored.name == "roundtrip"
    assert restored.profile.method == "POST"
    assert restored.scenario_id == "spike"
    assert restored.spec.max_vus == cfg.spec.max_vus


def test_series_aggregator():
    from seaped.core.metrics import IntervalSample
    agg = SeriesAggregator()
    agg.add(IntervalSample(ts=100.0, rps=10, ok=10, errors=0, p95=100, active=5))
    agg.add(IntervalSample(ts=100.0, rps=20, ok=18, errors=2, p95=200, active=7,
                           error_kinds={"timeout": 2}))
    samples = agg.samples()
    assert len(samples) == 1
    s = samples[0]
    assert s.rps == 30
    assert s.ok == 28 and s.errors == 2
    assert s.active == 12
    assert s.error_kinds["timeout"] == 2


def test_i18n_tables():
    import os as _os
    from seaped import i18n

    # both languages must cover exactly the same keys
    assert set(i18n.STRINGS["en"]) == set(i18n.STRINGS["ru"]), (
        set(i18n.STRINGS["en"]) ^ set(i18n.STRINGS["ru"])
    )
    # format placeholders must match between languages
    import re as _re
    for key, en in i18n.STRINGS["en"].items():
        ru = i18n.STRINGS["ru"][key]
        en_fields = set(_re.findall(r"\{(\w+)\}", en))
        ru_fields = set(_re.findall(r"\{(\w+)\}", ru))
        assert en_fields == ru_fields, f"{key}: {en_fields} != {ru_fields}"

    settings_existed = i18n.settings_path().exists()
    try:
        i18n.set_language("ru")
        assert i18n.tr("nav.dashboard") == "Главная"
        i18n.set_language("en")
        assert i18n.tr("nav.dashboard") == "Dashboard"
        # unknown key falls back to the key itself
        i18n.set_language("ru")
        assert i18n.tr("no.such.key") == "no.such.key"
        # non-interactive resolution never prompts
        assert i18n.ensure_language(ask=False) in i18n.LANGUAGES
        i18n.save_setting("lang", "en")
        assert i18n.ensure_language(ask=False) == "en"
        # engine-facing messages are localized
        i18n.set_language("ru")
        assert i18n.tr("stop.duration") == "Достигнут лимит длительности"
        i18n.set_language("en")
        assert i18n.tr("val.auth").startswith("Test not authorized")
    finally:
        if not settings_existed:
            try:
                i18n.settings_path().unlink()
            except OSError:
                pass
        i18n.set_language("en")


def main():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for fn in tests:
        try:
            fn()
            print(f"  PASS  {fn.__name__}")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            import traceback

            print(f"  FAIL  {fn.__name__}: {exc}")
            traceback.print_exc()
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
