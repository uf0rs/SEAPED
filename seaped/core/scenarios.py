"""Load scenarios: how the virtual-user count evolves over time."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, List


@dataclass
class ScenarioSpec:
    """User-facing parameters shared by every scenario.

    Mutable on purpose: safety clamping (owner limits, coordinator rules)
    rewrites these fields before a test starts.
    """

    start_vus: int = 10
    max_vus: int = 100
    duration: int = 60  # seconds
    ramp_up: int = 20  # seconds to reach max_vus
    ramp_down: int = 10  # seconds used to release users at the end


@dataclass(frozen=True)
class Scenario:
    id: str
    name: str
    kind: str
    description: str
    default_spec: ScenarioSpec
    doc: str

    def target_vus(self, spec: ScenarioSpec, elapsed: float) -> int:
        """Desired number of active virtual users at time *elapsed* (seconds)."""
        return SCHEDULERS[self.kind](spec, elapsed)


def _clamp(value: float, low: int, high: int) -> int:
    return max(low, min(high, int(round(value))))


def _constant(spec: ScenarioSpec, elapsed: float) -> int:
    """Steady load: start_vus -> max_vus quickly, then hold."""
    if spec.ramp_up <= 0:
        return spec.max_vus
    if elapsed >= spec.ramp_up:
        return spec.max_vus
    frac = elapsed / spec.ramp_up
    return _clamp(spec.start_vus + (spec.max_vus - spec.start_vus) * frac, 1, spec.max_vus)


def _ramp(spec: ScenarioSpec, elapsed: float) -> int:
    """Linear ramp-up over the whole duration (classic load ramp)."""
    if spec.duration <= 0:
        return spec.max_vus
    if elapsed >= spec.duration:
        return 0
    frac = elapsed / spec.duration
    return _clamp(spec.start_vus + (spec.max_vus - spec.start_vus) * frac, 1, spec.max_vus)


def _step(spec: ScenarioSpec, elapsed: float) -> int:
    """Stepped ramp: +25% of max every ramp_up/4 seconds."""
    if spec.ramp_up <= 0:
        return spec.max_vus
    step_len = max(1.0, spec.ramp_up / 4.0)
    steps = int(elapsed // step_len)
    value = spec.start_vus + (spec.max_vus - spec.start_vus) * min(steps, 4) / 4.0
    return _clamp(value, 1, spec.max_vus)


def _spike(spec: ScenarioSpec, elapsed: float) -> int:
    """Sudden jump to max, hold, drop to 10%, then release."""
    if spec.duration <= 0:
        return spec.max_vus
    frac = elapsed / spec.duration
    if frac < 0.10:
        return _clamp(spec.start_vus, 1, spec.max_vus)
    if frac < 0.75:
        return spec.max_vus
    if frac < 0.90:
        return _clamp(spec.max_vus * 0.1, 1, spec.max_vus)
    return 0


def _stress(spec: ScenarioSpec, elapsed: float) -> int:
    """Aggressive ramp intended to find the server's breaking point."""
    if spec.duration <= 0:
        return spec.max_vus
    if elapsed >= spec.duration:
        return 0
    # exponential-ish growth keeps early phase gentle and late phase brutal
    frac = elapsed / spec.duration
    value = spec.start_vus + (spec.max_vus - spec.start_vus) * (frac ** 1.6)
    return _clamp(value, 1, spec.max_vus)


def _endurance(spec: ScenarioSpec, elapsed: float) -> int:
    """Long-running soak at a fixed fraction of max_vus."""
    if spec.ramp_up <= 0:
        return max(1, int(spec.max_vus * 0.4))
    if elapsed < spec.ramp_up:
        frac = elapsed / spec.ramp_up
        return _clamp(spec.start_vus + (spec.max_vus * 0.4 - spec.start_vus) * frac, 1, spec.max_vus)
    if elapsed >= spec.duration:
        return 0
    return max(1, int(spec.max_vus * 0.4))


def _smoke(spec: ScenarioSpec, elapsed: float) -> int:
    """Quick sanity check: a handful of users for a short time."""
    if spec.duration <= 0:
        return 5
    if elapsed >= spec.duration:
        return 0
    return max(1, min(5, spec.max_vus))


SCHEDULERS: Dict[str, Callable[[ScenarioSpec, float], int]] = {
    "constant": _constant,
    "ramp": _ramp,
    "step": _step,
    "spike": _spike,
    "stress": _stress,
    "endurance": _endurance,
    "smoke": _smoke,
}

SCENARIOS: Dict[str, Scenario] = {
    s.id: s
    for s in [
        Scenario(
            id="smoke",
            name="Smoke Test",
            kind="smoke",
            description="Quick sanity check with a few users",
            default_spec=ScenarioSpec(start_vus=1, max_vus=5, duration=30, ramp_up=3, ramp_down=2),
            doc="Very light test (up to 5 users). Use it to verify that the target "
            "URL, method, headers and proxy settings are correct before a full run.",
        ),
        Scenario(
            id="constant",
            name="Constant Load",
            kind="constant",
            description="Steady number of users for the whole duration",
            default_spec=ScenarioSpec(start_vus=10, max_vus=100, duration=60, ramp_up=10),
            doc="Holds a fixed amount of virtual users. Best for measuring baseline "
            "response time and throughput under a known, stable load.",
        ),
        Scenario(
            id="ramp",
            name="Ramp-Up",
            kind="ramp",
            description="Linear growth of users up to the limit",
            default_spec=ScenarioSpec(start_vus=5, max_vus=200, duration=120, ramp_up=120),
            doc="Users are added linearly until the end of the test. Shows how "
            "latency and throughput scale with load — the point where the curve "
            "flattens is the practical capacity of the server.",
        ),
        Scenario(
            id="step",
            name="Step Load",
            kind="step",
            description="Load grows in four discrete steps",
            default_spec=ScenarioSpec(start_vus=10, max_vus=200, duration=120, ramp_up=60),
            doc="The load increases by 25% of the maximum every quarter of the ramp. "
            "Each plateau makes it easy to compare metrics between load levels.",
        ),
        Scenario(
            id="spike",
            name="Spike",
            kind="spike",
            description="Sudden burst, hold, partial drop, release",
            default_spec=ScenarioSpec(start_vus=10, max_vus=300, duration=90, ramp_up=5),
            doc="Simulates a traffic burst (announcement, promo, incident). Verifies "
            "autoscaling, queueing and how fast the service recovers.",
        ),
        Scenario(
            id="stress",
            name="Stress Test",
            kind="stress",
            description="Aggressive growth until a limit is reached",
            default_spec=ScenarioSpec(start_vus=10, max_vus=500, duration=180, ramp_up=180),
            doc="Load grows non-linearly until a safety limit triggers (error rate, "
            "latency or duration). The stop reason tells you where the system broke.",
        ),
        Scenario(
            id="endurance",
            name="Endurance (Soak)",
            kind="endurance",
            description="Long stable load to catch leaks and degradation",
            default_spec=ScenarioSpec(start_vus=5, max_vus=100, duration=900, ramp_up=30),
            doc="Runs a moderate load for a long time. Reveals memory leaks, "
            "connection pool exhaustion and slow degradation over hours.",
        ),
    ]
}


def get_scenario(scenario_id: str) -> Scenario:
    if scenario_id not in SCENARIOS:
        raise KeyError(f"Unknown scenario: {scenario_id}")
    return SCENARIOS[scenario_id]


def schedule_preview(spec: ScenarioSpec, scenario_id: str, points: int = 60) -> List[int]:
    """Used by the UI to draw a preview curve of the selected scenario."""
    scenario = get_scenario(scenario_id)
    duration = max(1, spec.duration)
    return [
        scenario.target_vus(spec, duration * i / max(1, points - 1)) for i in range(points)
    ]
