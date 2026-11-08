"""Proxy parsing / storage unit tests (no network access)."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from seaped.net.proxy import ProxyEntry, ProxyError, ProxyManager, _extract_ip


def test_parse_line():
    e = ProxyManager.parse_line("10.0.0.1:8080")
    assert (e.host, e.port, e.scheme) == ("10.0.0.1", 8080, "http")

    e = ProxyManager.parse_line("socks5://user:pass@host.example:1080")
    assert e.scheme == "socks5"
    assert e.username == "user" and e.password == "pass"
    assert e.url == "socks5://user:pass@host.example:1080"

    e = ProxyManager.parse_line("  # comment  ")
    assert e is None

    e = ProxyManager.parse_line("")
    assert e is None

    for bad in ("no-port", "host:99999", "host:abc"):
        try:
            ProxyManager.parse_line(bad)
            raise AssertionError(f"should reject {bad!r}")
        except ProxyError:
            pass


def test_crud_and_profiles():
    mgr = ProxyManager()
    saved = list(mgr.entries)
    try:
        mgr.clear()
        assert mgr.entries == []

        a = ProxyEntry(host="1.2.3.4", port=3128, profile="europe", label="eu-1")
        b = ProxyEntry(host="5.6.7.8", port=1080, scheme="socks5", profile="lab")
        assert mgr.add(a) is True
        assert mgr.add(b) is True
        assert mgr.add(ProxyEntry(host="1.2.3.4", port=3128)) is False  # duplicate

        assert mgr.get("1.2.3.4:3128") is not None
        assert set(mgr.profile_names()) == {"europe", "lab"}
        assert mgr.urls_for_profile("europe") == ["http://1.2.3.4:3128"]
        assert len(mgr.urls_for_profile("all")) == 2
        assert mgr.urls_for_profile("") == []  # no profile selected -> direct

        # disabled / offline proxies are excluded
        a.enabled = False
        assert mgr.urls_for_profile("europe") == []
        a.enabled = True
        a.status = "offline"
        assert mgr.urls_for_profile("europe") == []

        assert mgr.remove("1.2.3.4:3128") is True
        assert mgr.remove("1.2.3.4:3128") is False
        assert mgr.get("1.2.3.4:3128") is None

        # persistence round-trip
        mgr.save()
        mgr2 = ProxyManager()
        assert mgr2.get("5.6.7.8:1080") is not None
        assert mgr2.get("5.6.7.8:1080").scheme == "socks5"
    finally:
        # restore the operator's original list
        mgr.entries = saved
        mgr.save()


def test_import_text():
    mgr = ProxyManager()
    saved = list(mgr.entries)
    try:
        mgr.clear()
        text = """
# my proxies
10.0.0.1:8000
http://10.0.0.2:9000
bad-line
10.0.0.1:8000
"""
        added, errors = mgr.import_text(text, profile="imported")
        assert added == 2, (added, errors)
        assert len(errors) == 2  # bad-line + duplicate
        entry = mgr.get("10.0.0.1:8000")
        assert entry is not None and entry.profile == "imported"
    finally:
        mgr.entries = saved
        mgr.save()


def test_extract_ip():
    assert _extract_ip('{"origin": "203.0.113.7"}') == "203.0.113.7"
    assert _extract_ip('{"ip": "198.51.100.2"}') == "198.51.100.2"
    assert _extract_ip("hello 192.0.2.55 world") == "192.0.2.55"
    assert _extract_ip("no address here") == ""
    assert _extract_ip("not-an-ip 999.1.1.1") == ""


def test_entry_location_display():
    e = ProxyEntry(host="h", port=1, city="Berlin", region="BE", country="Germany")
    assert e.location == "Berlin, BE, Germany"
    e2 = ProxyEntry(host="h", port=1)
    assert e2.location == "—"
    assert "auth" not in ProxyEntry(host="h", port=1).display
    e3 = ProxyEntry(host="h", port=1, username="u", password="p")
    assert "(auth)" in e3.display
    # password must never appear in the URL used for checks? it does (aiohttp needs it)
    assert "p@" in e3.url


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
