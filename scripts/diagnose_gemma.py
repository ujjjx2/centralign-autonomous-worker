#!/usr/bin/env python3
"""Call real locally installed Gemma without starting the company web app.

No invoice or ticket is written. Print only validated decisions/diagnostics,
not raw model reasoning or confidential user content.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.agent.gemma import GemmaClient, InvalidModelResponse, ModelUnavailable
from app.agent.planner_v6 import canonical_steps, validate_plan
from app.config import Settings


def main():
    parser=argparse.ArgumentParser(description='Test Gemma 4 E2B decision protocol locally')
    parser.add_argument('--full',action='store_true',help='Also test planning and next-action choice')
    args=parser.parse_args()
    settings=Settings()
    client=GemmaClient(settings.ollama_url,settings.ollama_timeout)
    info=client.available()
    print('Ollama:',info['endpoint'],'Model:',info['model'],'Available:',info['available'])
    if not info['available']:
        print('ERROR:',info['reason'])
        return 1
    tasks=[('invoice_operation',{'instruction':'Record the latest invoice from Northstar Labs'})]
    if args.full:
        required=canonical_steps('invoice','record')
        tasks.extend([
            ('plan', {'user_goal':'Record the latest invoice from Northstar Labs',
                      'workflow':'invoice','parsed_goal':{'operation':'record','vendor':'Northstar Labs'},
                      'required_milestones':required}),
            ('action', {'stage':'invoice_ready_to_write','observed':{'invoice_present':True,'record_existing':False}}),
        ])
    ok=True
    for task,observation in tasks:
        try:
            response=client.decide(task,observation,
                ['create_ledger_entry','ask_human'] if task=='action' else None)
            if task=='plan':validate_plan(response['steps'],'invoice','record')
            print('PASS',task,response,'protocol:',client.last_diagnostic)
        except (InvalidModelResponse,ModelUnavailable,ValueError) as exc:
            ok=False
            print('FAIL',task,type(exc).__name__,str(exc))
            print('  protocol:',client.last_diagnostic)
    return 0 if ok else 1

if __name__=='__main__':raise SystemExit(main())
