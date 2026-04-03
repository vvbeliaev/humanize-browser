# humanize-browser Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a CLI browser automation tool with a persistent HTTP daemon backed by Camoufox+stealth, an accessibility ref system, and a human behaviour middleware (record → aggregate → replay).

**Architecture:** FastAPI daemon holds a single Camoufox browser session and is auto-started by the CLI on first use. A PID file stores port + PID. BehaviourMiddleware intercepts `click` and `type` to inject Bezier mouse paths and per-bigram key delays sampled from a recorded human profile.

**Tech Stack:** Python 3.13, Camoufox, Playwright, playwright-stealth, FastAPI, uvicorn, httpx, pytest, pytest-asyncio

---

## File Map

| File | Responsibility |
|------|----------------|
| `humanize_browser/__init__.py` | Package marker |
| `humanize_browser/browser.py` | Camoufox + stealth launch, async context manager yielding a `Page` |
| `humanize_browser/snapshot.py` | Accessibility tree walker; assigns `@e{n}` refs |
| `humanize_browser/behaviour.py` | `RecordSession`, `aggregate()`, `bezier_path()`, `sample_key_delay()` |
| `humanize_browser/daemon.py` | FastAPI app, `AppState`, all HTTP endpoints |
| `humanize_browser/_daemon_entry.py` | Subprocess entry point for daemon |
| `humanize_browser/cli.py` | `build_request()`, `ensure_daemon()`, `main()` |
| `tests/__init__.py` | Package marker |
| `tests/test_snapshot.py` | Unit tests for tree walker |
| `tests/test_behaviour.py` | Unit tests for aggregate + replay math |
| `tests/test_cli.py` | Unit tests for CLI dispatch (no browser) |
| `tests/test_integration.py` | Integration tests (real browser, `@pytest.mark.integration`) |

---

## Task 1: Project setup

**Files:**
- Modify: `pyproject.toml`
- Create: `humanize_browser/__init__.py`
- Create: `tests/__init__.py`

- [ ] **Step 1: Replace pyproject.toml**

```toml
[project]
name = "humanize-browser"
version = "0.1.0"
description = "Human-like browser automation CLI with Camoufox stealth and behaviour middleware"
readme = "README.md"
requires-python = ">=3.13"
dependencies = [
    "camoufox[geoip]>=0.4.11",
    "fastapi>=0.115.0",
    "httpx>=0.28.0",
    "playwright>=1.58.0",
    "playwright-stealth>=2.0.2",
    "uvicorn>=0.34.0",
]

[project.scripts]
humanize-browser = "humanize_browser.cli:main"

[project.optional-dependencies]
dev = [
    "pytest>=8.0.0",
    "pytest-asyncio>=0.25.0",
]

[tool.pytest.ini_options]
asyncio_mode = "auto"
markers = ["integration: requires a real browser (slow)"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
```

- [ ] **Step 2: Install new dependencies**

```bash
uv add fastapi uvicorn httpx
uv add --dev pytest pytest-asyncio
```

Expected: lock file updated, no errors.

- [ ] **Step 3: Create package and test directories**

Create `humanize_browser/__init__.py` — empty file.
Create `tests/__init__.py` — empty file.

- [ ] **Step 4: Verify**

```bash
uv run python -c "import fastapi, httpx, uvicorn; print('ok')"
```

Expected: `ok`

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml uv.lock humanize_browser/__init__.py tests/__init__.py
git commit -m "chore: project setup — fastapi, uvicorn, httpx, pytest"
```

---

## Task 2: browser.py — Camoufox + stealth launch

**Files:**
- Create: `humanize_browser/browser.py`
- Create: `tests/test_integration.py`

- [ ] **Step 1: Write failing integration test**

Create `tests/test_integration.py`:

```python
import pytest

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_browser_launches_with_stealth():
    from humanize_browser.browser import launch_browser

    async with launch_browser(headless=True) as page:
        webdriver = await page.evaluate("navigator.webdriver")
        ua = await page.evaluate("navigator.userAgent")

        assert webdriver is False or webdriver is None
        assert "Headless" not in ua
        assert "headless" not in ua
```

- [ ] **Step 2: Run to verify it fails**

```bash
uv run pytest tests/test_integration.py -v -m integration
```

Expected: `ModuleNotFoundError: No module named 'humanize_browser.browser'`

- [ ] **Step 3: Implement browser.py**

Create `humanize_browser/browser.py`:

```python
from contextlib import asynccontextmanager
from typing import AsyncIterator

from camoufox.async_api import AsyncCamoufox
from playwright.async_api import Page
from playwright_stealth import Stealth

_stealth = Stealth()


@asynccontextmanager
async def launch_browser(headless: bool = True) -> AsyncIterator[Page]:
    """Launch Camoufox with stealth patches applied. Yields a ready Page."""
    async with AsyncCamoufox(headless=headless, geoip=True) as browser:
        page = await browser.new_page()
        await _stealth.apply_stealth_async(page)
        yield page
```

- [ ] **Step 4: Run test to verify it passes**

```bash
uv run pytest tests/test_integration.py -v -m integration
```

Expected: `PASSED`

- [ ] **Step 5: Commit**

```bash
git add humanize_browser/browser.py tests/test_integration.py
git commit -m "feat: browser.py — Camoufox + stealth launch"
```

---

## Task 3: snapshot.py — accessibility tree walker

**Files:**
- Create: `humanize_browser/snapshot.py`
- Create: `tests/test_snapshot.py`

`walk_tree` takes the raw dict from `page.accessibility.snapshot()` and returns:
1. Formatted text lines with `@e{n}` refs
2. A ref map: `{"@e1": (role, name, occurrence_index), ...}`

Occurrence index is needed when two nodes share the same role+name (resolved via `.nth(index)` on the locator).

- [ ] **Step 1: Write failing unit tests**

Create `tests/test_snapshot.py`:

```python
from humanize_browser.snapshot import walk_tree, build_ref_locator_args, format_snapshot


def make_tree():
    return {
        "role": "RootWebArea",
        "name": "Test Page",
        "children": [
            {"role": "heading", "name": "Hello World", "level": 1},
            {"role": "link", "name": "Click me"},
            {"role": "button", "name": "Submit"},
            {"role": "link", "name": "Click me"},  # duplicate
        ],
    }


def test_walk_tree_assigns_refs():
    lines, ref_map = walk_tree(make_tree())
    assert "@e1" in ref_map
    assert "@e2" in ref_map
    assert "@e3" in ref_map
    assert "@e4" in ref_map
    assert len(ref_map) == 4


def test_walk_tree_formats_output():
    lines, _ = walk_tree(make_tree())
    text = "\n".join(lines)
    assert 'heading "Hello World" @e1' in text
    assert 'link "Click me" @e2' in text
    assert 'button "Submit" @e3' in text


def test_walk_tree_tracks_duplicates():
    _, ref_map = walk_tree(make_tree())
    assert ref_map["@e2"] == ("link", "Click me", 0)
    assert ref_map["@e4"] == ("link", "Click me", 1)


def test_build_ref_locator_args():
    args = build_ref_locator_args("button", "Submit", 0)
    assert args == {"role": "button", "name": "Submit", "nth": 0}


def test_format_snapshot_adds_numbering():
    lines = ['heading "Hello" @e1', 'link "Go" @e2']
    out = format_snapshot(lines)
    assert out == '[1] heading "Hello" @e1\n[2] link "Go" @e2'


def test_empty_tree():
    lines, ref_map = walk_tree({"role": "RootWebArea", "name": ""})
    assert lines == []
    assert ref_map == {}
```

- [ ] **Step 2: Run to verify they fail**

```bash
uv run pytest tests/test_snapshot.py -v
```

Expected: `ModuleNotFoundError: No module named 'humanize_browser.snapshot'`

- [ ] **Step 3: Implement snapshot.py**

Create `humanize_browser/snapshot.py`:

```python
from typing import Any

# Roles worth surfacing to the agent — skip purely structural containers
_ACTIONABLE_ROLES = {
    "button", "link", "textbox", "checkbox", "radio", "combobox",
    "listbox", "option", "menuitem", "tab", "heading", "img",
    "searchbox", "spinbutton", "slider", "switch", "treeitem",
}


def walk_tree(
    node: dict[str, Any],
) -> tuple[list[str], dict[str, tuple[str, str, int]]]:
    """
    Walk an accessibility tree dict (from page.accessibility.snapshot()).

    Returns:
        lines:   formatted text, e.g. ['heading "Hello" @e1', ...]
        ref_map: {"@e1": (role, name, occurrence_index), ...}
    """
    lines: list[str] = []
    ref_map: dict[str, tuple[str, str, int]] = {}
    occurrence_counter: dict[tuple[str, str], int] = {}
    counter = [1]

    def _visit(n: dict[str, Any]) -> None:
        role = (n.get("role") or "").lower()
        name = n.get("name") or ""

        if role in _ACTIONABLE_ROLES and name:
            key = (role, name)
            idx = occurrence_counter.get(key, 0)
            occurrence_counter[key] = idx + 1

            ref = f"@e{counter[0]}"
            counter[0] += 1
            ref_map[ref] = (role, name, idx)
            lines.append(f'{role} "{name}" {ref}')

        for child in n.get("children") or []:
            _visit(child)

    _visit(node)
    return lines, ref_map


def build_ref_locator_args(role: str, name: str, nth: int) -> dict[str, Any]:
    """Return kwargs needed to resolve a ref: page.get_by_role(role, name=name).nth(nth)."""
    return {"role": role, "name": name, "nth": nth}


def format_snapshot(lines: list[str]) -> str:
    return "\n".join(f"[{i + 1}] {line}" for i, line in enumerate(lines))
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_snapshot.py -v
```

Expected: all 6 `PASSED`

- [ ] **Step 5: Commit**

```bash
git add humanize_browser/snapshot.py tests/test_snapshot.py
git commit -m "feat: snapshot.py — accessibility tree walker with @ref assignment"
```

---

## Task 4: daemon.py — FastAPI app with all endpoints

**Files:**
- Create: `humanize_browser/daemon.py`
- Create: `humanize_browser/_daemon_entry.py`

`AppState` is a module-level singleton. Endpoints resolve `@ref` or CSS selector via `resolve()`, act on the page, return `{"success": bool, "data": any}`.

- [ ] **Step 1: Write failing integration tests**

Add to `tests/test_integration.py`:

```python
@pytest.mark.asyncio
async def test_daemon_status_endpoint():
    from httpx import AsyncClient, ASGITransport
    from humanize_browser.browser import launch_browser
    from humanize_browser.daemon import app, state

    async with launch_browser(headless=True) as page:
        state.page = page
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            r = await client.get("/status")
            assert r.status_code == 200
            assert r.json()["data"]["ready"] is True


@pytest.mark.asyncio
async def test_daemon_snapshot_returns_refs():
    from httpx import AsyncClient, ASGITransport
    from humanize_browser.browser import launch_browser
    from humanize_browser.daemon import app, state

    async with launch_browser(headless=True) as page:
        await page.goto("data:text/html,<h1>Hello</h1><a href='#'>Link</a>")
        state.page = page
        state.refs = {}
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            r = await client.post("/snapshot")
            assert r.status_code == 200
            data = r.json()
            assert data["success"] is True
            assert len(data["data"]["refs"]) > 0
```

- [ ] **Step 2: Run to verify they fail**

```bash
uv run pytest tests/test_integration.py -v -m integration -k "daemon"
```

Expected: `ModuleNotFoundError: No module named 'humanize_browser.daemon'`

- [ ] **Step 3: Implement daemon.py**

Create `humanize_browser/daemon.py`:

```python
import asyncio
import json
import math
import os
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

from humanize_browser.snapshot import build_ref_locator_args, format_snapshot, walk_tree

PROFILES_DIR = Path.home() / ".humanize-browser" / "profiles"
PID_FILE = Path.home() / ".humanize-browser" / "daemon.pid"

# Module-level Camoufox handle kept alive for the daemon lifetime
_camoufox_ctx: Any = None


@dataclass
class AppState:
    page: Any = None  # playwright Page
    refs: dict[str, tuple[str, str, int]] = field(default_factory=dict)
    headless: bool = True
    humanize: bool = True
    profile: dict[str, Any] | None = None


state = AppState()


def ok(data: Any = None) -> JSONResponse:
    return JSONResponse({"success": True, "data": data})


def err(msg: str, status: int = 400) -> JSONResponse:
    return JSONResponse({"success": False, "error": msg}, status_code=status)


def resolve(selector: str) -> Any:
    """Resolve @ref or CSS selector to a Playwright locator."""
    if state.page is None:
        raise HTTPException(400, "No page open. Run 'open' first.")
    if selector.startswith("@"):
        if selector not in state.refs:
            raise HTTPException(400, f"Unknown ref {selector}. Run snapshot first.")
        role, name, nth = state.refs[selector]
        return state.page.get_by_role(role, name=name).nth(nth)
    return state.page.locator(selector)


app = FastAPI()


@app.get("/status")
async def status():
    return ok({"ready": True, "has_page": state.page is not None})


@app.post("/open")
async def open_url(body: dict):
    global _camoufox_ctx

    url = body.get("url")
    if not url:
        return err("url required")

    if state.page is None:
        from camoufox.async_api import AsyncCamoufox
        from playwright_stealth import Stealth

        headless = body.get("headless", state.headless)
        _camoufox_ctx = AsyncCamoufox(headless=headless, geoip=True)
        browser = await _camoufox_ctx.__aenter__()
        page = await browser.new_page()
        await Stealth().apply_stealth_async(page)
        state.page = page

    state.refs = {}
    await state.page.goto(url)
    return ok({"url": url})


@app.post("/snapshot")
async def snapshot():
    if state.page is None:
        return err("No page open.")
    tree = await state.page.accessibility.snapshot()
    if tree is None:
        return ok({"text": "", "refs": {}})
    lines, ref_map = walk_tree(tree)
    state.refs = ref_map
    text = format_snapshot(lines)
    serializable_refs = {k: list(v) for k, v in ref_map.items()}
    return ok({"text": text, "refs": serializable_refs})


@app.post("/click")
async def click(body: dict):
    selector = body.get("selector", "")
    locator = resolve(selector)

    if state.humanize and state.profile:
        from humanize_browser.behaviour import _sample_lognormal, bezier_path

        box = await locator.bounding_box()
        if box:
            tx = box["x"] + box["width"] / 2
            ty = box["y"] + box["height"] / 2
            sx = tx + random.uniform(-80, 80)
            sy = ty + random.uniform(-80, 80)

            sp = state.profile.get("mouse_speed", {"mu": 1.0, "sigma": 0.3})
            speed = _sample_lognormal(sp["mu"], sp["sigma"])
            dist = math.sqrt((tx - sx) ** 2 + (ty - sy) ** 2)
            steps = max(int(dist / max(speed * 16, 1)), 3)

            for px, py in bezier_path((sx, sy), (tx, ty), steps):
                await state.page.mouse.move(px, py)

            dwell = state.profile.get("pre_click_dwell_ms", [180.0, 60.0])
            await asyncio.sleep(max(random.gauss(dwell[0], dwell[1]), 50) / 1000)
            await state.page.mouse.click(tx, ty)
            return ok()

    await locator.click()
    return ok()


@app.post("/type")
async def type_text(body: dict):
    selector = body.get("selector", "")
    text = body.get("text", "")
    locator = resolve(selector)
    await locator.click()

    if state.humanize and state.profile:
        from humanize_browser.behaviour import sample_key_delay

        prev_key = ""
        for char in text:
            delay = sample_key_delay(state.profile, prev_key, char)
            if delay > 0:
                await asyncio.sleep(delay / 1000)
            await state.page.keyboard.type(char)
            prev_key = char
        return ok()

    await locator.type(text)
    return ok()


@app.post("/screenshot")
async def screenshot(body: dict = {}):
    if state.page is None:
        return err("No page open.")
    path = body.get("path", "screenshot.png")
    await state.page.screenshot(path=path)
    return ok({"path": path})


@app.post("/wait")
async def wait(body: dict):
    if state.page is None:
        return err("No page open.")
    ms = body.get("ms")
    selector = body.get("selector")
    if ms is not None:
        await asyncio.sleep(int(ms) / 1000)
    elif selector:
        await state.page.wait_for_selector(selector)
    else:
        return err("Provide selector or ms.")
    return ok()


@app.post("/record/start")
async def record_start(body: dict):
    from humanize_browser.behaviour import RECORDINGS_DIR, RecordSession

    if state.page is None:
        return err("No page open.")

    global _record_session
    profile_name = body.get("profile", "default")
    RECORDINGS_DIR.mkdir(parents=True, exist_ok=True)
    path = RECORDINGS_DIR / f"{profile_name}.jsonl"
    _record_session = RecordSession(path)

    async def _on_event(data: dict) -> None:
        if _record_session:
            _record_session.write_event(data)

    await state.page.expose_function("__humanize_record", _on_event)
    await state.page.add_init_script("""
        const _rec = d => window.__humanize_record && window.__humanize_record(d);
        window.addEventListener('mousemove', e =>
            _rec({type:'mousemove', x:e.clientX, y:e.clientY, t:Date.now()}), {passive:true});
        window.addEventListener('mousedown', e =>
            _rec({type:'mousedown', x:e.clientX, y:e.clientY, button:e.button, t:Date.now()}));
        window.addEventListener('mouseup', e =>
            _rec({type:'mouseup', x:e.clientX, y:e.clientY, button:e.button, t:Date.now()}));
        window.addEventListener('keydown', e =>
            _rec({type:'keydown', key:e.key, t:Date.now()}));
        window.addEventListener('keyup', e =>
            _rec({type:'keyup', key:e.key, t:Date.now()}));
    """)
    return ok({"recording": str(path)})


_record_session: Any = None


@app.post("/record/stop")
async def record_stop():
    global _record_session
    if _record_session is None:
        return err("No active recording.")
    path = _record_session._path
    _record_session.close()
    _record_session = None
    return ok({"saved": str(path)})


@app.post("/record/aggregate")
async def record_aggregate(body: dict):
    from humanize_browser.behaviour import RECORDINGS_DIR, aggregate

    name = body.get("profile", "default")
    recording_path = RECORDINGS_DIR / f"{name}.jsonl"
    if not recording_path.exists():
        return err(f"No recording found for profile '{name}'")
    aggregate(recording_path, name=name)
    return ok({"profile": name, "saved": True})


@app.post("/profile/use")
async def profile_use(body: dict):
    name = body.get("name", "default")
    path = PROFILES_DIR / f"{name}.json"
    if not path.exists():
        return err(f"Profile '{name}' not found.")
    state.profile = json.loads(path.read_text())
    return ok({"profile": name})


@app.post("/shutdown")
async def shutdown():
    global _camoufox_ctx
    if state.page:
        await state.page.close()
        state.page = None
    if _camoufox_ctx:
        await _camoufox_ctx.__aexit__(None, None, None)
        _camoufox_ctx = None
    PID_FILE.unlink(missing_ok=True)
    asyncio.get_event_loop().call_later(0.1, lambda: os._exit(0))
    return ok()


def run_daemon(port: int, headless: bool = True) -> None:
    PROFILES_DIR.mkdir(parents=True, exist_ok=True)
    PID_FILE.parent.mkdir(parents=True, exist_ok=True)
    state.headless = headless
    PID_FILE.write_text(json.dumps({"port": port, "pid": os.getpid()}))
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="error")
```

- [ ] **Step 4: Create daemon entry module**

Create `humanize_browser/_daemon_entry.py`:

```python
import sys
from humanize_browser.daemon import run_daemon

if __name__ == "__main__":
    run_daemon(int(sys.argv[1]))
```

- [ ] **Step 5: Run integration tests**

```bash
uv run pytest tests/test_integration.py -v -m integration
```

Expected: all `PASSED`

- [ ] **Step 6: Commit**

```bash
git add humanize_browser/daemon.py humanize_browser/_daemon_entry.py
git commit -m "feat: daemon.py — FastAPI app with all endpoints"
```

---

## Task 5: cli.py — daemon lifecycle + HTTP dispatch

**Files:**
- Create: `humanize_browser/cli.py`
- Create: `tests/test_cli.py`

- [ ] **Step 1: Write failing unit tests**

Create `tests/test_cli.py`:

```python
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
```

- [ ] **Step 2: Run to verify they fail**

```bash
uv run pytest tests/test_cli.py -v
```

Expected: `ModuleNotFoundError: No module named 'humanize_browser.cli'`

- [ ] **Step 3: Implement cli.py**

Create `humanize_browser/cli.py`:

```python
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
        [sys.executable, "-m", "humanize_browser._daemon_entry", str(port)],
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

    flags = {"headed": args.headed, "no_humanize": args.no_humanize}
    cmd_list = args.command

    if not cmd_list or cmd_list[0] == "status":
        port, pid = read_pid_file()
        if port is None or not _is_alive(pid or 0):
            print("Daemon not running")
            return
        method, path, body = "GET", "/status", {}
    else:
        port = ensure_daemon(headless=not args.headed)
        method, path, body = build_request(cmd_list, flags)

    try:
        with httpx.Client() as client:
            if method == "GET":
                r = client.get(f"http://127.0.0.1:{port}{path}")
            else:
                r = client.post(f"http://127.0.0.1:{port}{path}", json=body)
        data = r.json()
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    output = format_output(data, args.json)
    if output:
        print(output)
    if not data.get("success"):
        sys.exit(1)
```

- [ ] **Step 4: Run unit tests**

```bash
uv run pytest tests/test_cli.py -v
```

Expected: all `PASSED`

- [ ] **Step 5: Add /config endpoint to daemon.py**

Add after the `/status` endpoint in `humanize_browser/daemon.py`:

```python
@app.post("/config")
async def config(body: dict):
    if "humanize" in body:
        state.humanize = bool(body["humanize"])
    return ok({"humanize": state.humanize})
```

- [ ] **Step 6: Wire --no-humanize in cli.py main()**

Replace the `else` branch in `main()` that calls `ensure_daemon`:

```python
else:
    port = ensure_daemon(headless=not args.headed)
    if args.no_humanize:
        httpx.post(f"http://127.0.0.1:{port}/config", json={"humanize": False})
    method, path, body = build_request(cmd_list, flags)
```

- [ ] **Step 7: Add test for /config**

Add to `tests/test_cli.py`:

```python
def test_build_request_status():
    from humanize_browser.cli import build_request

    method, path, _ = build_request(["status"], {})
    assert method == "GET"
    assert path == "/status"
```

- [ ] **Step 8: Verify entry point**

```bash
uv run humanize-browser status
```

Expected: `Daemon not running`

- [ ] **Step 9: Commit**

```bash
git add humanize_browser/cli.py tests/test_cli.py
git commit -m "feat: cli.py — daemon lifecycle, arg dispatch, HTTP client"
```

---

## Task 6: behaviour.py — RECORD + AGGREGATE + REPLAY

**Files:**
- Create: `humanize_browser/behaviour.py`
- Create: `tests/test_behaviour.py`

All three modes live in one file. RECORD writes JSONL. AGGREGATE fits statistical models. REPLAY generates Bezier mouse paths and per-bigram key delays.

- [ ] **Step 1: Write failing tests**

Create `tests/test_behaviour.py`:

```python
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
```

- [ ] **Step 2: Run to verify they fail**

```bash
uv run pytest tests/test_behaviour.py -v
```

Expected: `ModuleNotFoundError: No module named 'humanize_browser.behaviour'`

- [ ] **Step 3: Implement behaviour.py**

Create `humanize_browser/behaviour.py`:

```python
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
        "recorded_at": datetime.datetime.utcnow().isoformat() + "Z",
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
```

- [ ] **Step 4: Run all unit tests**

```bash
uv run pytest tests/test_behaviour.py tests/test_snapshot.py tests/test_cli.py -v
```

Expected: all `PASSED`

- [ ] **Step 5: Run full integration suite**

```bash
uv run pytest tests/test_integration.py -v -m integration
```

Expected: all `PASSED`

- [ ] **Step 6: End-to-end CLI smoke test**

```bash
uv run humanize-browser status
# Expected: Daemon not running

uv run humanize-browser open https://example.com
uv run humanize-browser snapshot
# Expected: accessibility tree with @refs

uv run humanize-browser close
```

- [ ] **Step 7: Commit**

```bash
git add humanize_browser/behaviour.py tests/test_behaviour.py
git commit -m "feat: behaviour.py — record/aggregate/replay (Bezier mouse, per-bigram typing)"
```

---

## End state

After all tasks, the full workflow works:

```bash
# Agent workflow (no humanize)
humanize-browser open https://example.com --no-humanize
humanize-browser snapshot
# [1] heading "Example Domain" @e1
# [2] link "More information..." @e2

humanize-browser click @e2 --no-humanize
humanize-browser close

# Record your own behaviour profile
humanize-browser open https://example.com --headed
humanize-browser record start --profile me
# → browse manually, mouse and keyboard captured
humanize-browser record stop
# → builds profile at ~/.humanize-browser/profiles/me.json

# Agent workflow with human behaviour layer
humanize-browser profile use me
humanize-browser open https://example.com
humanize-browser snapshot
humanize-browser click @e1        # Bezier mouse path + dwell time from profile
humanize-browser type @e2 "hello" # per-bigram delays from profile
humanize-browser close
```
