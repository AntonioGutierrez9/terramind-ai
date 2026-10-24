"""Glue between the store and the engine: cached model results, analysis, assumption table."""

from __future__ import annotations

import statistics
from functools import lru_cache
from typing import Any

from engine import analysis, asset_mgmt, sustainability
from engine.model import run_model
from engine.registry import REGISTRY, SECTIONS, is_ground_up, model_mode

from . import store
from .db import dumps

KEY_METRICS = ["units", "saleable_area", "tdc", "financing_cost", "total_cost", "gdv", "revenue", "profit", "gross_margin",
               "net_margin", "profit_on_cost", "project_irr", "equity_irr", "moic", "npv", "equity_npv", "peak_funding",
               "peak_equity", "equity_contributed", "senior_commitment", "peak_debt", "ltc", "ltv", "dscr", "cash_on_cash",
               "funding_gap", "maturity_shortfall", "duration_months", "delivery_month", "sellout_months", "stabilized_noi",
               "yield_on_cost", "investor_irr", "sponsor_irr", "investor_moic", "sponsor_moic", "senior_rate_pct", "exit_value"]


@lru_cache(maxsize=64)
def _cached_model(profile_json: str, assumptions_json: str) -> dict:
    import json
    return run_model(json.loads(profile_json), json.loads(assumptions_json))


def results(project: dict) -> dict:
    return _cached_model(dumps(project["profile"]), dumps(project["assumptions"]))


def key_metrics(res: dict) -> dict:
    if res.get("status") != "ok":
        return {}
    return {k: res["metrics"].get(k) for k in KEY_METRICS if res["metrics"].get(k) is not None}


@lru_cache(maxsize=32)
def _cached_analysis(profile_json: str, assumptions_json: str, scenarios_json: str) -> dict:
    import json
    p, a, sc = json.loads(profile_json), json.loads(assumptions_json), json.loads(scenarios_json)
    base = run_model(p, a)
    if base["status"] != "ok":
        return {"status": base["status"], "missing": base.get("missing", [])}
    return {
        "status": "ok",
        "scenarios": analysis.run_scenarios(p, a, sc),
        "tornado": analysis.tornado(p, a, "equity_irr"),
        "tornado_profit": analysis.tornado(p, a, "profit"),
        "heatmap": analysis.heatmap(p, a, "equity_irr"),
        "breakeven": analysis.breakeven(p, a),
    }


def scenario_defs(project: dict) -> list[dict]:
    saved = [{"name": v["name"], "changes": v["payload"], "id": v["id"]} for v in store.list_variants(project["id"], "scenario")]
    return analysis.default_scenarios(project["profile"]) + saved


def full_analysis(project: dict) -> dict:
    return _cached_analysis(dumps(project["profile"]), dumps(project["assumptions"]), dumps(scenario_defs(project)))


def summarize_for_llm(project: dict) -> dict:
    """Compact project snapshot for the Investment Manager (keeps prompts small)."""
    res = results(project)
    a = project["assumptions"]
    filled = {k: a[k] for k in REGISTRY if a.get(k) is not None}
    pending_props = [k for k, m in project["meta"].items() if isinstance(m, dict) and (m.get("proposal") or {}).get("status") == "pending"]
    snap = {
        "project_id": project["id"], "name": project["name"], "status": project["status"],
        "profile": {k: project["profile"].get(k) for k in ("country", "city", "neighborhood", "address", "currency", "area_unit",
                                                             "property_type", "strategy", "business_model", "horizon_years")},
        "model_mode": model_mode(project["profile"]),
        "assumptions": filled,
        "unit_mix": a.get("unit_mix"),
        "sustainability_enabled": [m["key"] for m in a.get("sustainability_measures") or [] if m.get("enabled")],
        "model_status": res.get("status"),
        "missing_inputs": res.get("missing", []),
        "pending_research_proposals": pending_props,
        "pending_confirmations": [p["id"] for p in store.list_pending(project["id"])],
        "documents": [{"document_id": d["id"], "filename": d["filename"], "type": (d["analysis"] or {}).get("doc_type")}
                      for d in store.list_documents(project["id"])[:10]],
    }
    if res.get("status") == "ok":
        m = res["metrics"]
        snap["metrics"] = {k: (round(v, 4) if isinstance(v, float) and abs(v) < 100 else (round(v) if isinstance(v, float) else v))
                           for k, v in key_metrics(res).items()}
        snap["covenant_breaches"] = [c["name"] for c in res["covenants"] if not c["ok"]]
        snap["compliance_issues"] = [i["detail"] for i in res["compliance"]]
        snap["warnings"] = res["warnings"]
    return snap


def assumption_table(project: dict) -> list[dict]:
    a, meta = project["assumptions"], project["meta"]
    mode = model_mode(project["profile"])
    ground_up = is_ground_up(project["profile"])
    res = results(project)
    missing = set(res.get("missing", []))
    rows = []
    for key, spec in REGISTRY.items():
        if spec["section"] == "rent" and mode != "rent":
            continue
        if spec["section"] == "rev" and mode != "sale":
            continue
        if spec["section"] == "reg" and not ground_up:
            continue
        m = meta.get(key) or {}
        rows.append({
            "key": key, "label": spec["label"], "section": spec["section"], "section_label": SECTIONS[spec["section"]],
            "value": a.get(key), "unit": spec["unit"], "kind": spec["kind"], "choices": spec["choices"],
            "min": spec["min"], "max": spec["max"], "typical": spec["typical"], "help": spec["help"],
            "material": spec["material"], "regulatory": spec["regulatory"], "suggested": spec["suggested"],
            "required": mode in spec["required"], "missing": key in missing,
            "source": m.get("source") or ("default (unverified)" if a.get(key) is None and spec["suggested"] is not None else None),
            "status": m.get("status"), "verification": m.get("verification"), "confidence": m.get("confidence"),
            "source_url": m.get("source_url"), "source_title": m.get("source_title"), "note": m.get("note"),
            "updated_at": m.get("updated_at"), "updated_by": m.get("updated_by"),
            "noncompliant_override": m.get("noncompliant_override", False), "override_of": m.get("override_of"),
            "proposal": m.get("proposal") if (m.get("proposal") or {}).get("status") == "pending" else None,
        })
    return rows


def calculated_rows(res: dict) -> list[dict]:
    """Outputs shown in the control center as 'calculated' (never editable)."""
    if res.get("status") != "ok":
        return []
    m = res["metrics"]
    labels = {"units": "Units", "saleable_area": "Saleable area", "tdc": "Total development cost", "total_cost": "Total cost incl. financing",
              "gdv": "Gross development value", "profit": "Development profit", "equity_irr": "Equity IRR", "project_irr": "Project IRR",
              "moic": "MOIC", "npv": "NPV", "peak_equity": "Peak equity"}
    return [{"key": f"calc.{k}", "label": v, "value": m.get(k), "source": "calculated"} for k, v in labels.items()]


def comps_summary(comps: list[dict]) -> dict:
    """Deterministic price statistics from comparables (the LLM never computes these)."""
    rows = []
    for c in comps:
        price, size = c.get("price"), c.get("size")
        ppa = price / size if price and size and size > 0 else None
        rows.append({**c, "price_per_area": ppa})
    inc = [r["price_per_area"] for r in rows if r["price_per_area"] and not r.get("excluded")]
    stats = None
    if inc:
        stats = {"n": len(inc), "median": statistics.median(inc), "mean": statistics.fmean(inc), "min": min(inc), "max": max(inc),
                 "p25": statistics.quantiles(inc, n=4)[0] if len(inc) >= 4 else min(inc),
                 "p75": statistics.quantiles(inc, n=4)[2] if len(inc) >= 4 else max(inc)}
    return {"rows": rows, "stats": stats}


def asset_analysis(project: dict) -> dict:
    return asset_mgmt.analyze(project["profile"], project["assumptions"], store.list_actuals(project["id"]), results(project))


def sustainability_eval(project: dict) -> dict:
    a = project["assumptions"]
    return sustainability.evaluate(project["profile"], a, a.get("sustainability_measures") or [])


def portfolio(owner: str | None) -> dict:
    items = []
    for p in store.list_projects(owner):
        res = results(p)
        am = None
        if store.list_actuals(p["id"]) and res.get("status") == "ok":
            am = asset_analysis(p)
        items.append({"project": {"id": p["id"], "name": p["name"], **p["profile"], "status": p["status"],
                                  "in_portfolio": p["in_portfolio"]}, "result": res, "am": am})
    summary = asset_mgmt.portfolio_summary(items)
    alerts = []
    for it in items:
        for a in (it["am"] or {}).get("alerts", []):
            alerts.append({**a, "project_id": it["project"]["id"], "project": it["project"]["name"]})
        r = it["result"]
        if r.get("status") == "ok":
            for c in r["covenants"]:
                if not c["ok"] and not it["am"]:
                    alerts.append({"level": "red", "area": "Covenant", "message": f"{c['name']}: {c['actual']:.1f} vs {c['limit']:.1f}",
                                   "project_id": it["project"]["id"], "project": it["project"]["name"]})
            if not r["compliant"]:
                alerts.append({"level": "amber", "area": "Zoning", "message": "Scenario exceeds researched legal limits (potentially noncompliant).",
                               "project_id": it["project"]["id"], "project": it["project"]["name"]})
    return {**summary, "alerts": alerts,
            "projects": [{**it["project"], "metrics": key_metrics(it["result"]), "model_status": it["result"].get("status"),
                          "alerts": len((it["am"] or {}).get("alerts", []))} for it in items]}


def clear_caches() -> None:
    _cached_model.cache_clear()
    _cached_analysis.cache_clear()


def describe_change_effect(before: dict, after: dict) -> list[dict]:
    """Key metric deltas between two run_model results (used in chat tool summaries)."""
    if before.get("status") != "ok" or after.get("status") != "ok":
        return []
    out = []
    for k in ("total_cost", "gdv", "profit", "equity_irr", "project_irr", "moic", "npv", "peak_equity"):
        b, a = before["metrics"].get(k), after["metrics"].get(k)
        if b is None or a is None:
            continue
        if abs(a - b) > (1e-6 if abs(b) < 10 else 1):
            out.append({"metric": k, "before": b, "after": a})
    return out


def any_value(x: Any) -> Any:
    return x
