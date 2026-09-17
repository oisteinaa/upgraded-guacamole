"""Read-only browser verification; live samples are isolated HTTP fixtures."""
import copy
import os
import time
from pathlib import Path

from playwright.sync_api import sync_playwright, expect

BASE = os.getenv("DAS_BROWSER_URL", "http://127.0.0.1:8051")
OUT = Path(".local/screenshots/live-monitor")
OUT.mkdir(parents=True, exist_ok=True)

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--enable-unsafe-swiftshader"])
    page = browser.new_page(viewport={"width": 1536, "height": 1100})
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(BASE, wait_until="networkidle")
    page.get_by_role("button", name="Live monitor", exact=True).click()
    page.locator(".map-wrap[data-ready=true]").wait_for(timeout=30000)
    page.screenshot(path=str(OUT / "actual-desktop.png"))
    assert page.locator(".live-insights .live-card").count() == 3
    map_box = page.locator(".live-map-panel").bounding_box()
    column = page.locator(".live-insights").bounding_box()
    assert 1.9 < map_box["width"] / column["width"] < 2.1

    now = time.time()
    snapshot = dict(status="live", recording_id=900001, filename="browser-fixture.hdf5", frame=0,
                    summary_version=1, acquisition_epoch=now, published_at=now, lid=1,
                    mapping_verified=True, channel_count=5, points=[], unit="rad/(m*s)",
                    duration=10, metric_processing="scaled-ac-v1",
                    profile=dict(status="complete", start=0, end=10,
                                 channels=[0, 4, 8, None, 100, 104], values=[1, 2, 9, None, 3, 1]),
                    heatmap=dict(status="complete", channel_edges=[-2, 2, 6, 10, 98, 102, 106],
                                 time_edges=[0, 5, 10], values=[[1, 2, 9, None, 3, 1], [2, 4, 8, None, 1, 2]],
                                 peak_channels=[[0, 4, 8, None, 100, 104], [0, 4, 8, None, 100, 104]],
                                 aggregation="Maximum per-channel AC RMS in each time/channel bin"),
                    detection=dict(status="complete", evaluated_channels=4, requested_channels=4,
                                   total_channels=5, candidate_count=1, unit="rad/(m*s)",
                                   metric="Whole-file RMS (mean included)",
                                   candidates=[dict(channel=8, value=12, threshold=10, ratio=1.2, rule="Fixture only")]))
    metric = dict(recording_id=900001, frame=0, lid=1, metric="ac_rms", unit=snapshot["unit"],
                  start=0, end=10, acquisition_epoch=now, time_verified=True,
                  scale=dict(min=0, max=9), mapping={}, data=dict(type="FeatureCollection", features=[
                      dict(type="Feature", id=ch, geometry=dict(type="Point", coordinates=[14.05+i*.001, 68.18]),
                           properties=dict(channel=ch, recording_channel=ch, value=value, lid=1, run=0))
                      for i, (ch, value) in enumerate([(0, 1), (4, 2), (8, 9), (100, 3), (104, 1)])]))
    state = {"snapshot": snapshot, "metric": metric, "fail": False, "delay": False, "pending": []}
    def live_route(route):
        if state["fail"]:
            route.abort()
        else:
            route.fulfill(json=state["snapshot"])
    def metric_route(route):
        if state["delay"]:
            state["pending"].append(route)
        else:
            route.fulfill(json=state["metric"])
    page.route("**/api/live", live_route)
    page.route("**/api/recordings/*/metrics?*", metric_route)
    page.clock.install()
    def poll():
        page.clock.fast_forward(5100)
        page.wait_for_timeout(300)
    poll()
    expect(page.locator(".live-status h2")).to_have_text("Live capture")
    page.locator(".live-card .js-plotly-plot").first.wait_for()
    expect(page.locator(".live-candidate-count")).to_contain_text("1 candidate channel")
    page.get_by_role("button", name="Ch 8", exact=False).click()
    expect(page.get_by_label("Highlight live channel")).to_have_value("8")
    expect(page.locator(".live-selection")).to_contain_text("Highlighted on map")
    # A real scatter-point click selects a channel and updates the map highlight.
    page.locator(".live-card .scatterlayer .point").first.click(force=True)
    expect(page.get_by_label("Highlight live channel")).to_have_value("0")
    page.screenshot(path=str(OUT / "fixture-desktop.png"))
    assert page.locator(".live-card .js-plotly-plot").nth(1).evaluate("el => el.data[0].z[0][3]") is None

    # Keep the displayed file coherent while the replacement map request is pending.
    state["snapshot"] = copy.deepcopy(snapshot)
    state["snapshot"].update(recording_id=900002, filename="next-fixture.hdf5")
    state["metric"] = {**metric, "recording_id": 900002, "scale": {"min": 0, "max": 90}}
    state["delay"] = True
    poll()
    expect(page.locator(".live-status")).to_contain_text("browser-fixture.hdf5")
    assert state["pending"]
    state["pending"].pop().fulfill(json=state["metric"])
    state["delay"] = False
    expect(page.locator(".live-status")).to_contain_text("next-fixture.hdf5")
    assert page.locator(".live-card .js-plotly-plot").nth(1).evaluate("el => el.data[0].zmax") == 9
    page.get_by_role("button", name="Rescale", exact=True).click()
    page.wait_for_function("document.querySelectorAll('.live-card .js-plotly-plot')[1].data[0].zmax === 90")

    page.set_viewport_size({"width": 390, "height": 844})
    page.screenshot(path=str(OUT / "fixture-mobile.png"), full_page=True)
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    assert page.locator(".live-insights").bounding_box()["y"] > page.locator(".live-map-panel").bounding_box()["y"]
    page.set_viewport_size({"width": 1536, "height": 1100})
    page.clock.fast_forward(31000)
    expect(page.locator(".live-status h2")).to_have_text("Capture is stale")
    assert page.locator(".live-card .js-plotly-plot").count() == 0
    assert page.locator(".live-candidates button").count() == 0

    def refresh_times():
        epoch = page.evaluate("Date.now()/1000")
        state["snapshot"].update(acquisition_epoch=epoch, published_at=epoch)
        state["metric"]["acquisition_epoch"] = epoch
    for detection_status in ["not_configured", "processing", "failed", "unavailable"]:
        refresh_times()
        state["snapshot"]["detection"] = {"status": detection_status}
        poll()
        expect(page.locator(".detection-badge")).to_have_text({"not_configured": "Not configured", "processing": "Processing", "failed": "Failed", "unavailable": "Unavailable"}[detection_status])
    refresh_times()
    state["snapshot"]["detection"] = {**snapshot["detection"], "candidate_count": 0, "candidates": []}
    poll()
    expect(page.locator(".live-detection")).to_contain_text("No threshold exceedances in evaluated channels")
    refresh_times()
    for field in ["detection", "heatmap", "profile"]:
        state["snapshot"].pop(field, None)
    poll()
    expect(page.locator(".detection-badge")).to_have_text("Unavailable")
    expect(page.locator(".live-insights")).to_contain_text("Activity summary unavailable")
    for status in ["replay", "unverified", "offline"]:
        state["snapshot"]["status"] = status
        poll()
        assert page.locator(".live-card .js-plotly-plot").count() == 0
        expect(page.locator(".live-detection")).to_contain_text("Waiting for current live signal")
    state["fail"] = True
    poll()
    expect(page.locator(".live-status h2")).to_have_text("Connection unavailable")
    page.get_by_role("button", name="Investigate", exact=True).click()
    expect(page.locator(".live-workspace")).to_have_count(0)
    assert not errors, errors
    print("Live desktop/mobile, chart selection, coherent replacement, scale lock, freshness, detection states and mode switching passed")
    browser.close()
