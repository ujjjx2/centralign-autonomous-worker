"""v4 goal state planning and robust semantic affordance scoring."""
from dataclasses import replace
import pytest
from app.agent.reactive import GoalStatePlanner,TaskState
from app.agent.ui_planner import find_live_locator


def test_invoice_graph_replans_on_observation():
    planner=GoalStatePlanner();s=TaskState('invoice',{'operation':'record'})
    assert planner.next_action(s)[0]=='discover'
    s.selected={'id':1};assert planner.next_action(s)[0]=='read_source'
    s.source={'text':'invoice'};assert planner.next_action(s)[0]=='extract'
    s.facts={'number':'123'};assert planner.next_action(s)[0]=='check_existing'
    s.lookup_done=True;assert planner.next_action(s)[0]=='check_approval'
    s.approval_checked=True;assert planner.next_action(s)[0]=='write'
    s.entry_id=7;assert planner.next_action(s)[0]=='verify'
    s.verified={'matched':True};assert planner.next_action(s)[0]=='complete'


def test_read_only_never_offers_write():
    s=TaskState('invoice',{'operation':'check'},selected={'id':1},
                source={'text':'x'},facts={'number':'x'},lookup_done=True)
    assert GoalStatePlanner().next_action(s)[0]=='complete_absent'


def test_retry_cap_and_duplicate_recovery():
    s=TaskState('invoice',{'operation':'record'},selected={'id':1},source={'text':'x'},
                facts={'number':'x'},lookup_done=True,approval_checked=True,write_attempts=3)
    assert GoalStatePlanner().next_action(s)[0]=='exhausted'
    s.entry_id=5
    assert GoalStatePlanner().next_action(s)[0]=='verify'


def test_browser_role_selection_on_renamed_ids():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError: pytest.skip('playwright missing')
    import os,shutil
    executable=os.getenv('BROWSER_EXECUTABLE') or shutil.which('chromium') or shutil.which('google-chrome')
    with sync_playwright() as p:
        try:
            b=p.chromium.launch(headless=True,executable_path=executable if executable else None,
                                args=['--no-sandbox'])
        except Exception:pytest.skip('Chromium binary not installed; run playwright install chromium')
        try:
            page=b.new_page()
            # Intentionally different IDs: selector based on old ID must fail,
            # while the semantics of visible form labels still work.
            page.set_content('''<form><label for="x-598">Invoice number</label>
              <input id="x-598" name="invoice_number" />
              <label for="x-877">Amount (USD)</label><input id="x-877" name="amount" />
              <button id="x-23" type="button">Record invoice</button></form>''')
            assert page.locator('#invoice-number').count()==0
            node,reason=find_live_locator(page,'input',['Invoice number'])
            node.fill('NL-2026-092')
            other,_=find_live_locator(page,'input',['Amount (USD)'])
            other.fill('390.00')
            button,reason=find_live_locator(page,'button',['Record invoice'])
            assert reason['score']>0
            assert page.locator('[name="invoice_number"]').input_value()=='NL-2026-092'
            assert page.locator('[name="amount"]').input_value()=='390.00'
        finally:b.close()


def test_invoice_events_include_replanning_and_verification(run_task):
    result=run_task('Find the latest invoice from Northstar Labs and record it')
    assert result['status']=='completed',result.get('error')
    steps=[x['detail'].get('next_action') for x in result['events'] if x['kind']=='replan']
    assert steps[:4]==['discover','read_source','extract','check_existing']
    assert 'check_approval' in steps and 'verify' in steps and 'complete' in steps
    assert result['report']['verification']['matched']
