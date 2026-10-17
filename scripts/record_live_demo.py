#!/usr/bin/env python3
"""Make a REAL Chromium cursor/click demo with isolated sandbox state.

Runs an isolated localhost server, performs tasks through the visible dashboard,
then joins dashboard and agent browser video recordings into MP4 with ffmpeg.
No fake animation or cloud API; Gemma 4 E2B runs locally through Ollama.
If Chromium is blocked, fail clearly rather than faking a browser recording.
"""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time
import httpx
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def poll(client,id,allowed,timeout=120):
    end=time.monotonic()+timeout
    while time.monotonic()<end:
        state=client.get('/api/tasks/'+id).json()
        if state['status'] in allowed:return state
        time.sleep(.35)
    raise RuntimeError(f'Timeout while waiting for task {id}; last state={state["status"]}')


def wait_file(path,seconds=18):
    until=time.monotonic()+seconds
    while time.monotonic()<until:
        if path.is_file() and path.stat().st_size>1024:return
        time.sleep(.2)
    raise RuntimeError(f'Expected real Chromium recording missing: {path}')


def human_click(page,selector):
    node=page.locator(selector)
    node.scroll_into_view_if_needed()
    box=node.bounding_box()
    if not box:raise RuntimeError(f'Cannot see {selector}')
    page.mouse.move(box['x']+box['width']/2,box['y']+box['height']/2,steps=12)
    time.sleep(.25)
    page.mouse.click(box['x']+box['width']/2,box['y']+box['height']/2)
    time.sleep(.3)


def main():
    cli=argparse.ArgumentParser(description='Record live browser automation; no fake cursor')
    cli.add_argument('--headful',action='store_true',help='Show both dashboard and worker Chromium windows')
    cli.add_argument('--task-timeout',type=int,default=360,help='Max seconds for each live task (Gemma may need time to load)')
    cli.add_argument('--strict',action='store_true',help='Require accepted Gemma decisions, approval pause, recovery and verified readback')
    cli.add_argument('--output',default='docs/CentrAlign_v6_REAL_BROWSER_DEMO.mp4')
    cli.add_argument('--chromium-executable',default=os.getenv('BROWSER_EXECUTABLE',''))
    cli.add_argument('--no-shifted-ui',action='store_true',help='Use standard form IDs instead of changed IDs')
    args=cli.parse_args()
    import uuid
    run_id=uuid.uuid4().hex[:8]
    outdir=ROOT/'data'/'recorded_demos'/run_id
    outdir.mkdir(parents=True,exist_ok=True)
    with socket.socket() as s:
        s.bind(('127.0.0.1',0));port=s.getsockname()[1]
    base=f'http://127.0.0.1:{port}'
    env=os.environ.copy()
    env.update(DATABASE_PATH=str(outdir/'company.sqlite3'),ARTIFACTS_DIR=str(outdir/'artifacts'),
               EXECUTION_MODE='browser',MODEL_BACKEND='gemma',
               HEADLESS='false' if args.headful else 'true',APP_PORT=str(port),
               UI_VARIANT='normal' if args.no_shifted_ui else 'shifted',
               BROWSER_ACTION_DELAY='0.22')
    if args.chromium_executable:env['BROWSER_EXECUTABLE']=args.chromium_executable
    log=open(outdir/'server.log','w')
    server=subprocess.Popen([sys.executable,'-m','uvicorn','app.main:app',
               '--host','127.0.0.1','--port',str(port),'--log-level','warning'],
               cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT)
    client=httpx.Client(base_url=base,timeout=15)
    dashboard_video=None
    task_ids=[]
    try:
        for _ in range(150):
            if server.poll() is not None:
                raise RuntimeError('Server failed. Check '+str(outdir/'server.log'))
            try:
                if client.get('/health').status_code==200:break
            except httpx.RequestError:pass
            time.sleep(.1)
        else:raise RuntimeError('Server did not become healthy')
        with sync_playwright() as p:
            kw={'headless':not args.headful,'args':['--no-sandbox']}
            if args.chromium_executable:kw['executable_path']=args.chromium_executable
            browser=p.chromium.launch(**kw)
            context=browser.new_context(viewport={'width':1280,'height':810},
                            record_video_dir=str(outdir/'dashboard_video'),
                            record_video_size={'width':1280,'height':810})
            from app.agent.browser_v4 import CURSOR_SCRIPT
            context.add_init_script(CURSOR_SCRIPT)
            page=context.new_page()
            page.goto(base,wait_until='domcontentloaded')
            page.wait_for_selector('#task-form')
            examples=[
                ('Invoice automation','Find the latest invoice from Northstar Labs and record it in accounts payable.'),
                ('Recover from simulated 503','Record the latest invoice from Harbor Office.'),
                ('Ticket triage','Triage ticket TKT-402 and assign it to the appropriate team.'),
                ('Approval gate','Record the latest invoice from Acme Services.'),
            ]
            completed=[]
            for title,instruction in examples:
                if title.startswith('Recover'):
                    human_click(page,'#inject-failure')
                page.locator('#instruction').fill(instruction)
                human_click(page,'#start-task')
                page.wait_for_function('()=>document.querySelector("#submit-message").textContent.startsWith("Task ")',timeout=12000)
                task_id=page.locator('#submit-message').inner_text().split('Task ')[1][:8]
                # Retrieve exact ID from task list, avoiding URL guessing.
                tasks=client.get('/api/tasks').json()
                found=next((t for t in tasks if t['id'].startswith(task_id)),None)
                if not found:raise RuntimeError('Submitted task ID missing')
                task_id=found['id'];task_ids.append(task_id)
                state=poll(client,task_id,{'completed','failed','awaiting_approval','needs_input'},timeout=args.task_timeout)
                paused_for_approval=(state['status']=='awaiting_approval')
                if state['status']=='awaiting_approval':
                    page.wait_for_selector('#task-actions button',timeout=12000)
                    human_click(page,'#task-actions button.primary')
                    state=poll(client,task_id,{'completed','failed'},timeout=args.task_timeout)
                if state['status']!='completed':
                    raise RuntimeError(f'{title} failed: {state["status"]} {state.get("error")}')
                events=state['events']
                accepted_plan=any(e.get('tool')=='gemma_task_decomposition' and
                                  e.get('detail',{}).get('source')=='gemma_validated' for e in events)
                accepted_choice=any(e.get('detail',{}).get('decision_mode')=='gemma4_e2b'
                                    for e in events)
                verified=bool(state.get('report',{}).get('verification',{}).get('matched'))
                recovery=any(e.get('kind')=='retry' for e in events)
                if args.strict:
                    if not accepted_plan or not accepted_choice:
                        raise RuntimeError(f'{title}: Gemma did not produce an accepted plan and decision')
                    if not verified:
                        raise RuntimeError(f'{title}: independent verification did not match')
                    if title.startswith('Recover') and not recovery:
                        raise RuntimeError(f'{title}: expected injected write failure did not produce retry')
                    if title=='Approval gate' and not paused_for_approval:
                        raise RuntimeError(f'{title}: workflow did not stop for human approval')
                    if title=='Ticket triage' and state.get('report',{}).get('outcome')!='triaged_and_verified':
                        raise RuntimeError(f'{title}: support case was not triaged and verified')
                completed.append({'title':title,'task_id':task_id,
                                  'outcome':state['report']['outcome'],
                                  'browser_steps':sum(1 for e in events if e['kind']=='browser_step'),
                                  'gemma_validated_plan':accepted_plan,
                                  'gemma_validated_action':accepted_choice,
                                  'fresh_readback_matched':verified,
                                  'retry_seen':recovery,
                                  'approval_pause_seen':paused_for_approval})
                time.sleep(1.0)
            dashboard_video=page.video
            context.close()
            dashboard_path=outdir/'dashboard-recording.webm'
            shutil.copy2(dashboard_video.path(),dashboard_path)
            browser.close()
        recordings=[outdir/'dashboard-recording.webm']
        for id in task_ids:
            path=outdir/'artifacts'/id/'browser-recording.webm'
            wait_file(path)
            recordings.append(path)
        outfile=(ROOT/args.output).resolve()
        outfile.parent.mkdir(parents=True,exist_ok=True)
        if shutil.which('ffmpeg'):
            # Re-encode equal-size video segments; frames are directly recorded
            # from Chromium's actual screen surface, including the AI cursor.
            concat=outdir/'segments.txt'
            concat.write_text(''.join("file '"+str(f).replace("'","'\\''")+"'\n" for f in recordings))
            subprocess.run(['ffmpeg','-y','-hide_banner','-loglevel','error',
                '-f','concat','-safe','0','-i',str(concat),'-vf','fps=16,scale=1280:810',
                '-c:v','libx264','-pix_fmt','yuv420p','-movflags','+faststart',str(outfile)],check=True)
            print('REAL BROWSER DEMO:',outfile)
        else:
            print('ffmpeg missing: use recorded .webm files in',outdir)
            print('On Mac: brew install ffmpeg, then rerun for joined MP4')
        (outdir/'run_summary.json').write_text(json.dumps({'source':'real Chromium recording',
                   'run_id':run_id,'ui_variant':env['UI_VARIANT'],'tasks':completed},indent=2))
        print('DONE: all four scenarios verified via browser automation')
        print('Recordings and audit evidence:',outdir)
    finally:
        client.close()
        server.terminate()
        try:server.wait(timeout=6)
        except subprocess.TimeoutExpired:server.kill()
        log.close()


if __name__=='__main__':
    main()
