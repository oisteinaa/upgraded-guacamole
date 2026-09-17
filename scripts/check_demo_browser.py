"""Read-only real-demo smoke test. No fixtures, no publication, no database writes."""
import os
from pathlib import Path
import time

from playwright.sync_api import sync_playwright, expect

base = os.getenv("DAS_BROWSER_URL", "http://127.0.0.1:8053")
out = Path(".local/screenshots/demo-monitor")
out.mkdir(parents=True, exist_ok=True)
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--enable-unsafe-swiftshader"])
    page = browser.new_page(viewport={"width": 1536, "height": 1100})
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(base, wait_until="domcontentloaded")
    page.get_by_role("button", name="Live monitor", exact=True).click()
    expect(page.locator(".live-status h2")).to_have_text("Demo replay · looping archive", timeout=120000)
    expect(page.locator(".live-insights .js-plotly-plot")).to_have_count(2, timeout=30000)
    expect(page.locator(".live-status")).to_contain_text("DEMONSTRATION · NOT LIVE ACQUISITION")
    expect(page.locator(".live-status")).to_contain_text("Original acquisition")
    expect(page.locator(".live-detection")).to_contain_text("Disabled in demo")
    expect(page.locator(".live-map-toolbar")).to_contain_text("illustrative mapping")
    first = page.request.get(base + "/api/live").json()
    assert first["status"] == "demo" and first["replay"] and first["demo"]
    assert not first["time_verified"] and not first["mapping_verified"]
    assert time.time() - first["acquisition_epoch"] > 3600
    metric = page.request.get(base + "/api/demo/metrics/" + first["demo_token"]).json()
    assert metric["recording_id"] == first["recording_id"]
    assert len(metric["data"]["features"]) > 0
    print("Demo source:", first["demo_source"], "file:", first["filename"], "mapped channels:", len(metric["data"]["features"]), flush=True)
    page.screenshot(path=str(out / "desktop.png"))
    page.set_viewport_size({"width": 390, "height": 844})
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    page.screenshot(path=str(out / "mobile.png"), full_page=True)
    page.set_viewport_size({"width": 1536, "height": 1100})
    # Observe the real publisher changing files while the monitor stays populated.
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        current = page.request.get(base + "/api/live").json()
        if current.get("filename") != first["filename"] and current["status"] == "demo":
            break
        page.wait_for_timeout(1000)
    else:
        raise AssertionError("Demo did not advance to another file")
    expect(page.locator(".live-status")).to_contain_text(current["filename"], timeout=15000)
    expect(page.locator(".live-insights .js-plotly-plot")).to_have_count(2)
    page.get_by_role("button", name="Investigate", exact=True).click()
    expect(page.locator(".live-workspace")).to_have_count(0)
    assert not errors, errors
    print("Real demo advanced:", first["filename"], "→", current["filename"], "; desktop/mobile and mode switching passed", flush=True)
    browser.close()
