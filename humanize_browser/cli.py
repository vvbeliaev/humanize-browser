import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import httpx

SESSIONS_DIR = Path.home() / ".humanize-browser" / "sessions"
STARTUP_TIMEOUT = 10  # seconds
CONFIG_FILENAME = "humanize-browser.json"
GLOBAL_CONFIG = Path.home() / ".humanize-browser" / "config.json"
DEFAULT_SESSION = "default"


def pid_file_for(session: str) -> Path:
    return SESSIONS_DIR / f"{session}.pid"


def load_config(config_path: Path | None = None) -> dict[str, Any]:
    """Load config from humanize-browser.json (CWD), global config, or explicit path.

    Priority (lowest → highest): global config < project config < --config flag.
    """
    if config_path is not None:
        if not config_path.exists():
            print(f"Error: config file not found: {config_path}", file=sys.stderr)
            sys.exit(1)
        try:
            return json.loads(config_path.read_text())
        except Exception as e:
            print(f"Error: failed to read config {config_path}: {e}", file=sys.stderr)
            sys.exit(1)

    merged: dict[str, Any] = {}
    for path in (GLOBAL_CONFIG, Path.cwd() / CONFIG_FILENAME):
        if path.exists():
            try:
                merged.update(json.loads(path.read_text()))
            except Exception as e:
                print(f"Warning: failed to read config {path}: {e}", file=sys.stderr)
    return merged


def read_pid_file(pid_file: Path) -> tuple[int | None, int | None]:
    if not pid_file.exists():
        return None, None
    try:
        data = json.loads(pid_file.read_text())
        return data["port"], data["pid"]
    except Exception:
        return None, None


def _is_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def ensure_daemon(pid_file: Path, headless: bool = True) -> int:
    """Return port of running daemon for this session, starting it if needed."""
    port, pid = read_pid_file(pid_file)
    if port is not None and pid is not None and _is_alive(pid):
        return port

    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    port = _free_port()
    subprocess.Popen(
        [
            sys.executable, "-m", "humanize_browser._daemon_entry",
            str(port),
            "0" if not headless else "1",
            str(pid_file),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    deadline = time.time() + STARTUP_TIMEOUT
    while time.time() < deadline:
        try:
            r = httpx.get(f"http://127.0.0.1:{port}/status", timeout=1)
            if r.status_code == 200:
                return port
        except Exception:
            pass
        time.sleep(0.2)

    print("Error: daemon failed to start", file=sys.stderr)
    sys.exit(1)


def build_request(
    args: list[str], flags: dict[str, Any]
) -> tuple[str, str, dict[str, Any]]:
    """Map CLI positional args to (http_method, path, body)."""
    if not args:
        return "GET", "/status", {}

    cmd = args[0]

    match cmd:
        case "open" | "goto" | "navigate":
            return "POST", "/open", {"url": args[1]}
        case "snapshot":
            return "POST", "/snapshot", {}
        case "click":
            return "POST", "/click", {"selector": args[1]}
        case "type":
            return "POST", "/type", {"selector": args[1], "text": args[2]}
        case "fill":
            return "POST", "/fill", {"selector": args[1], "text": args[2]}
        case "hover":
            return "POST", "/hover", {"selector": args[1]}
        case "screenshot":
            path = args[1] if len(args) > 1 else "screenshot.png"
            return "POST", "/screenshot", {"path": path}
        case "wait":
            val = args[1] if len(args) > 1 else "1000"
            if val.isdigit():
                return "POST", "/wait", {"ms": int(val)}
            return "POST", "/wait", {"selector": val}
        case "record":
            sub = args[1] if len(args) > 1 else ""
            if sub == "start":
                profile = args[3] if len(args) > 3 and args[2] == "--profile" else "default"
                return "POST", "/record/start", {"profile": profile}
            if sub == "stop":
                return "POST", "/record/stop", {}
            if sub == "aggregate":
                profile = args[3] if len(args) > 3 and args[2] == "--profile" else "default"
                return "POST", "/record/aggregate", {"profile": profile}
            return "GET", "/status", {}
        case "profile":
            sub = args[1] if len(args) > 1 else ""
            if sub == "use":
                name = args[2] if len(args) > 2 else "default"
                return "POST", "/profile/use", {"name": name}
            return "GET", "/status", {}
        case "scroll":
            direction = args[1] if len(args) > 1 else "down"
            amount = int(args[2]) if len(args) > 2 and args[2].isdigit() else 300
            body: dict[str, Any] = {"direction": direction, "amount": amount}
            if len(args) > 3:
                body["selector"] = args[3]
            return "POST", "/scroll", body
        case "eval":
            if len(args) < 2:
                print("Error: eval requires an expression", file=sys.stderr)
                sys.exit(1)
            return "POST", "/eval", {"expression": args[1]}
        case "select":
            return "POST", "/select", {"selector": args[1], "value": args[2]}
        case "close":
            return "POST", "/shutdown", {}
        case "status":
            return "GET", "/status", {}
        case _:
            print(f"Unknown command: {cmd}", file=sys.stderr)
            sys.exit(1)


def format_output(data: dict[str, Any], as_json: bool) -> str:
    if as_json:
        return json.dumps(data, indent=2)
    if not data.get("success"):
        return f"Error: {data.get('error', 'unknown')}"
    d = data.get("data") or {}
    if "text" in d:
        return d["text"]
    if "value" in d:
        return d["value"]
    if "path" in d:
        return d["path"]
    return ""


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(prog="humanize-browser")
    parser.add_argument("command", nargs="*")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--headed", action="store_true")
    parser.add_argument("--no-humanize", action="store_true")
    parser.add_argument("--session", default=None, metavar="NAME")
    parser.add_argument("--config", type=Path, default=None, metavar="PATH")
    args = parser.parse_args()

    config = load_config(args.config)

    # CLI flags take precedence over config
    headed = args.headed or bool(config.get("headed", False))
    humanize = (not args.no_humanize) and bool(config.get("humanize", True))
    profile: str | None = config.get("profile")
    profile_dir: str | None = (
        str(Path(config["profile_dir"]).resolve()) if "profile_dir" in config else None
    )
    session = args.session or config.get("session", DEFAULT_SESSION)
    pid_file = pid_file_for(session)

    cmd_list = args.command

    if not cmd_list or cmd_list[0] == "status":
        port, pid = read_pid_file(pid_file)
        if port is None or not _is_alive(pid or 0):
            print(f"Session '{session}': daemon not running")
            return
        method, path, body = "GET", "/status", {}
    else:
        port = ensure_daemon(pid_file, headless=not headed)
        try:
            with httpx.Client(timeout=5) as setup_client:
                setup_client.post(
                    f"http://127.0.0.1:{port}/config",
                    json={"humanize": humanize, "profile_dir": profile_dir},
                )
                if profile:
                    setup_client.post(
                        f"http://127.0.0.1:{port}/profile/use",
                        json={"name": profile},
                    )
        except httpx.RequestError:
            pass  # non-critical, proceed anyway
        method, path, body = build_request(cmd_list, {})

    try:
        with httpx.Client(timeout=60.0) as client:
            if method == "GET":
                r = client.get(f"http://127.0.0.1:{port}{path}")
            else:
                r = client.post(f"http://127.0.0.1:{port}{path}", json=body)
        if not r.content:
            print(f"Error: daemon returned empty response (HTTP {r.status_code})", file=sys.stderr)
            sys.exit(1)
        data = r.json()
    except (httpx.RequestError, httpx.HTTPStatusError) as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error: failed to parse daemon response: {e}", file=sys.stderr)
        sys.exit(1)

    output = format_output(data, args.json)
    if output:
        print(output)
    if not data.get("success"):
        sys.exit(1)
