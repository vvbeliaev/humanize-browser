"""
Smoke test: verifies camoufox + playwright-stealth stack is working.
Checks that navigator.webdriver is patched and fingerprint signals look human.
"""

import asyncio
import json

from camoufox.async_api import AsyncCamoufox
from playwright_stealth import Stealth

stealth = Stealth()


async def smoke_test() -> None:
    print("Starting smoke test...\n")

    async with AsyncCamoufox(headless=True, geoip=True) as browser:
        page = await browser.new_page()
        await stealth.apply_stealth_async(page)

        # 1. navigator.webdriver must be False or undefined
        webdriver = await page.evaluate("navigator.webdriver")
        status = "PASS" if not webdriver else "FAIL"
        print(f"[{status}] navigator.webdriver = {webdriver!r}")

        # 2. User agent must not contain 'Headless'
        ua = await page.evaluate("navigator.userAgent")
        headless_in_ua = "Headless" in ua or "headless" in ua
        status = "PASS" if not headless_in_ua else "FAIL"
        print(f"[{status}] userAgent = {ua!r}")

        # 3. Canvas fingerprint: camoufox injects noise — should return non-empty data
        canvas_data = await page.evaluate(
            """() => {
            const c = document.createElement('canvas');
            const ctx = c.getContext('2d');
            ctx.fillText('test', 10, 10);
            return c.toDataURL().length;
        }"""
        )
        status = "PASS" if canvas_data > 0 else "FAIL"
        print(f"[{status}] canvas dataURL length = {canvas_data}")

        # 4. Chrome object: real Chrome has window.chrome, headless Chrome used to lack it
        chrome_obj = await page.evaluate("typeof window.chrome")
        status = "PASS" if chrome_obj == "object" else "WARN"
        print(f"[{status}] typeof window.chrome = {chrome_obj!r}")

        # 5. Permissions API: headless Chrome returns 'denied' for notifications
        perm_state = await page.evaluate(
            """async () => {
            const result = await navigator.permissions.query({ name: 'notifications' });
            return result.state;
        }"""
        )
        status = "PASS" if perm_state != "denied" else "WARN"
        print(f"[{status}] notifications permission = {perm_state!r}")

        # 6. Plugin count: real browsers have plugins, headless has 0
        plugin_count = await page.evaluate("navigator.plugins.length")
        status = "PASS" if plugin_count > 0 else "WARN"
        print(f"[{status}] navigator.plugins.length = {plugin_count}")

        await page.close()

    print("\nSmoke test complete.")


if __name__ == "__main__":
    asyncio.run(smoke_test())
