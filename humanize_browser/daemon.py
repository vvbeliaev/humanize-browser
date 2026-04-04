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

from humanize_browser.snapshot import format_snapshot, walk_tree

PROFILES_DIR = Path.home() / ".humanize-browser" / "profiles"
PID_FILE = Path.home() / ".humanize-browser" / "daemon.pid"

# Module-level Camoufox handle kept alive for the daemon lifetime
_camoufox_ctx: Any = None
_record_session: Any = None


@dataclass
class AppState:
    page: Any = None  # playwright Page
    refs: dict[str, tuple[str, str, int]] = field(default_factory=dict)
    headless: bool = True
    humanize: bool = True
    profile: dict[str, Any] | None = None
    profile_dir: Path | None = None
    pid_file: Path = field(default_factory=lambda: PID_FILE)


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
        from humanize_browser.browser import setup_browser

        headless = body.get("headless", state.headless)
        _camoufox_ctx, page = await setup_browser(
            headless=headless, profile_dir=state.profile_dir
        )
        state.page = page

    state.refs = {}
    await state.page.goto(url)
    return ok({"url": url})


_AX_SNAPSHOT_JS = """() => {
    const tagToRole = {
        a: 'link', button: 'button',
        h1: 'heading', h2: 'heading', h3: 'heading',
        h4: 'heading', h5: 'heading', h6: 'heading',
        select: 'combobox', textarea: 'textbox', img: 'img',
    };
    const getRole = (el) => {
        const aria = el.getAttribute('role');
        if (aria) return aria;
        const tag = el.tagName.toLowerCase();
        if (tag === 'input') {
            const t = (el.getAttribute('type') || 'text').toLowerCase();
            if (t === 'checkbox') return 'checkbox';
            if (t === 'radio') return 'radio';
            if (t === 'submit' || t === 'button' || t === 'reset') return 'button';
            return 'textbox';
        }
        return tagToRole[tag] || null;
    };
    const getName = (el) => (
        el.getAttribute('aria-label') ||
        el.getAttribute('alt') ||
        el.getAttribute('title') ||
        el.textContent.trim().slice(0, 80) || ''
    );
    const getState = (el) => {
        const s = {};
        if (el.disabled) s.disabled = true;
        if (el.checked !== undefined && el.checked) s.checked = true;
        if (el.getAttribute('aria-checked') === 'true') s.checked = true;
        if (el.getAttribute('aria-selected') === 'true') s.selected = true;
        if (el.getAttribute('aria-expanded') !== null)
            s.expanded = el.getAttribute('aria-expanded') === 'true';
        return Object.keys(s).length ? s : null;
    };
    const nodes = [];
    document.querySelectorAll(
        'a,button,h1,h2,h3,h4,h5,h6,input,select,textarea,img,[role]'
    ).forEach(el => {
        const role = getRole(el);
        const name = getName(el);
        if (!role || !name) return;
        const node = {role, name};
        const st = getState(el);
        if (st) node.state = st;
        nodes.push(node);
    });
    return nodes;
}"""


@app.post("/snapshot")
async def snapshot():
    if state.page is None:
        return err("No page open.")
    raw_nodes: list[dict] = await state.page.evaluate(_AX_SNAPSHOT_JS)
    if not raw_nodes:
        return ok({"text": "", "refs": {}})
    tree = {"role": "root", "name": "", "children": raw_nodes}
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


@app.post("/fill")
async def fill(body: dict):
    selector = body.get("selector", "")
    text = body.get("text", "")
    locator = resolve(selector)
    await locator.fill(text)
    return ok()


@app.post("/hover")
async def hover(body: dict):
    selector = body.get("selector", "")
    locator = resolve(selector)
    await locator.hover()
    return ok()


@app.post("/screenshot")
async def screenshot(body: dict | None = None):
    body = body or {}
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
    await state.page.add_init_script(
        """
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
    """
    )
    return ok({"recording": str(path)})


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


@app.post("/scroll")
async def scroll(body: dict):
    if state.page is None:
        return err("No page open.")
    direction = body.get("direction", "down")
    amount = int(body.get("amount", 300))
    selector = body.get("selector")

    delta_x = amount if direction == "right" else -amount if direction == "left" else 0
    delta_y = amount if direction == "down" else -amount if direction == "up" else 0

    if selector:
        locator = resolve(selector)
        await locator.evaluate(f"el => el.scrollBy({delta_x}, {delta_y})")
    else:
        await state.page.mouse.wheel(delta_x, delta_y)
    return ok()


@app.post("/eval")
async def eval_js(body: dict):
    if state.page is None:
        return err("No page open.")
    expression = body.get("expression", "")
    if not expression:
        return err("expression required")
    result = await state.page.evaluate(expression)
    if isinstance(result, (dict, list)):
        value = json.dumps(result)
    elif result is None:
        value = ""
    else:
        value = str(result)
    return ok({"value": value})


@app.post("/select")
async def select(body: dict):
    selector = body.get("selector", "")
    value = body.get("value", "")
    locator = resolve(selector)
    await locator.select_option(value)
    return ok()


@app.post("/config")
async def config(body: dict):
    if "humanize" in body:
        state.humanize = bool(body["humanize"])
    if "profile_dir" in body:
        raw = body["profile_dir"]
        state.profile_dir = Path(raw) if raw else None
    return ok({"humanize": state.humanize})


@app.post("/shutdown")
async def shutdown():
    global _camoufox_ctx
    if state.page:
        await state.page.close()
        state.page = None
    if _camoufox_ctx:
        await _camoufox_ctx.__aexit__(None, None, None)
        _camoufox_ctx = None
    state.pid_file.unlink(missing_ok=True)
    asyncio.get_event_loop().call_later(0.1, lambda: os._exit(0))
    return ok()


def run_daemon(port: int, headless: bool = True, pid_file: Path | None = None) -> None:
    resolved_pid_file = pid_file or PID_FILE
    PROFILES_DIR.mkdir(parents=True, exist_ok=True)
    resolved_pid_file.parent.mkdir(parents=True, exist_ok=True)
    state.headless = headless
    state.pid_file = resolved_pid_file
    resolved_pid_file.write_text(json.dumps({"port": port, "pid": os.getpid()}))
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="error")
