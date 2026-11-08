"""Test configuration objects and preset storage."""

from __future__ import annotations

import json
import re
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import urlparse

from .limits import SafetyLimits
from .scenarios import ScenarioSpec

PRESETS_DIR_NAME = "presets"


class AuthorizationError(Exception):
    """Raised when a test is started without explicit authorization."""


def project_dir() -> Path:
    """Project root: the folder containing the package — or, in a packaged
    build (``SEAPED.exe``), the folder containing the executable."""
    if getattr(sys, "frozen", False):  # PyInstaller
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


def presets_dir() -> Path:
    path = project_dir() / PRESETS_DIR_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


@dataclass
class RequestProfile:
    """What a virtual user sends to the target."""

    method: str = "GET"
    path: str = "/"
    headers: str = ""          # raw text: one "Name: value" per line
    body: str = ""
    timeout: float = 10.0
    follow_redirects: bool = True
    verify_ssl: bool = True
    think_time: float = 0.0    # pause between requests inside one VU
    expect_status: int = 200   # 0 = any 2xx/3xx counts as success

    def header_dict(self) -> Dict[str, str]:
        out: Dict[str, str] = {}
        for line in self.headers.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if ":" in line:
                name, value = line.split(":", 1)
                out[name.strip()] = value.strip()
        return out


@dataclass
class TestConfig:
    """Complete description of one load test."""

    name: str = "Untitled test"
    target: str = ""
    profile: RequestProfile = field(default_factory=RequestProfile)
    scenario_id: str = "constant"
    spec: ScenarioSpec = field(default_factory=ScenarioSpec)
    limits: SafetyLimits = field(default_factory=SafetyLimits)
    proxy_profile: str = ""        # name of proxy profile, "" = direct connection
    authorized: bool = False       # explicit owner confirmation
    remember: bool = True
    created_at: float = field(default_factory=time.time)

    # ---------------- validation ---------------- #
    def validate(self) -> List[str]:
        from ..i18n import tr

        problems: List[str] = []
        if not self.target.strip():
            problems.append(tr("val.target_required"))
        else:
            url = self.target.strip()
            parsed = urlparse(url if "://" in url else "http://" + url)
            if parsed.scheme not in ("http", "https"):
                problems.append(tr("val.only_http"))
            if not parsed.hostname:
                problems.append(tr("val.host_invalid"))
            if parsed.username:
                problems.append(tr("val.no_credentials"))
        method = self.profile.method.upper()
        if method not in ("GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"):
            problems.append(tr("val.method", value=method))
        if self.profile.timeout <= 0 or self.profile.timeout > 300:
            problems.append(tr("val.timeout"))
        if self.profile.think_time < 0 or self.profile.think_time > 60:
            problems.append(tr("val.think"))
        if self.spec.duration < 1:
            problems.append(tr("val.duration_min"))
        if self.spec.max_vus < 1:
            problems.append(tr("val.vus_min"))
        if self.spec.max_vus < self.spec.start_vus:
            problems.append(tr("val.start_vus"))
        try:
            self.limits.validate()
        except ValueError as exc:
            problems.append(tr("val.limits", error=str(exc)))
        return problems

    def require_authorization(self) -> None:
        from ..i18n import tr

        if not self.authorized:
            raise AuthorizationError(tr("val.auth"))

    def normalized_target(self) -> str:
        url = self.target.strip()
        if "://" not in url:
            url = "http://" + url
        return url

    def request_url(self) -> str:
        base = self.normalized_target().rstrip("/")
        path = self.profile.path
        if not path:
            path = "/"
        if not path.startswith("/") and not path.startswith("?"):
            path = "/" + path
        return base + path

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "TestConfig":
        profile = RequestProfile(**data.get("profile", {}))
        spec = ScenarioSpec(**{k: v for k, v in data.get("spec", {}).items()
                               if k in ScenarioSpec.__dataclass_fields__})
        limits = SafetyLimits(**{k: v for k, v in data.get("limits", {}).items()
                                 if k in SafetyLimits.__dataclass_fields__})
        known = {k: v for k, v in data.items()
                 if k in cls.__dataclass_fields__ and k not in ("profile", "spec", "limits")}
        cfg = cls(profile=profile, spec=spec, limits=limits, **known)
        return cfg


# ----------------------------- presets ----------------------------- #

_SAFE_NAME = re.compile(r"[^A-Za-z0-9_\-. ]+")


def _preset_path(name: str) -> Path:
    safe = _SAFE_NAME.sub("_", name).strip() or "preset"
    return presets_dir() / f"{safe}.json"


def save_preset(config: TestConfig, name: Optional[str] = None) -> Path:
    preset_name = (name or config.name or "preset").strip()
    config.name = preset_name
    path = _preset_path(preset_name)
    path.write_text(json.dumps(config.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def load_preset(name: str) -> TestConfig:
    path = _preset_path(name)
    if not path.exists():
        raise FileNotFoundError(f"Preset not found: {name}")
    data = json.loads(path.read_text(encoding="utf-8"))
    return TestConfig.from_dict(data)


def list_presets() -> List[str]:
    return sorted(p.stem for p in presets_dir().glob("*.json"))


def delete_preset(name: str) -> bool:
    path = _preset_path(name)
    if path.exists():
        path.unlink()
        return True
    return False
