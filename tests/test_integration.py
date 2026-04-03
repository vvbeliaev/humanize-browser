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
        await page.set_content("<h1>Hello</h1><a href='#'>Link</a>")
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
