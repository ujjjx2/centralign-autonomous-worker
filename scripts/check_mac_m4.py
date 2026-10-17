#!/usr/bin/env python3
"""Apple Silicon, Ollama model availability, and Chromium smoke test."""
from __future__ import annotations
import argparse,platform,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.agent.gemma import GemmaClient
from app.config import Settings

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--skip-browser',action='store_true')
    p.add_argument('--allow-non-mac',action='store_true')
    p.add_argument('--skip-model',action='store_true',help='Skip Ollama check for CI only')
    args=p.parse_args()
    errors=[]
    print('Operating system:',platform.system(),'CPU:',platform.machine())
    print('Python:',sys.version.split()[0])
    if not ((3,10)<=sys.version_info[:2]<(3,15)):errors.append('Use Python 3.10–3.14; prefer 3.12')
    if not args.allow_non_mac and (platform.system()!='Darwin' or platform.machine()!='arm64'):
        errors.append('Native macOS ARM64 terminal and Python required')
    if not args.skip_model:
        settings=Settings()
        info=GemmaClient(settings.ollama_url).available()
        print('Gemma 4 E2B:',info)
        if not info['available']:errors.append('Start Ollama and run: ollama pull gemma4:e2b')
        else:
            try:
                reply=GemmaClient(settings.ollama_url,settings.ollama_timeout).decide(
                    'invoice_operation',{'instruction':'Record the latest invoice from Northstar Labs'})
                print('Inference:',reply)
                if reply['operation']!='record':errors.append('Unexpected model decision on smoke input')
                from app.agent.planner_v6 import canonical_steps,validate_plan
                required=canonical_steps('invoice','record')
                plan=GemmaClient(settings.ollama_url,settings.ollama_timeout).decide('plan',{
                    'user_goal':'Record the latest invoice from Northstar Labs',
                    'parsed_goal':{'workflow':'invoice','operation':'record','vendor':'Northstar Labs'},
                    'workflow':'invoice', 'required_milestones':required,
                    'skills':{'discover':'Search the source','read_source':'Read invoice',
                              'extract':'Extract fields','check_existing':'Check duplicates',
                              'check_approval':'Enforce approval','write':'Record form',
                              'verify':'Read back','complete':'Report with evidence'}
                })
                print('LLM-generated plan:',plan)
                validate_plan(plan['steps'],'invoice','record')
            except Exception as exc:errors.append('Model inference failed: '+str(exc))
    if not args.skip_browser:
        try:
            from playwright.sync_api import sync_playwright
            with sync_playwright() as p:
                b=p.chromium.launch(headless=True)
                page=b.new_page();page.set_content('<button>Test browser</button>')
                assert page.get_by_role('button',name='Test browser').count()==1
                b.close();print('Playwright Chromium: OK')
        except Exception as exc:errors.append('Chromium unavailable: '+str(exc))
    if errors:
        for err in errors:print('ERROR:',err,file=sys.stderr)
        return 1
    print('All preflight checks passed');return 0
if __name__=='__main__':raise SystemExit(main())
