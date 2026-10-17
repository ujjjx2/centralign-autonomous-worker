"""Validated LLM task decomposition and observation-driven action selection.

The model proposes a task plan but NEVER grants permissions. Mandatory causal
and safety milestones are checked by code before the plan is accepted.
Dynamic choices are constrained to affordances of the current observed state.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any

# These represent executable skills, not raw shell commands, URLs, or Python.
ACTIONS = ('discover','read_source','extract','check_existing','check_approval',
           'write','verify','complete','refresh_search','recheck_target',
           'refresh_form','ask_human')

DESCRIPTIONS = {
    'discover':'Search the source application for candidate documents',
    'read_source':'Open the chosen source document',
    'extract':'Derive validated structured facts from the source',
    'check_existing':'Look for a pre-existing target record (idempotency)',
    'check_approval':'Enforce mandatory approval policy',
    'write':'Submit the authorized company form',
    'verify':'Read back the saved target record and compare exact fields',
    'complete':'Report outcome with persisted verification evidence',
    'refresh_search':'Revisit the source inbox with a different allowed query',
    'recheck_target':'Read back the target application before further action',
    'refresh_form':'Reopen the target form before safely retrying',
    'ask_human':'Stop and request missing information or authorization',
}


def canonical_steps(workflow: str, operation: str) -> list[str]:
    if workflow not in {'invoice','ticket'} or operation not in {'record','triage','check'}:
        raise ValueError('Unsupported workflow or goal operation')
    core=['discover','read_source','extract','check_existing']
    if operation!='check':
        if workflow=='invoice':core.append('check_approval')
        core.append('write')
    core+=['verify','complete'] if operation!='check' else ['complete']
    return core


@dataclass(frozen=True)
class ValidatedPlan:
    steps: list[str]
    origin: str
    explanation: str
    proposed: list[str] | None = None


def validate_plan(steps: Any, workflow: str, operation: str) -> list[str]:
    """Model can add safe refresh steps; cannot skip/reorder core safety milestones."""
    core=canonical_steps(workflow,operation)
    if not isinstance(steps,list) or not (len(core)<=len(steps)<=12):
        raise ValueError('Plan must contain a bounded list of actions')
    if any(not isinstance(a,str) or a not in ACTIONS for a in steps):
        raise ValueError('Unrecognized action requested')
    if len(set(steps))!=len(steps):
        raise ValueError('Repeated actions in initial plan')
    actual=[a for a in steps if a in core]
    if actual!=core:
        raise ValueError('Missing or reordered mandatory milestones')
    if steps[-1]!='complete':
        raise ValueError('Completion must be last')
    # Extra refresh steps are permitted, but never before initial discovery,
    # after completion, or as an authorization bypass.
    optional=set(steps)-set(core)
    if optional-{'refresh_search','recheck_target','refresh_form'}:
        raise ValueError('Nonessential action not supported by the initial plan')
    for i,step in enumerate(steps):
        if step=='refresh_search' and not (steps.index('discover')<i<steps.index('read_source')):
            raise ValueError('Refresh search must follow discovery')
        if step=='recheck_target' and not (steps.index('check_existing')<i<steps.index('complete')):
            raise ValueError('Recheck must follow the initial target lookup')
        if step=='refresh_form' and not (('write' in steps) and steps.index('check_existing')<i<steps.index('write')):
            raise ValueError('Refreshing a form requires a valid pending write')
    return list(steps)


def build_plan(policy, instruction: str, workflow: str, goal: dict) -> ValidatedPlan:
    """Real Gemma decomposition or explicit deterministic fallback (never fake it)."""
    baseline=canonical_steps(workflow,goal['operation'])
    if policy.model is None:
        return ValidatedPlan(baseline,'rules_fallback','No model configured: bounded verified plan')
    from app.agent.gemma import InvalidModelResponse,ModelUnavailable
    context={
        'user_goal':instruction[:600], 'parsed_goal':goal,
        'workflow':workflow,
        'required_milestones':baseline,
        'skills':{a:DESCRIPTIONS[a] for a in ACTIONS},
        'constraints':['Read-only goals cannot write','Invoice writes need threshold approval',
                       'Never mark a write complete without fresh readback',
                       'No external websites or arbitrary commands']
    }
    from app.agent.gemma import InvalidModelResponse,ModelUnavailable
    try:
        proposal=policy.model.decide('plan',context)
        try:
            steps=validate_plan(proposal['steps'],workflow,goal['operation'])
        except ValueError as exc:
            # A syntactically valid plan may still omit a mandatory milestone.
            # Give Gemma one chance to repair it; never execute an unsafe plan.
            repaired=policy.model.decide('plan',{
                **context,'previous_proposal':proposal.get('steps',[]),
                'repair_instruction':'Previous plan failed validation. Every required_milestone must appear exactly once and IN ORDER. Do not remove any. End with complete.',
                'validation_error':str(exc)[:140]
            })
            steps=validate_plan(repaired['steps'],workflow,goal['operation'])
            proposal=repaired
        return ValidatedPlan(steps,'gemma_validated',proposal.get('reason','')[:400],steps)
    except (InvalidModelResponse,ModelUnavailable,ValueError,KeyError,TypeError) as exc:
        return ValidatedPlan(baseline,'validated_fallback',
                             'Model plan unavailable or rejected: '+type(exc).__name__)



class ObservationPlanner:
    """Select next allowed executable action using the live state and prior failures."""
    def __init__(self,policy,task_id:str,worker,plan:ValidatedPlan):
        self.policy=policy;self.task_id=task_id;self.worker=worker;self.plan=plan
        self.recovery_count={}

    def choose(self,stage:str,observed:dict,allowed:list[str],fallback:str) -> str:
        if fallback not in allowed or not allowed:
            raise ValueError('No authorized fallback action')
        decision=self.policy.next_action(stage,{
            'current_observation':observed,
            'initial_plan':self.plan.steps,
            'prior_recoveries':self.recovery_count,
        },allowed,fallback)
        action=decision['tool']
        self.worker.event(self.task_id,'adaptive_decision','observation_policy',
                          stage=stage,allowed=allowed,selected=action,
                          decision_mode=decision['decision_mode'],reason=decision['reason'],
                          model_diagnostic=decision.get('model_diagnostic'),observation=observed)
        return action

    def recovery(self,stage:str,error:str,observed:dict,allowed:list[str],fallback:str)->str:
        attempts=self.recovery_count.get(stage,0)+1
        self.recovery_count[stage]=attempts
        return self.choose('recover_'+stage,{
            'error':error[:400],'failure_count':attempts,**observed
        },allowed,fallback)
