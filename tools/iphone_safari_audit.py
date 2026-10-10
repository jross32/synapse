"""Repeatable iPhone-sized browser audit. Chromium emulation is NOT native Safari."""
import argparse, json, pathlib, sys
from playwright.sync_api import sync_playwright

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('url')
    parser.add_argument('--output',default='artifacts/iphone-audit')
    args=parser.parse_args()
    out=pathlib.Path(args.output);out.mkdir(parents=True,exist_ok=True)
    results=[]
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True)
        for name,width,height in [('iphone-compact',375,812),('iphone-large',430,932)]:
            page=browser.new_page(viewport={'width':width,'height':height},device_scale_factor=3,is_mobile=True,has_touch=True)
            response=page.goto(args.url,wait_until='domcontentloaded',timeout=30000)
            page.screenshot(path=str(out/f'{name}.png'),full_page=True)
            data=page.evaluate('''() => ({horizontalOverflow: document.documentElement.scrollWidth > innerWidth+2, viewport:innerWidth, textSamples:[...document.querySelectorAll('.market-list > div')].map(e=>({background:getComputedStyle(e).backgroundColor,text:getComputedStyle(e.querySelector('b')).color,description:getComputedStyle(e.querySelector('small')).color}))})''')
            results.append({'device':name,'http_status':response.status if response else None,**data})
            page.close()
        browser.close()
    report={'engine':'Chromium mobile emulation; not native iOS Safari','results':results,'native_safari_verified':False}
    (out/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report))
    return 1 if any(x['horizontalOverflow'] or x['http_status']!=200 for x in results) else 0
if __name__=='__main__':sys.exit(main())
