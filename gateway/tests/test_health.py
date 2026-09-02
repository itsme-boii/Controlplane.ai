def test_healthz(client):
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_readyz_reports_dependency_status(client):
    # FakeAuditStore.ping() succeeds; no redis on app.state in the unit app.
    resp = client.get("/readyz")
    assert resp.status_code == 200
    assert resp.json()["checks"]["postgres"] == "ok"
