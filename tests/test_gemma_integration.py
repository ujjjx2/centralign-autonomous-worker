"""True local server integration using a simulated Ollama *protocol*.

The LLM's actual weights are not available in CI. The fake server proves that
both workflows issue Ollama requests and use validated responses end-to-end.
"""
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json, os, socket, subprocess, sys, threading, time
from pathlib import Path
import httpx
from tests.conftest import until_status


@contextmanager
def fake_ollama():
    requests=[]
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_GET(self):
            data={'models':[{'name':'gemma4:e2b'}]}
            body=json.dumps(data).encode();self.send_response(200)
            self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(body)))
            self.end_headers();self.wfile.write(body)
        def do_POST(self):
            payload=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            requests.append(payload)
            spec=payload['format']['properties']
            if 'operation' in spec:answer={'operation':'record','reason':'User requested entry'}
            elif 'category' in spec:answer={'category':'technical','priority':'normal','reason':'Technical problem'}
            else:
                allowed=spec['tool']['enum']
                answer={'tool':next(x for x in allowed if x!='ask_human'), 'reason':'Source validated'}
            body=json.dumps({'message':{'content':json.dumps(answer)}}).encode()
            self.send_response(200);self.send_header('Content-Type','application/json')
            self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
    srv=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    thread=threading.Thread(target=srv.serve_forever,daemon=True);thread.start()
    try:yield f'http://127.0.0.1:{srv.server_address[1]}',requests
    finally:srv.shutdown();srv.server_close();thread.join(timeout=3)


def test_worker_uses_gemma_protocol_in_both_workflows(tmp_path):
    root=Path(__file__).resolve().parents[1]
    with fake_ollama() as (url,requests):
        with socket.socket() as sock:
            sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
        env=os.environ.copy()
        env.update(DATABASE_PATH=str(tmp_path/'test.sqlite3'),ARTIFACTS_DIR=str(tmp_path/'artifacts'),
                   MODEL_BACKEND='gemma',OLLAMA_URL=url,EXECUTION_MODE='http')
        process=subprocess.Popen([sys.executable,'-m','uvicorn','app.main:app','--host','127.0.0.1',
              '--port',str(port),'--log-level','error'],cwd=root,env=env,
              stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
        client=httpx.Client(base_url=f'http://127.0.0.1:{port}',timeout=30)
        try:
            for _ in range(100):
                try:
                    if client.get('/health').status_code==200:break
                except httpx.HTTPError:pass
                time.sleep(.1)
            else:raise AssertionError('Server never started')
            assert client.get('/api/model').json()['available'], client.get('/api/model').json()
            for instruction in ('Record the latest invoice from Northstar Labs',
                                'Triage ticket TKT-402 and assign it to the right team'):
                task_id=client.post('/api/tasks',json={'instruction':instruction}).json()['task_id']
                task=until_status(client,task_id,{'completed','failed','needs_input'},timeout=30)
                assert task['status']=='completed',task.get('error')
                assert any(e['detail'].get('decision_mode')=='gemma4_e2b'
                           for e in task['events'] if e['tool']=='policy_next_action')
            assert any('operation' in payload['format']['properties'] for payload in requests)
            assert any('category' in payload['format']['properties'] for payload in requests)
            assert any('tool' in payload['format']['properties'] for payload in requests)
            assert all(payload['model']=='gemma4:e2b' for payload in requests)
        finally:
            client.close();process.terminate()
            try:process.wait(timeout=5)
            except subprocess.TimeoutExpired:process.kill()
            process.stderr.close()
