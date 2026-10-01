"""Exercise the built dashboard with isolated, read-only HTTP fixtures."""
import copy
import mimetypes
import time
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / ".local/screenshots/calm"
OUT.mkdir(parents=True, exist_ok=True)
empty = dict(type="FeatureCollection", features=[])
epoch = time.time()
channels = [4, 8, 100]
norm = dict(status="partial", baseline_id="browser-fixture", available_channels=2, total_channels=3,
            training_start=epoch-86400, training_end=epoch-3600,
            channels=channels, times=[5, 15], starts=[0, 10], ends=[10, 20], training_frames=[True, False],
            scores={m: [[2, 20, None], [3, 4, None]] for m in ["ac_rms", "variance", "peak", "band_rms"]},
            raw={m: [[12, 120, 0], [13, 104, 0]] for m in ["ac_rms", "variance", "peak", "band_rms"]},
            medians={m: [10, 100, None] for m in ["ac_rms", "variance", "peak", "band_rms"]})
rec = dict(id=1, relative_path="fixture.hdf5", acquisition_epoch=epoch, dt=.01, samples=2000,
           unit="rad", lid=1, time_verified=True, mapping_verified=True, processing="stored values × dataScale",
           channel_count=3, first_channel=4)
metric = dict(recording_id=1, lid=1, metric="ac_rms", frame=0, frame_count=2, start=0, end=10, complete=True,
              unit="rad", acquisition_epoch=epoch, time_verified=True, scale=dict(min=0, max=120),
              mapping=dict(status="mapped", exact=3, interpolated=0, unmatched_recording=0),
              normalization=norm, data=dict(type="FeatureCollection", features=[
                  dict(type="Feature", id=ch, geometry=dict(type="Point", coordinates=[14+i*.001, 68]),
                       properties=dict(channel=ch, recording_channel=ch, run=1, lid=1, value=raw,
                                       calm_score=score, calm_median=median))
                  for i, (ch, raw, score, median) in enumerate(zip(channels, [12,120,0], [2,20,None], [10,100,None]))]))
signal = dict(recording_id=1, channel=4, unit="rad", processing=rec["processing"], time_verified=True,
              start=0, end=20, duration=20, sample_rate=100, acquisition_epoch=epoch,
              source_samples=2000, display_points=4, x=[0,1,2,3], y=[1,-1,2,-2],
              trend_time=[5,15], trend_start=0, trend_window_seconds=10,
              channel_rms=[[12,120,0],[13,104,0]], channel_variance=[[144,14400,0],[169,10816,0]],
              rms=[12,13], variance=[144,169], heat_time=[5,15], heat_channels=channels,
              channel_bounds=None, heat=[[12,13],[120,104],[0,0]], frequency=[1,2], power=[1,.5], normalization=norm)
raw_profile = dict(status="complete", channels=channels, values=[12,120,0], start=0, end=10)
raw_heat = dict(status="complete", channel_edges=[2,6,10,98,102], time_edges=[0,10,20],
                values=[[12,120,None,0],[13,104,None,0]], peak_channels=[[4,8,None,100],[4,8,None,100]])
live_norm = dict(norm, profile=dict(raw_profile, values=[2,20,None], raw=[12,120,None], medians=[10,100,None]),
                 heatmap=dict(raw_heat, values=[[2,20,None,None],[3,4,None,None]],
                              raw=raw_heat["values"], medians=[[10,100,None,None]]*2))
snapshot = dict(status="live", recording_id=1, frame=0, acquisition_epoch=epoch, published_at=epoch,
                mapping_verified=True, points=[], unit="rad", lid=1, channel_count=3, filename="fixture.hdf5",
                normalization=live_norm, profile=raw_profile, heatmap=raw_heat, detection=dict(status="not_configured"))
fixtures = {
    "/api/overview": dict(mapping_lids=[1], counts=dict(events=0,unclassified=0,masts=0,spans=0,recordings=1,aligned=0),
                          classes=[],routes=[],stations=[],environment="Browser fixture",write_enabled=False),
    "/api/map": dict(masts=metric["data"], spans=empty), "/api/recordings": [rec],
    "/api/events": dict(items=[],total=0), "/api/map/events": dict(data=empty),
    "/api/map/wind": dict(stations=[]), "/api/fibre": empty, "/api/live": snapshot,
    "/api/recordings/1/metrics": metric, "/api/recordings/1/signal": signal,
    "/api/recordings/1/channels": channels,
}

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--enable-unsafe-swiftshader"])
    page = browser.new_page(viewport=dict(width=1536,height=1100))
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    def route(request):
        url = urlparse(request.request.url)
        if url.netloc != "calm.test":
            request.abort(); return
        if url.path.startswith("/api/"):
            request.fulfill(json=fixtures.get(url.path, {})); return
        path = ROOT / "web/dist" / (url.path.lstrip("/") or "index.html")
        request.fulfill(path=str(path), content_type=mimetypes.guess_type(path)[0] or "application/octet-stream")
    page.route("**/*", route)
    page.goto("http://calm.test/", wait_until="networkidle")
    if errors:
        raise AssertionError(errors)
    page.screenshot(path=str(OUT / "startup.png"), full_page=True)
    panel = page.locator("#signal-investigation")
    expect(panel.get_by_label("Activity normalization")).to_have_value("calm")
    # Waveform stays physical even with calm mode selected.
    page.wait_for_function("document.querySelector('#signal-investigation .js-plotly-plot')?.data?.[0]?.y?.[0] === 1")
    panel.get_by_role("button", name="AC RMS", exact=True).click()
    page.wait_for_function("document.querySelector('#signal-investigation .js-plotly-plot')?.data?.[0]?.y?.[1] === 20")
    panel.get_by_role("button", name="Heatmap", exact=True).click()
    page.wait_for_function("document.querySelector('#signal-investigation .js-plotly-plot')?.data?.[0]?.zmax === 10")
    chart = panel.locator(".js-plotly-plot")
    assert chart.evaluate("e => e.data[0].z[1][0]") == 20
    assert chart.evaluate("e => e.data[0].z[2][0]") is None
    panel.get_by_label("Activity normalization").select_option("raw")
    page.wait_for_function("document.querySelector('#signal-investigation .js-plotly-plot')?.data?.[0]?.z?.[1]?.[0] === 120")
    panel.get_by_label("Activity normalization").select_option("calm")
    panel.get_by_role("button", name="AC RMS", exact=True).click()
    panel.get_by_label("Selected-channel time trend").check()
    page.wait_for_function("document.querySelector('#signal-investigation .js-plotly-plot')?.data?.[0]?.x?.[1] === 15")
    page.screenshot(path=str(OUT / "investigation.png"), full_page=True)
    page.get_by_role("button", name="Live monitor", exact=True).click()
    page.wait_for_function("document.querySelector('.live-card .js-plotly-plot')?.data?.[0]?.y?.[1] === 20")
    expect(page.get_by_label("Activity normalization")).to_have_value("calm")
    live_heat = page.locator(".live-card .js-plotly-plot").nth(1)
    assert live_heat.evaluate("e => e.data[0].zmax") == 10
    page.get_by_label("Activity normalization").select_option("raw")
    page.wait_for_function("document.querySelector('.live-card .js-plotly-plot')?.data?.[0]?.y?.[1] === 120")
    page.get_by_label("Activity normalization").select_option("calm")
    page.screenshot(path=str(OUT / "live.png"), full_page=True)
    page.set_viewport_size(dict(width=390,height=844))
    page.wait_for_timeout(300)
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth"), "Mobile overflow"
    page.screenshot(path=str(OUT / "mobile.png"), full_page=True)
    # Explicit calm choice never silently switches back to raw when references disappear.
    fixtures["/api/live"] = dict(snapshot, normalization=dict(status="unavailable", available_channels=0, note="No compatible calm reference"))
    page.wait_for_timeout(5500)
    expect(page.get_by_label("Activity normalization")).to_have_value("calm")
    assert page.locator(".live-card .js-plotly-plot").count() == 0
    assert not errors, errors
    browser.close()
print("Calm browser checks passed: investigation, live, raw toggle, fixed colors, gaps, missing references, mobile")
