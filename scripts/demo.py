#!/usr/bin/env python3
"""Live demo against the running sandbox; no external services or API key."""
from __future__ import annotations
import argparse
import json
import sys
import time
from urllib.request import Request, urlopen
from urllib.error import HTTPError


def api(base,path,method="GET",body=None):
    headers={"Content-Type":"application/json"}
    req=Request(base+path,headers=headers,method=method,
                data=json.dumps(body).encode() if body is not None else (b"" if method=="POST" else None))
    try:
        with urlopen(req,timeout=10) as response:
            return json.load(response)
    except HTTPError as exc:
        raise RuntimeError(f"HTTP {exc.code}: {exc.read().decode()}") from exc


def run(base,instruction,approve=False):
    created=api(base,"/api/tasks","POST",{"instruction":instruction})
    task_id=created["task_id"]
    print(f"\nTask {task_id[:8]} · {instruction}",flush=True)
    last_event_id=None
    for _ in range(150):
        data=api(base,"/api/tasks/"+task_id)
        for e in data["events"]:
            if last_event_id is None or e["id"]>last_event_id:
                print(f"  {e['kind']:18} {e['tool']:24} {str(e['detail'])[:105]}",flush=True)
                last_event_id=e["id"]
        if data["status"]=="awaiting_approval":
            if approve:
                print("  [DEMO] Approving invoice after displaying required manual gate",flush=True)
                api(base,f"/api/tasks/{task_id}/approve","POST")
                approve=False
                time.sleep(.4)
                continue
            print("  PAUSED: manager approval needed in dashboard",flush=True)
            return data
        if data["status"] in {"completed","failed","rejected","needs_input"}:
            print("  FINAL STATUS:",data["status"],"·",(data["report"] or {}).get("outcome",data["error"]),flush=True)
            return data
        time.sleep(.2)
    raise RuntimeError("Task did not reach a terminal or approval state")


def main():
    parser=argparse.ArgumentParser(description="Replay deterministic end-to-end agent scenarios")
    parser.add_argument("--url",default="http://127.0.0.1:8000")
    parser.add_argument("--scenario",choices=["standard","approval","retry","injection","ticket","incident","all"],default="all")
    args=parser.parse_args()
    base=args.url.rstrip("/")
    assert api(base,"/health")["ok"], "Sandbox is not running"
    print("Connected to local CentrAlign demo at",base)
    if args.scenario in {"standard","all"}:
        run(base,"Find the latest invoice from Northstar Labs and record it")
    if args.scenario in {"approval","all"}:
        run(base,"Record the latest invoice from Acme Services",approve=True)
    if args.scenario in {"retry","all"}:
        api(base,"/api/demo/fail-next-write","POST")
        run(base,"Record the latest invoice from Harbor Office")
    if args.scenario in {"injection","all"}:
        run(base,"Record invoice BP-774 from BluePeak Cloud")
    if args.scenario in {'ticket','all'}:
        run(base,'Triage ticket TKT-402 and assign it to the right team')
    if args.scenario in {'incident','all'}:
        run(base,'Triage the latest support ticket')
    print('\nLedger now contains',len(api(base,'/api/ledger')),'records')
    print('Helpdesk now contains',len(api(base,'/api/cases')),'saved cases')

if __name__=="__main__":
    try:main()
    except Exception as error:
        print("Demo error:",error,file=sys.stderr)
        sys.exit(1)
