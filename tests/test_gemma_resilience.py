"""Adversarial local Gemma/Ollama response-shape regression cases."""
import json
import httpx
import pytest
from app.agent.gemma import GemmaClient, InvalidModelResponse, ModelUnavailable


def fake_ollama(monkeypatch, handler):
    original = httpx.Client
    def factory(*args, **kwargs):
        kwargs['transport'] = httpx.MockTransport(handler)
        return original(*args, **kwargs)
    monkeypatch.setattr('app.agent.gemma.httpx.Client', factory)


def answer(raw):
    return httpx.Response(200, json={'message': {'content': raw}})


def test_no_reason_is_still_valid_when_action_is_allowlisted(monkeypatch):
    fake_ollama(monkeypatch, lambda req: answer('{"tool":"verify"}'))
    result = GemmaClient().decide('action', {'stage': 'verify'}, ['verify', 'ask_human'])
    assert result['tool'] == 'verify' and result['reason']


def test_markdown_json_and_alias_are_accepted_after_validation(monkeypatch):
    fake_ollama(monkeypatch, lambda req: answer('```json\n{"action":"verify"}\n```'))
    result = GemmaClient().decide('action', {}, ['verify', 'ask_human'])
    assert result['tool'] == 'verify'


def test_invalid_schema_reply_retries_json_mode(monkeypatch):
    observed = []
    def responder(req):
        payload=json.loads(req.content)
        observed.append(payload)
        return answer('Not valid JSON') if len(observed)==1 else answer('{"tool":"refresh_form"}')
    fake_ollama(monkeypatch, responder)
    client=GemmaClient()
    result=client.decide('action', {}, ['write', 'refresh_form'])
    assert result['tool']=='refresh_form'
    assert observed[0]['format']['type']=='object'
    assert observed[1]['format']=='json'
    assert client.last_diagnostic['response_format']=='json_retry'
    assert client.last_diagnostic['accepted']


def test_model_generated_plan_array_without_reason(monkeypatch):
    steps=['discover','read_source','extract','check_existing','check_approval','write','verify','complete']
    fake_ollama(monkeypatch, lambda req: answer(json.dumps(steps)))
    assert GemmaClient().decide('plan', {})['steps']==steps


def test_invalid_tool_is_never_executed_even_on_json_retry(monkeypatch):
    calls=[]
    def responder(req):
        calls.append(req)
        return answer('{"action":"send_money"}')
    fake_ollama(monkeypatch, responder)
    with pytest.raises(InvalidModelResponse,match='Rejected both'):
        GemmaClient().decide('action', {}, ['verify','ask_human'])
    assert len(calls)==2


def test_empty_content_cannot_be_mistaken_for_valid_response(monkeypatch):
    fake_ollama(monkeypatch, lambda req: answer(''))
    with pytest.raises(InvalidModelResponse): GemmaClient().decide('invoice_operation', {})


def test_timed_out_request_is_distinct_from_invalid_json(monkeypatch):
    def responder(req):
        raise httpx.ReadTimeout('test timeout')
    fake_ollama(monkeypatch,responder)
    with pytest.raises(ModelUnavailable,match='timed out'):
        GemmaClient().decide('invoice_operation', {})


def test_semantically_incomplete_model_plan_gets_safe_repair_request():
    from app.agent.planner_v6 import build_plan, canonical_steps
    class RepairModel:
        def __init__(self): self.observations=[]
        def decide(self,task,content,allowed=None):
            self.observations.append(content)
            if len(self.observations)==1:
                return {'steps':['discover','read_source','extract','check_existing','write','verify','complete']}
            return {'steps':canonical_steps('invoice','record')}
    class Policy:
        model=RepairModel()
    plan=build_plan(Policy(), 'Record the latest invoice from Northstar Labs',
                    'invoice',{'operation':'record','vendor':'Northstar Labs'})
    assert plan.origin=='gemma_validated'
    assert 'check_approval' in plan.steps
    assert len(Policy.model.observations)==2
    assert 'validation_error' in Policy.model.observations[1]
