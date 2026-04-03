import json
from pathlib import Path


def test_read_pid_file(tmp_path):
    from humanize_browser.cli import read_pid_file

    pid_file = tmp_path / "daemon.pid"
    pid_file.write_text(json.dumps({"port": 19876, "pid": 12345}))
    port, pid = read_pid_file(pid_file)
    assert port == 19876
    assert pid == 12345


def test_read_pid_file_missing(tmp_path):
    from humanize_browser.cli import read_pid_file

    port, pid = read_pid_file(tmp_path / "daemon.pid")
    assert port is None
    assert pid is None


def test_build_request_open():
    from humanize_browser.cli import build_request

    method, path, body = build_request(["open", "https://example.com"], {})
    assert method == "POST"
    assert path == "/open"
    assert body == {"url": "https://example.com"}


def test_build_request_snapshot():
    from humanize_browser.cli import build_request

    method, path, body = build_request(["snapshot"], {})
    assert method == "POST"
    assert path == "/snapshot"
    assert body == {}


def test_build_request_click():
    from humanize_browser.cli import build_request

    _, path, body = build_request(["click", "@e1"], {})
    assert path == "/click"
    assert body == {"selector": "@e1"}


def test_build_request_type():
    from humanize_browser.cli import build_request

    _, path, body = build_request(["type", "@e2", "hello world"], {})
    assert path == "/type"
    assert body == {"selector": "@e2", "text": "hello world"}


def test_build_request_wait_ms():
    from humanize_browser.cli import build_request

    _, path, body = build_request(["wait", "500"], {})
    assert path == "/wait"
    assert body == {"ms": 500}


def test_build_request_wait_selector():
    from humanize_browser.cli import build_request

    _, path, body = build_request(["wait", "#main"], {})
    assert path == "/wait"
    assert body == {"selector": "#main"}


def test_build_request_close():
    from humanize_browser.cli import build_request

    method, path, _ = build_request(["close"], {})
    assert method == "POST"
    assert path == "/shutdown"


def test_build_request_record_start():
    from humanize_browser.cli import build_request

    _, path, body = build_request(["record", "start", "--profile", "me"], {})
    assert path == "/record/start"
    assert body == {"profile": "me"}


def test_build_request_record_stop():
    from humanize_browser.cli import build_request

    _, path, _ = build_request(["record", "stop"], {})
    assert path == "/record/stop"


def test_build_request_profile_use():
    from humanize_browser.cli import build_request

    _, path, body = build_request(["profile", "use", "myprofile"], {})
    assert path == "/profile/use"
    assert body == {"name": "myprofile"}


def test_format_output_text(capsys):
    from humanize_browser.cli import format_output

    result = format_output({"success": True, "data": {"text": "hello @e1"}}, as_json=False)
    assert result == "hello @e1"


def test_format_output_json():
    from humanize_browser.cli import format_output

    result = format_output({"success": True, "data": {"text": "hi"}}, as_json=True)
    assert '"success": true' in result


def test_format_output_error():
    from humanize_browser.cli import format_output

    result = format_output({"success": False, "error": "No page"}, as_json=False)
    assert "No page" in result


def test_build_request_status():
    from humanize_browser.cli import build_request

    method, path, _ = build_request(["status"], {})
    assert method == "GET"
    assert path == "/status"
