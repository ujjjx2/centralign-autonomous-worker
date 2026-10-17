"""Bounded, observation-driven UI action selection.

The planner examines *current* HTML affordances before each action. It does not
trust page text as instructions and never grants tools outside the calling
workflow's allowlist. It can survive changed element IDs because it scores
visible labels, names, roles, accessible text and input types.
"""
from __future__ import annotations
from dataclasses import dataclass
import re
from typing import Any


@dataclass(frozen=True)
class ActionChoice:
    selector: str
    score: int
    reason: str
    alternatives: int


def normalize(value: str) -> str:
    return re.sub(r'[^a-z0-9]+', ' ', value.casefold()).strip()


def page_affordances(page) -> list[dict[str, Any]]:
    # Evaluation reads the DOM only. No arbitrary page JS is executed by the
    # model and the system never accepts a selector supplied by the document.
    return page.locator('a, button, input, select, textarea').evaluate_all('''nodes => nodes.map((e,i) => {
        const labels=e.labels ? Array.from(e.labels).map(x=>x.innerText).join(' ') : '';
        const rect=e.getBoundingClientRect();
        const style=getComputedStyle(e);
        return {index:i,tag:e.tagName.toLowerCase(),type:e.getAttribute('type')||'',
          name:e.getAttribute('name')||'',id:e.id||'',
          label:labels||'',text:(e.innerText||e.value||'').substring(0,120),
          placeholder:e.getAttribute('placeholder')||'',
          aria:e.getAttribute('aria-label')||'',href:e.getAttribute('href')||'',
          visible:rect.width>0&&rect.height>0&&style.visibility!=='hidden'&&style.display!=='none',
          disabled:!!e.disabled};
    })''')


def choose_action(items: list[dict], role: str, terms: list[str]) -> ActionChoice:
    valid_tags={'link':{'a'},'button':{'button','input'},'input':{'input','textarea'},'select':{'select'}}
    scored=[]
    for item in items:
        if item['tag'] not in valid_tags[role] or not item['visible'] or item['disabled']:
            continue
        if role=='input' and item['type'] in {'submit','button','checkbox','hidden'}:
            continue
        if role=='button' and item['tag']=='input' and item['type'] not in {'button','submit'}:
            continue
        fields=['label','aria','name','placeholder','text','id'] + (['href'] if role=='link' else [])
        score=0; reason=''
        for term in terms:
            needle=normalize(term)
            if not needle:continue
            for position,field in enumerate(fields):
                value=normalize(str(item.get(field,'')))
                if value == needle:
                    weight=120-position*7
                elif needle in value and len(needle)>2:
                    weight=65-position*3
                elif all(token in value.split() for token in needle.split()):
                    weight=35-position*2
                else:
                    continue
                if weight>score:
                    score=weight;reason=f"matched {field}: {item.get(field,'')}"
        if score>0:
            scored.append((score,item['index'],reason))
    if not scored:
        raise LookupError(f"No accessible {role} matching {terms}; observed {len(items)} controls")
    scored.sort(key=lambda x:(-x[0],x[1]))
    best=scored[0]
    return ActionChoice(selector=f'a, button, input, select, textarea',score=best[0],
                        reason=best[2],alternatives=len(scored))


def find_live_locator(page, role: str, terms: list[str]):
    items=page_affordances(page)
    scored=[]
    tag_match={'link':{'a'},'button':{'button','input'},'input':{'input','textarea'},'select':{'select'}}[role]
    for item in items:
        if item['tag'] not in tag_match or not item['visible'] or item['disabled']:continue
        if role=='input' and item['type'] in {'submit','button','checkbox','hidden'}:continue
        if role=='button' and item['tag']=='input' and item['type'] not in {'submit','button'}:continue
        fields=['label','aria','name','placeholder','text','id'] + (['href'] if role=='link' else [])
        for term in terms:
            needle=normalize(term)
            for p,field in enumerate(fields):
                value=normalize(str(item.get(field,'')))
                if not needle or not value:continue
                score=110-p*6 if needle==value else 55-p*3 if needle in value else 0
                if score:
                    scored.append((score,item['index'],f'{field}={item.get(field)}',item))
    if not scored:
        raise LookupError(f"No visible {role} matches {terms}; controls="+
                          repr([{'tag':x['tag'],'text':x['text'],'name':x['name'],'label':x['label']}
                                for x in items][:25]))
    scored.sort(key=lambda x:(-x[0],x[1]))
    score,idx,reason,item=scored[0]
    locator=page.locator('a, button, input, select, textarea').nth(idx)
    return locator, {'score':score,'reason':reason,'alternatives':len(scored),
                     'name':item['name'],'label':item['label'],'text':item['text']}
