"""Project store: the single write path for assumptions.

Every change, from a form, the chatbot or an agent, goes through apply_changes():
  1. validate with the engine registry (type, range, units)
  2. classify: ordinary / material / regulatory override
  3. chatbot or agent actors: material changes become a PENDING change that only a UI click can confirm
     user actor: regulatory overrides need confirm_override=True (the UI shows a dialog first)
  4. write value + provenance + audit row (old → new) in one transaction, grouped by batch for undo
"""

from __future__ import annotations

import uuid
from copy import deepcopy
from typing import Any

from engine.analysis import apply_changes as _relative
from engine.registry import REGISTRY
from engine.validation import ValidationError, validate_unit_mix, validate_value

from .db import dumps, loads, now, query, query_one, tx

LOOSER_IF_HIGHER = {"reg.max_stories", "reg.max_far", "reg.max_height_m", "reg.max_units",
                    "reg.max_underground_levels", "reg.parking_max_per_unit"}
LOOSER_IF_LOWER = {"reg.min_open_area_pct", "reg.min_land_per_unit", "reg.parking_min_per_unit"}
LIST_KEYS = {"unit_mix", "sustainability_measures", "hard_cost_split", "sales_phases", "price_phases", "land_payments", "custom_flows"}
HUMAN_ACTORS = {"user"}


class StoreError(ValueError):
    pass


# ----------------------------------------------------------------------------- projects
def _row_to_project(r) -> dict:
    return {"id": r["id"], "name": r["name"], "profile": loads(r["profile"]), "assumptions": loads(r["assumptions"]),
            "meta": loads(r["meta"]), "status": r["status"], "in_portfolio": bool(r["in_portfolio"]),
            "created_at": r["created_at"], "updated_at": r["updated_at"], "owner": r["owner"] if "owner" in r.keys() else None}


def create_project(profile: dict, assumptions: dict | None = None, source: str = "user", actor: str = "user",
                   status: str = "draft", owner: str | None = None) -> int:
    profile = {**profile}
    name = (profile.get("name") or "Untitled project").strip()[:120]
    profile["name"] = name
    clean: dict[str, Any] = {}
    meta: dict[str, Any] = {}
    for key, value in (assumptions or {}).items():
        if key in LIST_KEYS:
            clean[key] = _validate_list(key, value)
        else:
            v, _ = validate_value(key, value)
            clean[key] = v
        if clean[key] is not None:
            meta[key] = {"source": source, "status": "approved", "updated_at": now(), "updated_by": actor,
                         "confidence": "illustrative" if source == "demo" else None}
    ts = now()
    with tx() as c:
        cur = c.execute("INSERT INTO projects(name, profile, assumptions, meta, status, created_at, updated_at, owner) VALUES (?,?,?,?,?,?,?,?)",
                        (name, dumps(profile), dumps(clean), dumps(meta), status, ts, ts, owner))
        return cur.lastrowid


def get_project(pid: int) -> dict:
    r = query_one("SELECT * FROM projects WHERE id=?", (pid,))
    if not r:
        raise StoreError(f"project {pid} not found")
    return _row_to_project(r)


ALL = "*"


def list_projects(owner: str | None = ALL) -> list[dict]:
    """owner=ALL for internal use only; the API always passes the caller's owner key."""
    if owner == ALL:
        rows = query("SELECT * FROM projects WHERE status != 'archived' ORDER BY id")
    else:
        rows = query("SELECT * FROM projects WHERE status != 'archived' AND owner IS ? ORDER BY id", (owner,))
    return [_row_to_project(r) for r in rows]


def project_owner(pid: int) -> tuple[bool, str | None]:
    r = query_one("SELECT owner FROM projects WHERE id=?", (pid,))
    return (r is not None, r["owner"] if r else None)


def update_profile(pid: int, fields: dict, actor: str = "user") -> dict:
    p = get_project(pid)
    allowed = {"name", "country", "state", "city", "neighborhood", "municipality", "address", "lat", "lon", "currency", "area_unit", "zoning_code", "geo_precision",
               "property_type", "strategy", "business_model", "ownership_status", "horizon_years", "details", "start_date"}
    bad = set(fields) - allowed
    if bad:
        raise StoreError(f"unknown profile fields: {', '.join(sorted(bad))}")
    profile = {**p["profile"], **fields}
    batch = uuid.uuid4().hex[:12]
    with tx() as c:
        c.execute("UPDATE projects SET profile=?, name=?, updated_at=? WHERE id=?",
                  (dumps(profile), profile.get("name", p["name"]), now(), pid))
        for k, v in fields.items():
            c.execute("INSERT INTO changes(project_id,batch_id,actor,key,old_value,new_value,reason,created_at) VALUES (?,?,?,?,?,?,?,?)",
                      (pid, batch, actor, f"profile.{k}", dumps(p["profile"].get(k)), dumps(v), "profile update", now()))
    return profile


def set_status(pid: int, status: str, in_portfolio: bool | None = None, actor: str = "user") -> None:
    if status not in ("draft", "hypothetical", "approved", "portfolio", "archived"):
        raise StoreError("invalid status")
    p = get_project(pid)
    with tx() as c:
        c.execute("UPDATE projects SET status=?, in_portfolio=COALESCE(?, in_portfolio), updated_at=? WHERE id=?",
                  (status, None if in_portfolio is None else int(in_portfolio), now(), pid))
        c.execute("INSERT INTO changes(project_id,batch_id,actor,key,old_value,new_value,reason,created_at) VALUES (?,?,?,?,?,?,?,?)",
                  (pid, uuid.uuid4().hex[:12], actor, "project.status", dumps(p["status"]), dumps(status), "status change", now()))


def duplicate_project(pid: int, name: str | None = None) -> int:
    p = get_project(pid)
    prof = {**p["profile"], "name": name or f"{p['name']} (copy)"}
    new_id = create_project(prof, {}, actor="user", owner=p.get("owner"))
    with tx() as c:
        c.execute("UPDATE projects SET assumptions=?, meta=? WHERE id=?", (dumps(p["assumptions"]), dumps(p["meta"]), new_id))
    return new_id


# ----------------------------------------------------------------------------- validation helpers
def _validate_list(key: str, value: Any):
    if key == "unit_mix":
        return validate_unit_mix(value)[0]
    if key == "hard_cost_split":
        if not isinstance(value, dict) or not value:
            raise ValidationError("hard cost split must be a non-empty mapping")
        out = {str(k)[:60]: float(v) for k, v in value.items()}
        if any(v < 0 for v in out.values()) or abs(sum(out.values()) - 100) > 0.5:
            raise ValidationError("hard cost split shares must be ≥ 0 and add to 100%")
        return out
    if key == "sustainability_measures":
        if not isinstance(value, list):
            raise ValidationError("sustainability measures must be a list")
        clean = []
        for m in value:
            if not m.get("key") or not m.get("name"):
                raise ValidationError("each measure needs a key and a name")
            row = {**m}
            for f in ("capex", "life_years", "maintenance_annual", "energy_kwh_annual", "water_m3_annual", "co2_t_annual",
                      "savings_annual", "sale_premium_pct", "rent_premium_pct"):
                if row.get(f) is not None:
                    row[f] = float(row[f])
                    if f not in ("sale_premium_pct", "rent_premium_pct") and row[f] < 0:
                        raise ValidationError(f"{m['name']}: {f} cannot be negative")
            row["enabled"] = bool(row.get("enabled"))
            clean.append(row)
        return clean
    if key in ("sales_phases", "price_phases", "land_payments", "custom_flows"):
        from engine.schedules import validate_schedule
        return validate_schedule(key, value)
    raise ValidationError(f"unknown list field {key}")


def is_loosening(key: str, new: Any, meta: dict) -> tuple[bool, Any]:
    """True if `new` relaxes a legal limit that was approved from research (verified or preliminary)."""
    m = meta.get(key) or {}
    ref = m.get("regulatory_reference")
    if ref is None or new is None:
        return False, ref
    if key in LOOSER_IF_HIGHER and new > ref:
        return True, ref
    if key in LOOSER_IF_LOWER and new < ref:
        return True, ref
    return False, ref


# ----------------------------------------------------------------------------- the write path
def apply_changes(pid: int, changes: list[dict], actor: str = "user", reason: str = "", source: str | None = None,
                  confirm_override: bool = False, from_pending: bool = False, extra_meta: dict | None = None) -> dict:
    """changes: [{key, value}] or [{key, op: 'pct'|'add', value}]. Returns what happened to each change."""
    p = get_project(pid)
    a, meta = p["assumptions"], p["meta"]
    human = actor in HUMAN_ACTORS or from_pending
    src = source or ("user" if human else "chatbot")
    applied, pending, rejected, needs_confirmation, warnings = [], [], [], [], []

    for ch in changes:
        key = ch.get("key")
        try:
            if key in LIST_KEYS:
                new = _validate_list(key, ch.get("value"))
            elif key in REGISTRY:
                if ch.get("op") in ("pct", "add"):
                    new = _relative(a, [ch])[key]
                else:
                    new, w = validate_value(key, ch.get("value"))
                    warnings += w
            else:
                raise ValidationError(f"unknown variable '{key}'")
        except (ValidationError, KeyError, TypeError) as exc:
            rejected.append({"key": key, "value": ch.get("value"), "error": str(exc)})
            continue
        old = a.get(key)
        if old == new:
            continue
        spec = REGISTRY.get(key, {})
        loosen, ref = is_loosening(key, new, meta)
        material = bool(spec.get("material")) or loosen or bool(spec.get("regulatory"))
        item = {"key": key, "label": spec.get("label", key), "old": old, "new": new, "unit": spec.get("unit", ""),
                "material": material, "regulatory_override": loosen, "legal_reference": ref}
        if material and not human:
            pending.append(item)
            continue
        if loosen and not confirm_override:
            needs_confirmation.append(item)
            continue
        applied.append(item)

    batch = uuid.uuid4().hex[:12] if applied else None
    pending_id = None
    if applied or pending:
        with tx() as c:
            if applied:
                new_a, new_meta = deepcopy(a), deepcopy(meta)
                for it in applied:
                    k = it["key"]
                    prev_meta = new_meta.get(k)
                    m = {**(prev_meta or {}), "source": src, "status": "approved", "updated_at": now(),
                         "updated_by": actor, "reason": reason[:300] or None, **(extra_meta or {}).get(k, {})}
                    m.pop("proposal", None) if src == "researched" else None
                    if it["regulatory_override"]:
                        m["override_of"] = it["legal_reference"]
                        m["noncompliant_override"] = True
                    elif k in LOOSER_IF_HIGHER | LOOSER_IF_LOWER and m.get("noncompliant_override") and not is_loosening(k, it["new"], new_meta)[0]:
                        m["noncompliant_override"] = False
                    new_a[k] = it["new"]
                    new_meta[k] = m
                    c.execute("INSERT INTO changes(project_id,batch_id,actor,key,old_value,new_value,old_meta,new_meta,reason,created_at) "
                              "VALUES (?,?,?,?,?,?,?,?,?,?)",
                              (pid, batch, actor, k, dumps(it["old"]), dumps(it["new"]), dumps(prev_meta), dumps(m), reason[:300], now()))
                c.execute("UPDATE projects SET assumptions=?, meta=?, updated_at=? WHERE id=?", (dumps(new_a), dumps(new_meta), now(), pid))
            if pending:
                cur = c.execute("INSERT INTO pending_changes(project_id,kind,payload,reason,requested_by,created_at) VALUES (?,?,?,?,?,?)",
                                (pid, "assumptions", dumps(pending), reason[:300], actor, now()))
                pending_id = cur.lastrowid
    return {"applied": applied, "pending": pending, "pending_id": pending_id, "rejected": rejected,
            "needs_confirmation": needs_confirmation, "warnings": warnings, "batch_id": batch}


def list_pending(pid: int) -> list[dict]:
    rows = query("SELECT * FROM pending_changes WHERE project_id=? AND status='pending' ORDER BY id", (pid,))
    return [{"id": r["id"], "kind": r["kind"], "changes": loads(r["payload"]), "reason": r["reason"],
             "requested_by": r["requested_by"], "created_at": r["created_at"]} for r in rows]


def resolve_pending(pending_id: int, confirm: bool, actor: str = "user") -> dict:
    """Only reachable from the UI (an HTTP endpoint the chatbot has no tool for)."""
    r = query_one("SELECT * FROM pending_changes WHERE id=?", (pending_id,))
    if not r or r["status"] != "pending":
        raise StoreError("pending change not found or already resolved")
    result: dict = {"status": "rejected"}
    if confirm:
        payload = loads(r["payload"])
        if r["kind"] == "status":
            set_status(r["project_id"], payload["status"], payload.get("in_portfolio"), actor=actor)
            result = {"status": "confirmed", "project_status": payload["status"]}
        else:
            res = apply_changes(r["project_id"], [{"key": it["key"], "value": it["new"]} for it in payload], actor=actor,
                                reason=f"confirmed chatbot proposal: {r['reason'] or ''}", source="chatbot (confirmed)",
                                confirm_override=True, from_pending=True)
            result = {"status": "confirmed", **res}
    with tx() as c:
        c.execute("UPDATE pending_changes SET status=?, resolved_at=? WHERE id=?",
                  ("confirmed" if confirm else "rejected", now(), pending_id))
    return result


def request_status_change(pid: int, status: str, reason: str, actor: str) -> int:
    with tx() as c:
        cur = c.execute("INSERT INTO pending_changes(project_id,kind,payload,reason,requested_by,created_at) VALUES (?,?,?,?,?,?)",
                        (pid, "status", dumps({"status": status, "in_portfolio": status == "portfolio"}), reason[:300], actor, now()))
        return cur.lastrowid


def undo_last(pid: int, actor: str = "user") -> dict:
    r = query_one("SELECT batch_id FROM changes WHERE project_id=? AND undone=0 AND key NOT LIKE 'profile.%' "
                  "AND key != 'project.status' ORDER BY id DESC LIMIT 1", (pid,))
    if not r:
        return {"undone": [], "message": "Nothing to undo."}
    batch = r["batch_id"]
    rows = query("SELECT * FROM changes WHERE batch_id=? ORDER BY id DESC", (batch,))
    p = get_project(pid)
    a, meta = deepcopy(p["assumptions"]), deepcopy(p["meta"])
    undone = []
    for row in rows:
        k = row["key"]
        old_v, old_m = loads(row["old_value"]), loads(row["old_meta"])
        if old_v is None:
            a.pop(k, None)
        else:
            a[k] = old_v
        if old_m is None:
            meta.pop(k, None)
        else:
            meta[k] = old_m
        undone.append({"key": k, "label": REGISTRY.get(k, {}).get("label", k), "restored": old_v, "was": loads(row["new_value"])})
    with tx() as c:
        c.execute("UPDATE projects SET assumptions=?, meta=?, updated_at=? WHERE id=?", (dumps(a), dumps(meta), now(), pid))
        c.execute("UPDATE changes SET undone=1 WHERE batch_id=?", (batch,))
        c.execute("INSERT INTO changes(project_id,batch_id,actor,key,old_value,new_value,reason,created_at) VALUES (?,?,?,?,?,?,?,?)",
                  (pid, uuid.uuid4().hex[:12], actor, "undo", dumps(batch), dumps([u["key"] for u in undone]), "undo", now()))
    return {"undone": undone, "batch_id": batch}


def history(pid: int, limit: int = 200) -> list[dict]:
    rows = query("SELECT * FROM changes WHERE project_id=? ORDER BY id DESC LIMIT ?", (pid, limit))
    return [{"id": r["id"], "batch_id": r["batch_id"], "actor": r["actor"], "key": r["key"],
             "label": REGISTRY.get(r["key"], {}).get("label", r["key"]), "old": loads(r["old_value"]),
             "new": loads(r["new_value"]), "reason": r["reason"], "undone": bool(r["undone"]), "at": r["created_at"]} for r in rows]


# ----------------------------------------------------------------------------- research proposals
def propose_values(pid: int, agent: str, proposals: list[dict]) -> list[dict]:
    """Store researched values as PENDING proposals. They never touch the model until the user approves."""
    p = get_project(pid)
    meta = deepcopy(p["meta"])
    stored = []
    for pr in proposals:
        key = pr.get("key")
        if key not in REGISTRY or pr.get("value") is None:
            continue
        try:
            v, w = validate_value(key, pr["value"])
        except ValidationError as exc:
            stored.append({"key": key, "rejected": str(exc)})
            continue
        prop = {"value": v, "agent": agent, "verification": pr.get("verification", "preliminary"),
                "confidence": pr.get("confidence"), "source_title": pr.get("source_title"), "source_url": pr.get("source_url"),
                "note": (pr.get("note") or "")[:400], "status": "pending", "proposed_at": now(), "warnings": w}
        meta.setdefault(key, {})["proposal"] = prop
        stored.append({"key": key, **prop})
    with tx() as c:
        c.execute("UPDATE projects SET meta=?, updated_at=? WHERE id=?", (dumps(meta), now(), pid))
    return stored


def resolve_proposal(pid: int, key: str, approve: bool, actor: str = "user") -> dict:
    p = get_project(pid)
    prop = (p["meta"].get(key) or {}).get("proposal")
    if not prop or prop.get("status") != "pending":
        raise StoreError("no pending proposal for this variable")
    if not approve:
        meta = deepcopy(p["meta"])
        meta[key]["proposal"]["status"] = "rejected"
        with tx() as c:
            c.execute("UPDATE projects SET meta=? WHERE id=?", (dumps(meta), pid))
        return {"status": "rejected", "key": key}
    extra = {key: {"verification": prop.get("verification"), "confidence": prop.get("confidence"),
                   "source_url": prop.get("source_url"), "source_title": prop.get("source_title"),
                   "note": prop.get("note"), "agent": prop.get("agent")}}
    if REGISTRY[key].get("regulatory"):
        extra[key]["regulatory_reference"] = prop["value"]
    res = apply_changes(pid, [{"key": key, "value": prop["value"]}], actor=actor, reason=f"approved {prop.get('agent')} research",
                        source="researched", confirm_override=True, extra_meta=extra)
    if not res["applied"]:  # value identical: still record approval metadata
        meta = deepcopy(get_project(pid)["meta"])
        meta.setdefault(key, {}).update({**extra[key], "source": "researched", "status": "approved"})
        meta[key].pop("proposal", None)
        with tx() as c:
            c.execute("UPDATE projects SET meta=? WHERE id=?", (dumps(meta), pid))
    return {"status": "approved", "key": key, **res}


# ----------------------------------------------------------------------------- research, cache, actuals, variants
def save_research(pid: int, agent: str, request: str, payload: dict, from_cache: bool) -> int:
    with tx() as c:
        cur = c.execute("INSERT INTO research(project_id,agent,request,payload,from_cache,created_at) VALUES (?,?,?,?,?,?)",
                        (pid, agent, request, dumps(payload), int(from_cache), now()))
        return cur.lastrowid


def latest_research(pid: int) -> dict:
    rows = query("SELECT * FROM research WHERE project_id=? ORDER BY id DESC", (pid,))
    out: dict[str, dict] = {}
    for r in rows:
        if r["agent"] not in out:
            out[r["agent"]] = {"id": r["id"], "request": r["request"], "payload": loads(r["payload"]),
                               "from_cache": bool(r["from_cache"]), "created_at": r["created_at"]}
    return out


def cache_get(cache_key: str, max_age_days: int) -> dict | None:
    r = query_one("SELECT * FROM research_cache WHERE cache_key=?", (cache_key,))
    if not r:
        return None
    from datetime import datetime, timezone
    age = datetime.now(timezone.utc) - datetime.fromisoformat(r["created_at"])
    if age.days > max_age_days:
        return None
    return {"payload": loads(r["payload"]), "created_at": r["created_at"]}


def cache_put(cache_key: str, agent: str, request: str, payload: dict) -> None:
    with tx() as c:
        c.execute("INSERT OR REPLACE INTO research_cache(cache_key,agent,request,payload,created_at) VALUES (?,?,?,?,?)",
                  (cache_key, agent, request, dumps(payload), now()))


ACTUAL_FIELDS = {"cost": (0, 1e12), "units_sold": (0, 10_000), "avg_price_per_area": (0, 1e8), "collections": (0, 1e12),
                 "debt_balance": (0, 1e12), "progress_pct": (0, 100)}


def upsert_actual(pid: int, month: int, data: dict) -> dict:
    if not (0 <= int(month) <= 600):
        raise StoreError("month must be between 0 and 600")
    clean = {}
    for k, (lo, hi) in ACTUAL_FIELDS.items():
        v = data.get(k)
        if v is None or v == "":
            continue
        v = float(v)
        if not (lo <= v <= hi):
            raise StoreError(f"{k} must be between {lo:g} and {hi:g}")
        clean[k] = v
    with tx() as c:
        c.execute("INSERT INTO actuals(project_id,month,data,created_at) VALUES (?,?,?,?) "
                  "ON CONFLICT(project_id,month) DO UPDATE SET data=excluded.data, created_at=excluded.created_at",
                  (pid, int(month), dumps(clean), now()))
    return {"month": int(month), **clean}


def list_actuals(pid: int) -> list[dict]:
    return [{"month": r["month"], **loads(r["data"])} for r in query("SELECT * FROM actuals WHERE project_id=? ORDER BY month", (pid,))]


def delete_actual(pid: int, month: int) -> None:
    with tx() as c:
        c.execute("DELETE FROM actuals WHERE project_id=? AND month=?", (pid, month))


def save_variant(pid: int, kind: str, name: str, payload: Any) -> int:
    with tx() as c:
        cur = c.execute("INSERT INTO variants(project_id,kind,name,payload,created_at) VALUES (?,?,?,?,?)",
                        (pid, kind, name[:80], dumps(payload), now()))
        return cur.lastrowid


def list_variants(pid: int, kind: str | None = None) -> list[dict]:
    rows = query("SELECT * FROM variants WHERE project_id=? AND (? IS NULL OR kind=?) ORDER BY id", (pid, kind, kind))
    return [{"id": r["id"], "kind": r["kind"], "name": r["name"], "payload": loads(r["payload"]), "created_at": r["created_at"]} for r in rows]


def delete_variant(vid: int) -> None:
    with tx() as c:
        c.execute("DELETE FROM variants WHERE id=?", (vid,))


# ----------------------------------------------------------------------------- memos, chat, usage, settings
def save_memo(pid: int, recommendation: str, memo: dict, metrics: dict) -> int:
    with tx() as c:
        cur = c.execute("INSERT INTO ic_memos(project_id,recommendation,memo,metrics,created_at) VALUES (?,?,?,?,?)",
                        (pid, recommendation, dumps(memo), dumps(metrics), now()))
        return cur.lastrowid


def latest_memo(pid: int) -> dict | None:
    r = query_one("SELECT * FROM ic_memos WHERE project_id=? ORDER BY id DESC LIMIT 1", (pid,))
    if not r:
        return None
    return {"id": r["id"], "recommendation": r["recommendation"], "memo": loads(r["memo"]), "metrics": loads(r["metrics"]),
            "created_at": r["created_at"]}


def add_message(pid: int | None, role: str, content: str, extra: dict | None = None, owner: str | None = None) -> int:
    with tx() as c:
        cur = c.execute("INSERT INTO chat_messages(project_id,role,content,extra,created_at,owner) VALUES (?,?,?,?,?,?)",
                        (pid, role, content, dumps(extra or {}), now(), owner))
        return cur.lastrowid


def list_messages(pid: int | None, limit: int = 60, owner: str | None = ALL) -> list[dict]:
    if owner == ALL:
        rows = query("SELECT * FROM chat_messages WHERE project_id IS ? ORDER BY id DESC LIMIT ?", (pid, limit))
    else:
        rows = query("SELECT * FROM chat_messages WHERE project_id IS ? AND owner IS ? ORDER BY id DESC LIMIT ?", (pid, owner, limit))
    return [{"id": r["id"], "role": r["role"], "content": r["content"], "extra": loads(r["extra"]), "at": r["created_at"]}
            for r in reversed(rows)]


def record_usage(run_id: str, pid: int | None, agent: str, purpose: str, model: str, usage: dict, cost: float,
                 seconds: float | None = None, owner: str | None = None) -> None:
    with tx() as c:
        c.execute("INSERT INTO token_usage(run_id,project_id,agent,purpose,model,requests,input_tokens,cached_tokens,output_tokens,"
                  "web_searches,cost_usd,seconds,created_at,owner) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                  (run_id, pid, agent, purpose, model, usage.get("requests", 0), usage.get("input_tokens", 0),
                   usage.get("cached_tokens", 0), usage.get("output_tokens", 0), usage.get("web_searches", 0), cost, seconds, now(), owner))


def usage_report(pid: int | None = None, owner: str | None = ALL) -> dict:
    if owner != ALL:
        where, params = "WHERE owner IS ?", (owner,)
    else:
        where = "WHERE project_id=?" if pid else ""
        params = (pid,) if pid else ()
    by_agent = query(f"SELECT agent, COUNT(*) calls, SUM(requests) requests, SUM(input_tokens) input_tokens, SUM(cached_tokens) cached_tokens, "
                     f"SUM(output_tokens) output_tokens, SUM(web_searches) web_searches, SUM(cost_usd) cost_usd, AVG(seconds) avg_seconds "
                     f"FROM token_usage {where} GROUP BY agent ORDER BY cost_usd DESC", params)
    by_run = query(f"SELECT run_id, MIN(created_at) at, MAX(purpose) purpose, GROUP_CONCAT(DISTINCT agent) agents, SUM(requests) requests, "
                   f"SUM(input_tokens) input_tokens, SUM(cached_tokens) cached_tokens, SUM(output_tokens) output_tokens, "
                   f"SUM(web_searches) web_searches, SUM(cost_usd) cost_usd FROM token_usage {where} GROUP BY run_id ORDER BY at DESC LIMIT 100", params)
    total = query_one(f"SELECT COUNT(DISTINCT run_id) runs, SUM(input_tokens) input_tokens, SUM(cached_tokens) cached_tokens, "
                      f"SUM(output_tokens) output_tokens, SUM(web_searches) web_searches, SUM(cost_usd) cost_usd FROM token_usage {where}", params)
    return {"by_agent": [dict(r) for r in by_agent], "by_run": [dict(r) for r in by_run], "total": dict(total) if total else {}}


def get_setting(key: str, default=None):
    r = query_one("SELECT value FROM settings WHERE key=?", (key,))
    return loads(r["value"]) if r else default


def set_setting(key: str, value) -> None:
    with tx() as c:
        c.execute("INSERT OR REPLACE INTO settings(key,value) VALUES (?,?)", (key, dumps(value)))


def apply_zoning_code(pid: int, code: str, actor: str = "user") -> dict:
    """Parse a CDMX zoning code (from the user's certificate / SEDUVI map) and apply the implied legal limits.

    User: applied directly and recorded as the legal reference for override detection.
    Chatbot: material regulatory changes, so they come back pending like any other.
    """
    from engine.zoning import SOURCE_URL, parse_cdmx_code, zoning_code_changes
    p = get_project(pid)
    parsed = parse_cdmx_code(code, p["assumptions"].get("site.land_area"))
    changes = zoning_code_changes(parsed)
    note = f"Parsed from zoning code {parsed['code']}" + (f"; density {parsed['density_letter']} per Norma General de Ordenacion 11" if parsed.get("min_land_per_unit") else "")
    extra = {c["key"]: {"verification": "from zoning code", "confidence": "high", "note": note, "regulatory_reference": c["value"],
                        "source_title": "CDMX zoning code (entered by user); density table: NGO 11 (2005)", "source_url": SOURCE_URL}
             for c in changes}
    res = apply_changes(pid, changes, actor=actor, reason=f"zoning code {parsed['code']}", source="user (zoning code)" if actor == "user" else None,
                        confirm_override=True, extra_meta=extra)
    if actor == "user":
        update_profile(pid, {"zoning_code": parsed["code"]}, actor=actor)
        # record the reference even when a value was already identical
        meta = deepcopy(get_project(pid)["meta"])
        for k, m in extra.items():
            meta.setdefault(k, {}).update({kk: vv for kk, vv in m.items()})
        with tx() as c:
            c.execute("UPDATE projects SET meta=? WHERE id=?", (dumps(meta), pid))
    return {"parsed": parsed, **res}


# ----------------------------------------------------------------------------- documents
def add_document(pid: int | None, owner: str | None, filename: str, kind: str, mime: str | None, size: int, path: str,
                 text: str, meta: dict) -> int:
    with tx() as c:
        cur = c.execute("INSERT INTO documents(project_id,owner,filename,kind,mime,size,path,text,meta,created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                        (pid, owner, filename[:200], kind, mime, size, path, text, dumps(meta), now()))
        return cur.lastrowid


def _doc_row(r, with_text: bool = False) -> dict:
    d = {"id": r["id"], "project_id": r["project_id"], "owner": r["owner"], "filename": r["filename"], "kind": r["kind"],
         "mime": r["mime"], "size": r["size"], "meta": loads(r["meta"]) or {}, "analysis": loads(r["analysis"]),
         "created_at": r["created_at"], "path": r["path"]}
    if with_text:
        d["text"] = r["text"] or ""
    return d


def get_document(doc_id: int, with_text: bool = False) -> dict:
    r = query_one("SELECT * FROM documents WHERE id=?", (doc_id,))
    if not r:
        raise StoreError(f"document {doc_id} not found")
    return _doc_row(r, with_text)


def list_documents(pid: int) -> list[dict]:
    return [_doc_row(r) for r in query("SELECT * FROM documents WHERE project_id=? ORDER BY id DESC", (pid,))]


def save_document_analysis(doc_id: int, analysis: dict) -> None:
    with tx() as c:
        c.execute("UPDATE documents SET analysis=? WHERE id=?", (dumps(analysis), doc_id))


def delete_document(doc_id: int) -> str:
    d = get_document(doc_id)
    with tx() as c:
        c.execute("DELETE FROM documents WHERE id=?", (doc_id,))
    return d["path"]
