import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import httpx

PID_FILE = Path.home() / ".humanize-browser" / "daemon.pid"
STARTUP_TIMEOUT = 10  # seconds


def read_pid_file(pid_file: Path = PID_FILE) -> tuple[int | None, int | None]:
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


def ensure_daemon(headless: bool = True) -> int:
    """Return port of running daemon, starting it if needed."""
    port, pid = read_pid_file()
    if port is not None and pid is not None and _is_alive(pid):
        return port

    port = _free_port()
    subprocess.Popen(
        [sys.executable, "-m", "humanize_browser._daemon_entry", str(port), "0" if not headless else "1"],
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
    args = parser.parse_args()

    cmd_list = args.command

    if not cmd_list or cmd_list[0] == "status":
        port, pid = read_pid_file()
        if port is None or not _is_alive(pid or 0):
            print("Daemon not running")
            return
        method, path, body = "GET", "/status", {}
    else:
        port = ensure_daemon(headless=not args.headed)
        try:
            httpx.post(
                f"http://127.0.0.1:{port}/config",
                json={"humanize": not args.no_humanize},
                timeout=5,
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
        data = r.json()
    except (httpx.RequestError, httpx.HTTPStatusError) as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    output = format_output(data, args.json)
    if output:
        print(output)
    if not data.get("success"):
        sys.exit(1)
