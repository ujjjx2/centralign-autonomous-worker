"""Dashboard has live counter hooks for completed sandbox writes."""
from app.main import create_app
from app.config import Settings
from fastapi.testclient import TestClient


def test_dashboard_count_hooks_and_ledger_api(tmp_path):
    app=create_app(Settings(database_path=tmp_path/'data.sqlite3',
        artifacts_dir=tmp_path/'artifacts',model_backend='rules',execution_mode='http'))
    with TestClient(app) as client:
        html=client.get('/').text
        assert 'id="recorded-invoices-count"' in html
        assert 'id="support-cases-count"' in html
        assert isinstance(client.get('/api/ledger').json(),list)
        assert isinstance(client.get('/api/cases').json(),list)
    js=(__import__('pathlib').Path(__file__).parents[1]/'app/static/app.js').read_text()
    assert 'refreshCounters' in js and "api('/api/ledger')" in js
