import json
import math
import random
import statistics
from pathlib import Path
from typing import Any

RECORDINGS_DIR = Path.home() / ".humanize-browser" / "recordings"
PROFILES_DIR = Path.home() / ".humanize-browser" / "profiles"


# ── RECORD ────────────────────────────────────────────────────────────────────

class RecordSession:
    """Writes raw input events as JSONL to a file."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._file = path.open("w")

    def write_event(self, event: dict[str, Any]) -> None:
        self._file.write(json.dumps(event) + "\n")
        self._file.flush()

    def close(self) -> None:
        self._file.close()

    def __enter__(self) -> "RecordSession":
        return self

    def __exit__(self, *args: object) -> None:
        self.close()


# ── AGGREGATE ─────────────────────────────────────────────────────────────────

def _lognormal_fit(values: list[float]) -> tuple[float, float]:
    """Fit log-normal distribution. Returns (mu, sigma) of the underlying normal."""
    log_vals = [math.log(v) for v in values if v > 0]
    if not log_vals:
        return 0.0, 0.0
    mu = statistics.mean(log_vals)
    sigma = statistics.stdev(log_vals) if len(log_vals) > 1 else 0.0
    return mu, sigma


def _normal_fit(values: list[float]) -> tuple[float, float]:
    if not values:
        return 0.0, 0.0
    mu = statistics.mean(values)
    sigma = statistics.stdev(values) if len(values) > 1 else 0.0
    return mu, sigma


def aggregate(recording_path: Path, name: str) -> dict[str, Any]:
    """
    Read a JSONL recording and build a Profile.
    Saves to PROFILES_DIR/<name>.json and returns the profile dict.
    """
    import datetime

    events = [
        json.loads(line)
        for line in recording_path.read_text().splitlines()
        if line.strip()
    ]

    # Mouse speed: pixels/ms between consecutive mousemove events
    mouse_speeds: list[float] = []
    prev_move: dict | None = None
    for e in events:
        if e["type"] == "mousemove":
            if prev_move is not None:
                dt = e["t"] - prev_move["t"]
                if dt > 0:
                    dist = math.sqrt((e["x"] - prev_move["x"]) ** 2 + (e["y"] - prev_move["y"]) ** 2)
                    if dist > 0:
                        mouse_speeds.append(dist / dt)
            prev_move = e

    # Key delays: ms between consecutive keydown events, per bigram
    bigram_delays: dict[str, list[float]] = {}
    prev_key: dict | None = None
    for e in events:
        if e["type"] == "keydown":
            if prev_key is not None:
                delay = e["t"] - prev_key["t"]
                if 10 < delay < 2000:
                    bigram = prev_key["key"] + e["key"]
                    bigram_delays.setdefault(bigram, []).append(delay)
                    bigram_delays.setdefault("default", []).append(delay)
            prev_key = e

    speed_mu, speed_sigma = _lognormal_fit(mouse_speeds) if mouse_speeds else (1.0, 0.3)

    key_delay_models: dict[str, list[float]] = {}
    for bigram, delays in bigram_delays.items():
        mu, sigma = _normal_fit(delays)
        key_delay_models[bigram] = [round(mu, 1), round(sigma, 1)]
    if "default" not in key_delay_models:
        key_delay_models["default"] = [95.0, 18.0]

    profile: dict[str, Any] = {
        "name": name,
        "recorded_at": datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z"),
        "mouse_speed": {"mu": round(speed_mu, 4), "sigma": round(speed_sigma, 4)},
        "key_delays": key_delay_models,
        "overshoot_prob": 0.15,
        "pre_click_dwell_ms": [180.0, 60.0],
    }

    PROFILES_DIR.mkdir(parents=True, exist_ok=True)
    (PROFILES_DIR / f"{name}.json").write_text(json.dumps(profile, indent=2))
    return profile


# ── REPLAY ────────────────────────────────────────────────────────────────────

def bezier_path(
    start: tuple[float, float],
    end: tuple[float, float],
    steps: int,
) -> list[tuple[float, float]]:
    """
    Cubic Bezier path from start to end with randomised control points.
    Returns `steps` (x, y) tuples.
    """
    x0, y0 = start
    x3, y3 = end
    spread = max(abs(x3 - x0), abs(y3 - y0)) * 0.3 + 10
    x1 = x0 + (x3 - x0) / 3 + random.uniform(-spread, spread)
    y1 = y0 + (y3 - y0) / 3 + random.uniform(-spread, spread)
    x2 = x0 + 2 * (x3 - x0) / 3 + random.uniform(-spread, spread)
    y2 = y0 + 2 * (y3 - y0) / 3 + random.uniform(-spread, spread)

    points = []
    for i in range(steps):
        t = i / max(steps - 1, 1)
        u = 1 - t
        x = u**3 * x0 + 3 * u**2 * t * x1 + 3 * u * t**2 * x2 + t**3 * x3
        y = u**3 * y0 + 3 * u**2 * t * y1 + 3 * u * t**2 * y2 + t**3 * y3
        points.append((x, y))
    return points


def _sample_lognormal(mu: float, sigma: float) -> float:
    """Sample from log-normal distribution with given underlying normal params."""
    if sigma == 0:
        return math.exp(mu)
    return math.exp(random.gauss(mu, sigma))


def sample_key_delay(
    profile: dict[str, Any] | None, prev_key: str, key: str
) -> float:
    """
    Return delay in milliseconds before typing `key` after `prev_key`.
    Returns 0.0 when no profile is active (raw mode).
    """
    if profile is None:
        return 0.0
    delays = profile.get("key_delays", {})
    params = delays.get(prev_key + key) or delays.get("default") or [95.0, 18.0]
    return max(random.gauss(params[0], params[1]), 20.0)
