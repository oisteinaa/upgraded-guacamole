"""Read-only deployed-dashboard smoke test for wind timing and movable legend."""
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    browser=p.chromium.launch(headless=True,args=['--no-sandbox','--enable-unsafe-swiftshader'])
    page=browser.new_page(viewport={'width':1536,'height':1100})
    errors=[]; requests=[]
    page.on('pageerror',lambda e: errors.append(str(e)))
    page.on('request',lambda r: requests.append(r.url) if '/api/map/wind' in r.url else None)
    page.goto('http://10.147.20.10:8051',wait_until='networkidle')
    page.locator('.map-wrap[data-ready=true]').wait_for(timeout=30000)
    page.get_by_label('Wind arrows',exact=True).check()
    page.wait_for_function("document.querySelector('.wind-key')?.textContent.includes('UTC')")
    page.wait_for_timeout(1000)
    assert requests and '?at=' in requests[-1],requests
    first=requests[-1]
    handle=page.get_by_role('button',name='Move map legend')
    box=handle.bounding_box()
    page.mouse.move(box['x']+40,box['y']+10)
    page.mouse.down();page.mouse.move(box['x']+300,box['y']-180,steps=10);page.mouse.up()
    moved=page.locator('.map-legend').bounding_box()
    assert moved['x']>box['x']+200,(moved,box)
    handle.focus();page.keyboard.press('ArrowRight')
    page.get_by_role('tab',name='Signal layer',exact=True).click()
    page.get_by_role('button',name='Next signal frame',exact=True).click()
    page.wait_for_timeout(3000)
    assert requests[-1]!=first,(first,requests)
    print('Historical weather updates:',requests)
    page.locator('.map-wrap').screenshot(path='/tmp/wind-refresh-investigate.png')
    page.get_by_role('button',name='Live monitor',exact=True).click()
    page.locator('.map-wrap[data-ready=true]').wait_for()
    page.get_by_label('Wind arrows',exact=True).check()
    page.wait_for_timeout(1000)
    assert requests[-1].endswith('/api/map/wind'),requests
    page.clock.install()
    count=len(requests)
    page.clock.fast_forward(61000)
    page.wait_for_timeout(1200)
    assert len(requests)>count
    print('Live polling passed')
    page.get_by_role('button',name='Investigate',exact=True).click()
    page.locator('.map-wrap[data-ready=true]').wait_for()
    restored=page.locator('.map-legend').bounding_box()
    assert abs(restored['x']-moved['x']-10)<2,(restored,moved)
    print('Legend drag, keyboard move, and saved position passed')
    assert not errors,errors
    print('No browser errors')
    browser.close()
