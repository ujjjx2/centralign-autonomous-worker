"""Video artifact smoke test uses real Chromium, but not localhost navigation.

Full browser navigation is exercised by record_live_demo.py on the target Mac.
"""
import os
from pathlib import Path
import shutil
import pytest
from app.agent.ui_planner import find_live_locator


def test_real_cursor_and_video_artifact(tmp_path):
    from playwright.sync_api import sync_playwright
    from app.agent.browser_v4 import CURSOR_SCRIPT
    binary=os.getenv('BROWSER_EXECUTABLE') or shutil.which('chromium')
    with sync_playwright() as p:
        try:
            browser=p.chromium.launch(headless=True,executable_path=binary if binary else None,args=['--no-sandbox'])
        except Exception:pytest.skip('Chromium executable not available')
        try:
            ctx=browser.new_context(record_video_dir=str(tmp_path))
            ctx.add_init_script(CURSOR_SCRIPT)
            try:
                page=ctx.new_page()
            except Exception:
                ctx.close();pytest.skip('Playwright bundled FFmpeg missing')
            page.set_content('<h1>Sandbox form</h1><label for="renamed">Vendor</label>'
                             '<input id="renamed" name="vendor_id"/>')
            # set_content replaces the initial about:blank DOM rather than
            # creating a fresh navigation; reinstall the overlay explicitly.
            page.evaluate('window.__centralignCursor=false')
            page.evaluate(CURSOR_SCRIPT)
            assert page.locator('#centralign-pointer').count()==1
            page.mouse.move(180,220)
            assert page.locator('#centralign-pointer').evaluate('(e)=>e.style.left')=='168px'
            # init_script is evaluated on navigation but set_content also runs
            # an init-script with a document replacement in current Playwright.
            node,_=find_live_locator(page,'input',['Vendor'])
            node.fill('Northstar Labs')
            page.screenshot(path=str(tmp_path/'cursor.png'))
            assert page.locator('#renamed').input_value()=='Northstar Labs'
            recording=page.video
            ctx.close()
            path=Path(recording.path())
            assert path.is_file() and path.stat().st_size>500
        finally:browser.close()


def test_v4_adapter_saves_real_browser_recording(tmp_path,monkeypatch):
    from types import SimpleNamespace
    from app.agent.browser_v4 import VisualBrowserTools
    import os,shutil
    executable=os.getenv('BROWSER_EXECUTABLE') or shutil.which('chromium') or ''
    with monkeypatch.context() as m:
        m.setattr(VisualBrowserTools,'_goto',lambda self,url:self.page.set_content(
            '<h1>Sandbox Invoice</h1><label for="renamed">Invoice number</label>'
            '<input id="renamed" name="invoice_number"/>'))
        settings=SimpleNamespace(artifacts_dir=tmp_path,browser_executable=executable,headless=True)
        try:
            with VisualBrowserTools('http://127.0.0.1:8000',settings,task_id='test') as agent:
                agent._fill(['Invoice number'],'NL-2026-092')
                assert agent.page.locator('#renamed').input_value()=='NL-2026-092'
        except Exception as e:
            if ('Executable doesn\'t exist' in str(e) or 'ffmpeg' in str(e).lower()):
                pytest.skip('Required Playwright browser binaries missing')
            raise
    artifact=tmp_path/'test'
    assert (artifact/'browser-recording.webm').stat().st_size>500
    assert (artifact/'playwright-trace.zip').stat().st_size>500
    assert list(artifact.glob('*.png'))
