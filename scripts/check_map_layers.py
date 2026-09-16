"""Read-only checks for signal layers, map picking, scale locking and playback."""
import base64
import json
from pathlib import Path
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser=p.chromium.launch(headless=True,args=['--no-sandbox','--enable-unsafe-swiftshader'])
    page=browser.new_page(viewport={'width':1536,'height':1150})
    errors=[];metric_requests=[]
    page.on('pageerror',lambda e:errors.append(str(e)))
    page.on('request',lambda r:metric_requests.append(r.url) if '/metrics?' in r.url else None)
    page.goto('http://127.0.0.1:8051',wait_until='networkidle')
    page.get_by_text('17,010 exact + 8,224 interpolated',exact=False).wait_for(timeout=60000)
    assert page.get_by_label('Map signal layer').input_value()=='ac_rms'
    limits=page.get_by_label('Color maximum').input_value()
    # Pick an actual warm-colored signal point from a screenshot of the map canvas.
    canvas=page.locator('.maplibregl-canvas');box=canvas.bounding_box()
    png=base64.b64encode(canvas.screenshot()).decode()
    pixel=page.evaluate('''async png=>{const img=new Image();img.src='data:image/png;base64,'+png;await img.decode();const c=document.createElement('canvas');c.width=img.width;c.height=img.height;const ctx=c.getContext('2d');ctx.drawImage(img,0,0);const d=ctx.getImageData(0,0,c.width,c.height).data;let best=null,score=Infinity;for(let y=70;y<c.height-120;y++)for(let x=230;x<c.width-140;x++){const i=(y*c.width+x)*4;if(d[i]>175&&d[i+1]>115&&d[i+1]<220&&d[i+2]>85&&d[i+2]<165){const s=(x-c.width/2)**2+(y-c.height/2)**2;if(s<score){score=s;best={x,y};}}}return best;}''',png)
    assert pixel,'No colormapped signal points rendered'
    page.mouse.click(box['x']+pixel['x'],box['y']+pixel['y'])
    page.get_by_text('RECORDED SIGNAL',exact=True).wait_for()
    assert int(page.get_by_label('Channel ID',exact=True).input_value())>0
    before=len(metric_requests)
    page.get_by_role('button',name='Zoom in',exact=True).click()
    page.wait_for_timeout(500)
    assert len(metric_requests)==before,'Map zoom recalculated analysis metrics'
    page.get_by_label('Next signal frame').click()
    page.wait_for_function("document.querySelector('.metric-status').textContent.includes('17,010 exact')")
    assert page.get_by_label('Recording',exact=True).input_value()=='2'
    assert page.get_by_label('Color maximum').input_value()==limits,'Playback changed locked limits'
    page.get_by_label('Map signal layer').select_option('peak')
    page.wait_for_function("document.querySelector('.metric-status').textContent.includes('17,010 exact')")
    page.get_by_label('Map signal layer').select_option('variance')
    page.wait_for_function("document.querySelector('.metric-status').textContent.includes('17,010 exact')")
    assert '²' in page.locator('.color-legend').inner_text()
    page.get_by_label('Map signal layer').select_option('band_rms')
    page.get_by_label('Band low frequency').fill('3')
    page.get_by_label('Band high frequency').fill('10')
    page.get_by_role('button',name='Apply band',exact=True).click()
    page.wait_for_function("document.querySelector('.metric-status').textContent.includes('17,010 exact')",timeout=60000)
    page.get_by_label('Color scale',exact=True).select_option('log')
    assert float(page.get_by_label('Color minimum').input_value())>0
    page.get_by_label('Color maximum').fill('25')
    page.get_by_role('button',name='Set limits',exact=True).click()
    assert page.get_by_label('Color maximum').input_value()=='25'
    page.get_by_label('Rescale colors').click()
    page.get_by_label('Map signal layer').select_option('ac_rms')
    page.wait_for_function("document.querySelector('.metric-status').textContent.includes('17,010 exact')")
    # Playback crosses the recording boundary and advances the shared map selection.
    page.get_by_label('Recording',exact=True).select_option('1')
    page.locator('.js-plotly-plot').wait_for()
    page.get_by_label('Playback position').fill('9.95')
    page.get_by_label('Play playback',exact=True).click()
    page.wait_for_function("document.querySelector('select[aria-label=Recording]').value==='2'",timeout=10000)
    page.get_by_label('Pause playback',exact=True).click()
    page.set_viewport_size({'width':390,'height':844})
    page.wait_for_timeout(500)
    assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
    page.screenshot(path='.local/screenshots/layers-mobile.png',full_page=True)
    browser.close()
    print(json.dumps({'page_errors':errors,'metric_requests':len(metric_requests),'result':'Layer, map selection, zoom, scale and playback checks passed'},indent=2))
    assert not errors
