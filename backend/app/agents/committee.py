"""Investment Committee: two challengers in parallel, then the chair. Plus the Asset Management commentary.

Deterministic guardrails wrap the LLM:
  * no complete model → "Insufficient information" without spending tokens
  * covenant breach, funding gap or noncompliant design → "Invest" is downgraded to "Invest with conditions"
  * base-case equity IRR below the hurdle AND downside profit < 0 → "Invest" is not allowed
  * every percentage in the memo text is checked against engine numbers; unmatched ones are flagged
"""

from __future__ import annotations

import asyncio
import json
import re
import time
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field
from pydantic_ai import Agent

from engine import analysis

from .. import services, store
from ..config import build_model
from .runtime import TurnContext

PROMPTS = Path(__file__).resolve().parents[2] / "prompts"
_sections = (PROMPTS / "committee.md").read_text(encoding="utf-8").split("## ")
SECTION = {s.split("\n", 1)[0].strip(): s.split("\n", 1)[1].strip() for s in _sections[1:]}
AM_PROMPT = (PROMPTS / "asset_manager.md").read_text(encoding="utf-8")
SETTINGS = {"openai_reasoning_effort": "low"}


class Concern(BaseModel):
    area: str
    issue: str
    severity: Literal["high", "medium", "low"]
    evidence: str = Field(description="Which packet item supports this")
    suggested_test: str


class ChallengeReport(BaseModel):
    concerns: list[Concern]
    strengths: list[str] = []


class Risk(BaseModel):
    risk: str
    mitigation: str


class ICMemo(BaseModel):
    recommendation: Literal["Invest", "Invest with conditions", "Reject", "Insufficient information"]
    summary: str
    rationale: str
    conditions: list[str] = []
    key_risks: list[Risk] = []
    required_diligence: list[str] = []


class Priority(BaseModel):
    lever_id: str
    why: str
    how_to_execute: str
    main_risk: str


class AdvisorPlan(BaseModel):
    headline: str
    priorities: list[Priority]
    quick_wins: list[str] = []
    avoid: list[str] = []
    data_gaps: list[str] = []


class AMCommentary(BaseModel):
    headline: str
    drivers: list[str]
    actions: list[str]


underwriting_challenger = Agent(output_type=ChallengeReport, instructions=SECTION["Challenger: Underwriting"], name="IC Underwriting Challenger")
risk_challenger = Agent(output_type=ChallengeReport, instructions=SECTION["Challenger: Capital & Risk"], name="IC Capital & Risk Challenger")
chair = Agent(output_type=ICMemo, instructions=SECTION["Chair"], name="IC Chair")
asset_agent = Agent(output_type=AMCommentary, instructions=AM_PROMPT, name="Asset Management")
advisor_agent = Agent(output_type=AdvisorPlan, instructions=(PROMPTS / "advisor.md").read_text(encoding="utf-8"), name="Improvement Advisor")


def slim_recommendations(rec: dict) -> dict:
    def pct(x):
        return None if x is None else round(x * 100, 2)
    return {"base": {"equity_irr_pct": pct(rec["base"]["equity_irr"]), "profit": round(rec["base"]["profit"]), "npv": round(rec["base"]["npv"]),
                     "peak_equity": round(rec["base"]["peak_equity"])},
            "issues": [i["detail"] for i in rec.get("issues", [])],
            "levers": [{"id": lv["id"], "title": lv["title"], "category": lv["category"], "risk": lv["risk"], "note": lv["note"],
                        "fixes": lv["fixes"], "delta_equity_irr_pts": pct(lv["delta"]["equity_irr"]), "delta_profit": round(lv["delta"]["profit"] or 0),
                        "delta_peak_equity": round(lv["delta"]["peak_equity"] or 0), "remaining_issues": lv.get("remaining_issues", [])}
                       for lv in rec.get("levers", [])],
            "package": rec.get("package") and {"lever_ids": rec["package"]["lever_ids"], "delta_equity_irr_pts": pct(rec["package"]["delta"]["equity_irr"]),
                                               "delta_profit": round(rec["package"]["delta"]["profit"] or 0)}}


async def run_advisor(ctx: TurnContext, project: dict, rec: dict) -> dict:
    if rec.get("status") != "ok":
        return {"headline": "Complete the model first.", "priorities": [], "quick_wins": [], "avoid": [], "data_gaps": [i["detail"] for i in rec.get("issues", [])]}
    ctx.check_budget(extra_usd=0.004)
    t0 = time.perf_counter()
    r = await advisor_agent.run(json.dumps(slim_recommendations(rec), default=str), model=build_model(), model_settings=SETTINGS)
    ctx.record("Improvement Advisor", r.usage, time.perf_counter() - t0, purpose="advisor")
    return r.output.model_dump()


def _pct(x):
    return None if x is None else round(x * 100, 2)


def build_packet(project: dict) -> dict:
    res = services.results(project)
    m = res["metrics"]
    p, a = project["profile"], project["assumptions"]
    sc = analysis.run_scenarios(p, a, services.scenario_defs(project))
    tor = analysis.tornado(p, a, "equity_irr")
    meta = project["meta"]
    prov: dict[str, int] = {}
    for k, v in a.items():
        if k in ("unit_mix", "sustainability_measures", "hard_cost_split") or v is None:
            continue
        src = (meta.get(k) or {}).get("source", "unknown")
        prov[src] = prov.get(src, 0) + 1
    research = store.latest_research(project["id"])
    comps = (research.get("market") or {}).get("payload", {}).get("summary", {}).get("stats")
    hurdle = a.get("val.equity_discount_rate_pct") or 18
    return {
        "project": {"name": project["name"], "location": f"{p.get('neighborhood')}, {p.get('city')}", "business_model": p.get("business_model"),
                    "fictional_demo": bool(p.get("demo"))},
        "metrics": {"units": m["units"], "total_cost": round(m["total_cost"]), "gdv": round(m["gdv"]), "profit": round(m["profit"]),
                    "net_margin_pct": _pct(m["net_margin"]), "profit_on_cost_pct": _pct(m["profit_on_cost"]),
                    "project_irr_pct": _pct(m["project_irr"]), "equity_irr_pct": _pct(m["equity_irr"]), "moic": round(m["moic"] or 0, 2),
                    "npv": round(m["npv"]), "peak_equity": round(m["peak_equity"]), "ltc_pct": _pct(m["ltc"]), "ltv_pct": _pct(m["ltv"]),
                    "duration_months": m["duration_months"], "funding_gap": round(m["funding_gap"]),
                    "investor_irr_pct": _pct(m["investor_irr"]), "sponsor_irr_pct": _pct(m["sponsor_irr"]),
                    "dscr": round(m["dscr"], 2) if m.get("dscr") else None, "hurdle_equity_irr_pct": hurdle},
        "covenants": [{"name": c["name"], "limit": c["limit"], "actual": round(c["actual"], 2), "ok": c["ok"]} for c in res["covenants"]],
        "compliance_issues": [i["detail"] for i in res["compliance"]],
        "warnings": res["warnings"],
        "scenarios": [{"name": s["name"], "equity_irr_pct": _pct((s.get("metrics") or {}).get("equity_irr")),
                       "profit": round((s.get("metrics") or {}).get("profit") or 0)} for s in sc if s["status"] == "ok"],
        "top_sensitivities": [{"driver": b["driver"], "equity_irr_low_pct": _pct(b["low_input"]), "equity_irr_high_pct": _pct(b["high_input"])}
                              for b in tor.get("bars", [])[:4]],
        "assumption_provenance": prov,
        "pending_research_proposals": sum(1 for v in meta.values() if isinstance(v, dict) and (v.get("proposal") or {}).get("status") == "pending"),
        "market_comps": comps and {"n": comps["n"], "median_price_per_area": round(comps["median"])},
        "key_assumptions": {k: a.get(k) for k in ("site.land_area", "site.land_price", "rev.price_per_area", "rev.absorption_per_month",
                                                   "rent.rent_per_area_month", "rent.exit_cap_pct", "cost.hard_per_area",
                                                   "sch.construction_months", "fin.senior_ltc_pct") if a.get(k) is not None},
        "sustainability_enabled": [x["name"] for x in a.get("sustainability_measures") or [] if x.get("enabled")],
    }


def _numbers_check(text: str, packet: dict) -> list[str]:
    """Flag percentages in LLM text that don't match any number in the packet (±0.15 pts)."""
    known = []

    def walk(x):
        if isinstance(x, dict):
            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)
        elif isinstance(x, (int, float)) and not isinstance(x, bool):
            known.append(float(x))

    walk(packet)
    flagged = []
    for mt in re.finditer(r"(-?\d+(?:\.\d+)?)\s?%", text):
        v = float(mt.group(1))
        if not any(abs(v - k) <= 0.15 for k in known):
            flagged.append(mt.group(0))
    return sorted(set(flagged))


async def run_committee(ctx: TurnContext, project: dict) -> dict:
    res = services.results(project)
    if res.get("status") != "ok":
        memo = {"recommendation": "Insufficient information", "summary": "The financial model is incomplete.",
                "rationale": "Required inputs are missing: " + ", ".join(res.get("missing_labels") or res.get("missing") or []),
                "conditions": [], "key_risks": [], "required_diligence": ["Complete the missing inputs"], "guardrail_adjustments": [],
                "challengers": {}, "llm_used": False}
        store.save_memo(project["id"], memo["recommendation"], memo, {})
        return {"recommendation": memo["recommendation"], "memo": memo}

    ctx.check_budget(extra_usd=0.01)
    packet = build_packet(project)
    pj = json.dumps(packet, ensure_ascii=False)
    model = build_model()
    ctx.emit("specialist_start", agent="Investment Committee", kind="committee")
    t0 = time.perf_counter()
    uw, rk = await asyncio.gather(
        underwriting_challenger.run(f"Packet:\n{pj}", model=model, model_settings=SETTINGS),
        risk_challenger.run(f"Packet:\n{pj}", model=model, model_settings=SETTINGS),
    )
    dt = time.perf_counter() - t0
    ctx.record("IC Underwriting Challenger", uw.usage, dt, purpose="committee")
    ctx.record("IC Capital & Risk Challenger", rk.usage, dt, purpose="committee")
    t1 = time.perf_counter()
    chair_in = (f"Packet:\n{pj}\n\nUnderwriting challenger:\n{uw.output.model_dump_json()}\n\n"
                f"Capital & risk challenger:\n{rk.output.model_dump_json()}")
    ch = await chair.run(chair_in, model=model, model_settings=SETTINGS)
    ctx.record("IC Chair", ch.usage, time.perf_counter() - t1, purpose="committee")
    memo = ch.output.model_dump()

    # deterministic guardrails
    adj = []
    m = res["metrics"]
    breaches = [c["name"] for c in res["covenants"] if not c["ok"]]
    if memo["recommendation"] == "Invest" and (breaches or m["funding_gap"] > 1 or not res["compliant"]):
        memo["recommendation"] = "Invest with conditions"
        adj.append("Downgraded from Invest: covenant breach, funding gap or noncompliant design present.")
        if breaches:
            memo["conditions"].insert(0, f"Cure covenant breach before closing: {', '.join(breaches)}.")
        if not res["compliant"]:
            memo["conditions"].insert(0, "Obtain regulatory approval for design elements exceeding researched legal limits.")
    hurdle = (project["assumptions"].get("val.equity_discount_rate_pct") or 18) / 100
    down = next((s for s in packet["scenarios"] if s["name"] == "Downside"), None)
    if memo["recommendation"] == "Invest" and m["equity_irr"] is not None and m["equity_irr"] < hurdle and down and down["profit"] < 0:
        memo["recommendation"] = "Invest with conditions"
        adj.append("Downgraded: base equity IRR below hurdle and downside loses money.")
    if project["profile"].get("demo"):
        memo.setdefault("required_diligence", []).append("All inputs are FICTIONAL demo values; replace with verified data before any real decision.")
    memo["guardrail_adjustments"] = adj
    text = " ".join([memo["summary"], memo["rationale"], *memo["conditions"], *[r["risk"] + " " + r["mitigation"] for r in memo["key_risks"]]])
    memo["unverified_numbers"] = _numbers_check(text, packet)
    memo["challengers"] = {"underwriting": uw.output.model_dump(), "capital_risk": rk.output.model_dump()}
    memo["llm_used"] = True
    store.save_memo(project["id"], memo["recommendation"], memo, packet)
    ctx.emit("specialist_done", agent="Investment Committee", kind="committee")
    return {"recommendation": memo["recommendation"], "memo": memo, "packet": packet}


async def run_asset_commentary(ctx: TurnContext, project: dict, am: dict) -> dict:
    if am.get("status") != "ok":
        return {"headline": am.get("message", "No actuals yet."), "drivers": [], "actions": []}
    ctx.check_budget(extra_usd=0.005)
    slim = {"as_of_month": am["as_of_month"], "drivers": am["drivers"], "alerts": am["alerts"],
            "variances": am["variances"], "comparison": [{**c, "underwriting": c["underwriting"], "updated": c["updated"]} for c in am["comparison"]]}
    t0 = time.perf_counter()
    r = await asset_agent.run(json.dumps(slim, default=str), model=build_model(), model_settings=SETTINGS)
    ctx.record("Asset Management", r.usage, time.perf_counter() - t0, purpose="asset_management")
    return r.output.model_dump()
