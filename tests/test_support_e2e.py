"""Real local-server integration tests for generalized support-ticket workflow."""
from .conftest import until_status


def test_support_ticket_classified_saved_and_verified(sandbox,run_task):
    task=run_task('Triage ticket TKT-402 and assign it to the right team')
    assert task['status']=='completed',task.get('error')
    assert task['goal']['workflow']=='support_ticket'
    assert task['report']['outcome']=='triaged_and_verified'
    case=task['report']['case']
    assert (case['category'],case['priority'],case['assigned_team'])==(
        'technical','normal','Engineering Support')
    assert task['report']['verification']['matched']
    evidence=sandbox.get(task['report']['evidence_url'])
    assert evidence.status_code==200 and evidence.json()['matched']
    assert len(sandbox.get('/api/cases').json())==1
    assert any(e['tool']=='policy_next_action' for e in task['events'])


def test_latest_support_ticket_escalated_automatically(sandbox,run_task):
    task=run_task('Triage the latest support ticket')
    assert task['status']=='completed',task.get('error')
    assert task['report']['case']['number']=='TKT-404'
    assert task['report']['case']['priority']=='high'
    assert task['report']['case']['assigned_team']=='Engineering Support'


def test_ticket_idempotency_and_status_check(sandbox,run_task):
    check=run_task('Check whether support ticket TKT-403 has already been triaged')
    assert check['status']=='completed'
    assert check['report']['outcome']=='not_triaged'
    assert not sandbox.get('/api/cases').json()
    first=run_task('Triage support ticket TKT-403')
    assert first['status']=='completed',first.get('error')
    assert first['report']['case']['category']=='billing'
    again=run_task('Triage support ticket TKT-403')
    assert again['status']=='completed',again.get('error')
    assert again['report']['outcome']=='already_triaged'
    assert len(sandbox.get('/api/cases').json())==1


def test_high_priority_cannot_be_downgraded_by_http_form(sandbox):
    invoice=next(t for t in sandbox.get('/api/tickets').json() if t['number']=='TKT-404')
    resp=sandbox.post('/workspace/cases/new',data={
        'source_ticket_id':invoice['id'],'number':invoice['number'],
        'requester':invoice['requester'],'subject':invoice['subject'],
        'category':'technical','priority':'normal',
        'assigned_team':'Engineering Support','task_id':'test'})
    assert resp.status_code==422
    assert 'Critical incident' in resp.text
    assert sandbox.get('/api/cases').json()==[]


def test_ticket_missing_number_asks_for_clarification(sandbox,run_task):
    task=run_task('Triage support ticket TKT-999')
    assert task['status']=='needs_input'
    resp=sandbox.post(f"/api/tasks/{task['id']}/clarify",json={
        'instruction':'Triage support ticket TKT-401'})
    assert resp.status_code==202
    done=until_status(sandbox,task['id'],{'completed','failed'})
    assert done['status']=='completed',done.get('error')
    assert done['report']['case']['category']=='access'


def test_company_support_html_is_real(sandbox):
    assert 'ticket-search' in sandbox.get('/workspace/tickets').text
    assert 'ticket-document' in sandbox.get('/workspace/tickets/1').text
    assert 'submit-case' in sandbox.get('/workspace/cases/new').text
