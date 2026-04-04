from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator

from camoufox.async_api import AsyncCamoufox
from playwright.async_api import Page
from playwright_stealth import Stealth

_stealth = Stealth()


async def setup_browser(
    headless: bool = True, profile_dir: Path | None = None
) -> tuple[Any, Page]:
    """Start Camoufox and return (ctx, page) for manual lifecycle management.

    If profile_dir is given, launches a persistent Firefox context so that
    all browser state (cookies, IndexedDB, localStorage, service workers) is
    preserved across daemon restarts.
    """
    if profile_dir is not None:
        profile_dir.mkdir(parents=True, exist_ok=True)
        ctx = AsyncCamoufox(
            headless=headless,
            geoip=True,
            persistent_context=True,
            user_data_dir=str(profile_dir),
        )
        # persistent_context=True → __aenter__ returns BrowserContext directly
        context = await ctx.__aenter__()
    else:
        ctx = AsyncCamoufox(headless=headless, geoip=True)
        browser = await ctx.__aenter__()
        context = await browser.new_context()

    page = await context.new_page()
    await _stealth.apply_stealth_async(page)
    return ctx, page


@asynccontextmanager
async def launch_browser(headless: bool = True) -> AsyncIterator[Page]:
    """Launch Camoufox with stealth patches applied. Yields a ready Page."""
    async with AsyncCamoufox(headless=headless, geoip=True) as browser:
        context = await browser.new_context()
        page = await context.new_page()
        await _stealth.apply_stealth_async(page)
        try:
            yield page
        finally:
            await page.close()
1