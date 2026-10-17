"""Gemma 4 E2B local reasoning + deterministic business and permission guards.

Model output can recommend permitted actions. It cannot introduce tools, weaken
critical incident priority, bypass human approvals, or override known facts.
"""
from __future__ import annotations
from typing import Any
from app.config import Settings
from app.agent.gemma import GemmaClient, ModelUnavailable, InvalidModelResponse


class DecisionPolicy:
    def __init__(self, settings: Settings):
        self.settings=settings
        self.model=GemmaClient(settings.ollama_url,settings.ollama_timeout) if settings.model_backend=='gemma' else None

    def model_json(self, system: str, observation: dict) -> dict|None:
        if self.model is None:return None
        try:
            if 'allowed_actions' in observation:
                return self.model.decide('action',{'stage':observation.get('stage'),
                         'observed':observation.get('observed',{})},observation['allowed_actions'])
            if 'subject' in observation and 'description' in observation:
                return self.model.decide('ticket_classification',{
                    'subject':observation['subject'][:180],
                    'description':observation['description'][:2000]})
        except InvalidModelResponse:
            # Badly formatted JSON never becomes executable instructions.
            return None
        return None

    def next_action(self,stage: str,observation:dict,allowed:list[str],fallback:str):
        if not allowed or fallback not in allowed:raise ValueError('Unsafe or empty action set')
        reply=self.model_json('Choose one permitted next action',{'stage':stage,
                       'observed':observation,'allowed_actions':allowed}) if self.model else None
        chosen=reply.get('tool') if isinstance(reply,dict) else None
        if chosen not in allowed:
            chosen=fallback
            mode='validated_fallback' if self.model else 'offline_policy'
            reason='Invalid structured action proposal; using authorized fallback'
        else:
            mode='gemma4_e2b'
            reason=str(reply.get('reason',''))[:240]
        return {'tool':chosen,'stage':stage,'allowed_tools':allowed,
                'decision_mode':mode,'reason':reason,
                'model_diagnostic':self.model.last_diagnostic if self.model else None}

    def classify_ticket(self,subject:str,description:str)->dict[str,Any]:
        text=(subject+' '+description).lower()
        if any(w in text for w in ('outage','system-wide','service down','production unavailable')):
            category='technical'
        elif any(w in text for w in ('invoice','refund','charge','payment','billing')):
            category='billing'
        elif any(w in text for w in ('login','sign in','password','permission','access','oauth','account locked')):
            category='access'
        elif any(w in text for w in ('error','bug','export','crash','api','server','unavailable','down')):
            category='technical'
        else:category='general'
        critical=any(w in text for w in ('entire company','all customers','system-wide',
                                         'production outage','security breach','data leak'))
        urgency='high' if critical or any(w in text for w in ('blocked','urgent','cannot work','critical')) else 'normal'
        strong_category=any(w in text for w in (
            'outage','system-wide','service down','production unavailable',
            'invoice','refund','charge','payment','billing','login','sign in',
            'password','permission','access','oauth','account locked',
            'error','bug','export','crash','api','server','unavailable','down'))
        explicit_urgency=critical or any(w in text for w in ('blocked','urgent','cannot work','critical'))
        reply=self.model_json('Classify support ticket',{'subject':subject,'description':description}) if self.model else None
        mode='offline_policy'
        if isinstance(reply,dict):
            guess_category=reply.get('category')
            guess_priority=reply.get('priority')
            if guess_category in {'billing','access','technical','general'} and (not strong_category or guess_category==category):
                category=guess_category;mode='gemma4_e2b'
            if guess_priority in {'normal','high'}:
                # Model cannot downgrade an explicit urgency cue or upgrade without one.
                if explicit_urgency:urgency='high'
                else:urgency='normal'
        if critical:
            urgency='high'
            if 'outage' in text or 'system-wide' in text:category='technical'
        teams={'billing':'Finance Support','access':'Identity Support',
               'technical':'Engineering Support','general':'Customer Operations'}
        return {'category':category,'priority':urgency,'assigned_team':teams[category],
                'decision_mode':mode,'rationale':str(reply.get('reason',''))[:240]
                if mode=='gemma4_e2b' else 'Rule-based safety signals and critical-incident escalation'}
