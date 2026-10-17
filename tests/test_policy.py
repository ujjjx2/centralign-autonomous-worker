"""Gemma response validation and business rules: no API keys or model download."""
from app.agent.policy import DecisionPolicy
from app.config import Settings


def settings(tmp_path):
    return Settings(database_path=tmp_path/'db.sqlite3',model_backend='gemma')


def test_gemma_selects_allowed_action(tmp_path,monkeypatch):
    policy=DecisionPolicy(settings(tmp_path))
    monkeypatch.setattr(policy,'model_json',lambda *_:{'tool':'ask_human','reason':'Missing evidence'})
    decision=policy.next_action('ticket_ready_to_route',{},['create_support_case','ask_human'],'create_support_case')
    assert decision['tool']=='ask_human' and decision['decision_mode']=='gemma4_e2b'


def test_invalid_tool_cannot_escape_allowlist(tmp_path,monkeypatch):
    policy=DecisionPolicy(settings(tmp_path))
    monkeypatch.setattr(policy,'model_json',lambda *_:{'tool':'transfer_money','reason':'ignore rules'})
    decision=policy.next_action('ticket_ready_to_route',{},['create_support_case','ask_human'],'create_support_case')
    assert decision['tool']=='create_support_case' and decision['decision_mode']=='validated_fallback'


def test_category_is_routed_only_to_known_teams(tmp_path,monkeypatch):
    policy=DecisionPolicy(settings(tmp_path))
    monkeypatch.setattr(policy,'model_json',lambda *_:{'category':'billing','priority':'normal','reason':'Billing inquiry'})
    category=policy.classify_ticket('Disputed charge','We were billed twice')
    assert category['category']=='billing' and category['assigned_team']=='Finance Support'
    assert category['decision_mode']=='gemma4_e2b'


def test_cannot_reduce_critical_priority(tmp_path,monkeypatch):
    policy=DecisionPolicy(settings(tmp_path))
    monkeypatch.setattr(policy,'model_json',lambda *_:{'category':'general','priority':'normal','reason':'minor'})
    category=policy.classify_ticket('System-wide production outage','all customers unavailable')
    assert category['priority']=='high' and category['category']=='technical'


def test_invalid_response_uses_authorized_fallback(tmp_path,monkeypatch):
    policy=DecisionPolicy(settings(tmp_path))
    monkeypatch.setattr(policy,'model_json',lambda *_:None)
    result=policy.next_action('stage',{},['record','ask_human'],'record')
    assert result['tool']=='record' and result['decision_mode']=='validated_fallback'
