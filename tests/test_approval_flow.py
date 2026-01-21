import os
from fastapi.testclient import TestClient
from app.main import app
from app.security import generate_sig
from app.db import SessionLocal
from app.models import PendingApproval

client = TestClient(app)


def test_approval_requires_signature_behavior(monkeypatch):
    # set a signing secret
    monkeypatch.setenv("APP_SIGNING_SECRET", "testsecret")

    # create pending approval via endpoint
    r = client.post("/issues/check_and_maybe_create", json={
        "owner": "towner",
        "repo": "trepo",
        "title": "Test approval",
        "body": "body",
        "create_if_missing": False
    })
    assert r.status_code == 200
    assert r.json().get("status") == "pending"
    approval_id = r.json().get("approval_id")
    assert approval_id is not None

    # missing signature -> /approve should be rejected
    r2 = client.get(f"/approve?approval_id={approval_id}&action=approve")
    assert r2.status_code == 403

    # now generate valid signature and approve
    sig = generate_sig("testsecret", approval_id, "approve")
    r3 = client.get(f"/approve?approval_id={approval_id}&action=approve&sig={sig}")
    assert r3.status_code == 200
    assert r3.json().get("status") == "approved"

    # verify DB record updated
    db = SessionLocal()
    p = db.query(PendingApproval).filter(PendingApproval.id == approval_id).first()
    assert p is not None and p.status == "approved"
