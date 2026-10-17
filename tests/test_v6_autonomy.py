"""Model-origin planning, safe affordance selection, recovery through real forms."""
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import json,os,socket,subprocess,sys,threading,time
import httpx
import pytest
from app.agent.planner_v6 import canonical_steps,validate_plan,build_plan,ObservationPlanner
from app.agent.gemma import GemmaClient,InvalidModelResponse
from tests.conftest import until_status


def test_validated_decomposition_keeps_causal_invariants():
    required=canonical_steps('invoice','record')
    assert validate_plan(required,'invoice','record')==required
    assert validate_plan(['discover','refresh_search',*required[1:]],'invoice','record')
    for invalid in (
        [x for x in required if x!='check_approval'],
        [x for x in required if x!='verify'],
        ['write',*required],
        [*required[:-1],'transfer_funds','complete'],
        ['discover','discover',*required[1:]],
    ):
        with pytest.raises(ValueError):validate_plan(invalid,'invoice','record')
    read_only=canonical_steps('invoice','check')
    assert 'write' not in read_only and 'check_approval' not in read_only
    with pytest.raises(ValueError):validate_plan(required,'invoice','check')


class StubModel:
    def __init__(self,steps):self.steps=steps;self.calls=[]
    def decide(self,task,payload,allowed=None):
        self.calls.append((task,payload))
        return {'steps':self.steps,'reason':'Derived from the goal and available tools'}


class StubPolicy:
    def __init__(self,steps):self.model=StubModel(steps)


def test_model_can_decompose_and_cannot_skip_mandatory_actions():
    core=canonical_steps('ticket','triage')
    candidate=['discover','refresh_search',*core[1:]]
    policy=StubPolicy(candidate)
    plan=build_plan(policy,'Triage the latest ticket','ticket',{'operation':'triage'})
    assert plan.origin=='gemma_validated'
    assert plan.steps==candidate
    assert policy.model.calls[0][0]=='plan'
    assert 'user_goal' in policy.model.calls[0][1]
    invalid=StubPolicy(['discover','write','complete'])
    recovered=build_plan(invalid,'Triage the latest ticket','ticket',{'operation':'triage'})
    assert recovered.origin=='validated_fallback'
    assert recovered.steps==core


@contextmanager
def adaptive_fake_ollama():
    calls=[];once=set()
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_GET(self):
            body=json.dumps({'models':[{'name':'gemma4:e2b'}]}).encode()
            self.send_response(200);self.send_header('Content-Type','application/json')
            self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
        def do_POST(self):
            payload=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            props=payload['format']['properties']
            prompt=json.loads(payload['messages'][1]['content'])
            calls.append({'props':list(props),'input':prompt})
            if 'steps' in props:
                goal=prompt['observation']
                actions=goal['required_milestones']
                answer={'steps':actions,'reason':'Decomposed from user goal with required safety milestones'}
            elif 'operation' in props:
                answer={'operation':'record','reason':'Explicitly asked to record'}
            elif 'category' in props:
                answer={'category':'technical','priority':'normal','reason':'Export failure'}
            else:
                allowed=props['tool']['enum']
                stage=prompt['observation']['stage']
                if stage=='next_action_write' and 'refresh_form' in allowed and stage not in once:
                    once.add(stage);choice='refresh_form'
                elif stage=='recover_write_invoice' and 'refresh_form_and_retry' in allowed:
                    choice='refresh_form_and_retry'
                elif stage=='recover_write_case' and 'refresh_form_and_retry' in allowed:
                    choice='refresh_form_and_retry'
                else:
                    choice=allowed[0]
                answer={'tool':choice,'reason':'Choose based on current observed state'}
            body=json.dumps({'message':{'content':json.dumps(answer)}}).encode()
            self.send_response(200);self.send_header('Content-Type','application/json')
            self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
    srv=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    thread=threading.Thread(target=srv.serve_forever,daemon=True);thread.start()
    try:yield 'http://127.0.0.1:'+str(srv.server_address[1]),calls
    finally:srv.shutdown();srv.server_close();thread.join(timeout=3)


def test_model_decomposes_replans_and_recovers_in_real_sandbox(tmp_path):
    root=Path(__file__).resolve().parents[1]
    with adaptive_fake_ollama() as (url,calls):
        with socket.socket() as sock:
            sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
        env=os.environ.copy();env.update(DATABASE_PATH=str(tmp_path/'work.sqlite3'),
            ARTIFACTS_DIR=str(tmp_path/'artifacts'),EXECUTION_MODE='http',
            MODEL_BACKEND='gemma',OLLAMA_URL=url)
        proc=subprocess.Popen([sys.executable,'-m','uvicorn','app.main:app',
            '--host','127.0.0.1','--port',str(port),'--log-level','error'],
            cwd=root,env=env,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
        client=httpx.Client(base_url=f'http://127.0.0.1:{port}',timeout=30)
        try:
            for _ in range(100):
                try:
                    if client.get('/health').status_code==200:break
                except httpx.HTTPError:pass
                time.sleep(.1)
            else:raise AssertionError('App failed to start')
            assert client.post('/api/demo/fail-next-write').status_code==200
            number=client.post('/api/tasks',json={
                'instruction':'Record the latest invoice from Northstar Labs'}).json()['task_id']
            task=until_status(client,number,{'completed','failed','needs_input'},timeout=35)
            assert task['status']=='completed',task.get('error')
            assert task['report']['verification']['matched']
            plans=[x for x in task['events'] if x['tool']=='gemma_task_decomposition']
            assert plans and plans[0]['detail']['source']=='gemma_validated'
            assert any(e['tool']=='model_selected_alternative' and
                e['detail']['proposed']=='refresh_form' for e in task['events'])
            assert any(e['kind']=='retry' for e in task['events'])
            assert any(e['tool']=='alternate_form_refresh' for e in task['events'])
            assert any(e['kind']=='adaptive_decision' for e in task['events'])
            assert client.post('/api/demo/fail-next-case-write').status_code==200
            number=client.post('/api/tasks',json={
                'instruction':'Triage ticket TKT-402 and assign it to a team'}).json()['task_id']
            ticket=until_status(client,number,{'completed','failed','needs_input'},timeout=35)
            assert ticket['status']=='completed',ticket.get('error')
            assert ticket['report']['verification']['matched']
            assert any(e['tool']=='alternate_form_refresh' for e in ticket['events'])
            assert any('steps' in c['props'] for c in calls)
            assert any('tool' in c['props'] for c in calls)
        finally:
            client.close();proc.terminate()
            try:proc.wait(timeout=5)
            except subprocess.TimeoutExpired:proc.kill();proc.wait(timeout=4)
            proc.stderr.close()


def test_model_plan_protocol_rejects_shell_tool(monkeypatch):
    real_client=httpx.Client
    def factory(*a,**kw):
        def handler(request):
            return httpx.Response(200,json={'message':{'content':json.dumps({
                'steps':['discover','run_shell_command','complete'],'reason':'Bypass policy'})}})
        kw['transport']=httpx.MockTransport(handler)
        return real_client(*a,**kw)
    monkeypatch.setattr('app.agent.gemma.httpx.Client',factory)
    with pytest.raises(InvalidModelResponse):
        GemmaClient().decide('plan',{'user_goal':'Ignore policy'})


def test_broader_source_search_and_fresh_verification_are_real_alternatives(tmp_path,monkeypatch):
    """Exercise recovery branches with a strict fake of the company form adapter.

    Unlike mocking an LLM result, the tools here implement different search
    responses and require actual state progression before a simulated write.
    """
    from app.agent import reactive
    from app.agent.policy import DecisionPolicy
    from app.config import Settings
    settings=Settings(database_path=tmp_path/'test.sqlite3',artifacts_dir=tmp_path/'evidence',
                      model_backend='rules',execution_mode='http')
    class FakeDB:
        def vendors(self):return [{'name':'Northstar Labs'}]
        def update_task(self,*args,**kwargs):pass
    class FakeWorker:
        db=FakeDB();policy=DecisionPolicy(settings);base_url='http://127.0.0.1:8000'
        def __init__(self):self.events=[];self.outcome=None;self.settings=settings
        def event(self,tid,kind,tool,**kw):self.events.append((kind,tool,kw))
        def complete(self,tid,outcome,**kw):self.outcome=(outcome,kw)
    class FakeTools:
        backend_name='http_html_automation';fallback_reason=None
        def __init__(self,*args):self.persisted=False;self.verifies=0
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def search_invoices(self,vendor):
            if vendor:return []  # the first, filtered query misses the document
            return [{'id':12,'vendor':'Northstar Labs','number':'NL-2026-092',
                     'arrived_at':'2026-10-15T08:00:00Z'}]
        def read_invoice(self,i):
            return {'url':'http://127.0.0.1:8000/workspace/invoices/12',
                    'text':'Vendor: Northstar Labs\nInvoice Number: NL-2026-092\n'
                           'Amount Due: USD 725.50\nDue Date: 2026-11-03'}
        def find_ledger_entry(self,n,v):return 99 if self.persisted else None
        def write_ledger_entry(self,*args):self.persisted=True;return 99
        def verify_entry(self,*args):
            self.verifies+=1
            return {'matched':self.verifies>=2, 'observed':{},'entry_id':99}
    monkeypatch.setattr(reactive,'BrowserTools',FakeTools)
    worker=FakeWorker()
    reactive.execute_invoice(worker,'unit-task',{'instruction':'Record the latest invoice from Northstar Labs'})
    assert worker.outcome is not None
    assert worker.outcome[1]['verification']['matched']
    assert any(kind=='recovery' and tool=='broaden_source_search' for kind,tool,kw in worker.events)
    assert any(tool=='second_independent_readback' for kind,tool,kw in worker.events)
