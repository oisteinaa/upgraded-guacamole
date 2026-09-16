"""Read-only browser smoke test against the local app."""

import json
from pathlib import Path

from playwright.sync_api import sync_playwright

out = Path(".local/screenshots")
out.mkdir(parents=True, exist_ok=True)
with sync_playwright() as p:
    browser = p.chromium.launch(
        headless=True, args=["--no-sandbox", "--enable-unsafe-swiftshader"]
    )
    page = browser.new_page(
        viewport={"width": 1536, "height": 1150}, device_scale_factor=1
    )
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto("http://127.0.0.1:8051", wait_until="networkidle")
    page.locator(".event-item").first.wait_for()
    page.locator(".map-wrap[data-ready=true]").wait_for(timeout=30000)
    assert page.locator(".maplibregl-canvas").bounding_box()["height"] > 300
    page.locator(".js-plotly-plot").wait_for(timeout=30000)
    page.screenshot(path=str(out / "overview.png"), full_page=True)
    page.locator(".event-item").first.click()
    page.get_by_label("Review classification").wait_for()
    assert page.get_by_text("No verified recording linked to this event").is_visible()
    page.screenshot(path=str(out / "event.png"), full_page=True)
    page.get_by_role("button", name="Recording browser", exact=True).click()
    page.locator(".js-plotly-plot").wait_for()
    page.get_by_role("button", name="Heatmap", exact=True).click()
    page.wait_for_timeout(1000)
    page.screenshot(path=str(out / "heatmap.png"), full_page=True)
    page.get_by_role("button", name="Spectrum", exact=True).click()
    page.get_by_label("Find mast").fill("R06 M12")
    page.locator(".asset-results button").first.click()
    page.get_by_role("heading", name="Asset details").wait_for()
    page.get_by_role("button", name="Live monitor", exact=True).click()
    page.locator(".live-bar").wait_for()
    page.get_by_role("button", name="Investigate", exact=True).click()
    page.get_by_label("Classification filter").select_option("3")
    page.get_by_text("No matching events", exact=True).wait_for()
    page.get_by_role("button", name="Reset filters").click()
    page.locator(".event-item").first.wait_for()
    page.set_viewport_size({"width": 390, "height": 844})
    page.wait_for_timeout(600)
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth"), (
        "Mobile layout overflows"
    )
    page.screenshot(path=str(out / "mobile.png"), full_page=True)
    browser.close()
    print(json.dumps({"page_errors": errors, "screenshots": str(out)}, indent=2))
    assert not errors
