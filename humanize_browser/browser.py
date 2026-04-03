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
