"""Research specialists: Regulatory, Market, Cost, Financing, Sustainability.

Design for safety and cost:
  * each specialist has ONLY the web_search tool and a structured output schema (no write tools, no delegation)
  * results are scrubbed for instruction-like text, cached by (agent, normalized request), and stored as
    research records; numeric findings become PENDING proposals that the user must approve
  * price per m² of comparables is computed by code, never by the model
"""

from __future__ import annotations

import hashlib
import re
import time
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field
from pydantic_ai import Agent
from pydantic_ai.capabilities import WebSearch

from engine.registry import REGISTRY

from .. import store
from ..config import RESEARCH_CACHE_DAYS, build_model
from ..services import comps_summary
from .runtime import CURRENT_LANG, LimitReached, TurnContext, lang_note, scrub_obj

PROMPTS = Path(__file__).resolve().parents[2] / "prompts"
RULES = (PROMPTS / "_research_rules.md").read_text(encoding="utf-8")


def _prompt(name: str) -> str:
    return (PROMPTS / f"{name}.md").read_text(encoding="utf-8") + "\n\n" + RULES


# ----------------------------------------------------------------------------- output schemas
class RegFinding(BaseModel):
    parameter: str = Field(description="Human-readable parameter, e.g. 'Maximum stories'")
    key: str | None = Field(None, description="Registry key such as reg.max_stories, or null for qualitative findings")
    value: float | None = None
    value_text: str | None = Field(None, description="Original wording, e.g. 'H/4/20/M' or 'commercial ground floor allowed'")
    unit: str | None = None
    verification: Literal["verified", "preliminary", "not_found"]
    level: Literal["parcel", "corridor_or_colonia", "district_program", "citywide_rule"] | None = Field(
        None, description="Geographic level the value applies to: this parcel, the street corridor / colonia, the alcaldia program, or a citywide rule")
    source_title: str | None = None
    source_url: str | None = None
    note: str = ""


class ZoningFindings(BaseModel):
    zoning_code: str | None = None
    zoning_summary: str
    permitted_uses: list[str] = []
    findings: list[RegFinding]
    missing: list[str] = Field(default_factory=list, description="What could not be verified and how the user can obtain it")
    caveats: list[str] = []


class Comparable(BaseModel):
    title: str
    neighborhood: str | None = None
    property_type: str | None = None
    size: float | None = Field(None, description="Interior size in m²")
    bedrooms: int | None = None
    bathrooms: float | None = None
    price: float | None = None
    currency: str | None = "MXN"
    price_type: Literal["asking", "transaction", "unknown"] = "asking"
    quality: str | None = None
    amenities: list[str] = []
    listing_date: str | None = None
    source_url: str
    notes: str = ""


class MarketFindings(BaseModel):
    comparables: list[Comparable]
    market_notes: list[str] = []
    absorption_evidence: str | None = None
    caveats: list[str] = []


class CostBenchmark(BaseModel):
    item: str
    key: str | None = None
    value: float | None = None
    unit: str
    low: float | None = None
    high: float | None = None
    year: str | None = None
    verification: Literal["published_benchmark", "indicative", "not_found"]
    source_title: str | None = None
    source_url: str | None = None
    note: str = ""


class CostFindings(BaseModel):
    benchmarks: list[CostBenchmark]
    caveats: list[str] = []


class RateBenchmark(BaseModel):
    item: str
    key: str | None = None
    value_pct: float | None = None
    as_of: str | None = None
    kind: Literal["published_rate", "indicative_assumption", "lender_offer"]
    institution: str | None = None
    source_title: str | None = None
    source_url: str | None = None
    note: str = ""


class FinancingFindings(BaseModel):
    rates: list[RateBenchmark]
    lenders: list[str] = []
    caveats: list[str] = []


class SusBenchmark(BaseModel):
    measure_key: str | None = None
    item: str
    value: float | None = None
    unit: str
    verification: Literal["published", "indicative", "not_found"]
    source_title: str | None = None
    source_url: str | None = None
    note: str = ""


class SustainabilityFindings(BaseModel):
    benchmarks: list[SusBenchmark]
    caveats: list[str] = []


SPECS = {
    "regulatory": ("Regulatory & Development", ZoningFindings, "regulatory"),
    "market": ("Market Research", MarketFindings, "market"),
    "cost": ("Cost & Construction", CostFindings, "cost"),
    "financing": ("Financing", FinancingFindings, "financing"),
    "sustainability": ("Sustainability", SustainabilityFindings, "sustainability"),
}
AGENT_NAMES = {k: v[0] for k, v in SPECS.items()}
_agents: dict[str, Agent] = {}


def _agent(kind: str) -> Agent:
    if kind not in _agents:
        name, out, prompt = SPECS[kind]
        _agents[kind] = Agent(
            build_model(), output_type=out, instructions=_prompt(prompt), name=name,
            capabilities=[WebSearch(search_context_size="medium" if kind == "regulatory" else "low")],
            model_settings={"openai_reasoning_effort": "low"}, retries=1,
        )
    return _agents[kind]


def default_request(kind: str, project: dict) -> str:
    p, a = project["profile"], project["assumptions"]
    loc = ", ".join(x for x in (p.get("address"), p.get("neighborhood"), p.get("city"), p.get("state"), p.get("country")) if x)
    ptype = f"{p.get('property_type', 'residential')} {p.get('business_model', '').replace('_', ' ')}"
    if kind == "regulatory":
        muni = f" (alcaldía {p['municipality']})" if p.get("municipality") else ""
        code = f" The owner reports zoning code {p['zoning_code']}; confirm and interpret it." if p.get("zoning_code") else ""
        return (f"Development regulations for a {a.get('site.land_area') or '?'} m² lot at {loc}{muni}: zoning code, stories, open area, "
                f"FAR, density, parking and other restrictions. If parcel-level zoning is not readable online, report the zoning that the "
                f"applicable Programa Delegacional/Parcial assigns to this colonia or street corridor, and the citywide rules that apply.{code}")
    if kind == "market":
        product = "new apartments for sale" if "sell" in ptype else "apartments for rent"
        return f"Comparable {product} ({a.get('dev.quality') or 'high'} quality) in {p.get('neighborhood') or ''}, {p.get('city') or ''}."
    if kind == "cost":
        return f"Construction cost benchmarks per m² for {a.get('dev.quality') or 'high'}-quality {ptype} (mid-rise, {a.get('dev.stories') or '?'} stories, with underground parking) in {p.get('city')}, {p.get('country')}, current year."
    if kind == "financing":
        return f"Reference interest rate and construction-loan terms for a residential development in {p.get('city')}, {p.get('country')}."
    return f"Parameters for solar PV, efficient HVAC, water saving, LED and green certification for a {ptype} building in {p.get('city')}, {p.get('country')}."


def cache_key(kind: str, request: str) -> str:
    norm = re.sub(r"\s+", " ", request.strip().lower())
    return hashlib.sha256(f"{kind}|{norm}".encode()).hexdigest()[:32]


# ----------------------------------------------------------------------------- post-processing (deterministic)
def _proposals(kind: str, payload: dict) -> list[dict]:
    props = []
    if kind == "regulatory":
        for f in payload.get("findings", []):
            if f.get("key") in REGISTRY and f.get("value") is not None and f["verification"] != "not_found":
                lvl = (f.get("level") or "").replace("_", " ")
                props.append({"key": f["key"], "value": f["value"], "verification": f["verification"],
                              "confidence": "high" if f["verification"] == "verified" else ("medium" if f.get("level") in ("parcel", "corridor_or_colonia") else "low"),
                              "source_title": f.get("source_title"), "source_url": f.get("source_url"),
                              "note": (f"[{lvl}] " if lvl else "") + (f.get("note") or "")})
        # a zoning code found by research is expanded deterministically (FAR, density) with the same certainty label
        code_finding = next((f for f in payload.get("findings", []) if f.get("value_text") and f["verification"] != "not_found"
                             and _looks_like_code(f["value_text"])), None)
        raw_code = payload.get("zoning_code") or (code_finding or {}).get("value_text")
        parsed = _try_parse_code(raw_code)
        if parsed:
            have = {x["key"] for x in props}
            ver = (code_finding or {}).get("verification") or "preliminary"
            src = (code_finding or {}).get("source_url")
            lvl = ((code_finding or {}).get("level") or "").replace("_", " ")
            derived = [("reg.max_stories", parsed["max_stories"]), ("reg.min_open_area_pct", parsed["min_open_area_pct"]),
                       ("reg.max_far", parsed["max_far"]), ("reg.min_land_per_unit", parsed.get("min_land_per_unit"))]
            for key, val in derived:
                if val is not None and key not in have:
                    props.append({"key": key, "value": val, "verification": ver, "confidence": "medium" if ver == "verified" else "low",
                                  "source_title": f"Derived by TerraMind from zoning code {parsed['code']}", "source_url": src,
                                  "note": (f"[{lvl}] " if lvl else "") + f"Computed from {parsed['code']} (stories × (1 − open area); density per NGO 11)."})
            payload["parsed_zoning_code"] = parsed
    elif kind == "cost":
        for b in payload.get("benchmarks", []):
            if b.get("key") in REGISTRY and b.get("value") is not None and b["verification"] != "not_found":
                props.append({"key": b["key"], "value": b["value"], "verification": b["verification"], "confidence": "medium",
                              "source_title": b.get("source_title"), "source_url": b.get("source_url"),
                              "note": f"{b['item']} ({b.get('year') or 'n.d.'}); range {b.get('low')}–{b.get('high')} {b['unit']}. Estimate, not a contractor quote."})
    elif kind == "financing":
        for r in payload.get("rates", []):
            if r.get("key") in REGISTRY and r.get("value_pct") is not None:
                props.append({"key": r["key"], "value": r["value_pct"], "verification": r["kind"],
                              "confidence": "high" if r["kind"] == "published_rate" else "low",
                              "source_title": r.get("source_title"), "source_url": r.get("source_url"),
                              "note": f"{r['item']} as of {r.get('as_of') or 'n.d.'}" + (f" ({r['institution']})" if r.get("institution") else "")})
    elif kind == "market":
        stats = payload.get("summary", {}).get("stats")
        if stats:
            props.append({"key": "rev.price_per_area", "value": round(stats["median"], -2), "verification": "preliminary",
                          "confidence": "medium" if stats["n"] >= 5 else "low", "source_title": f"Median of {stats['n']} comparables (asking prices)",
                          "source_url": None, "note": "Computed by TerraMind from listed comparables; asking prices, not transactions."})
    return props


def _looks_like_code(text: str) -> bool:
    return _try_parse_code(text) is not None


def _try_parse_code(text: str | None) -> dict | None:
    from engine.zoning import parse_cdmx_code
    if not text:
        return None
    candidate = re.split(r"[(;,]", str(text))[0].strip()
    try:
        return parse_cdmx_code(candidate)
    except ValueError:
        return None


def postprocess(kind: str, raw: dict) -> dict:
    flags: list[str] = []
    payload = scrub_obj(raw, flags)
    if kind == "financing":  # web pages are never real lender offers
        for r in payload.get("rates", []):
            if r.get("kind") == "lender_offer":
                r["kind"] = "indicative_assumption"
                r["note"] = (r.get("note") or "") + " [relabelled: a web page is not a lender offer]"
    if kind == "market":
        comps = [c for c in payload.get("comparables", []) if c.get("source_url", "").startswith("http")]
        dropped = len(payload.get("comparables", [])) - len(comps)
        payload["comparables"] = comps
        payload["summary"] = comps_summary(comps)
        if dropped:
            payload.setdefault("caveats", []).append(f"{dropped} comparables without a source URL were discarded.")
    payload["suspicious_fields"] = flags
    return payload


# ----------------------------------------------------------------------------- runner
async def run_specialist(ctx: TurnContext, kind: str, project: dict, request: str | None = None, force: bool = False) -> dict:
    if kind not in SPECS:
        return {"status": "error", "message": f"unknown specialist '{kind}'"}
    request = (request or default_request(kind, project)).strip()[:600]
    key = cache_key(kind, request + ("|es" if CURRENT_LANG.get() == "es" else ""))
    name = AGENT_NAMES[kind]
    if key in ctx.specialist_requests_seen:
        return {"status": "duplicate", "message": "This exact research request already ran in this turn."}
    ctx.specialist_requests_seen.add(key)

    cached = None if force else store.cache_get(key, RESEARCH_CACHE_DAYS)
    if cached:
        payload = cached["payload"]
        store.save_research(project["id"], kind, request, payload, from_cache=True)
        proposals = store.propose_values(project["id"], kind, _proposals(kind, payload))
        ctx.emit("specialist_done", agent=name, kind=kind, from_cache=True)
        return {"status": "ok", "agent": name, "from_cache": True, "cached_at": cached["created_at"],
                "payload": payload, "proposals": proposals, "usage": None}

    if ctx.specialist_calls >= ctx.limits["max_specialist_calls"]:
        raise LimitReached("specialists", f"Specialist research limit ({ctx.limits['max_specialist_calls']} per turn) reached.")
    ctx.check_budget(extra_usd=0.005)
    ctx.specialist_calls += 1
    ctx.emit("specialist_start", agent=name, kind=kind, request=request)
    t0 = time.perf_counter()
    result = await _agent(kind).run(f"Research request: {request}\nProject location context: "
                                    f"{project['profile'].get('neighborhood') or ''}, {project['profile'].get('city') or ''}, "
                                    f"{project['profile'].get('country') or ''}.{lang_note()}",
                                    usage_limits=_specialist_limits())
    usage = ctx.record(name, result.usage, time.perf_counter() - t0, result.all_messages(), purpose=f"research:{kind}")
    payload = postprocess(kind, result.output.model_dump())
    store.cache_put(key, kind, request, payload)
    store.save_research(project["id"], kind, request, payload, from_cache=False)
    proposals = store.propose_values(project["id"], kind, _proposals(kind, payload))
    ctx.emit("specialist_done", agent=name, kind=kind, from_cache=False, cost_usd=usage["cost_usd"])
    return {"status": "ok", "agent": name, "from_cache": False, "payload": payload, "proposals": proposals, "usage": usage}


def _specialist_limits():
    from pydantic_ai.usage import UsageLimits
    return UsageLimits(request_limit=6, total_tokens_limit=150_000)


def compact(kind: str, res: dict) -> dict:
    """Short version of a specialist result for the manager's context (saves tokens)."""
    if res.get("status") != "ok":
        return res
    p = res["payload"]
    out = {"agent": res["agent"], "from_cache": res["from_cache"],
           "proposals": [{"key": x["key"], "value": x.get("value"), "verification": x.get("verification")} for x in res["proposals"] if "key" in x],
           "suspicious_content_removed": bool(p.get("suspicious_fields"))}
    if kind == "regulatory":
        out.update(zoning_code=p.get("zoning_code"), summary=p.get("zoning_summary"), missing=p.get("missing", [])[:5])
    elif kind == "market":
        out.update(comparables=len(p.get("comparables", [])), price_stats=(p.get("summary") or {}).get("stats"))
    elif kind == "cost":
        out.update(benchmarks=[{"item": b["item"], "value": b.get("value"), "unit": b["unit"]} for b in p.get("benchmarks", [])][:6])
    elif kind == "financing":
        out.update(rates=[{"item": r["item"], "value_pct": r.get("value_pct"), "kind": r["kind"]} for r in p.get("rates", [])][:6])
    else:
        out.update(benchmarks=[{"item": b["item"], "value": b.get("value"), "unit": b["unit"]} for b in p.get("benchmarks", [])][:8])
    out["caveats"] = p.get("caveats", [])[:3]
    return out
