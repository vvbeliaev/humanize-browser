# humanize-browser — Design Spec

**Date:** 2026-04-03
**Status:** Approved
**Goal:** A CLI browser automation tool that gives AI agents human-like browser access, built on Camoufox + playwright-stealth, with a behaviour middleware that replays recorded human interaction patterns.

---

## Problem

Agent-browser CLI is the best existing tool for giving AI agents browser access (daemon architecture, accessibility refs), but it uses stock Chrome with no local anti-detection. Building our own stack on Camoufox (patched Firefox, different JA3 fingerprint, canvas/WebGL noise) gives us the stealth layer. Adding a behaviour middleware that records real human interaction patterns and replays them with noise adds the human signal layer.

---

## Scope

`humanize-browser` is a CLI tool (and underlying Python library) that:
- Exposes `browser_*`-style commands that AI agents call via bash
- Runs a persistent local HTTP daemon holding a Camoufox browser session
- Intercepts every browser action through a BehaviourMiddleware that replays recorded human patterns

Out of scope for v1:
- MCP server mode
- Multiple simultaneous sessions
- Proxy support
- Mobile emulation

---

## Architecture

```
CLI (humanize-browser)
    │  HTTP (localhost)
    ▼
Daemon (FastAPI)
├── Session
│   ├── Camoufox browser + playwright-stealth
│   ├── Active page
│   └── RefStore: {@e1: locator, @e2: locator, ...}
│
├── BehaviourMiddleware
│   ├── RECORD  → writes MouseEvent/KeyEvent to JSONL
│   ├── AGGREGATE → builds Profile from recordings
│   └── REPLAY  → intercepts click/type, injects human noise
│
└── HTTP Endpoints
    POST /open        POST /click
    POST /snapshot    POST /type
    POST /screenshot  POST /record/start
    POST /wait        POST /record/stop
    GET  /status
```

### Daemon lifecycle

The CLI checks for a running daemon via `~/.humanize-browser/daemon.pid` (contains port + PID). Daemon binds to a random free port on startup and writes it to the PID file. CLI reads the port from the PID file. If the daemon is not running, CLI starts it as a subprocess, waits for `/status` to respond, then sends the command. Subsequent CLI calls go directly to the running daemon. Daemon shuts down on `humanize-browser close`.

---

## CLI Interface

```bash
# Core browser actions
humanize-browser open <url>
humanize-browser snapshot                      # accessibility tree with @refs
humanize-browser click <@ref|selector>
humanize-browser type <@ref|selector> <text>
humanize-browser screenshot [path]
humanize-browser wait <ms|selector>
humanize-browser close

# Behaviour recording
humanize-browser record start [--profile <name>]   # opens headed browser
humanize-browser record stop                        # builds and saves profile
humanize-browser profile use <name>                 # activate profile for replay

# Flags
--json          # machine-readable output: {"success": true, "data": {...}}
--headed        # show browser window
--no-humanize   # bypass behaviour middleware, raw Playwright
```

### Snapshot output

`snapshot` returns an accessibility tree with short stable refs. Agents use refs in subsequent commands instead of CSS selectors:

```
[1] heading "Example Domain" @e1
[2] link "More information..." @e2
```

Refs are invalidated on navigation (`open`). Always re-snapshot after page changes.

---

## Components

### `cli.py`
Argument parsing (argparse). Checks daemon liveness, starts it if needed, sends HTTP request, prints response. Entry point for the `humanize-browser` command.

### `daemon.py`
FastAPI application. Holds the single browser session. Each endpoint resolves the selector/ref, passes the action through BehaviourMiddleware, returns JSON result.

### `browser.py`
Camoufox + playwright-stealth setup. Responsible for launching the browser with all stealth patches applied. Returns a Playwright `Page` object.

### `snapshot.py`
Calls `page.accessibility.snapshot()`, walks the tree, assigns short `@e{n}` refs, formats output. Updates RefStore in the daemon session.

### `behaviour.py`
BehaviourMiddleware with three modes:

**RECORD:** Attaches CDP event listeners for mouse movement, mouse buttons, and keyboard. Writes raw events as JSONL to `~/.humanize-browser/recordings/<name>.jsonl`.

**AGGREGATE:** Reads a recording file. Builds a `Profile` — statistical models, not raw coordinates:
- `mouse_speed`: log-normal (μ, σ) fitted to recorded movement speeds
- `key_delays`: per-bigram (μ, σ) fitted to inter-key intervals
- `overshoot_prob`: fraction of clicks where cursor overshoots target
- `pre_click_dwell_ms`: (μ, σ) of hover time before click

**REPLAY:** For each browser action:
- `click(locator)` → compute element center, generate Bezier path from current position with speed sampled from profile, execute via `page.mouse.move()` + `page.mouse.click()` with dwell time
- `type(locator, text)` → type character by character with per-bigram delays sampled from profile; occasionally inject typo + backspace

Without a profile, or with `--no-humanize`, actions execute as raw Playwright calls.

---

## Profile format

Saved to `~/.humanize-browser/profiles/<name>.json`:

```json
{
  "name": "default",
  "recorded_at": "2026-04-03T12:00:00Z",
  "mouse_speed": {"mu": 1.2, "sigma": 0.3},
  "key_delays": {
    "default": [95, 18],
    "th": [72, 11],
    "he": [68, 9]
  },
  "overshoot_prob": 0.15,
  "pre_click_dwell_ms": [180, 60]
}
```

---

## File layout

```
humanize-browser/
├── humanize_browser/
│   ├── __init__.py
│   ├── cli.py          # entry point, arg parsing, daemon management
│   ├── daemon.py       # FastAPI app, session, endpoints
│   ├── browser.py      # Camoufox + stealth launch
│   ├── snapshot.py     # accessibility tree → refs
│   └── behaviour.py    # record / aggregate / replay
├── main.py             # smoke test (existing)
├── pyproject.toml
└── docs/
```

---

## Implementation order

| Phase | What | Notes |
|-------|------|-------|
| 1 | `browser.py` + `daemon.py` skeleton | Camoufox session, `/status` endpoint |
| 2 | `snapshot.py` + `/snapshot` endpoint | Ref system, core agent primitive |
| 3 | `cli.py` + daemon lifecycle | Auto-start, PID file, HTTP client |
| 4 | Remaining actions | `open`, `click`, `type`, `screenshot`, `wait` |
| 5 | `behaviour.py` RECORD | CDP listeners, JSONL writer |
| 6 | `behaviour.py` AGGREGATE | Statistical model fitting |
| 7 | `behaviour.py` REPLAY | Bezier mouse, per-bigram typing |
