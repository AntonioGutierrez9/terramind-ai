"""Accounts and guests (same approach as Homework 4's Campus Customs store).

* Passwords: PBKDF2-HMAC-SHA256 from Python's standard library, random salt per user, 120,000 iterations,
  stored as  pbkdf2_sha256$<salt>$<hex digest>. Never logged, never returned to the frontend.
* Login state: a signed, HttpOnly session cookie (Starlette SessionMiddleware) holding only the user id,
  or a random guest id for people who continue without an account.
* Ownership: every project belongs to an owner key, "u:<user id>" or "g:<guest id>". The API only serves
  projects whose owner matches the caller's session (enforced in main.py), so one user's data is never
  visible to another user or guest. When a guest signs up or logs in, their guest projects move to the account.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from typing import Annotated

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, EmailStr, Field, StringConstraints, model_validator

from .db import now, query_one, tx

router = APIRouter(prefix="/api/auth")

HASH_ALGORITHM = "pbkdf2_sha256"
HASH_ITERATIONS = 120_000
LOGIN_FAILED = "Incorrect email or password."


def _pbkdf2(password: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), HASH_ITERATIONS).hex()


def hash_password(password: str) -> str:
    salt = secrets.token_hex(8)
    return f"{HASH_ALGORITHM}${salt}${_pbkdf2(password, salt)}"


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        algorithm, salt, digest = stored_hash.split("$")
    except ValueError:
        return False
    if algorithm != HASH_ALGORITHM:
        return False
    return hmac.compare_digest(_pbkdf2(password, salt), digest)


_DUMMY_HASH = hash_password(secrets.token_hex(16))  # equal timing for unknown emails

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)]


class SignupRequest(BaseModel):
    first_name: Name
    last_name: Name
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    confirm_password: str

    @model_validator(mode="after")
    def passwords_match(self):
        if self.password != self.confirm_password:
            raise ValueError("Passwords do not match.")
        return self


class LoginRequest(BaseModel):
    email: str
    password: str


def public_user(row) -> dict:
    return {"id": row["id"], "first_name": row["first_name"], "last_name": row["last_name"],
            "name": f"{row['first_name']} {row['last_name']}", "email": row["email"]}


def current_user(request: Request) -> dict | None:
    uid = request.session.get("user_id")
    if uid is None:
        return None
    row = query_one("SELECT id, email, first_name, last_name FROM users WHERE id=?", (uid,))
    if row is None:
        request.session.clear()
        return None
    return public_user(row)


def owner_key(request: Request) -> str | None:
    """'u:<id>' for a signed-in user, 'g:<token>' for a guest, None for a visitor who hasn't chosen yet."""
    uid = request.session.get("user_id")
    if uid is not None and current_user(request):
        return f"u:{uid}"
    gid = request.session.get("guest_id")
    return f"g:{gid}" if gid else None


def _claim(old_owner: str | None, new_owner: str) -> int:
    """Move a guest's projects (and chat history) to the account they just signed into."""
    if not old_owner or not old_owner.startswith("g:"):
        return 0
    with tx() as c:
        n = c.execute("UPDATE projects SET owner=? WHERE owner=?", (new_owner, old_owner)).rowcount
        c.execute("UPDATE chat_messages SET owner=? WHERE owner=?", (new_owner, old_owner))
        c.execute("UPDATE token_usage SET owner=? WHERE owner=?", (new_owner, old_owner))
        c.execute("UPDATE documents SET owner=? WHERE owner=?", (new_owner, old_owner))
    return n


def _adopt_local_projects(new_owner: str) -> int:
    """The very first account on a local install adopts projects created before accounts existed."""
    if query_one("SELECT COUNT(*) n FROM users")["n"] != 1:
        return 0
    with tx() as c:
        n = c.execute("UPDATE projects SET owner=? WHERE owner IS NULL", (new_owner,)).rowcount
        c.execute("UPDATE chat_messages SET owner=? WHERE owner IS NULL", (new_owner,))
        c.execute("UPDATE documents SET owner=? WHERE owner IS NULL", (new_owner,))
        c.execute("UPDATE token_usage SET owner=? WHERE owner IS NULL", (new_owner,))
    return n


def _start(request: Request, user_id: int) -> dict:
    previous = owner_key(request)
    request.session.clear()
    request.session["user_id"] = user_id
    new_owner = f"u:{user_id}"
    moved = _claim(previous, new_owner)
    adopted = _adopt_local_projects(new_owner)
    from .seed import seed_for_owner
    seeded = seed_for_owner(new_owner)
    return {"moved_guest_projects": moved, "adopted_local_projects": adopted, "seeded_demo_projects": len(seeded)}


@router.post("/signup", status_code=201)
def signup(body: SignupRequest, request: Request):
    email = body.email.strip().lower()
    if query_one("SELECT 1 FROM users WHERE lower(email)=?", (email,)):
        raise HTTPException(409, "An account with this email already exists.")
    with tx() as c:
        cur = c.execute("INSERT INTO users(email, password_hash, first_name, last_name, created_at) VALUES (?,?,?,?,?)",
                        (email, hash_password(body.password), body.first_name, body.last_name, now()))
        uid = cur.lastrowid
    info = _start(request, uid)
    return {"user": current_user(request), **info}


@router.post("/login")
def login(body: LoginRequest, request: Request):
    email = body.email.strip().lower()
    row = query_one("SELECT id, password_hash FROM users WHERE lower(email)=?", (email,))
    if row is None:
        verify_password(body.password, _DUMMY_HASH)
        raise HTTPException(401, LOGIN_FAILED)
    if not verify_password(body.password, row["password_hash"]):
        raise HTTPException(401, LOGIN_FAILED)
    info = _start(request, row["id"])
    return {"user": current_user(request), **info}


@router.post("/guest")
def guest(request: Request):
    """Continue without an account: a private guest workspace tied to this browser's session cookie."""
    if request.session.get("user_id"):
        return {"user": current_user(request), "guest": False}
    if not request.session.get("guest_id"):
        request.session["guest_id"] = secrets.token_urlsafe(18)
    from .seed import seed_for_owner
    seed_for_owner(owner_key(request))
    return {"user": None, "guest": True}


@router.post("/logout")
def logout(request: Request):
    request.session.clear()
    return {"ok": True}


@router.get("/me")
def me(request: Request):
    return {"user": current_user(request), "guest": bool(request.session.get("guest_id")) and not request.session.get("user_id")}
