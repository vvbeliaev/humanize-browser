from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

from camoufox.async_api import AsyncCamoufox
from playwright.async_api import Page
from playwright_stealth import Stealth

_stealth = Stealth()


async def setup_browser(headless: bool = True) -> tuple[Any, Page]:
    """Start Camoufox and return (ctx, page) for manual lifecycle management."""
    ctx = AsyncCamoufox(headless=headless, geoip=True)
    browser = await ctx.__aenter__()
    page = await browser.new_page()
    await _stealth.apply_stealth_async(page)
    return ctx, page


@asynccontextmanager
async def launch_browser(headless: bool = True) -> AsyncIterator[Page]:
    """Launch Camoufox with stealth patches applied. Yields a ready Page."""
    async with AsyncCamoufox(headless=headless, geoip=True) as browser:
        page = await browser.new_page()
        await _stealth.apply_stealth_async(page)
        try:
            yield page
        finally:
            await page.close()
1