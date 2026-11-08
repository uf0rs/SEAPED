"""Proxy management: storage, import, health checks and network profiles.

SEAPED only uses proxies that the operator adds explicitly. No public proxy
lists are fetched automatically.
"""

from __future__ import annotations

import asyncio
import ipaddress
import json
import re
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import aiohttp

from ..core.config import project_dir

PROXIES_FILE = "proxies.json"
REGION_LOOKUP_URL = "http://ip-api.com/json/{ip}?fields=status,country,countryCode,regionName,city,isp,org"

_PROXY_LINE = re.compile(
    r"^(?:(?P<scheme>https?|socks5|socks4)://)?"
    r"(?:(?P<user>[^:@\s]+):(?P<pw>[^@\s]+)@)?"
    r"(?P<host>[A-Za-z0-9.\-_]+):(?P<port>\d{1,5})$"
)


class ProxyError(Exception):
    pass


@dataclass
class ProxyEntry:
    host: str
    port: int
    scheme: str = "http"          # http | https | socks5 | socks4
    username: str = ""
    password: str = ""
    label: str = ""
    profile: str = "default"
    enabled: bool = True

    # check results
    status: str = "unchecked"      # unchecked | checking | online | offline | error
    latency_ms: float = 0.0
    exit_ip: str = ""
    country: str = ""
    region: str = ""
    city: str = ""
    isp: str = ""
    last_checked: float = 0.0
    message: str = ""

    @property
    def url(self) -> str:
        auth = f"{self.username}:{self.password}@" if self.username else ""
        return f"{self.scheme}://{auth}{self.host}:{self.port}"

    @property
    def display(self) -> str:
        auth = " (auth)" if self.username else ""
        return f"{self.scheme}://{self.host}:{self.port}{auth}"

    @property
    def location(self) -> str:
        parts = [p for p in (self.city, self.region, self.country) if p]
        return ", ".join(parts) if parts else "—"

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "ProxyEntry":
        known = {k: v for k, v in data.items() if k in cls.__dataclass_fields__}
        return cls(**known)


@dataclass
class ProxyProfile:
    name: str
    description: str = ""
    proxies: List[str] = field(default_factory=list)  # ids: host:port


class ProxyManager:
    """Owns the proxy list persisted in ``proxies.json``."""

    def __init__(self) -> None:
        self._path = project_dir() / PROXIES_FILE
        self.entries: List[ProxyEntry] = []
        self.load()

    # ------------------------- storage ------------------------- #
    @property
    def path(self) -> Path:
        return self._path

    def load(self) -> None:
        if not self._path.exists():
            self.entries = []
            return
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            self.entries = [ProxyEntry.from_dict(d) for d in data.get("proxies", [])]
        except Exception:
            self.entries = []

    def save(self) -> None:
        payload = {"proxies": [e.to_dict() for e in self.entries]}
        self._path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    # ------------------------- CRUD ---------------------------- #
    def _key(self, entry: ProxyEntry) -> str:
        return f"{entry.host}:{entry.port}"

    def add(self, entry: ProxyEntry) -> bool:
        if entry.port < 1 or entry.port > 65535:
            raise ProxyError("Port must be between 1 and 65535.")
        if not entry.host:
            raise ProxyError("Host is required.")
        if any(self._key(e) == self._key(entry) for e in self.entries):
            return False
        if not entry.label:
            entry.label = f"{entry.host}:{entry.port}"
        self.entries.append(entry)
        self.save()
        return True

    def remove(self, key: str) -> bool:
        before = len(self.entries)
        self.entries = [e for e in self.entries if self._key(e) != key]
        if len(self.entries) != before:
            self.save()
            return True
        return False

    def get(self, key: str) -> Optional[ProxyEntry]:
        for e in self.entries:
            if self._key(e) == key:
                return e
        return None

    def clear(self) -> None:
        self.entries = []
        self.save()

    # ------------------------- parsing ------------------------- #
    @staticmethod
    def parse_line(line: str) -> Optional[ProxyEntry]:
        line = line.strip()
        if not line or line.startswith("#"):
            return None
        m = _PROXY_LINE.match(line)
        if not m:
            raise ProxyError(f"Cannot parse proxy line: {line!r}")
        port = int(m.group("port"))
        if not 1 <= port <= 65535:
            raise ProxyError(f"Invalid port in: {line!r}")
        return ProxyEntry(
            host=m.group("host"),
            port=port,
            scheme=(m.group("scheme") or "http").lower(),
            username=m.group("user") or "",
            password=m.group("pw") or "",
        )

    def import_text(self, text: str, profile: str = "default") -> Tuple[int, List[str]]:
        """Import a block of text; returns (added, errors)."""
        added, errors = 0, []
        for raw in text.splitlines():
            try:
                entry = self.parse_line(raw)
                if entry is None:
                    continue
                entry.profile = profile
                if self.add(entry):
                    added += 1
                else:
                    errors.append(f"duplicate: {raw.strip()}")
            except ProxyError as exc:
                errors.append(str(exc))
        return added, errors

    def import_file(self, path: Path, profile: str = "default") -> Tuple[int, List[str]]:
        try:
            text = Path(path).read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            raise ProxyError(f"Cannot read file: {exc}") from exc
        return self.import_text(text, profile=profile)

    # ------------------------- checks -------------------------- #
    def urls_for_profile(self, profile: str) -> List[str]:
        """Proxy URLs of a profile; an empty profile means a direct connection."""
        if not profile:
            return []
        out = []
        for e in self.entries:
            if not e.enabled or e.status == "offline":
                continue
            if profile != "all" and e.profile != profile:
                continue
            out.append(e.url)
        return out

    def profile_names(self) -> List[str]:
        names = sorted({e.profile for e in self.entries if e.profile})
        return names

    async def check_one(
        self,
        entry: ProxyEntry,
        check_url: str = "http://httpbin.org/ip",
        timeout: float = 10.0,
        lookup_region: bool = False,
        session: Optional[aiohttp.ClientSession] = None,
    ) -> ProxyEntry:
        entry.status = "checking"
        own_session = session is None
        if own_session:
            session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout))
        started = time.perf_counter()
        try:
            kwargs = {}
            if entry.scheme.startswith("socks"):
                if SocksProxyConnector is None:
                    entry.status = "error"
                    entry.message = "SOCKS support requires 'aiohttp-socks'"
                    return entry
                kwargs["proxy"] = entry.url
            else:
                kwargs["proxy"] = entry.url
                if entry.username:
                    kwargs["proxy_auth"] = aiohttp.BasicLogin(entry.username, entry.password)
            async with session.get(check_url, allow_redirects=True, **kwargs) as resp:
                body = await resp.text()
                entry.latency_ms = round((time.perf_counter() - started) * 1000, 1)
                if resp.status >= 400:
                    entry.status = "offline"
                    entry.message = f"HTTP {resp.status}"
                    return entry
                entry.status = "online"
                entry.message = "OK"
                ip = _extract_ip(body)
                if ip:
                    entry.exit_ip = ip
        except asyncio.TimeoutError:
            entry.status = "offline"
            entry.message = "timeout"
        except aiohttp.ClientProxyConnectionError:
            entry.status = "offline"
            entry.message = "proxy unreachable"
        except aiohttp.ClientConnectorCertificateError:
            entry.status = "error"
            entry.message = "TLS certificate error"
        except aiohttp.ClientError as exc:
            entry.status = "offline"
            entry.message = str(exc)[:120]
        except Exception as exc:  # noqa: BLE001
            entry.status = "error"
            entry.message = str(exc)[:120]
        finally:
            entry.last_checked = time.time()
            if own_session:
                await session.close()

        if entry.status == "online" and lookup_region and entry.exit_ip:
            await self._lookup_region(entry, timeout=6.0)
        return entry

    async def _lookup_region(self, entry: ProxyEntry, timeout: float = 6.0) -> None:
        url = REGION_LOOKUP_URL.format(ip=entry.exit_ip)
        try:
            async with aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=timeout)
            ) as session:
                async with session.get(url) as resp:
                    if resp.status != 200:
                        return
                    data = await resp.json(content_type=None)
                    if data.get("status") == "success":
                        entry.country = data.get("country", "")
                        entry.region = data.get("regionName", "")
                        entry.city = data.get("city", "")
                        entry.isp = data.get("isp", "") or data.get("org", "")
                    else:
                        entry.message = "region lookup failed"
        except Exception:
            entry.message = "region lookup unavailable"

    async def check_all(
        self,
        check_url: str = "http://httpbin.org/ip",
        concurrency: int = 20,
        timeout: float = 10.0,
        lookup_region: bool = False,
        on_progress=None,
    ) -> List[ProxyEntry]:
        semaphore = asyncio.Semaphore(max(1, concurrency))
        async with aiohttp.ClientSession() as session:

            async def worker(entry: ProxyEntry) -> None:
                async with semaphore:
                    await self.check_one(
                        entry,
                        check_url=check_url,
                        timeout=timeout,
                        lookup_region=lookup_region,
                        session=session,
                    )
                    if on_progress:
                        try:
                            on_progress(entry)
                        except Exception:
                            pass

            await asyncio.gather(*(worker(e) for e in self.entries if e.enabled))
        self.save()
        return list(self.entries)


def _extract_ip(body: str) -> str:
    body = body.strip()
    try:
        data = json.loads(body)
        for key in ("origin", "ip", "query"):
            if key in data:
                value = str(data[key]).split(",")[0].strip()
                _ipaddress(value)
                return value
    except Exception:
        pass
    for token in re.findall(r"\b(?:\d{1,3}\.){3}\d{1,3}\b", body):
        try:
            _ipaddress(token)
            return token
        except Exception:
            continue
    return ""


def _ipaddress(value: str) -> None:
    ipaddress.ip_address(value)


try:
    from aiohttp_socks import ProxyConnector as SocksProxyConnector  # type: ignore

    SOCKS_AVAILABLE = True
except Exception:  # pragma: no cover
    SocksProxyConnector = None  # type: ignore
    SOCKS_AVAILABLE = False
