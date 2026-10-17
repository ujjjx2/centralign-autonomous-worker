"""Browser crash recovery never hides root causes or blindly repeats writes."""
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from playwright.sync_api import Error as PlaywrightError
from app.agent.browser import BrowserTools
from app.agent.browser_v4 import VisualBrowserTools

class ClosedPage:
    url='http://127.0.0.1:8000/'
    video=None
    def is_closed(self):return True
    def title(self):raise PlaywrightError('Target page, context or browser has been closed')


def test_context_cleanup_does_not_hide_original_error(tmp_path):
    session=VisualBrowserTools('http://127.0.0.1:8000',SimpleNamespace(
        artifacts_dir=tmp_path,headless=True,browser_executable=''))
    session.page=ClosedPage()
    session._shutdown()
    assert session.page is None


def test_disconnected_page_snapshot_is_not_misreported(tmp_path):
    session=VisualBrowserTools('http://127.0.0.1:8000',SimpleNamespace(
        artifacts_dir=tmp_path,headless=True,browser_executable=''))
    session.page=ClosedPage()
    with pytest.raises(PlaywrightError,match='closed'):
        session._snapshot('navigation')


class FakeVisualBackend:
    def __init__(self, method, stored_record=None):
        self.method=method
        self.stored_record=stored_record
        self.calls=[]
        self.restart_count=0
    def _log(self,action,**kwargs):self.calls.append(('event',action))
    def restart_session(self):self.restart_count+=1
    def search_invoices(self, vendor):
        self.calls.append(('search_invoices',vendor))
        if self.restart_count==0:
            raise PlaywrightError('Page.title: Target page, context or browser has been closed')
        return [{'id':1,'vendor':vendor}]
    def write_ledger_entry(self,invoice_id,invoice,task_id):
        self.calls.append(('write_ledger_entry',invoice_id))
        if self.restart_count==0:
            raise PlaywrightError('Page.click: Target page, context or browser has been closed')
        return 45
    def find_ledger_entry(self,number,vendor):
        self.calls.append(('find_ledger_entry',number))
        return self.stored_record
    def write_case(self,ticket_id,facts,task_id):
        self.calls.append(('write_case',ticket_id))
        if self.restart_count==0:
            raise PlaywrightError('Page.click: Target page, context or browser has been closed')
        return 52
    def find_case(self,number):
        self.calls.append(('find_case',number))
        return self.stored_record


def make_wrapper(fake):
    wrapper=BrowserTools('http://127.0.0.1:8000',SimpleNamespace(),task_id='unit')
    wrapper.backend=fake
    wrapper.backend_name='playwright_chromium'
    return wrapper


def test_read_only_action_retries_after_browser_restart():
    fake=FakeVisualBackend('search_invoices')
    result=make_wrapper(fake).search_invoices('Northstar Labs')
    assert result[0]['vendor']=='Northstar Labs'
    assert fake.restart_count==1
    assert len([c for c in fake.calls if c[0]=='search_invoices'])==2


def test_no_duplicate_write_if_browser_crashed_after_submission():
    invoice={'number':'NL-9','vendor':'Northstar Labs'}
    fake=FakeVisualBackend('write_ledger_entry',stored_record=87)
    assert make_wrapper(fake).write_ledger_entry(1,invoice,'task')==87
    assert fake.restart_count==1
    assert len([c for c in fake.calls if c[0]=='write_ledger_entry'])==1
    assert ('find_ledger_entry','NL-9') in fake.calls


def test_safe_retry_when_write_did_not_commit():
    invoice={'number':'NL-9','vendor':'Northstar Labs'}
    fake=FakeVisualBackend('write_ledger_entry',stored_record=None)
    assert make_wrapper(fake).write_ledger_entry(1,invoice,'task')==45
    assert len([c for c in fake.calls if c[0]=='write_ledger_entry'])==2


def test_case_write_is_read_back_before_retry():
    facts={'number':'TKT-402'}
    fake=FakeVisualBackend('write_case',stored_record=91)
    assert make_wrapper(fake).write_case(1,facts,'task')==91
    assert len([c for c in fake.calls if c[0]=='write_case'])==1


def test_unrelated_playwright_errors_do_not_trigger_restart():
    class NotClosed(FakeVisualBackend):
        def search_invoices(self,vendor):raise PlaywrightError('Timeout 7000ms exceeded while waiting for locator')
    fake=NotClosed('search_invoices')
    with pytest.raises(PlaywrightError,match='Timeout'):
        make_wrapper(fake).search_invoices('Northstar Labs')
    assert fake.restart_count==0
