"""TerraMind AI — FastAPI application.

Run from the repo root:  python run.py   (serves the API and the built React app on http://localhost:8000)
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import secrets
import time
from typing import Any

import httpx
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.middleware.sessions import SessionMiddleware

from engine import analysis, sustainability
from engine.model import run_model
from engine.registry import DEFAULT_HARD_COST_SPLIT, PROFILE_CHOICES, REGISTRY, SECTIONS, model_mode
from engine.validation import ValidationError

from . import auth, documents, seed, services, store
from .agents.runtime import CURRENT_OWNER
from .config import DEFAULT_LIMITS, FRONTEND_DIST, ai_available, api_key_status
from .db import get_conn

app = FastAPI(title="TerraMind AI", version="1.1")
app.include_router(auth.router)

# ----------------------------------------------------------------------------- data protection
# Every project-scoped route is checked here: the caller's session owner must own the project.
# Unknown or foreign ids return 404 so the existence of other people's projects is not revealed.
OWNED_ROUTES = [(re.compile(r"^/api/projects/(\d+)"), "project"), (re.compile(r"^/api/pending/(\d+)"), "pending"),
                (re.compile(r"^/api/variants/(\d+)"), "variant"), (re.compile(r"^/api/documents/(\d+)"), "document")]
PUBLIC_API = ("/api/health", "/api/meta", "/api/auth/", "/api/geocode")  # geocode checks project ownership itself


def _project_of(kind: str, ident: int) -> int | None:
    from .db import query_one
    if kind == "project":
        return ident
    table = {"pending": "pending_changes", "variant": "variants", "document": "documents"}[kind]
    r = query_one(f"SELECT project_id FROM {table} WHERE id=?", (ident,))
    return r["project_id"] if r else None


@app.middleware("http")
async def ownership(request: Request, call_next):
    path = request.url.path
    if not path.startswith("/api/") or path.startswith(PUBLIC_API):
        return await call_next(request)
    owner = auth.owner_key(request)
    if owner is None:
        return JSONResponse({"detail": "Sign in or continue as a guest first."}, status_code=401)
    for rx, kind in OWNED_ROUTES:
        m = rx.match(path)
        if m:
            pid = _project_of(kind, int(m.group(1)))
            exists, proj_owner = store.project_owner(pid) if pid else (False, None)
            if not exists or proj_owner != owner:
                return JSONResponse({"detail": "Not found."}, status_code=404)
            break
    token = CURRENT_OWNER.set(owner)
    request.state.owner = owner
    try:
        return await call_next(request)
    finally:
        CURRENT_OWNER.reset(token)


def _session_secret() -> str:
    """SESSION_SECRET from .env if set; otherwise a random secret generated once and kept in the local database."""
    env = os.getenv("SESSION_SECRET", "").strip()
    if env:
        return env
    get_conn()
    secret = store.get_setting("session_secret")
    if not secret:
        secret = secrets.token_urlsafe(48)
        store.set_setting("session_secret", secret)
    return secret


app.add_middleware(SessionMiddleware, secret_key=_session_secret(), session_cookie="tm_session",
                   max_age=14 * 24 * 3600, same_site="lax", https_only=False)
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"], allow_methods=["*"],
                   allow_headers=["*"], allow_credentials=True)


def owner_of(request: Request) -> str:
    return request.state.owner


@app.on_event("startup")
def startup() -> None:
    get_conn()


@app.exception_handler(ValidationError)
async def _val(_, exc):
    return JSONResponse({"detail": str(exc)}, status_code=422)


@app.exception_handler(store.StoreError)
async def _store(_, exc):
    return JSONResponse({"detail": str(exc)}, status_code=404 if "not found" in str(exc) else 422)


def limits(owner: str | None = None) -> dict:
    owner = owner or CURRENT_OWNER.get()
    return {**DEFAULT_LIMITS, **(store.get_setting(f"limits:{owner}") or {})}


# ----------------------------------------------------------------------------- meta
@app.get("/api/health")
def health():
    return {"ok": True, "ai": api_key_status(), "ai_available": ai_available(), "limits": limits()}


@app.get("/api/meta")
def meta():
    return {"registry": REGISTRY, "sections": SECTIONS, "profile_choices": PROFILE_CHOICES, "hard_cost_split": DEFAULT_HARD_COST_SPLIT}


# ----------------------------------------------------------------------------- projects
class ProjectIn(BaseModel):
    profile: dict
    assumptions: dict = {}
    apply_suggested: bool = True


@app.get("/api/projects")
def projects(request: Request):
    out = []
    for p in store.list_projects(owner_of(request)):
        res = services.results(p)
        out.append({"id": p["id"], "name": p["name"], "profile": p["profile"], "status": p["status"], "in_portfolio": p["in_portfolio"],
                    "updated_at": p["updated_at"], "model_status": res.get("status"), "metrics": services.key_metrics(res),
                    "missing": res.get("missing_labels", [])})
    return out


@app.post("/api/projects")
def create(body: ProjectIn, request: Request):
    a = dict(body.assumptions)
    pid = store.create_project(body.profile, {}, actor="user", owner=owner_of(request))
    if a:
        r = store.apply_changes(pid, [{"key": k, "value": v} for k, v in a.items()], actor="user", reason="project wizard")
        if r["rejected"]:
            return {"id": pid, "rejected": r["rejected"]}
    if body.apply_suggested:
        apply_suggested(pid)
    return {"id": pid}


@app.get("/api/projects/{pid}")
def project(pid: int):
    p = store.get_project(pid)
    res = services.results(p)
    return {"project": p, "results": res, "pending": store.list_pending(pid), "mode": model_mode(p["profile"])}


@app.get("/api/projects/{pid}/assumptions")
def assumptions(pid: int):
    p = store.get_project(pid)
    return {"rows": services.assumption_table(p), "calculated": services.calculated_rows(services.results(p)),
            "custom": services.custom_variable_rows(p)}


@app.patch("/api/projects/{pid}/profile")
def patch_profile(pid: int, fields: dict):
    return store.update_profile(pid, fields, actor="user")


class ChangesIn(BaseModel):
    changes: list[dict]
    reason: str = ""
    confirm_override: bool = False


@app.post("/api/projects/{pid}/changes")
def changes(pid: int, body: ChangesIn):
    res = store.apply_changes(pid, body.changes, actor="user", reason=body.reason, confirm_override=body.confirm_override)
    p = store.get_project(pid)
    return {**res, "results": services.results(p)}


@app.post("/api/projects/{pid}/suggested-defaults")
def apply_suggested(pid: int, body: dict | None = None):
    keys = (body or {}).get("keys")
    p = store.get_project(pid)
    mode = model_mode(p["profile"])
    todo = []
    for k, spec in REGISTRY.items():
        if keys and k not in keys:
            continue
        if spec["suggested"] is None or p["assumptions"].get(k) is not None:
            continue
        if spec["section"] == "rent" and mode != "rent" or spec["section"] == "rev" and mode != "sale":
            continue
        todo.append({"key": k, "value": spec["suggested"]})
    return store.apply_changes(pid, todo, actor="user", reason="applied suggested defaults (unverified)", source="default (unverified)")


@app.post("/api/projects/{pid}/undo")
def undo(pid: int):
    return store.undo_last(pid, actor="user")


@app.get("/api/projects/{pid}/history")
def hist(pid: int):
    return store.history(pid)


@app.get("/api/projects/{pid}/pending")
def pending(pid: int):
    return store.list_pending(pid)


@app.post("/api/pending/{pending_id}/{action}")
def resolve(pending_id: int, action: str):
    if action not in ("confirm", "reject"):
        raise HTTPException(400, "action must be confirm or reject")
    return store.resolve_pending(pending_id, action == "confirm", actor="user")


@app.post("/api/projects/{pid}/proposals/{key}/{action}")
def proposal(pid: int, key: str, action: str):
    if action not in ("approve", "reject"):
        raise HTTPException(400, "action must be approve or reject")
    return store.resolve_proposal(pid, key, action == "approve", actor="user")


@app.post("/api/projects/{pid}/zoning-code")
def zoning_code(pid: int, body: dict):
    from engine.zoning import ZoningCodeError
    try:
        return store.apply_zoning_code(pid, str(body.get("code", "")), actor="user")
    except ZoningCodeError as exc:
        raise HTTPException(422, str(exc))


@app.post("/api/projects/{pid}/status")
def status(pid: int, body: dict):
    store.set_status(pid, body["status"], body.get("in_portfolio"), actor="user")
    return {"ok": True}


@app.post("/api/projects/{pid}/duplicate")
def duplicate(pid: int, body: dict | None = None):
    return {"id": store.duplicate_project(pid, (body or {}).get("name"))}


@app.delete("/api/projects/{pid}")
def archive(pid: int):
    store.set_status(pid, "archived", False, actor="user")
    return {"ok": True}


# ----------------------------------------------------------------------------- analysis
@app.get("/api/projects/{pid}/analysis")
def full_analysis(pid: int):
    return services.full_analysis(store.get_project(pid))


@app.post("/api/projects/{pid}/what-if")
def what_if(pid: int, body: dict):
    p = store.get_project(pid)
    ov = analysis.apply_changes(p["assumptions"], body.get("changes", []))
    r = run_model(p["profile"], p["assumptions"], ov)
    return {"overrides": ov, "status": r["status"], "metrics": r.get("metrics"), "covenants": r.get("covenants"),
            "warnings": r.get("warnings"), "missing": r.get("missing")}


class SolveIn(BaseModel):
    key: str
    metric: str
    target: float


@app.post("/api/projects/{pid}/solve")
def solve(pid: int, body: SolveIn):
    p = store.get_project(pid)
    return analysis.solve_for(p["profile"], p["assumptions"], body.key, body.metric, body.target)


@app.get("/api/projects/{pid}/unit-mix")
def unit_mix(pid: int, metric: str = "equity_irr"):
    p = store.get_project(pid)
    return analysis.optimize_unit_mix(p["profile"], p["assumptions"], metric)


@app.get("/api/projects/{pid}/variants")
def variants(pid: int):
    return store.list_variants(pid)


@app.post("/api/projects/{pid}/variants")
def add_variant(pid: int, body: dict):
    kind = body.get("kind", "scenario")
    payload = body.get("payload")
    if kind == "scenario":
        analysis.apply_changes(store.get_project(pid)["assumptions"], payload or [])  # validate
    return {"id": store.save_variant(pid, kind, body.get("name", "Scenario"), payload)}


@app.delete("/api/variants/{vid}")
def del_variant(vid: int):
    store.delete_variant(vid)
    return {"ok": True}


@app.post("/api/projects/{pid}/variants/{vid}/apply")
def apply_variant(pid: int, vid: int):
    v = next((x for x in store.list_variants(pid) if x["id"] == vid), None)
    if not v or v["kind"] != "configuration":
        raise HTTPException(404, "configuration not found")
    return store.apply_changes(pid, [{"key": k, "value": val} for k, val in v["payload"].items()], actor="user",
                               reason=f"applied saved configuration '{v['name']}'")


@app.get("/api/projects/{pid}/recommendations")
def recommendations(pid: int):
    return services.recommendations(store.get_project(pid))


@app.post("/api/projects/{pid}/recommendations/apply")
def apply_recommendation(pid: int, body: dict):
    rec = services.recommendations(store.get_project(pid))
    if body.get("package"):
        changes, label = (rec.get("package") or {}).get("changes"), "recommended package"
    else:
        lv = next((x for x in rec.get("levers", []) if x["id"] == body.get("lever_id")), None)
        changes, label = (lv or {}).get("changes"), (lv or {}).get("title")
    if not changes:
        raise HTTPException(404, "Recommendation not found (the project may have changed; refresh).")
    res = store.apply_changes(pid, changes, actor="user", reason=f"applied recommendation: {label}")
    return {**res, "results": services.results(store.get_project(pid))}


@app.post("/api/projects/{pid}/recommendations/commentary")
async def recommendation_commentary(pid: int):
    _need_ai()
    from .agents.committee import run_advisor
    from .agents.runtime import TurnContext
    ctx = TurnContext(project_id=pid, purpose="advisor", limits=limits())
    p = store.get_project(pid)
    out = await run_advisor(ctx, p, services.recommendations(p))
    return {**out, "turn_usage": ctx.summary()}


@app.get("/api/projects/{pid}/sustainability")
def sus(pid: int):
    return services.sustainability_eval(store.get_project(pid))


@app.post("/api/projects/{pid}/sustainability/optimize")
def sus_opt(pid: int, body: dict):
    p = store.get_project(pid)
    ms = p["assumptions"].get("sustainability_measures") or []
    return sustainability.optimize(p["profile"], p["assumptions"], ms, float(body.get("budget", 0)), body.get("objective", "co2"))


# ----------------------------------------------------------------------------- research, committee, asset mgmt (LLM)
def _need_ai():
    if not ai_available():
        raise HTTPException(503, "AI is unavailable: no PORTKEY_API_KEY / OPENAI_API_KEY found in .env (repo folder or the folder above).")


@app.get("/api/projects/{pid}/research")
def research(pid: int):
    return store.latest_research(pid)


@app.post("/api/projects/{pid}/research/{kind}")
async def run_research(pid: int, kind: str, body: dict | None = None):
    _need_ai()
    from .agents.runtime import LimitReached, TurnContext
    from .agents.specialists import run_specialist
    ctx = TurnContext(project_id=pid, purpose=f"research:{kind}", limits=limits())
    try:
        res = await run_specialist(ctx, kind, store.get_project(pid), (body or {}).get("request"), bool((body or {}).get("force")))
    except LimitReached as exc:
        return {"status": "limit_reached", "detail": exc.detail}
    return {**res, "turn_usage": ctx.summary()}


@app.post("/api/projects/{pid}/research/market/exclude")
def exclude_comp(pid: int, body: dict):
    """Toggle a comparable's exclusion and recompute the (deterministic) price statistics."""
    r = store.latest_research(pid).get("market")
    if not r:
        raise HTTPException(404, "no market research yet")
    payload = r["payload"]
    idx = int(body["index"])
    payload["comparables"][idx]["excluded"] = bool(body.get("excluded", True))
    payload["summary"] = services.comps_summary(payload["comparables"])
    store.save_research(pid, "market", r["request"], payload, from_cache=r["from_cache"])
    from .agents.specialists import _proposals
    store.propose_values(pid, "market", _proposals("market", payload))
    return payload


@app.post("/api/projects/{pid}/committee")
async def committee(pid: int):
    _need_ai()
    from .agents.committee import run_committee
    from .agents.runtime import LimitReached, TurnContext
    ctx = TurnContext(project_id=pid, purpose="committee", limits=limits())
    try:
        out = await run_committee(ctx, store.get_project(pid))
    except LimitReached as exc:
        return {"status": "limit_reached", "detail": exc.detail}
    return {**out, "turn_usage": ctx.summary()}


@app.get("/api/projects/{pid}/committee")
def memo(pid: int):
    return store.latest_memo(pid)


@app.get("/api/projects/{pid}/actuals")
def actuals(pid: int):
    return store.list_actuals(pid)


@app.post("/api/projects/{pid}/actuals")
def add_actual(pid: int, body: dict):
    return store.upsert_actual(pid, int(body["month"]), body)


@app.delete("/api/projects/{pid}/actuals/{month}")
def del_actual(pid: int, month: int):
    store.delete_actual(pid, month)
    return {"ok": True}


@app.get("/api/projects/{pid}/asset")
def asset(pid: int):
    return services.asset_analysis(store.get_project(pid))


@app.post("/api/projects/{pid}/asset/commentary")
async def asset_commentary(pid: int):
    _need_ai()
    from .agents.committee import run_asset_commentary
    from .agents.runtime import TurnContext
    ctx = TurnContext(project_id=pid, purpose="asset_management", limits=limits())
    p = store.get_project(pid)
    out = await run_asset_commentary(ctx, p, services.asset_analysis(p))
    return {**out, "turn_usage": ctx.summary()}


@app.get("/api/portfolio")
def portfolio(request: Request):
    return services.portfolio(owner_of(request))


@app.get("/api/usage")
def usage(request: Request):
    """Anonymous aggregate across all users (for tokenomics) plus the caller's own usage."""
    return {**store.usage_report(), "mine": store.usage_report(owner=owner_of(request))}


@app.get("/api/settings/limits")
def get_limits():
    return limits()


@app.put("/api/settings/limits")
def put_limits(body: dict):
    clean = {}
    for k, v in body.items():
        if k not in DEFAULT_LIMITS:
            continue
        v = float(v) if k == "max_usd" else int(v)
        if v <= 0:
            raise HTTPException(422, f"{k} must be positive")
        clean[k] = v
    key = f"limits:{CURRENT_OWNER.get()}"
    store.set_setting(key, {**(store.get_setting(key) or {}), **clean})
    return limits()


# ----------------------------------------------------------------------------- chat (SSE)
@app.get("/api/chat/messages")
def chat_messages(request: Request, project_id: int | None = None):
    owner = owner_of(request)
    if project_id is not None and store.project_owner(project_id) != (True, owner):
        raise HTTPException(404, "Not found.")
    return store.list_messages(project_id, owner=owner)


class ChatIn(BaseModel):
    message: str
    project_id: int | None = None
    limit_multiplier: float = 1.0


@app.post("/api/chat")
async def chat(body: ChatIn, request: Request):
    _need_ai()
    owner = owner_of(request)
    if body.project_id is not None and store.project_owner(body.project_id) != (True, owner):
        raise HTTPException(404, "Not found.")
    from .agents.manager import run_chat
    from .agents.runtime import TurnContext
    msg = body.message.strip()
    if not msg:
        raise HTTPException(422, "empty message")
    if len(msg) > 4000:
        raise HTTPException(422, "message too long (max 4000 characters)")
    mult = max(1.0, min(body.limit_multiplier, 4.0))  # user-approved raise, capped at 4×
    lim = {k: (v * mult if k == "max_usd" else int(v * mult)) for k, v in limits().items()}
    queue: asyncio.Queue = asyncio.Queue()
    ctx = TurnContext(project_id=body.project_id, purpose="chat", limits=lim, queue=queue, owner=owner)

    async def work():
        try:
            final = await run_chat(body.project_id, msg, ctx)
            queue.put_nowait({"type": "final", "data": final})
        except Exception as exc:  # noqa: BLE001
            queue.put_nowait({"type": "error", "data": {"message": f"{type(exc).__name__}: {exc}"}})
        finally:
            queue.put_nowait(None)

    async def stream():
        task = asyncio.create_task(work())
        try:
            while True:
                ev = await queue.get()
                if ev is None:
                    break
                yield f"data: {json.dumps(ev, default=str)}\n\n"
        finally:
            if not task.done():
                task.cancel()

    return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})


# ----------------------------------------------------------------------------- documents
@app.get("/api/projects/{pid}/documents")
def list_docs(pid: int):
    return [{k: v for k, v in d.items() if k != "path"} for d in store.list_documents(pid)]


@app.post("/api/projects/{pid}/documents")
async def upload_doc(pid: int, request: Request, file: UploadFile = File(...), analyze: bool = Form(True)):
    try:
        kind = documents.kind_for(file.filename or "file")
        data = await file.read()
        path = documents.save_file(owner_of(request), file.filename or "file", data)
        text, meta = documents.extract(kind, data, file.filename or "file")
    except documents.UploadError as exc:
        raise HTTPException(422, str(exc))
    except Exception as exc:  # noqa: BLE001  (corrupt / password-protected files)
        raise HTTPException(422, f"Could not read this file ({type(exc).__name__}). Is it corrupt or password-protected?")
    doc_id = store.add_document(pid, owner_of(request), file.filename or "file", kind, file.content_type, len(data), str(path), text, meta)
    out = {"document": {k: v for k, v in store.get_document(doc_id).items() if k != "path"}}
    if analyze and ai_available():
        out.update(await _analyze_doc(doc_id))
    return out


async def _analyze_doc(doc_id: int) -> dict:
    from .agents.document_agent import analyze
    from .agents.runtime import LimitReached, TurnContext
    d = store.get_document(doc_id)
    ctx = TurnContext(project_id=d["project_id"], purpose="document", limits=limits())
    try:
        res = await analyze(ctx, doc_id)
    except LimitReached as exc:
        return {"status": "limit_reached", "detail": exc.detail}
    return {"analysis": res, "turn_usage": ctx.summary()}


@app.get("/api/documents/{doc_id}")
def get_doc(doc_id: int):
    d = store.get_document(doc_id, with_text=True)
    d.pop("path", None)
    d["text_preview"] = d.pop("text")[:5000]
    return d


@app.get("/api/documents/{doc_id}/file")
def doc_file(doc_id: int):
    d = store.get_document(doc_id)
    return FileResponse(d["path"], filename=d["filename"], media_type=d["mime"] or "application/octet-stream")


@app.post("/api/documents/{doc_id}/analyze")
async def analyze_doc(doc_id: int):
    _need_ai()
    return await _analyze_doc(doc_id)


@app.post("/api/documents/{doc_id}/ask")
async def ask_doc(doc_id: int, body: dict):
    _need_ai()
    from .agents.document_agent import ask
    from .agents.runtime import LimitReached, TurnContext
    q = str(body.get("question", "")).strip()
    if not q:
        raise HTTPException(422, "Ask a question.")
    d = store.get_document(doc_id)
    ctx = TurnContext(project_id=d["project_id"], purpose="document", limits=limits())
    try:
        res = await ask(ctx, doc_id, q)
    except LimitReached as exc:
        return {"status": "limit_reached", "detail": exc.detail}
    return {**res, "turn_usage": ctx.summary()}


@app.delete("/api/documents/{doc_id}")
def delete_doc(doc_id: int):
    from pathlib import Path
    path = store.delete_document(doc_id)
    try:
        Path(path).unlink(missing_ok=True)
    except OSError:
        pass
    return {"ok": True}


# ----------------------------------------------------------------------------- geocoding (map)
COUNTRY_CODES = {"mexico": "mx", "méxico": "mx", "united states": "us", "usa": "us", "colombia": "co", "spain": "es", "españa": "es"}


async def _nominatim(client: httpx.AsyncClient, q: str, country: str | None) -> dict | None:
    """One Nominatim lookup with persistent caching (OSM usage policy: low volume, identify the app, cache results)."""
    key = f"geo:{country or ''}:{q.lower()}"
    cached = store.get_setting(key)
    if cached is not None:
        return cached or None
    params = {"q": q, "format": "json", "limit": 1}
    if country:
        params["countrycodes"] = country
    for attempt in range(2):  # one retry on network errors / rate limiting
        try:
            r = await client.get("https://nominatim.openstreetmap.org/search", params=params)
            if r.status_code == 200:
                data = r.json()
                hit = {"lat": float(data[0]["lat"]), "lon": float(data[0]["lon"]), "display_name": data[0]["display_name"]} if data else {}
                store.set_setting(key, hit)
                return hit or None
        except (httpx.HTTPError, ValueError):
            pass
        await asyncio.sleep(1.2)
    raise HTTPException(503, "The map service (OpenStreetMap Nominatim) did not respond. Try again in a moment.")


@app.get("/api/geocode")
async def geocode(q: str = "", project_id: int | None = None, request: Request = None):
    """Locate an address, falling back to street → colonia/alcaldía → city. If project_id is given (and owned by the
    caller), the location found is saved to the project so the map never needs to look it up again."""
    prof: dict = {}
    if project_id is not None:
        owner = auth.owner_key(request)
        if not owner or store.project_owner(project_id) != (True, owner):
            raise HTTPException(404, "Not found.")
        prof = store.get_project(project_id)["profile"]
    country = COUNTRY_CODES.get((prof.get("country") or "").strip().lower()) or ("mx" if "mexico" in q.lower() or "méxico" in q.lower() else None)
    city = ", ".join(x for x in (prof.get("city"), prof.get("state")) if x)
    street = re.sub(r"\s+\d+[\w\-]*$", "", (prof.get("address") or "").split(",")[0]).strip()
    candidates = [(q.strip()[:200], "address")] if q.strip() else []
    if prof:
        candidates += [(", ".join(x for x in (prof.get("address"), prof.get("neighborhood"), city) if x), "address"),
                       (", ".join(x for x in (street, prof.get("neighborhood"), city) if x), "street"),
                       (", ".join(x for x in (prof.get("neighborhood"), prof.get("municipality"), city) if x), "neighborhood"),
                       (city, "city")]
    seen = set()
    async with httpx.AsyncClient(timeout=8, headers={"User-Agent": "TerraMindAI/1.0 (Yale SOM course project)"}) as client:
        for cand, precision in candidates:
            if not cand or cand in seen:
                continue
            seen.add(cand)
            hit = await _nominatim(client, cand, country)
            if hit:
                if project_id is not None:
                    store.update_profile(project_id, {"lat": hit["lat"], "lon": hit["lon"], "geo_precision": precision}, actor="system")
                return {"found": True, **hit, "precision": precision, "query": cand}
    return {"found": False}


# ----------------------------------------------------------------------------- static frontend
if FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")

    @app.get("/{path:path}")
    def spa(path: str, request: Request):
        if path.startswith("api/"):
            raise HTTPException(404)
        f = FRONTEND_DIST / path
        if path and f.is_file():
            return FileResponse(f)
        return FileResponse(FRONTEND_DIST / "index.html")
