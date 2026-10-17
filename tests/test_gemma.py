"""Test the actual Ollama JSON protocol via fake localhost HTTP responses.

These are protocol tests, not claims that the actual Gemma weights were run in CI.
"""
import json
import pytest
import httpx
from app.agent.gemma import (GemmaClient,MODEL_NAME,ModelUnavailable,
                             InvalidModelResponse,validate_ollama_url)


def mock_client(monkeypatch, handler):
    real_client=httpx.Client
    def factory(*a,**kw):
        kw['transport']=httpx.MockTransport(handler)
        return real_client(*a,**kw)
    monkeypatch.setattr('app.agent.gemma.httpx.Client',factory)


def test_rejects_nonlocal_ollama_endpoints():
    for url in ('https://ollama.com','http://google.com:11434',
                'http://127.0.0.1.evil.net:11434','file:///tmp/api',
                'http://user:pass@localhost:11434','http://localhost:11434/redirect'):
        with pytest.raises(ValueError):validate_ollama_url(url)
    assert validate_ollama_url('http://127.0.0.1:11434/')=='http://127.0.0.1:11434'


def test_local_model_check_and_structured_decision(monkeypatch):
    requests=[]
    def responder(request):
        requests.append(request)
        if request.url.path=='/api/tags':
            return httpx.Response(200,json={'models':[{'name':'gemma4:e2b'}]})
        assert request.url.path=='/api/chat'
        payload=json.loads(request.content)
        assert payload['model']==MODEL_NAME and payload['stream'] is False
        assert payload['format']['properties']['tool']['enum']==['create_support_case','ask_human']
        assert payload['messages'][0]['role']=='system'
        return httpx.Response(200,json={'message':{'content':json.dumps(
            {'tool':'ask_human','reason':'Needs human clarification'})}})
    mock_client(monkeypatch,responder)
    model=GemmaClient()
    assert model.available()['available']
    got=model.decide('action',{'stage':'ticket_ready_to_route'},['create_support_case','ask_human'])
    assert got['tool']=='ask_human'
    assert len(requests)==2


def test_invalid_model_action_fails_closed(monkeypatch):
    def responder(request):
        return httpx.Response(200,json={'message':{'content':json.dumps(
            {'tool':'send_money','reason':'unsafe'})}})
    mock_client(monkeypatch,responder)
    with pytest.raises(InvalidModelResponse):
        GemmaClient().decide('action',{'stage':'invoice_ready_to_write'},['create_ledger_entry','ask_human'])


def test_offline_service_is_not_silently_called_cloud(monkeypatch):
    def responder(request):
        assert request.url.host=='127.0.0.1'
        return httpx.Response(503,json={'error':'Ollama unavailable'})
    mock_client(monkeypatch,responder)
    with pytest.raises(ModelUnavailable):
        GemmaClient().decide('invoice_operation',{'text':'Record invoice'})


def test_invalid_json_ignored_not_executed(monkeypatch):
    def responder(request):return httpx.Response(200,json={'message':{'content':'Sure I clicked the button'}})
    mock_client(monkeypatch,responder)
    with pytest.raises(InvalidModelResponse):GemmaClient().decide('invoice_operation',{'text':'Record'})
