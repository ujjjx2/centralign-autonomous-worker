#!/usr/bin/env python3
"""Offline classification + allowed-tool benchmark. No vendor API key required."""
from __future__ import annotations
import json
from pathlib import Path
from app.agent.policy import DecisionPolicy
from app.config import Settings
from app.db import Store

ROOT=Path(__file__).resolve().parents[1]
EXPECTED={
    'TKT-401':('access','high','Identity Support'),
    'TKT-402':('technical','normal','Engineering Support'),
    'TKT-403':('billing','normal','Finance Support'),
    'TKT-404':('technical','high','Engineering Support'),
}


def main():
    store=Store(ROOT/'data/company.sqlite3')
    policy=DecisionPolicy(Settings(model_backend='gemma'))
    results=[]
    for ticket in store.tickets():
        result=policy.classify_ticket(ticket['subject'],ticket['description'])
        observed=tuple(result[k] for k in ('category','priority','assigned_team'))
        results.append({'ticket':ticket['number'],'expected':EXPECTED[ticket['number']],
                        'observed':observed,'matched':observed==EXPECTED[ticket['number']]})
    passed=sum(r['matched'] for r in results)
    print(json.dumps({'workflow':'support_ticket','policy':'gemma4_e2b_with_rule_guards',
        'passed':passed,'total':len(results),'accuracy':passed/len(results),
        'cases':results},indent=2))
    if passed!=len(results):raise SystemExit(1)

if __name__=='__main__':main()
