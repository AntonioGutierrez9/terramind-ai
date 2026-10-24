"""Investment Manager: the chat agent. The only agent in the chat loop.

It reads and edits the project through structured tools that call the SAME store/engine functions the UI
uses, so validation, materiality rules and the audit trail apply equally. Material edits come back as
pending; only a UI click (an endpoint with no chatbot tool) can confirm them.
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field
from pydantic_ai import Agent, RunContext
from pydantic_ai.exceptions import UsageLimitExceeded
from pydantic_ai.messages import ModelRequest, ModelResponse, TextPart, UserPromptPart
from pydantic_ai.usage import UsageLimits

from engine import analysis, sustainability
from engine.model import run_model
from engine.registry import PROFILE_CHOICES, REGISTRY, SECTIONS
from engine.validation import ValidationError

from .. import services, store
from ..config import build_model
from .runtime import LimitReached, TurnContext
from . import specialists

PROMPT = (Path(__file__).resolve().parents[2] / "prompts" / "investment_manager.md").read_text(encoding="utf-8")
PERCENT_METRICS = {"equity_irr", "project_irr", "net_margin", "gross_margin", "profit_on_cost", "investor_irr", "sponsor_irr",
                   "ltc", "ltv", "yield_on_cost", "cash_on_cash"}


@dataclass
class ManagerDeps:
    ctx: TurnContext
    project_id: int | None


class ChangeIn(BaseModel):
    key: str = Field(description="Registry key, e.g. site.land_price, fin.senior_ltc_pct, cost.hard_per_area")
    value: float | str | bool | None = Field(description="New value (set) or the adjustment (pct/add). Percent fields: 60 means 60%.")
    op: Literal["set", "pct", "add"] = "set"


Anchor = Literal["closing", "sales_start", "construction_start", "delivery"]


class SalesPhaseIn(BaseModel):
    name: str
    anchor: Anchor = Field(description="Milestone the phase starts from")
    offset: int = Field(0, description="Months after (negative = before) the anchor")
    months: int = Field(description="Duration in months")
    units_per_month: float = Field(description="Gross units sold per month during this phase (cancellations are applied by the model)")


class PricePhaseIn(BaseModel):
    name: str
    anchor: Anchor
    offset: int = 0
    months: int
    pct: float = Field(description="Price change for contracts signed in this period, in percent (-8 = 8% discount)")


class LandPaymentIn(BaseModel):
    month: int = Field(description="Month from land closing (0 = at closing)")
    pct: float = Field(description="Percent of the land price paid in that month; all rows must add to 100")


class CustomFlowIn(BaseModel):
    label: str
    type: Literal["cost", "revenue"]
    amount: float = Field(description="Positive amount in the project currency")
    month: int | None = Field(None, description="Absolute month from closing, OR use anchor + offset")
    anchor: Anchor | None = None
    offset: int = 0


class UnitTypeIn(BaseModel):
    name: str
    bedrooms: int = 0
    bathrooms: float = 1
    size: float
    share_pct: float
    terrace: float = 0
    premium_pct: float = 0


agent = Agent(deps_type=ManagerDeps, output_type=str, instructions=PROMPT, name="Investment Manager", retries=1)


def _project(ctx: RunContext[ManagerDeps]) -> dict:
    if ctx.deps.project_id is None:
        raise ValidationError("No project is open. Open a project or call create_project first.")
    return store.get_project(ctx.deps.project_id)


def _log(ctx: RunContext[ManagerDeps], tool: str, summary: str, page: str | None = None, **extra) -> None:
    entry = {"tool": tool, "summary": summary, "page": page, **extra}
    ctx.deps.ctx.tool_log.append(entry)
    if page and page not in ctx.deps.ctx.links:
        ctx.deps.ctx.links.append(page)
    ctx.deps.ctx.emit("tool_end", **entry)


def _round(v: Any) -> Any:
    if isinstance(v, float):
        return round(v, 4) if abs(v) < 100 else round(v)
    return v


def _metrics(res: dict, keys=("total_cost", "gdv", "profit", "net_margin", "project_irr", "equity_irr", "moic", "npv",
                              "peak_equity", "funding_gap", "duration_months")) -> dict:
    if res.get("status") != "ok":
        return {"status": res.get("status"), "missing": res.get("missing_labels") or res.get("missing"), "errors": res.get("errors")}
    return {k: _round(res["metrics"].get(k)) for k in keys if res["metrics"].get(k) is not None}


PAGE_FOR_SECTION = {"site": "property", "reg": "property", "dev": "design", "rev": "market", "rent": "market",
                    "cost": "budget", "sch": "budget", "fin": "financing", "val": "model"}


# ----------------------------------------------------------------------------- read tools
@agent.tool
def describe_variables(ctx: RunContext[ManagerDeps], section: str | None = None, search: str | None = None) -> list[dict]:
    """List editable variables (key, label, unit, material flag, current value). Filter by section
    (site, reg, dev, rev, rent, cost, sch, fin, val) or a search word."""
    a = store.get_project(ctx.deps.project_id)["assumptions"] if ctx.deps.project_id else {}
    out = []
    for k, s in REGISTRY.items():
        if section and s["section"] != section:
            continue
        if search and search.lower() not in (k + " " + s["label"]).lower():
            continue
        out.append({"key": k, "label": s["label"], "unit": s["unit"], "material": s["material"] or s["regulatory"],
                    "value": a.get(k), **({"choices": s["choices"]} if s["choices"] else {})})
    _log(ctx, "describe_variables", f"{len(out)} variables")
    return out[:60]


@agent.tool
def get_results(ctx: RunContext[ManagerDeps],
                view: Literal["summary", "budget", "schedule", "covenants", "sensitivity", "scenarios", "waterfall", "design"] = "summary") -> dict:
    """Read engine outputs for the open project. All numbers come from the deterministic engine."""
    p = _project(ctx)
    res = services.results(p)
    if res.get("status") != "ok":
        _log(ctx, "get_results", "model incomplete", "assumptions")
        return {"status": res.get("status"), "missing": res.get("missing_labels") or res.get("missing"), "errors": res.get("errors")}
    page = {"summary": "model", "budget": "budget", "schedule": "budget", "covenants": "financing", "sensitivity": "model",
            "scenarios": "model", "waterfall": "financing", "design": "design"}[view]
    if view == "summary":
        out = {**services.key_metrics(res), "warnings": res["warnings"], "compliant": res["compliant"]}
        out = {k: _round(v) for k, v in out.items()}
    elif view == "budget":
        groups: dict[str, float] = {}
        for b in res["budget"]:
            groups[b["group"]] = groups.get(b["group"], 0) + b["amount"]
        out = {"by_group": {k: round(v) for k, v in groups.items()}, "total_cost": round(res["metrics"]["total_cost"]),
               "cost_per_area_gba": _round(res["metrics"]["cost_per_area_gba"])}
    elif view == "schedule":
        out = res["schedule"]
    elif view == "covenants":
        out = {"covenants": [{**c, "actual": _round(c["actual"])} for c in res["covenants"]],
               "funding_gap": round(res["metrics"]["funding_gap"]), "maturity_month": res["metrics"].get("maturity_month")}
    elif view == "sensitivity":
        t = analysis.tornado(p["profile"], p["assumptions"], "equity_irr")
        out = {"metric": "equity_irr", "base": _round(t["base"]),
               "bars": [{"driver": b["driver"], "low": _round(b["low_input"]), "high": _round(b["high_input"])} for b in t["bars"]]}
    elif view == "scenarios":
        sc = analysis.run_scenarios(p["profile"], p["assumptions"], services.scenario_defs(p))
        out = {"scenarios": [{"name": s["name"], **(_metrics({"status": s["status"], "metrics": s.get("metrics")})
                                                     if s["status"] == "ok" else {"status": s["status"]})} for s in sc]}
    elif view == "waterfall":
        out = {k: {kk: _round(vv) for kk, vv in v.items()} for k, v in res["waterfall"].items()}
    else:
        d = res["design"]
        out = {k: _round(d.get(k)) for k in ("land_area", "max_far_area", "max_coverage_area", "footprint", "gba_above", "saleable",
                                              "units", "parking_spaces", "below_area", "levels_below_needed", "max_units_density")}
        out["unit_types"] = [{"name": t["name"], "units": t["units"], "size": t["size"]} for t in d.get("unit_types", [])]
        out["compliance_issues"] = [i["detail"] for i in res["compliance"]]
    _log(ctx, "get_results", f"read {view}", page)
    return out


# ----------------------------------------------------------------------------- write tools
@agent.tool
def update_assumptions(ctx: RunContext[ManagerDeps], changes: list[ChangeIn], reason: str) -> dict:
    """Validate and apply assumption changes. Ordinary edits are applied now and the model recalculates.
    Material edits (financing, rates, regulatory limits) are returned as pending: the user must click Confirm in the app."""
    p = _project(ctx)
    before = services.results(p)
    res = store.apply_changes(p["id"], [c.model_dump() for c in changes], actor="chatbot", reason=reason)
    after = services.results(store.get_project(p["id"]))
    ctx.deps.ctx.changes += res["applied"]
    if res["pending_id"]:
        ctx.deps.ctx.pending_ids.append(res["pending_id"])
    pages = {PAGE_FOR_SECTION.get(REGISTRY[c.key]["section"]) for c in changes if c.key in REGISTRY}
    summary = f"applied {len(res['applied'])}, pending {len(res['pending'])}, rejected {len(res['rejected'])}"
    _log(ctx, "update_assumptions", summary, next(iter(pages - {None}), "assumptions"),
         applied=res["applied"], pending=res["pending"], pending_id=res["pending_id"], rejected=res["rejected"])
    return {
        "applied": [{"key": x["key"], "label": x["label"], "old": x["old"], "new": x["new"], "unit": x["unit"]} for x in res["applied"]],
        "pending_user_confirmation": [{"key": x["key"], "label": x["label"], "old": x["old"], "new": x["new"]} for x in res["pending"]],
        "rejected": res["rejected"], "warnings": res["warnings"],
        "effect_on_metrics": [{"metric": e["metric"], "before": _round(e["before"]), "after": _round(e["after"])}
                              for e in services.describe_change_effect(before, after)],
        "model_status": after.get("status"), "missing_inputs": after.get("missing_labels", []),
    }


@agent.tool
def update_profile(ctx: RunContext[ManagerDeps], fields: dict[str, str | float | int]) -> dict:
    """Update project profile facts: name, country, state, city, neighborhood, address, currency, property_type,
    strategy, business_model, ownership_status, horizon_years."""
    p = _project(ctx)
    clean = {}
    for k, v in fields.items():
        if k in PROFILE_CHOICES:
            v = str(v).strip().lower().replace(" ", "_").replace("-", "_")
            if v not in PROFILE_CHOICES[k]:
                return {"error": f"{k} must be one of {PROFILE_CHOICES[k]}"}
        clean[k] = v
    try:
        store.update_profile(p["id"], clean, actor="chatbot")
    except store.StoreError as exc:
        return {"error": str(exc)}
    _log(ctx, "update_profile", ", ".join(f"{k}={v}" for k, v in clean.items()), "property")
    return {"updated": clean}


@agent.tool
def scale_unit_sizes(ctx: RunContext[ManagerDeps], target_average_size: float) -> dict:
    """Scale every unit type proportionally so the average unit size (per unit) equals the target, keeping the mix shares."""
    p = _project(ctx)
    res = services.results(p)
    mix = p["assumptions"].get("unit_mix") or []
    if not mix or res.get("status") != "ok" or not res["design"]["units"]:
        return {"error": "Unit mix or design is incomplete."}
    current = res["design"]["sold_area"] / res["design"]["units"]
    factor = target_average_size / current
    new_mix = [{**t, "size": round(t["size"] * factor, 1)} for t in mix]
    before = res
    r = store.apply_changes(p["id"], [{"key": "unit_mix", "value": new_mix}], actor="chatbot",
                            reason=f"scale unit sizes to average {target_average_size}")
    after = services.results(store.get_project(p["id"]))
    ctx.deps.ctx.changes += r["applied"]
    _log(ctx, "scale_unit_sizes", f"average size {current:.1f} → {target_average_size:g}", "design", applied=r["applied"])
    return {"previous_average": round(current, 1), "new_sizes": {t["name"]: t["size"] for t in new_mix},
            "units_before": before["design"]["units"], "units_after": after.get("design", {}).get("units"), "rejected": r["rejected"],
            "effect_on_metrics": [{"metric": e["metric"], "before": _round(e["before"]), "after": _round(e["after"])}
                                  for e in services.describe_change_effect(before, after)]}


@agent.tool
def set_unit_mix(ctx: RunContext[ManagerDeps], unit_types: list[UnitTypeIn], reason: str) -> dict:
    """Replace the unit mix (shares must add to 100%)."""
    p = _project(ctx)
    before = services.results(p)
    r = store.apply_changes(p["id"], [{"key": "unit_mix", "value": [u.model_dump() for u in unit_types]}], actor="chatbot", reason=reason)
    after = services.results(store.get_project(p["id"]))
    ctx.deps.ctx.changes += r["applied"]
    _log(ctx, "set_unit_mix", f"{len(unit_types)} unit types", "design", applied=r["applied"], rejected=r["rejected"])
    return {"rejected": r["rejected"], "units_after": after.get("design", {}).get("units"),
            "effect_on_metrics": [{"metric": e["metric"], "before": _round(e["before"]), "after": _round(e["after"])}
                                  for e in services.describe_change_effect(before, after)]}


@agent.tool
def apply_zoning_code(ctx: RunContext[ManagerDeps], code: str) -> dict:
    """Parse a Mexico City zoning code the user provides (e.g. "H/4/20/M" from their Certificado Único de Zonificación)
    into stories, open area, FAR and density. Regulatory limits are material, so they come back pending confirmation."""
    p = _project(ctx)
    try:
        r = store.apply_zoning_code(p["id"], code, actor="chatbot")
    except ValueError as exc:
        return {"error": str(exc)}
    if r.get("pending_id"):
        ctx.deps.ctx.pending_ids.append(r["pending_id"])
    ctx.deps.ctx.changes += r["applied"]
    _log(ctx, "apply_zoning_code", f"{r['parsed']['code']}: pending {len(r['pending'])}", "property", pending_id=r.get("pending_id"))
    return {"parsed": r["parsed"], "pending_user_confirmation": [{"key": x["key"], "new": x["new"]} for x in r["pending"]],
            "applied": [{"key": x["key"], "new": x["new"]} for x in r["applied"]]}


def _apply_schedule(ctx: RunContext[ManagerDeps], key: str, rows: list, reason: str, page: str) -> dict:
    p = _project(ctx)
    before = services.results(p)
    payload = [r.model_dump(exclude_none=True) for r in rows]
    res = store.apply_changes(p["id"], [{"key": key, "value": payload}], actor="chatbot", reason=reason)
    after = services.results(store.get_project(p["id"]))
    ctx.deps.ctx.changes += res["applied"]
    _log(ctx, f"set_{key}", f"{len(payload)} row(s)" + (f", rejected: {res['rejected'][0]['error']}" if res["rejected"] else ""), page,
         applied=res["applied"], rejected=res["rejected"])
    return {"saved_rows": payload if res["applied"] else [], "rejected": res["rejected"], "model_status": after.get("status"),
            "effect_on_metrics": [{"metric": e["metric"], "before": _round(e["before"]), "after": _round(e["after"])}
                                  for e in services.describe_change_effect(before, after)],
            "schedule": after.get("schedule") if after.get("status") == "ok" else None}


@agent.tool
def set_sales_phases(ctx: RunContext[ManagerDeps], phases: list[SalesPhaseIn], reason: str) -> dict:
    """Give the sales pace a shape over time: periods with their own units/month (e.g. a launch peak at construction start
    and a second peak at delivery). Outside the phases the base absorption (rev.absorption_per_month) applies, so set that
    to the slow 'in-between' pace. Replaces the existing phases; pass an empty list to remove them."""
    return _apply_schedule(ctx, "sales_phases", phases, reason, "market")


@agent.tool
def set_price_phases(ctx: RunContext[ManagerDeps], phases: list[PricePhaseIn], reason: str) -> dict:
    """Price changes for contracts signed in given periods (e.g. -8% presale/launch discount, +5% premium after delivery).
    Applied on top of the base price and annual escalation. Replaces existing price phases; empty list removes them."""
    return _apply_schedule(ctx, "price_phases", phases, reason, "market")


@agent.tool
def set_land_payments(ctx: RunContext[ManagerDeps], payments: list[LandPaymentIn], reason: str) -> dict:
    """Pay the land in installments (percent of the price by month from closing; must add to 100). Empty list = all at closing."""
    return _apply_schedule(ctx, "land_payments", payments, reason, "budget")


@agent.tool
def set_custom_cash_flows(ctx: RunContext[ManagerDeps], flows: list[CustomFlowIn], reason: str) -> dict:
    """Add any one-off cost or revenue the standard inputs don't cover (a mitigation fee, a utility connection, the sale of
    a commercial unit, a subsidy...). Replaces the list, so include existing flows you want to keep (see the snapshot)."""
    return _apply_schedule(ctx, "custom_flows", flows, reason, "budget")


@agent.tool
def undo_last_change(ctx: RunContext[ManagerDeps]) -> dict:
    """Undo the most recent batch of assumption changes for the open project."""
    p = _project(ctx)
    r = store.undo_last(p["id"], actor="chatbot")
    _log(ctx, "undo_last_change", f"undid {len(r['undone'])} change(s)", "assumptions")
    return r


@agent.tool
def request_status_change(ctx: RunContext[ManagerDeps], status: Literal["approved", "portfolio", "hypothetical"], reason: str) -> dict:
    """Ask to change the project status (approve, add to portfolio). Always requires the user's confirmation click."""
    p = _project(ctx)
    pid = store.request_status_change(p["id"], status, reason, actor="chatbot")
    ctx.deps.ctx.pending_ids.append(pid)
    _log(ctx, "request_status_change", f"status → {status} (pending confirmation)", "portfolio", pending_id=pid)
    return {"pending_id": pid, "message": "Pending: the user must confirm this in the app."}


@agent.tool
def create_project(ctx: RunContext[ManagerDeps], name: str, city: str, neighborhood: str = "", country: str = "Mexico",
                   property_type: str = "residential", strategy: str = "ground_up", business_model: str = "build_to_sell",
                   currency: str = "MXN") -> dict:
    """Create a new project (when the user describes a new deal and no project is open). Then set its assumptions
    with update_assumptions."""
    for k, v in (("property_type", property_type), ("strategy", strategy), ("business_model", business_model)):
        if v not in PROFILE_CHOICES[k]:
            return {"error": f"{k} must be one of {PROFILE_CHOICES[k]}"}
    pid = store.create_project({"name": name, "city": city, "neighborhood": neighborhood, "country": country,
                                "state": "Ciudad de México" if "mexico city" in city.lower() or "cdmx" in city.lower() else "",
                                "property_type": property_type, "strategy": strategy, "business_model": business_model,
                                "currency": currency, "area_unit": "m²", "horizon_years": 5}, actor="chatbot", owner=ctx.deps.ctx.owner)
    ctx.deps.project_id = pid
    ctx.deps.ctx.project_id = pid
    _log(ctx, "create_project", f"created project #{pid} {name}", f"project:{pid}")
    return {"project_id": pid, "message": "Project created and opened. Now record the user's assumptions."}


# ----------------------------------------------------------------------------- analysis tools (no saving)
@agent.tool
def what_if(ctx: RunContext[ManagerDeps], changes: list[ChangeIn] | None = None, sales_phases: list[SalesPhaseIn] | None = None,
            price_phases: list[PricePhaseIn] | None = None, land_payments: list[LandPaymentIn] | None = None,
            custom_flows: list[CustomFlowIn] | None = None) -> dict:
    """Run the full model with temporary changes (nothing is saved): scalar changes and/or schedules (sales phases, price
    phases, land payments, custom cash flows). Returns base vs scenario metrics."""
    from engine.schedules import validate_schedule
    p = _project(ctx)
    changes = changes or []
    try:
        ov = analysis.apply_changes(p["assumptions"], [c.model_dump() for c in changes])
        for key, rows in (("sales_phases", sales_phases), ("price_phases", price_phases), ("land_payments", land_payments),
                          ("custom_flows", custom_flows)):
            if rows is not None:
                ov[key] = validate_schedule(key, [r.model_dump(exclude_none=True) for r in rows])
    except ValidationError as exc:
        return {"error": str(exc)}
    base = services.results(p)
    sc = run_model(p["profile"], p["assumptions"], ov)
    _log(ctx, "what_if", ", ".join([f"{c.key} {c.op} {c.value}" for c in changes] + [k for k in ov if k in ("sales_phases", "price_phases", "land_payments", "custom_flows")]), "model")
    return {"changes": ov, "base": _metrics(base), "scenario": _metrics(sc),
            "scenario_covenant_breaches": [c["name"] for c in sc.get("covenants", []) if not c["ok"]],
            "scenario_warnings": sc.get("warnings", [])}


@agent.tool
def solve_for_target(ctx: RunContext[ManagerDeps], key: str, metric: str, target_value: float) -> dict:
    """Reverse underwriting: find the value of `key` (e.g. site.land_price) at which `metric` (equity_irr, project_irr,
    profit, net_margin, npv) equals the target. Percent targets may be given as 18 or 0.18."""
    p = _project(ctx)
    t = target_value / 100 if metric in PERCENT_METRICS and target_value > 1.5 else target_value
    try:
        r = analysis.solve_for(p["profile"], p["assumptions"], key, metric, t)
    except ValidationError as exc:
        return {"error": str(exc)}
    _log(ctx, "solve_for_target", f"{key} for {metric} = {t:g} → {r.get('status')}", "model")
    return {k: _round(v) for k, v in r.items()}


@agent.tool
def compare_sustainability(ctx: RunContext[ManagerDeps], measure_keys: list[str] | None = None) -> dict:
    """Compare the project with vs without sustainability measures (all enabled ones, or the listed keys)."""
    p = _project(ctx)
    a = p["assumptions"]
    ms = a.get("sustainability_measures") or []
    if not ms:
        return {"error": "No sustainability measures defined for this project."}
    keys = set(measure_keys or [m["key"] for m in ms if m.get("enabled")] or [m["key"] for m in ms])
    without = run_model(p["profile"], {**a, "sustainability_measures": [{**m, "enabled": False} for m in ms]})
    with_ = run_model(p["profile"], {**a, "sustainability_measures": [{**m, "enabled": m["key"] in keys} for m in ms]})
    ev = sustainability.evaluate(p["profile"], a, [m for m in ms if m["key"] in keys])
    _log(ctx, "compare_sustainability", f"{len(keys)} measures", "sustainability")
    return {"measures": sorted(keys), "without": _metrics(without), "with": _metrics(with_),
            "capex": sum(m.get("capex") or 0 for m in ms if m["key"] in keys),
            "co2_t_per_year": sum(m.get("co2_t_annual") or 0 for m in ms if m["key"] in keys),
            "beneficiary_note": ev["beneficiary_note"],
            "per_measure": [{"key": r["key"], "lifecycle_npv": _round(r["lifecycle_npv"]), "payback_years": _round(r["simple_payback_years"]),
                             "delta_equity_irr": _round(r.get("delta_equity_irr"))} for r in ev["measures"]]}


# ----------------------------------------------------------------------------- delegation
@agent.tool
async def request_research(ctx: RunContext[ManagerDeps], kind: Literal["regulatory", "market", "cost", "financing", "sustainability"],
                           request: str | None = None) -> dict:
    """Delegate web research to ONE specialist (slow, costs money; cached). Results become pending proposals the
    user approves in the app. Specialists cannot delegate further."""
    p = _project(ctx)
    try:
        res = await specialists.run_specialist(ctx.deps.ctx, kind, p, request)
    except LimitReached as exc:
        ctx.deps.ctx.limit_hit = {"kind": exc.kind, "detail": exc.detail}
        _log(ctx, "request_research", f"blocked: {exc.detail}")
        return {"status": "limit_reached", "message": exc.detail + " Ask the user for permission to continue."}
    page = {"regulatory": "property", "market": "market", "cost": "budget", "financing": "financing", "sustainability": "sustainability"}[kind]
    _log(ctx, "request_research", f"{specialists.AGENT_NAMES[kind]}: {'cache' if res.get('from_cache') else 'web'}", page)
    return specialists.compact(kind, res)


@agent.tool
def list_documents(ctx: RunContext[ManagerDeps]) -> list[dict]:
    """Files the user uploaded to this project (permits, certificates, contracts, Excel models...) with their analysis summary."""
    from .document_agent import compact
    p = _project(ctx)
    docs = store.list_documents(p["id"])
    _log(ctx, "list_documents", f"{len(docs)} document(s)", "documents")
    return [{"document_id": d["id"], "filename": d["filename"], "kind": d["kind"], "uploaded": d["created_at"],
             "analysis": compact(d["analysis"])} for d in docs[:20]]


@agent.tool
async def analyze_document(ctx: RunContext[ManagerDeps], document_id: int, force: bool = False) -> dict:
    """Run the Document agent on an uploaded file: summary, key facts, permit details, contract risks, and values it
    proposes for the model (pending until the user approves them in the app)."""
    from .document_agent import analyze, compact
    p = _project(ctx)
    d = store.get_document(document_id)
    if d["project_id"] != p["id"]:
        return {"error": "That document belongs to another project."}
    if d["analysis"] and not force:  # already analyzed at upload: reuse (no tokens)
        _log(ctx, "analyze_document", f"{d['filename']}: cached analysis", "documents")
        return compact(d["analysis"])
    try:
        res = await analyze(ctx.deps.ctx, document_id)
    except LimitReached as exc:
        ctx.deps.ctx.limit_hit = {"kind": exc.kind, "detail": exc.detail}
        return {"status": "limit_reached", "message": exc.detail}
    _log(ctx, "analyze_document", f"{d['filename']}: {res.get('doc_type')}, {len(res.get('accepted_proposals', []))} proposals", "documents")
    return compact(res)


@agent.tool
async def ask_document(ctx: RunContext[ManagerDeps], document_id: int, question: str) -> dict:
    """Answer a question from an uploaded file (e.g. 'when does the permit expire?', 'what are the penalty clauses?',
    'what land price does the Excel model use?'). Returns an answer with verbatim quotes."""
    from .document_agent import ask
    p = _project(ctx)
    d = store.get_document(document_id)
    if d["project_id"] != p["id"]:
        return {"error": "That document belongs to another project."}
    try:
        res = await ask(ctx.deps.ctx, document_id, question)
    except LimitReached as exc:
        ctx.deps.ctx.limit_hit = {"kind": exc.kind, "detail": exc.detail}
        return {"status": "limit_reached", "message": exc.detail}
    _log(ctx, "ask_document", f"{d['filename']}: {question[:60]}", "documents")
    return {k: res.get(k) for k in ("answer", "quotes", "found_in_document", "confidence")}


@agent.tool
async def run_investment_committee(ctx: RunContext[ManagerDeps]) -> dict:
    """Run the Investment Committee (two challenger agents, then the chair). Use only when the user asks for an IC review."""
    from .committee import run_committee
    p = _project(ctx)
    try:
        memo = await run_committee(ctx.deps.ctx, p)
    except LimitReached as exc:
        ctx.deps.ctx.limit_hit = {"kind": exc.kind, "detail": exc.detail}
        return {"status": "limit_reached", "message": exc.detail}
    _log(ctx, "run_investment_committee", f"recommendation: {memo['recommendation']}", "committee")
    return {"recommendation": memo["recommendation"], "rationale": memo["memo"].get("rationale"),
            "conditions": memo["memo"].get("conditions", [])[:5], "guardrails": memo["memo"].get("guardrail_adjustments", [])}


# ----------------------------------------------------------------------------- run a chat turn
def _history(pid: int | None, owner: str | None, limit: int = 6) -> list:
    msgs = store.list_messages(pid, limit=limit, owner=owner)
    hist: list = []
    for m in msgs:
        if m["role"] == "user":
            hist.append(ModelRequest(parts=[UserPromptPart(content=m["content"][:2000])]))
        else:
            hist.append(ModelResponse(parts=[TextPart(content=m["content"][:2000])]))
    while hist and isinstance(hist[0], ModelResponse):
        hist.pop(0)
    return hist


async def run_chat(project_id: int | None, message: str, ctx: TurnContext) -> dict:
    deps = ManagerDeps(ctx=ctx, project_id=project_id)
    snapshot = services.summarize_for_llm(store.get_project(project_id)) if project_id else {"project": None,
               "projects": [{"id": p["id"], "name": p["name"]} for p in store.list_projects(ctx.owner)]}
    prompt = f"<project_snapshot>\n{json.dumps(snapshot, ensure_ascii=False, default=str)}\n</project_snapshot>\n\nUser message:\n{message}"
    history = _history(project_id, ctx.owner)
    store.add_message(project_id, "user", message, owner=ctx.owner)
    limits = UsageLimits(request_limit=ctx.limits["max_requests"], tool_calls_limit=ctx.limits["max_tool_calls"],
                         total_tokens_limit=ctx.limits["max_tokens"])
    ctx.emit("thinking", agent="Investment Manager")
    t0 = time.perf_counter()
    answer, run = None, None
    try:
        async with agent.iter(prompt, deps=deps, model=build_model(), message_history=history, usage_limits=limits,
                              model_settings={"openai_reasoning_effort": ctx.limits.get("reasoning_effort", "low")}) as run:
            async for node in run:
                if Agent.is_call_tools_node(node):
                    for part in node.model_response.parts:
                        if getattr(part, "tool_name", None) and hasattr(part, "args_as_dict"):
                            ctx.emit("tool_start", tool=part.tool_name, args=_safe_args(part))
                    # dollar limit on the whole turn (manager + specialists)
                    so_far = ctx.spent_usd + _cost_of(run.usage)
                    if so_far > ctx.limits["max_usd"]:
                        raise LimitReached("usd", f"Turn spend ${so_far:.4f} exceeded the ${ctx.limits['max_usd']:.2f} limit.")
            answer = run.result.output
    except UsageLimitExceeded as exc:
        ctx.limit_hit = {"kind": "usage", "detail": str(exc)}
    except LimitReached as exc:
        ctx.limit_hit = {"kind": exc.kind, "detail": exc.detail}
    finally:
        if run is not None:
            ctx.record("Investment Manager", run.usage, time.perf_counter() - t0,
                       run.all_messages() if hasattr(run, "all_messages") else None, purpose="chat")
    if answer is None:
        answer = ("I stopped safely because this turn reached a configured limit "
                  f"({ctx.limit_hit['detail'] if ctx.limit_hit else 'limit'}). Changes made before the stop were saved and are listed below. "
                  "Use **Continue with higher limits** to let me finish.")
    extra = {"tool_log": ctx.tool_log, "changes": ctx.changes, "pending_ids": ctx.pending_ids, "links": ctx.links,
             "usage": ctx.summary(), "limit_hit": ctx.limit_hit, "project_id": deps.project_id}
    store.add_message(deps.project_id, "assistant", answer, extra, owner=ctx.owner)
    return {"answer": answer, **extra}


def _cost_of(usage) -> float:
    from ..config import cost_usd
    return cost_usd(getattr(usage, "input_tokens", 0) or 0, getattr(usage, "output_tokens", 0) or 0,
                    getattr(usage, "cache_read_tokens", 0) or 0)


def _safe_args(part) -> dict:
    try:
        args = part.args_as_dict()
    except Exception:
        return {}
    s = json.dumps(args, default=str)
    return args if len(s) < 600 else {"_truncated": s[:600]}
