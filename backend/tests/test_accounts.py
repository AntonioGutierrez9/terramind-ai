"""Accounts, guests and data isolation through the real HTTP API (no LLM calls)."""

import io
import os
import tempfile

os.environ["TERRAMIND_DB"] = os.path.join(tempfile.mkdtemp(), "accounts.db")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.auth import hash_password, verify_password  # noqa: E402
from app.main import app  # noqa: E402


def client():
    return TestClient(app)


def test_password_hashing_is_salted_and_verifiable():
    h1, h2 = hash_password("correct horse"), hash_password("correct horse")
    assert h1 != h2 and h1.startswith("pbkdf2_sha256$")
    assert verify_password("correct horse", h1) and not verify_password("wrong", h1)


def test_api_requires_a_session():
    c = client()
    assert c.get("/api/projects").status_code == 401
    assert c.get("/api/health").status_code == 200  # public


def test_guest_gets_private_demo_projects_and_others_cannot_see_them():
    a, b = client(), client()
    assert a.post("/api/auth/guest").json()["guest"] is True
    b.post("/api/auth/guest")
    pa = a.get("/api/projects").json()
    pb = b.get("/api/projects").json()
    assert len(pa) == 3 and len(pb) == 3
    assert {p["id"] for p in pa}.isdisjoint({p["id"] for p in pb})
    foreign = pa[0]["id"]
    assert b.get(f"/api/projects/{foreign}").status_code == 404
    assert b.post(f"/api/projects/{foreign}/changes", json={"changes": [{"key": "site.land_price", "value": 1}]}).status_code == 404
    assert b.get(f"/api/chat/messages?project_id={foreign}").status_code == 404


def test_signup_moves_guest_work_to_the_account_and_login_restores_it():
    c = client()
    c.post("/api/auth/guest")
    pid = c.get("/api/projects").json()[0]["id"]
    c.post(f"/api/projects/{pid}/changes", json={"changes": [{"key": "rev.absorption_per_month", "value": 4}]})
    r = c.post("/api/auth/signup", json={"first_name": "Ana", "last_name": "López", "email": "ana@example.com",
                                         "password": "s3cure-pass", "confirm_password": "s3cure-pass"})
    assert r.status_code == 201 and r.json()["moved_guest_projects"] == 3
    assert "password" not in str(r.json()).lower()
    c.post("/api/auth/logout")
    assert c.get("/api/projects").status_code == 401
    c2 = client()
    assert c2.post("/api/auth/login", json={"email": "ANA@example.com", "password": "wrong-pass"}).status_code == 401
    assert c2.post("/api/auth/login", json={"email": "ana@example.com", "password": "s3cure-pass"}).status_code == 200
    p = c2.get(f"/api/projects/{pid}").json()["project"]
    assert p["assumptions"]["rev.absorption_per_month"] == 4


def test_duplicate_email_and_weak_password_are_rejected():
    c = client()
    body = {"first_name": "A", "last_name": "B", "email": "dup@example.com", "password": "longenough1", "confirm_password": "longenough1"}
    assert c.post("/api/auth/signup", json=body).status_code == 201
    assert client().post("/api/auth/signup", json=body).status_code == 409
    assert client().post("/api/auth/signup", json={**body, "email": "x@example.com", "password": "short", "confirm_password": "short"}).status_code == 422


def test_document_upload_is_private_and_extracted():
    a, b = client(), client()
    a.post("/api/auth/guest")
    b.post("/api/auth/guest")
    pid = a.get("/api/projects").json()[0]["id"]
    text = b"CERTIFICADO UNICO DE ZONIFICACION\nZonificacion: H/6/20/M\nSuperficie del predio: 1,800 m2"
    r = a.post(f"/api/projects/{pid}/documents", files={"file": ("certificado.txt", io.BytesIO(text), "text/plain")},
               data={"analyze": "false"})
    assert r.status_code == 200
    doc_id = r.json()["document"]["id"]
    assert "H/6/20/M" in a.get(f"/api/documents/{doc_id}").json()["text_preview"]
    assert b.get(f"/api/documents/{doc_id}").status_code == 404
    assert b.get(f"/api/documents/{doc_id}/file").status_code == 404
    bad = a.post(f"/api/projects/{pid}/documents", files={"file": ("virus.exe", io.BytesIO(b"MZ"), "application/octet-stream")})
    assert bad.status_code == 422


def test_quote_verification_blocks_invented_values():
    from app.agents.document_agent import verify_quote
    doc = "El precio de compraventa será de $120,000,000.00 (ciento veinte millones de pesos)."
    assert verify_quote("precio de compraventa será de $120,000,000.00", 120_000_000, doc)
    assert not verify_quote("precio de compraventa será de $95,000,000.00", 95_000_000, doc)  # not in the document
    assert not verify_quote("precio de compraventa será de $120,000,000.00", 95_000_000, doc)  # number mismatch


def test_chat_translation_is_cached_private_and_skips_text_already_in_language():
    from app import db, store
    from app.agents.translator import detect
    assert detect("What is the equity IRR of this project?") == "en"
    assert detect("¿Cuál es la TIR del capital de este proyecto?") == "es"
    assert detect("24.9%") is None  # language-neutral: never sent to the model
    a, b = client(), client()
    a.post("/api/auth/guest")
    b.post("/api/auth/guest")
    pid = a.get("/api/projects").json()[0]["id"]
    owner = store.project_owner(pid)[1]
    en_id = store.add_message(pid, "user", "What is the equity IRR of this project?", owner=owner)
    store.add_message(pid, "assistant", "La TIR del capital es de 24.9% para este proyecto.", owner=owner)
    with db.tx() as c:  # pretend the English message was translated earlier (cache hit -> no model call)
        c.execute("INSERT INTO message_translations(message_id, lang, content) VALUES (?,?,?)",
                  (en_id, "es", "¿Cuál es la TIR del capital de este proyecto?"))
    r = a.post("/api/chat/translate", json={"project_id": pid}, headers={"X-Lang": "es"}).json()
    assert [m["content"] for m in r["messages"]] == ["¿Cuál es la TIR del capital de este proyecto?",
                                                     "La TIR del capital es de 24.9% para este proyecto."]
    assert r["messages"][0]["original"] == "What is the equity IRR of this project?" and r["messages"][1]["original"] is None
    assert not r["turn_usage"] or r["turn_usage"]["total"]["requests"] == 0  # nothing needed the model
    got = a.get(f"/api/chat/messages?project_id={pid}", headers={"X-Lang": "es"}).json()
    assert got[0]["content"].startswith("¿Cuál") and got[0]["lang"] == "es"
    assert a.get(f"/api/chat/messages?project_id={pid}", headers={"X-Lang": "en"}).json()[0]["content"].startswith("What")
    assert b.post("/api/chat/translate", json={"project_id": pid}, headers={"X-Lang": "es"}).status_code == 404


def test_only_signed_in_users_can_remove_their_projects():
    from app import store
    guest, user, other = client(), client(), client()
    guest.post("/api/auth/guest")
    gpid = guest.get("/api/projects").json()[0]["id"]
    assert guest.delete(f"/api/projects/{gpid}").status_code == 403  # guests keep their projects
    assert len(guest.get("/api/projects").json()) == 3
    pw = "remove-me-123"
    user.post("/api/auth/signup", json={"first_name": "Ana", "last_name": "Ruiz", "email": "ana.remove@example.com",
                                        "password": pw, "confirm_password": pw})
    other.post("/api/auth/signup", json={"first_name": "Leo", "last_name": "Paz", "email": "leo.remove@example.com",
                                         "password": pw, "confirm_password": pw})
    projects = user.get("/api/projects").json()
    pid = projects[0]["id"]
    up = user.post(f"/api/projects/{pid}/documents", files={"file": ("note.txt", io.BytesIO(b"Lot area 2,500 m2"), "text/plain")},
                   data={"analyze": "false"})
    path = store.get_document(up.json()["document"]["id"])["path"]
    assert os.path.exists(path)
    assert other.delete(f"/api/projects/{pid}").status_code == 404  # cannot touch someone else's project
    assert user.delete(f"/api/projects/{pid}").json()["ok"] is True
    assert pid not in {p["id"] for p in user.get("/api/projects").json()}
    assert len(user.get("/api/projects").json()) == len(projects) - 1
    assert store.project_owner(pid)[0] is False and not os.path.exists(path)  # data and stored file are gone
    assert user.get(f"/api/projects/{pid}").status_code == 404
