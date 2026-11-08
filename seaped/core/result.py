"""Test result persistence and report generation (JSON / CSV / HTML)."""

from __future__ import annotations

import csv
import html
import json
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from .config import TestConfig, project_dir
from .metrics import IntervalSample, MetricsSnapshot

RESULTS_DIR_NAME = "results"


def results_dir() -> Path:
    path = project_dir() / RESULTS_DIR_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


@dataclass
class TestResult:
    id: str
    name: str
    target: str
    scenario: str
    started_at: float
    finished_at: float
    stop_reason: str
    authorized: bool
    config: dict
    summary: dict
    series: List[dict] = field(default_factory=list)
    agents: List[dict] = field(default_factory=list)
    app_version: str = "2.0.0"

    @property
    def duration(self) -> float:
        return max(0.0, self.finished_at - self.started_at)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "target": self.target,
            "scenario": self.scenario,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "stop_reason": self.stop_reason,
            "authorized": self.authorized,
            "config": self.config,
            "summary": self.summary,
            "series": self.series,
            "agents": self.agents,
            "app_version": self.app_version,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "TestResult":
        known = {k: v for k, v in data.items() if k in cls.__dataclass_fields__}
        return cls(**known)


def _series_to_dicts(series: List[IntervalSample]) -> List[dict]:
    return [
        {
            "ts": s.ts,
            "rps": s.rps,
            "ok": s.ok,
            "errors": s.errors,
            "p50": s.p50,
            "p75": s.p75,
            "p90": s.p90,
            "p95": s.p95,
            "p99": s.p99,
            "avg": s.avg,
            "max": s.max_lat,
            "active": s.active,
            "err_rate": s.err_rate,
            "bps": s.bytes_per_s,
        }
        for s in series
    ]


def build_result(
    config: TestConfig,
    snapshot: MetricsSnapshot,
    stop_reason: str,
    agents: Optional[List[dict]] = None,
    started_at: Optional[float] = None,
) -> TestResult:
    now = time.time()
    summary = {
        "elapsed": round(snapshot.elapsed, 2),
        "total": snapshot.total,
        "ok": snapshot.ok,
        "failed": snapshot.failed,
        "rps": snapshot.rps,
        "peak_rps": snapshot.peak_rps,
        "avg_latency": snapshot.avg_latency,
        "min_latency": snapshot.min_latency,
        "max_latency": snapshot.max_latency,
        "p50": snapshot.p50,
        "p75": snapshot.p75,
        "p90": snapshot.p90,
        "p95": snapshot.p95,
        "p99": snapshot.p99,
        "error_rate": snapshot.error_rate,
        "availability": snapshot.availability,
        "bytes_in": snapshot.bytes_in,
        "bytes_out": snapshot.bytes_out,
        "status_classes": snapshot.status_classes,
        "error_kinds": snapshot.error_kinds,
        "max_vus": config.spec.max_vus,
        "scenario": config.scenario_id,
        "target": config.request_url(),
    }
    return TestResult(
        id=time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6],
        name=config.name,
        target=config.request_url(),
        scenario=config.scenario_id,
        started_at=started_at or (now - snapshot.elapsed),
        finished_at=now,
        stop_reason=stop_reason,
        authorized=config.authorized,
        config=config.to_dict(),
        summary=summary,
        series=_series_to_dicts(snapshot.series),
        agents=agents or [],
    )


def save_result(result: TestResult) -> Path:
    path = results_dir() / f"{result.id}.json"
    path.write_text(json.dumps(result.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def load_result(result_id: str) -> TestResult:
    path = results_dir() / f"{result_id}.json"
    if not path.exists():
        # allow passing a bare filename or stem
        matches = list(results_dir().glob(f"*{result_id}*.json"))
        if not matches:
            raise FileNotFoundError(f"Result not found: {result_id}")
        path = matches[0]
    data = json.loads(path.read_text(encoding="utf-8"))
    return TestResult.from_dict(data)


def list_results() -> List[TestResult]:
    out: List[TestResult] = []
    for path in sorted(results_dir().glob("*.json"), reverse=True):
        try:
            out.append(TestResult.from_dict(json.loads(path.read_text(encoding="utf-8"))))
        except Exception:
            continue
    out.sort(key=lambda r: r.started_at, reverse=True)
    return out


def delete_result(result_id: str) -> bool:
    path = results_dir() / f"{result_id}.json"
    if path.exists():
        path.unlink()
        return True
    return False


# ------------------------------- exports ------------------------------- #

def export_csv(result: TestResult, path: Optional[Path] = None) -> Path:
    path = path or (results_dir() / f"{result.id}.csv")
    fields = ["ts", "rps", "ok", "errors", "p50", "p95", "p99", "avg", "max", "active", "err_rate", "bps"]
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        for row in result.series:
            writer.writerow({k: row.get(k, "") for k in fields})
    return path


def _svg_chart(series: List[dict], width: int = 960, height: int = 260) -> str:
    if not series:
        return "<p>No samples recorded.</p>"
    pad_l, pad_r, pad_t, pad_b = 52, 52, 18, 30
    w = width - pad_l - pad_r
    h = height - pad_t - pad_b
    rps = [s.get("rps", 0) for s in series]
    lat = [s.get("p95", 0) for s in series]
    max_rps = max(rps) or 1
    max_lat = max(lat) or 1
    n = len(series)

    def x(i: float) -> float:
        return pad_l + (w * i / max(1, n - 1))

    def y_rps(v: float) -> float:
        return pad_t + h - (h * v / max_rps)

    def y_lat(v: float) -> float:
        return pad_t + h - (h * v / max_lat)

    rps_points = " ".join(f"{x(i):.1f},{y_rps(v):.1f}" for i, v in enumerate(rps))
    lat_points = " ".join(f"{x(i):.1f},{y_lat(v):.1f}" for i, v in enumerate(lat))

    grid = []
    for i in range(5):
        gy = pad_t + h * i / 4
        grid.append(
            f'<line x1="{pad_l}" y1="{gy:.1f}" x2="{pad_l + w}" y2="{gy:.1f}" '
            f'stroke="#2a2f3a" stroke-width="1"/>'
        )
        grid.append(
            f'<text x="{pad_l - 6}" y="{gy + 4:.1f}" fill="#8b93a7" font-size="10" '
            f'text-anchor="end">{max_rps * (4 - i) / 4:.0f}</text>'
        )
        grid.append(
            f'<text x="{pad_l + w + 6}" y="{gy + 4:.1f}" fill="#f0a35e" font-size="10">'
            f"{max_lat * (4 - i) / 4:.0f}</text>"
        )

    return f"""
<svg viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg" role="img"
     style="width:100%;height:auto;background:#12151c;border:1px solid #2a2f3a;border-radius:8px">
  {''.join(grid)}
  <polyline points="{rps_points}" fill="none" stroke="#4fd1c5" stroke-width="2"/>
  <polyline points="{lat_points}" fill="none" stroke="#f0a35e" stroke-width="2" stroke-dasharray="4 3"/>
  <text x="{pad_l}" y="{height - 8}" fill="#8b93a7" font-size="11">0s</text>
  <text x="{pad_l + w}" y="{height - 8}" fill="#8b93a7" font-size="11" text-anchor="end">{n}s</text>
  <text x="{pad_l}" y="12" fill="#4fd1c5" font-size="11">RPS (max {max_rps:.0f})</text>
  <text x="{pad_l + 110}" y="12" fill="#f0a35e" font-size="11">p95 ms (max {max_lat:.0f})</text>
</svg>"""


def export_html(result: TestResult, path: Optional[Path] = None) -> Path:
    path = path or (results_dir() / f"{result.id}.html")
    s = result.summary
    rows = "".join(
        f"<tr><td>{html.escape(str(k))}</td><td>{html.escape(str(v))}</td></tr>"
        for k, v in [
            ("Target", result.target),
            ("Scenario", result.scenario),
            ("Started", time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(result.started_at))),
            ("Duration", f"{s.get('elapsed', 0):.1f} s"),
            ("Requests", f"{s.get('total', 0):,}".replace(",", " ")),
            ("Successful", f"{s.get('ok', 0):,}".replace(",", " ")),
            ("Failed", f"{s.get('failed', 0):,}".replace(",", " ")),
            ("Availability", f"{s.get('availability', 0):.2f} %"),
            ("Throughput", f"{s.get('rps', 0):.1f} req/s (peak {s.get('peak_rps', 0):.1f})"),
            ("Latency avg", f"{s.get('avg_latency', 0):.1f} ms"),
            ("Latency p50", f"{s.get('p50', 0):.1f} ms"),
            ("Latency p95", f"{s.get('p95', 0):.1f} ms"),
            ("Latency p99", f"{s.get('p99', 0):.1f} ms"),
            ("Latency max", f"{s.get('max_latency', 0):.1f} ms"),
            ("Error rate", f"{s.get('error_rate', 0):.2f} %"),
            ("Stop reason", result.stop_reason),
            ("Authorized", "yes" if result.authorized else "NO"),
        ]
    )
    err_rows = "".join(
        f"<tr><td>{html.escape(str(k))}</td><td>{v}</td></tr>"
        for k, v in sorted((s.get("error_kinds") or {}).items(), key=lambda kv: -kv[1])
    ) or "<tr><td colspan='2'>No errors</td></tr>"

    doc = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<title>SEAPED report — {html.escape(result.name)}</title>
<style>
 body {{ background:#0d1017; color:#e6e9f0; font-family:Segoe UI,Roboto,system-ui,sans-serif;
        max-width:1040px; margin:32px auto; padding:0 16px; }}
 h1 {{ color:#4fd1c5; letter-spacing:2px; }}
 h2 {{ color:#a78bfa; border-bottom:1px solid #2a2f3a; padding-bottom:6px; }}
 table {{ border-collapse:collapse; width:100%; margin-top:8px; }}
 td, th {{ border:1px solid #2a2f3a; padding:7px 10px; text-align:left; font-size:14px; }}
 td:first-child {{ color:#8b93a7; width:220px; }}
 footer {{ margin-top:28px; color:#8b93a7; font-size:12px; }}
</style></head><body>
<h1>SEAPED — TEST REPORT</h1>
<p>{html.escape(result.name)} · id {html.escape(result.id)}</p>
<h2>Summary</h2>
<table>{rows}</table>
<h2>Load chart</h2>
{_svg_chart(result.series)}
<h2>Error breakdown</h2>
<table><tr><th>Error kind</th><th>Count</th></tr>{err_rows}</table>
<footer>SEAPED — Professional Load Testing Suite · Developer: @uf0rs · Telegram: @HSIIHprime<br>
Run only against systems you own or are explicitly authorized to test.</footer>
</body></html>"""
    path.write_text(doc, encoding="utf-8")
    return path
