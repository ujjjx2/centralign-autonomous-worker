"""Observable goal-state planner and two reusable sandbox skill graphs.

The planner chooses the next permissible action from *observed state*, not
from a one-shot instruction list. Tools remain separate; all writes are
checked for duplicates and verified after execution. The local model proposes
bounded intent/classification while business rules enforce safety.
"""
from __future__ import annotations
import time
from dataclasses import dataclass,field
from typing import Any
from app.agent.browser import BrowserTools,ToolError,RetryableToolError
from app.agent.extract import extract_invoice,ExtractionError
from app.agent.interpret import understand,NeedClarification
from app.agent.tickets import understand_ticket
from app.agent.planner_v6 import build_plan,ObservationPlanner


@dataclass
class TaskState:
    workflow: str
    goal: dict
    facts: dict=field(default_factory=dict)
    selected: dict|None=None
    source: dict|None=None
    lookup_done: bool=False
    entry_id: int|None=None
    wrote: bool=False
    verified: dict|None=None
    write_attempts: int=0
    approval_checked: bool=False
    approval_ok: bool=False
    adaptations: dict=field(default_factory=dict)


class GoalStatePlanner:
    """Small reusable decision graph, usable with either browser or HTTP tools.

    No untrusted document can create new tools. This is bounded symbolic
    planning, not open-domain chain-of-thought or free-form LLM planning.
    """
    def next_action(self,state:TaskState) -> tuple[str,str]:
        if state.selected is None:return ('discover','Find candidates in the source application')
        if state.source is None:return ('read_source','Open selected source document')
        if not state.facts:return ('extract','Derive structured facts from source content')
        if not state.lookup_done:return ('check_existing','Observe target application before writing')
        if state.entry_id is not None and state.verified is None:
            return ('verify','Read back persisted target record')
        if state.verified is not None:return ('complete','Goal predicate has been checked')
        if state.goal['operation']=='check':return ('complete_absent','Read-only task: no write permitted')
        if state.workflow=='invoice' and not state.approval_checked:
            return ('check_approval','Enforce threshold and human permission')
        if state.write_attempts>=3:return ('exhausted','No retries remain')
        return ('write','Attempt authorized target-system action')


def initialize_adaptive(worker,task_id,task,workflow,goal):
    plan=build_plan(worker.policy,task['instruction'],workflow,goal)
    worker.db.update_task(task_id,context={'validated_plan':plan.steps,'plan_origin':plan.origin})
    worker.event(task_id,'plan','gemma_task_decomposition',steps=plan.steps,
                 source=plan.origin,reason=plan.explanation,
                 note='LLM steps validated against required security and dependency milestones')
    return ObservationPlanner(worker.policy,task_id,worker,plan)


def adaptive_step(adaptive,stage,st,worker,task_id):
    # The symbolic goal predicates decide what is SAFE to do; Gemma chooses
    # among the afforded actions after every new observation.
    alternative={
        'read_source':['refresh_search'],
        'write':['recheck_target','refresh_form'],
        'verify':['recheck_target'],
    }
    offered=[stage]
    for a in alternative.get(stage,[]):
        if st.adaptations.get(a,0)<1:offered.append(a)
    observed={'workflow':st.workflow,'goal':st.goal,'selected':st.selected,
              'source_read':bool(st.source),'facts':st.facts,
              'lookup_done':st.lookup_done,'entry_id':st.entry_id,
              'approval_checked':st.approval_checked,
              'write_attempts':st.write_attempts,'previous_adaptations':st.adaptations}
    if len(offered)==1:return stage
    planned={'read_source':'refresh_search','write':'refresh_form',
             'verify':'recheck_target'}.get(stage)
    fallback=planned if planned in adaptive.plan.steps and planned in offered else stage
    chosen=adaptive.choose('next_action_'+stage,observed,offered,fallback)
    if chosen!=stage:st.adaptations[chosen]=st.adaptations.get(chosen,0)+1
    return chosen


def select_latest_matching(rows,goal,workflow):
    if workflow=='invoice':
        rows=[r for r in rows if r['vendor'].casefold()==goal['vendor'].casefold()]
        if goal.get('invoice_number'):
            rows=[r for r in rows if r['number'].casefold()==goal['invoice_number'].casefold()]
    else:
        if goal.get('ticket_number'):
            rows=[r for r in rows if r['number']==goal['ticket_number']]
    return max(rows,key=lambda r:(r['arrived_at'],r['id'])) if rows else None


def execute_invoice(worker,task_id,task):
    vendors=worker.db.vendors()
    goal=understand(task['instruction'],[v['name'] for v in vendors],worker.settings)
    worker.db.update_task(task_id,goal=goal)
    worker.event(task_id,'plan','goal_state',goal=goal,
                 method='dynamic bounded goal-state planner; replans after observations')
    st=TaskState('invoice',goal)
    planner=GoalStatePlanner()
    adaptive=initialize_adaptive(worker,task_id,task,'invoice',goal)
    chosen_candidates=[]
    with BrowserTools(worker.base_url,worker.settings,task_id,
            lambda step:worker.event(task_id,'browser_step','semantic_ui',**step)) as tools:
        worker.event(task_id,'tool_backend','execution_transport',backend=tools.backend_name,
                     fallback_reason=tools.fallback_reason)
        for iteration in range(35):
            action,why=planner.next_action(st)
            worker.event(task_id,'replan','goal_state_planner',step=iteration,
                         next_action=action,reason=why,observed={
                          'selected':bool(st.selected),'source_read':bool(st.source),
                          'facts':bool(st.facts),'lookup_done':st.lookup_done,
                          'entry_id':st.entry_id,'verified':st.verified is not None,
                          'write_attempts':st.write_attempts})
            recommended=action
            action=adaptive_step(adaptive,action,st,worker,task_id)
            if action!=recommended:
                worker.event(task_id,'adaptation','model_selected_alternative',
                             proposed=action,baseline=recommended)
            if action=='discover':
                try:
                    rows=tools.search_invoices(goal['vendor'])
                except ToolError as exc:
                    recovery=adaptive.recovery('invoice_search',str(exc),
                         {'query':goal['vendor']},['broaden_search','ask_human'],'broaden_search')
                    if recovery=='ask_human':raise NeedClarification('Invoice inbox unavailable; please check access')
                    worker.event(task_id,'recovery','source_search_failed_broaden',error=str(exc))
                    rows=tools.search_invoices('')
                worker.event(task_id,'observation','search_invoices',query=goal['vendor'],candidates=rows)
                st.selected=select_latest_matching(rows,goal,'invoice')
                if st.selected is None:
                    # A different real source-search strategy: unfiltered inbox
                    # then local identity matching. Never select another vendor.
                    worker.event(task_id,'recovery','broaden_source_search',reason='Filtered search empty')
                    broader=tools.search_invoices('')
                    st.selected=select_latest_matching(broader,goal,'invoice')
                    if st.selected is None:
                        raise NeedClarification('No matching invoice found after filtered and broad search. Check vendor/invoice number')
                worker.event(task_id,'decision','select_invoice',selected=st.selected,reason='Latest matching arrival')
            elif action=='refresh_search':
                rows=tools.search_invoices('')
                updated=select_latest_matching(rows,goal,'invoice')
                if updated is None:raise NeedClarification('Invoice no longer available after refreshing source inbox')
                st.selected=updated
                worker.event(task_id,'recovery','refresh_search',selected=updated,strategy='broad_inbox_search')
            elif action=='read_source':
                try:
                    st.source=tools.read_invoice(st.selected['id'])
                except ToolError as exc:
                    if st.adaptations.get('source_retry',0)>=1:raise
                    st.adaptations['source_retry']=1
                    selected=adaptive.recovery('read_invoice',str(exc),
                                 {'selected':st.selected},['refresh_search','ask_human'],'refresh_search')
                    if selected=='ask_human':raise NeedClarification('Source invoice page unavailable; please review')
                    rows=tools.search_invoices('')
                    refreshed=select_latest_matching(rows,goal,'invoice')
                    if not refreshed:raise NeedClarification('Invoice missing after retry of source search')
                    st.selected=refreshed
                    worker.event(task_id,'recovery','refresh_source_after_read_failure',selected=refreshed)
                    continue
                worker.event(task_id,'observation','read_invoice',url=st.source['url'],
                             characters=len(st.source['text']),untrusted_document=True)
            elif action=='extract':
                st.facts=extract_invoice(st.source['text'])
                if (st.facts['vendor']!=goal['vendor'] or
                    st.facts['number']!=st.selected['number']):
                    raise ToolError('Source document identity does not match inbox selection')
                worker.db.update_task(task_id,context={'source_invoice_id':st.selected['id'],'facts':st.facts})
                worker.event(task_id,'observation','extract_invoice',facts=st.facts)
            elif action=='check_existing':
                st.entry_id=tools.find_ledger_entry(st.facts['number'],st.facts['vendor'])
                st.lookup_done=True
                worker.event(task_id,'observation','check_existing_record',entry_id=st.entry_id)
            elif action=='recheck_target':
                found=tools.find_ledger_entry(st.facts['number'],st.facts['vendor'])
                if found:st.entry_id=found
                worker.event(task_id,'recovery','recheck_target',entry_id=found)
            elif action=='refresh_form':
                result=tools.refresh_form('invoice')
                worker.event(task_id,'recovery','refresh_form',**result)
            elif action=='check_approval':
                if st.facts['amount_cents']>=worker.settings.approval_threshold_cents:
                    current=worker.db.task(task_id)['approval']
                    if not current or current['state']!='approved' or current['invoice_id']!=st.selected['id']:
                        reason=(f"Invoice {st.facts['number']} for "
                                f"{st.facts['amount_cents']/100:.2f} USD requires approval")
                        worker.db.request_approval(task_id,st.selected['id'],reason)
                        worker.db.update_task(task_id,status='awaiting_approval')
                        worker.event(task_id,'approval_required','human_approval',reason=reason,
                                     invoice=st.facts)
                        return
                    worker.event(task_id,'approval_granted','human_approval',invoice=st.facts['number'])
                st.approval_ok=True
                st.approval_checked=True
            elif action=='write':
                decision=worker.policy.next_action('invoice_ready_to_write',
                    {'goal':goal,'invoice':st.facts,'existing':False,'approval_required':False},
                    ['create_ledger_entry','ask_human'],'create_ledger_entry')
                worker.event(task_id,'decision','policy_next_action',tool_choice=decision['tool'],
                             stage=decision['stage'],allowed_tools=decision['allowed_tools'],
                             decision_mode=decision['decision_mode'],reason=decision['reason'],
                             model_diagnostic=decision.get('model_diagnostic'))
                if decision['tool']=='ask_human':
                    raise NeedClarification('The worker requested human review before recording')
                st.write_attempts+=1
                # A new observation is made on EVERY retry (uncertain submit).
                previously=tools.find_ledger_entry(st.facts['number'],st.facts['vendor'])
                if previously:
                    st.entry_id=previously
                    worker.event(task_id,'adaptation','idempotent_readback',entry_id=previously)
                    continue
                try:
                    worker.event(task_id,'action','create_ledger_entry',attempt=st.write_attempts,fields=st.facts)
                    st.entry_id=tools.write_ledger_entry(st.selected['id'],st.facts,task_id)
                    st.wrote=True
                    worker.event(task_id,'observation','create_ledger_entry',entry_id=st.entry_id)
                except RetryableToolError as exc:
                    worker.event(task_id,'retry','create_ledger_entry',attempt=st.write_attempts,
                                 reason=str(exc),next_step='Model-guided recovery with mandatory readback')
                    # Always read the target first: a lost response may conceal a committed write.
                    existing=tools.find_ledger_entry(st.facts['number'],st.facts['vendor'])
                    if existing:
                        st.entry_id=existing
                        worker.event(task_id,'recovery','write_may_have_committed',entry_id=existing)
                        continue
                    if st.write_attempts>=3:raise ToolError('Invoice write failed after three attempts: '+str(exc))
                    decision=adaptive.recovery('write_invoice',str(exc),
                        {'attempt':st.write_attempts,'target_record_exists':False},
                        ['reobserve_target','refresh_form_and_retry','ask_human'],'reobserve_target')
                    if decision=='ask_human':
                        raise NeedClarification('Invoice submission failed; human intervention requested')
                    if decision=='refresh_form_and_retry':
                        result=tools.refresh_form('invoice')
                        worker.event(task_id,'recovery','alternate_form_refresh',**result)
                    else:
                        worker.event(task_id,'recovery','reobserve_target_then_retry',attempt=st.write_attempts)
                    time.sleep(.15*st.write_attempts)
            elif action=='verify':
                path=worker.settings.artifacts_dir/task_id/'verification.png'
                st.verified=tools.verify_entry(st.entry_id,st.facts,path)
                worker.event(task_id,'verification','verify_entry',**st.verified)
                if not st.verified['matched']:
                    worker.event(task_id,'recovery','verification_mismatch',
                                 strategy='fresh_readback_before_escalation')
                    again=tools.verify_entry(st.entry_id,st.facts,path)
                    worker.event(task_id,'verification','second_independent_readback',**again)
                    if again['matched']:
                        st.verified=again
                        continue
                    if st.wrote:raise ToolError('Persistent post-write mismatch after two independent readbacks')
                    raise NeedClarification('Existing ledger record conflicts with source invoice')
            elif action=='complete':
                worker.complete(task_id,'recorded_and_verified' if st.wrote else 'already_recorded',
                    entry_id=st.entry_id,invoice=st.facts,verification=st.verified,
                    evidence_url=f'/api/tasks/{task_id}/evidence',
                    browser_video_url=f'/api/tasks/{task_id}/browser-video' if tools.backend_name=='playwright_chromium' else None)
                return
            elif action=='complete_absent':
                worker.complete(task_id,'not_recorded',invoice=st.facts,
                                verified_by='Read-only missing-record check')
                return
            else:raise ToolError('The planner could not reach a safe goal state')
    raise ToolError('Iteration bound reached before invoice goal was verified')


def execute_ticket(worker,task_id,task):
    goal=understand_ticket(task['instruction'])
    worker.db.update_task(task_id,goal=goal)
    worker.event(task_id,'plan','goal_state',goal=goal,
                 method='dynamic bounded goal-state planner; replans after observations')
    st=TaskState('ticket',goal)
    planner=GoalStatePlanner()
    adaptive=initialize_adaptive(worker,task_id,task,'ticket',goal)
    with BrowserTools(worker.base_url,worker.settings,task_id,
            lambda step:worker.event(task_id,'browser_step','semantic_ui',**step)) as tools:
        worker.event(task_id,'tool_backend','execution_transport',backend=tools.backend_name,
                     fallback_reason=tools.fallback_reason)
        for iteration in range(35):
            action,why=planner.next_action(st)
            worker.event(task_id,'replan','goal_state_planner',step=iteration,next_action=action,
                         reason=why,observed={'selected':bool(st.selected),'facts':bool(st.facts),
                                'lookup_done':st.lookup_done,'entry_id':st.entry_id,
                                'verified':st.verified is not None})
            recommended=action
            action=adaptive_step(adaptive,action,st,worker,task_id)
            if action!=recommended:
                worker.event(task_id,'adaptation','model_selected_alternative',
                             proposed=action,baseline=recommended)
            if action=='discover':
                try:
                    rows=tools.search_tickets(goal['ticket_number'] or '')
                except ToolError as exc:
                    recovery=adaptive.recovery('ticket_search',str(exc),
                         {'query':goal['ticket_number']},['broaden_search','ask_human'],'broaden_search')
                    if recovery=='ask_human':raise NeedClarification('Ticket inbox unavailable; please check access')
                    worker.event(task_id,'recovery','source_search_failed_broaden',error=str(exc))
                    rows=tools.search_tickets('')
                worker.event(task_id,'observation','search_tickets',candidates=rows)
                st.selected=select_latest_matching(rows,goal,'ticket')
                if st.selected is None:
                    worker.event(task_id,'recovery','broaden_source_search',reason='Filtered search empty')
                    rows=tools.search_tickets('')
                    st.selected=select_latest_matching(rows,goal,'ticket')
                    if st.selected is None:
                        raise NeedClarification('Ticket not found after alternate search; provide an existing ticket reference')
                worker.event(task_id,'decision','select_ticket',selected=st.selected)
            elif action=='refresh_search':
                rows=tools.search_tickets('')
                st.selected=select_latest_matching(rows,goal,'ticket')
                if st.selected is None:raise NeedClarification('Ticket not available after refreshing search')
                worker.event(task_id,'recovery','refresh_search',selected=st.selected,strategy='broad_ticket_search')
            elif action=='read_source':
                try:
                    st.source=tools.read_ticket(st.selected['id'])
                except ToolError as exc:
                    if st.adaptations.get('source_retry',0)>=1:raise
                    st.adaptations['source_retry']=1
                    selected=adaptive.recovery('read_ticket',str(exc),
                                 {'selected':st.selected},['refresh_search','ask_human'],'refresh_search')
                    if selected=='ask_human':raise NeedClarification('Support ticket document unavailable; please review')
                    rows=tools.search_tickets('')
                    refreshed=select_latest_matching(rows,goal,'ticket')
                    if not refreshed:raise NeedClarification('Ticket missing after alternate search')
                    st.selected=refreshed
                    worker.event(task_id,'recovery','refresh_source_after_read_failure',selected=refreshed)
                    continue
                if st.source['number']!=st.selected['number']:raise ToolError('Ticket identity mismatch')
                worker.event(task_id,'observation','read_ticket',source=st.source['url'],
                             subject=st.source['subject'],untrusted_document=True)
            elif action=='extract':
                cls=worker.policy.classify_ticket(st.source['subject'],st.source['description'])
                st.facts={key:st.source[key] for key in ('number','requester','subject')}
                st.facts.update({key:cls[key] for key in ('category','priority','assigned_team')})
                worker.db.update_task(task_id,context={'source_ticket_id':st.selected['id'],
                                                      'facts':st.facts,'classification':cls})
                worker.event(task_id,'decision','classify_and_route',**cls)
            elif action=='check_existing':
                st.entry_id=tools.find_case(st.facts['number'])
                st.lookup_done=True
                worker.event(task_id,'observation','check_existing_case',case_id=st.entry_id)
            elif action=='recheck_target':
                found=tools.find_case(st.facts['number'])
                if found:st.entry_id=found
                worker.event(task_id,'recovery','recheck_target',case_id=found)
            elif action=='refresh_form':
                result=tools.refresh_form('ticket')
                worker.event(task_id,'recovery','refresh_form',**result)
            elif action=='write':
                decision=worker.policy.next_action('ticket_ready_to_route',
                    {'goal':goal,'source':st.source,'recommended_classification':st.facts},
                    ['create_support_case','ask_human'],'create_support_case')
                worker.event(task_id,'decision','policy_next_action',tool_choice=decision['tool'],
                             stage=decision['stage'],allowed_tools=decision['allowed_tools'],
                             decision_mode=decision['decision_mode'],reason=decision['reason'],
                             model_diagnostic=decision.get('model_diagnostic'))
                if decision['tool']=='ask_human':
                    raise NeedClarification('Worker requested human review before routing')
                st.write_attempts+=1
                previous=tools.find_case(st.facts['number'])
                if previous:
                    st.entry_id=previous
                    worker.event(task_id,'adaptation','idempotent_readback',case_id=previous)
                    continue
                worker.event(task_id,'action','create_support_case',fields=st.facts)
                try:
                    st.entry_id=tools.write_case(st.selected['id'],st.facts,task_id)
                except RetryableToolError as exc:
                    existing=tools.find_case(st.facts['number'])
                    if existing:
                        st.entry_id=existing
                        worker.event(task_id,'recovery','case_may_have_committed',case_id=existing)
                        continue
                    if st.write_attempts>=3:raise ToolError('Case write failed after three attempts: '+str(exc))
                    decision=adaptive.recovery('write_case',str(exc),
                        {'attempt':st.write_attempts,'target_record_exists':False},
                        ['reobserve_target','refresh_form_and_retry','ask_human'],'reobserve_target')
                    if decision=='ask_human':raise NeedClarification('Support case submission failed; review requested')
                    if decision=='refresh_form_and_retry':
                        worker.event(task_id,'recovery','alternate_form_refresh',**tools.refresh_form('ticket'))
                    else:worker.event(task_id,'recovery','reobserve_target_then_retry',attempt=st.write_attempts)
                    time.sleep(.15*st.write_attempts)
                    continue
                st.wrote=True
                worker.event(task_id,'observation','write_case',case_id=st.entry_id)
            elif action=='verify':
                path=worker.settings.artifacts_dir/task_id/'verification.png'
                st.verified=tools.verify_case(st.entry_id,st.facts,path)
                worker.event(task_id,'verification','verify_case',**st.verified)
                if not st.verified['matched']:
                    worker.event(task_id,'recovery','verification_mismatch',
                                 strategy='fresh_readback_before_escalation')
                    again=tools.verify_case(st.entry_id,st.facts,path)
                    worker.event(task_id,'verification','second_independent_readback',**again)
                    if again['matched']:
                        st.verified=again
                        continue
                    if st.wrote:raise ToolError('Persistent case mismatch after two independent readbacks')
                    raise NeedClarification('Existing case conflicts with observed classification')
            elif action=='complete':
                worker.complete(task_id,'triaged_and_verified' if st.wrote else 'already_triaged',
                    case_id=st.entry_id,case=st.facts,verification=st.verified,
                    evidence_url=f'/api/tasks/{task_id}/evidence',
                    browser_video_url=f'/api/tasks/{task_id}/browser-video' if tools.backend_name=='playwright_chromium' else None)
                return
            elif action=='complete_absent':
                worker.complete(task_id,'not_triaged',ticket=st.facts,
                                verified_by='No matching case observed')
                return
            else:raise ToolError('Task cannot proceed safely')
    raise ToolError('Iteration bound reached before support goal verified')
