#!/usr/bin/env python3
"""Browser integration checks; uses upstream examples, never private photos or a paid API."""
import argparse
from io import BytesIO
import json
from pathlib import Path
import shutil
import sys
import tempfile
import time
from zipfile import ZipFile

from PIL import Image
from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.models import PackOptions
from app.upstream import demo_atlas


def png_bytes(image):
    buffer = BytesIO(); image.save(buffer, 'PNG'); return buffer.getvalue()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--url', default='http://127.0.0.1:8000')
    args = parser.parse_args()
    output = ROOT / 'artifacts'
    output.mkdir(exist_ok=True)
    errors = []
    report = {'url': args.url, 'checks': [], 'page_errors': errors}
    with sync_playwright() as pw, tempfile.TemporaryDirectory() as folder:
        browser = pw.chromium.launch(executable_path=shutil.which('chromium') or None, headless=True, args=['--no-sandbox'])
        desktop = browser.new_context(viewport={'width': 1440, 'height': 1120}, device_scale_factor=1, accept_downloads=True)
        page = desktop.new_page()
        page.on('pageerror', lambda error: errors.append(str(error)))
        writes = []
        page.on('request', lambda request: writes.append(request.url) if request.method == 'POST' else None)
        page.goto(args.url, wait_until='networkidle')
        page.evaluate('document.fonts.ready')
        expect(page.locator('#connection-label')).to_have_text('图像服务待配置')
        expect(page.locator('.sticker-card')).to_have_count(6)
        page.wait_for_function("[...document.querySelectorAll('.sticker-card img')].every(i=>i.complete&&i.naturalWidth>0)")
        page.screenshot(path=str(output/'ui-desktop.png'), full_page=True)
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        report['checks'].append('desktop layout and real upstream sample images')

        page.locator('#source-input').set_input_files({'name': 'test-only-photo.png', 'mimeType': 'image/png', 'buffer': png_bytes(Image.new('RGB', (240, 300), '#808080'))})
        expect(page.locator('#source-thumbnail')).to_be_visible()
        assert not writes, 'Selecting a file must not upload it'
        page.locator('#consent').check()
        expect(page.locator('#generate-button')).to_be_disabled()
        report['checks'].append('local-only file selection; unavailable AI is blocked')
        page.get_by_label('选择生气', exact=True).check()
        page.get_by_label('选择加油', exact=True).check()
        page.get_by_label('选择挥手', exact=True).click()
        expect(page.locator('#selection-count')).to_have_text('8 / 8')
        expect(page.get_by_label('选择挥手', exact=True)).not_to_be_checked()
        page.get_by_label('选择生气', exact=True).uncheck()
        page.get_by_label('选择加油', exact=True).uncheck()
        page.get_by_label('开心的文案', exact=True).fill('开心就笑')
        page.locator('#connection-button').click()
        expect(page.locator('#connection-dialog')).to_be_visible()
        page.keyboard.press('Escape')
        page.locator('#help-button').click()
        expect(page.locator('#help-dialog')).to_be_visible()
        page.keyboard.press('Escape')
        report['checks'].append('expression limits, editable captions and dialogs')

        page.locator('#demo-button').click()
        expect(page.locator('#review-area')).to_be_visible(timeout=20000)
        expect(page.locator('#export-button')).to_be_disabled()
        expect(page.locator('#cell-map span')).to_have_count(6)
        page.locator('#review-checkbox').check()
        page.locator('#export-button').click()
        expect(page.locator('#gif-download')).to_have_attribute('aria-disabled', 'false', timeout=50000)
        expect(page.locator('.sticker-card')).to_have_count(6)
        with page.expect_download() as download_event:
            page.locator('#gif-download').click()
        download = download_event.value
        path = Path(folder)/'demo.zip'; download.save_as(path)
        with ZipFile(path) as archive:
            assert archive.testzip() is None
            assert len([n for n in archive.namelist() if n.endswith('.gif')]) == 6
            assert '动图浏览.html' in archive.namelist()
        shutil.copyfile(path, output/'upstream-demo-6-gifs.zip')
        page.locator('[data-format=png]').click()
        expect(page.locator('.sticker-card img').first).to_have_attribute('src', __import__('re').compile('/files/png_0$'))
        page.locator('.sticker-card').first.click()
        expect(page.locator('#sticker-dialog')).to_be_visible()
        expect(page.locator('#sticker-downloads a')).to_have_count(2)
        page.keyboard.press('Escape')
        page.locator('#clear-button').click()
        expect(page.locator('#gif-download')).to_have_attribute('aria-disabled', 'true')
        report['checks'].append('6-pose review → original CLI export → valid downloadable ZIP → PNG preview → deletion')
        desktop.close()

        mobile = browser.new_context(viewport={'width': 390, 'height': 844}, device_scale_factor=1, is_mobile=True, has_touch=True, accept_downloads=True)
        page = mobile.new_page(); page.on('pageerror', lambda error: errors.append(str(error)))
        page.goto(args.url, wait_until='networkidle'); page.evaluate('document.fonts.ready')
        page.screenshot(path=str(output/'ui-mobile.png'), full_page=True)
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        page.locator('[data-source=atlas]').click()
        for name in ['比心', '委屈', '躺平', '震惊']:
            page.get_by_label('选择'+name, exact=True).uncheck()
        opts = PackOptions.model_validate({'expressions': [{'id':'happy','caption':'开心'}, {'id':'ok','caption':'收到'}]})
        atlas = png_bytes(demo_atlas(opts.expressions))
        page.locator('#source-input').set_input_files({'name':'upstream-test-atlas.png','mimeType':'image/png','buffer':atlas})
        page.locator('#consent').check()
        expect(page.locator('#generate-button')).to_be_enabled()
        page.locator('#generate-button').click()
        expect(page.locator('#review-area')).to_be_visible(timeout=20000)
        page.locator('#review-checkbox').check(); page.locator('#export-button').click()
        expect(page.locator('#gif-download')).to_have_attribute('aria-disabled', 'false', timeout=50000)
        expect(page.locator('#canvas-label')).to_have_text('2 张 / 512 × 512')
        page.reload(wait_until='networkidle')
        expect(page.locator('.sticker-card')).to_have_count(2)
        expect(page.locator('#preview-badge')).to_have_text('你的表情包')
        expect(page.locator('#selection-count')).to_have_text('2 / 8')
        expect(page.locator('[data-source=atlas]')).to_have_attribute('aria-pressed', 'true')
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        page.screenshot(path=str(output/'ui-mobile-result.png'), full_page=True)
        result_url=page.locator('.sticker-card img').first.get_attribute('src')
        stranger=browser.new_context()
        assert stranger.request.get(args.url+result_url).status==404
        stranger.close()
        page.locator('#clear-button').click()
        expect(page.locator('#clear-button')).to_be_hidden()
        report['checks'].append('mobile atlas import and HD export; refresh recovery; session isolation; no overflow')
        mobile.close()

        expiry_context = browser.new_context(viewport={'width': 1000, 'height': 900})
        for phase in ['review', 'completed']:
            config = expiry_context.request.get(args.url+'/api/config').json()
            job = expiry_context.request.post(args.url+'/api/demo', data={'expressions':[{'id':'happy','caption':'开心'}]}).json()
            deadline = time.monotonic()+30
            while time.monotonic() < deadline:
                job = expiry_context.request.get(args.url+f"/api/jobs/{job['id']}").json()
                if job['status']=='review': break
                assert job['status']!='failed', job
                time.sleep(.05)
            assert job['status']=='review'
            if phase=='completed':
                expiry_context.request.post(args.url+f"/api/jobs/{job['id']}/export", data={'reviewed':True})
                while time.monotonic() < deadline:
                    job = expiry_context.request.get(args.url+f"/api/jobs/{job['id']}").json()
                    if job['status']=='completed': break
                    assert job['status']!='failed', job
                    time.sleep(.05)
                assert job['status']=='completed'
            # Exercise browser expiry handling against explicit 410 responses.
            # Server lifetime boundaries are separately covered by backend tests.
            job['expires_in_seconds'] = 1
            config['latest_job'] = job
            config['ttl_seconds'] = 90
            page = expiry_context.new_page()
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.clock.install()
            page.route('**/api/config', lambda route, request, payload=config: route.fulfill(json=payload))
            page.route('**/api/jobs/'+job['id'], lambda route: route.fulfill(status=410,json={'detail':'任务已过期。'}))
            page.goto(args.url,wait_until='networkidle')
            page.clock.fast_forward(1500)
            expect(page.locator('#toast')).to_contain_text('任务已过期')
            expect(page.locator('#review-area')).to_be_hidden()
            expect(page.locator('#gif-download')).to_have_attribute('aria-disabled','true')
            expect(page.locator('#demo-button')).to_be_enabled()
            expect(page.locator('#retention-note')).to_contain_text('1 分钟 30 秒')
            expiry_context.request.delete(args.url+'/api/jobs')
            page.close()
        expiry_context.close()
        report['checks'].append('review/completed expiry unlocks UI and disables downloads; retention follows configured TTL')
        browser.close()
    assert not errors, errors
    report['passed'] = True
    (output/'ui-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__=='__main__': main()
