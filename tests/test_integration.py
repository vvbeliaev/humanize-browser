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
