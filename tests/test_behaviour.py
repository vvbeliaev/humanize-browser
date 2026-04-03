import json
import math
import tempfile
from pathlib import Path


def make_jsonl(events: list[dict]) -> Path:
    f = tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False)
    for e in events:
        f.write(json.dumps(e) + "\n")
    f.close()
    return Path(f.name)


# --- RecordSession ---

def test_record_session_writes_jsonl():
    from humanize_browser.behaviour import RecordSession

    with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as f:
        path = Path(f.name)

    session = RecordSession(path)
    session.write_event({"type": "mousemove", "x": 10, "y": 20, "t": 1000})
    session.write_event({"type": "keydown", "key": "a", "t": 1050})
    session.close()

    lines = path.read_text().strip().split("\n")
    assert len(lines) == 2
    assert json.loads(lines[0]) == {"type": "mousemove", "x": 10, "y": 20, "t": 1000}
    assert json.loads(lines[1]) == {"type": "keydown", "key": "a", "t": 1050}


# --- aggregate ---

def test_aggregate_mouse_speed():
    from humanize_browser.behaviour import aggregate

    events = [
        {"type": "mousemove", "x": 0, "y": 0, "t": 0},
        {"type": "mousemove", "x": 10, "y": 0, "t": 100},
        {"type": "mousemove", "x": 20, "y": 0, "t": 200},
        {"type": "mousemove", "x": 30, "y": 0, "t": 400},
    ]
    path = make_jsonl(events)
    profile = aggregate(path, name="test")
    assert profile["mouse_speed"]["mu"] != 0


def test_aggregate_key_delays():
    from humanize_browser.behaviour import aggregate

    events = [
        {"type": "keydown", "key": "t", "t": 0},
        {"type": "keydown", "key": "h", "t": 80},
        {"type": "keydown", "key": "e", "t": 145},
        {"type": "keydown", "key": "t", "t": 300},
        {"type": "keydown", "key": "h", "t": 375},
    ]
    path = make_jsonl(events)
    profile = aggregate(path, name="test")
    assert "th" in profile["key_delays"]
    assert profile["key_delays"]["th"][0] > 0
    assert "default" in profile["key_delays"]


def test_aggregate_saves_json(tmp_path):
    from humanize_browser.behaviour import aggregate
    import humanize_browser.behaviour as beh

    events = [{"type": "mousemove", "x": i * 5, "y": 0, "t": i * 100} for i in range(5)]
    path = make_jsonl(events)

    original = beh.PROFILES_DIR
    beh.PROFILES_DIR = tmp_path
    try:
        profile = aggregate(path, name="myprofile")
    finally:
        beh.PROFILES_DIR = original

    assert profile["name"] == "myprofile"
    assert (tmp_path / "myprofile.json").exists()


# --- bezier_path ---

def test_bezier_path_endpoints():
    from humanize_browser.behaviour import bezier_path

    points = bezier_path(start=(0.0, 0.0), end=(100.0, 100.0), steps=10)
    assert len(points) == 10
    assert abs(points[0][0]) < 5
    assert abs(points[-1][0] - 100) < 5


def test_bezier_path_minimum_steps():
    from humanize_browser.behaviour import bezier_path

    points = bezier_path(start=(0.0, 0.0), end=(50.0, 50.0), steps=2)
    assert len(points) == 2


# --- sample_key_delay ---

def test_sample_key_delay_uses_bigram():
    from humanize_browser.behaviour import sample_key_delay

    profile = {"key_delays": {"th": [70.0, 5.0], "default": [100.0, 10.0]}}
    for _ in range(20):
        assert sample_key_delay(profile, "t", "h") > 0


def test_sample_key_delay_falls_back_to_default():
    from humanize_browser.behaviour import sample_key_delay

    profile = {"key_delays": {"default": [100.0, 10.0]}}
    assert sample_key_delay(profile, "z", "z") > 0


def test_sample_key_delay_no_profile():
    from humanize_browser.behaviour import sample_key_delay

    assert sample_key_delay(None, "a", "b") == 0.0
