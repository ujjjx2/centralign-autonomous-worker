"""Regression: template engine is a required runtime dependency."""


def test_dashboard_renders(sandbox):
    response = sandbox.get("/")
    assert response.status_code == 200, response.text
    assert "text/html" in response.headers["content-type"]
    assert "CentrAlign" in response.text
