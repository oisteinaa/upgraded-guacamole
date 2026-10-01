"""Read-only check of real deployed normalization, without HTTP fixtures."""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

out = Path(".local/screenshots/calm-deployed")
out.mkdir(parents=True, exist_ok=True)
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--enable-unsafe-swiftshader"])
    page = browser.new_page(viewport={"width":1536,"height":1100})
    errors=[]
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto("http://10.147.20.10:8051", wait_until="domcontentloaded")
    panel=page.locator("#signal-investigation")
    expect(panel.get_by_label("Activity normalization")).to_have_value("calm", timeout=60000)
    panel.get_by_role("button",name="AC RMS",exact=True).click()
    page.wait_for_function("document.querySelector('#signal-investigation .js-plotly-plot')?.data?.[0]?.customdata?.length > 0",timeout=30000)
    signal=panel.locator(".js-plotly-plot").evaluate("e => ({points:e.data[0].y.length,first:e.data[0].y.find(v=>v!=null),unit:e.layout.yaxis.title.text})")
    assert signal["unit"] == "Departure from calm reference"
    page.screenshot(path=str(out/"investigation.png"),full_page=True)
    panel.get_by_role("button",name="Waveform",exact=True).click()
    page.wait_for_function("document.querySelector('#signal-investigation .js-plotly-plot')?.layout?.yaxis?.title?.text === 'rad/(m*s)'")
    page.get_by_role("button",name="Live monitor",exact=True).click()
    expect(page.get_by_label("Activity normalization")).to_have_value("calm",timeout=60000)
    page.wait_for_function("document.querySelectorAll('.live-card .js-plotly-plot')[1]?.data?.[0]?.zmax === 10",timeout=30000)
    expect(page.locator(".live-status h2")).to_have_text("Live capture")
    live=page.locator(".live-card .js-plotly-plot").first.evaluate("e => ({points:e.data[0].y.length,first:e.data[0].y.find(v=>v!=null),unit:e.layout.yaxis.title.text})")
    assert live["unit"] == "Calm score"
    page.screenshot(path=str(out/"live.png"),full_page=True)
    page.get_by_label("Activity normalization").select_option("raw")
    page.wait_for_function("document.querySelector('.live-card .js-plotly-plot')?.layout?.yaxis?.title?.text === 'AC RMS'")
    assert not errors,errors
    browser.close()
report=dict(signal=signal,live=live,page_errors=errors,raw_switch=True,waveform_physical_units=True)
Path("results/calm-baseline-20261001/browser-verification.json").write_text(json.dumps(report,indent=2))
print(json.dumps(report,indent=2))
