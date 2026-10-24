"""Asset management: underwriting vs actuals, reforecast and early-warning alerts.

Actuals are monthly rows: {month, cost, units_sold, avg_price_per_area, collections, debt_balance, progress_pct}
(cost / units / collections are per-month amounts; progress_pct and debt_balance are end-of-month levels).

Reforecast method (transparent, deterministic):
  cost factor     = actual development cost to date / underwritten cost to date (land excluded), applied to hard costs
  absorption      = actual net units sold per month since sales started
  price factor    = actual average price per area / underwritten effective price per area
  schedule delay  = (planned progress − actual progress) × construction months, added to construction duration
The whole model is then re-run, so IRR, MOIC, peak equity, covenants and the funding gap update together.
"""

from __future__ import annotations

from typing import Any

from .model import g, run_model
from .registry import model_mode


def _sum(rows, key, upto):
    return sum((r.get(key) or 0) for r in rows if r["month"] <= upto)


def analyze(profile: dict, a: dict, actuals: list[dict], underwriting: dict | None = None) -> dict:
    base = underwriting or run_model(profile, a)
    if base.get("status") != "ok":
        return {"status": "incomplete", "message": "Underwriting model is incomplete.", "missing": base.get("missing", [])}
    if not actuals:
        return {"status": "no_actuals", "underwriting": base["metrics"], "alerts": [], "message": "No actuals recorded yet."}
    actuals = sorted(actuals, key=lambda r: r["month"])
    as_of = actuals[-1]["month"]
    months = base["months"]
    sched = base["schedule"]
    plan = {
        "cost": sum(m["outflow"] - m["land_acq"] for m in months if m["month"] <= as_of),
        "units_sold": sum((m["units_sold"] or 0) for m in months if m["month"] <= as_of) if base["mode"] == "sale" else None,
        "collections": sum(m["inflow"] for m in months if m["month"] <= as_of),
        "debt_balance": next((m["senior_balance"] + m["mezz_balance"] for m in months if m["month"] == as_of), 0.0),
    }
    hard_total = sum(m["hard"] for m in months) or 1
    plan["progress_pct"] = sum(m["hard"] for m in months if m["month"] <= as_of) / hard_total * 100
    act = {
        "cost": _sum(actuals, "cost", as_of),
        "units_sold": _sum(actuals, "units_sold", as_of),
        "collections": _sum(actuals, "collections", as_of),
        "debt_balance": next((r.get("debt_balance") for r in reversed(actuals) if r.get("debt_balance") is not None), None),
        "progress_pct": next((r.get("progress_pct") for r in reversed(actuals) if r.get("progress_pct") is not None), None),
    }
    priced = [r for r in actuals if r.get("avg_price_per_area") and r.get("units_sold")]
    act["avg_price_per_area"] = (sum(r["avg_price_per_area"] * r["units_sold"] for r in priced) / sum(r["units_sold"] for r in priced)) if priced else None

    overrides: dict[str, Any] = {}
    drivers = []
    if plan["cost"] > 0 and act["cost"] > 0:
        cf = act["cost"] / plan["cost"]
        if abs(cf - 1) > 0.005 and a.get("cost.hard_per_area"):
            overrides["cost.hard_per_area"] = a["cost.hard_per_area"] * cf
            drivers.append({"driver": "Construction cost", "factor": cf, "detail": f"cost to date {act['cost']:,.0f} vs plan {plan['cost']:,.0f}"})
    if base["mode"] == "sale":
        start = sched.get("sales_start") or 1
        elapsed = as_of - start + 1
        if elapsed > 0 and act["units_sold"] is not None:
            pace = act["units_sold"] / elapsed
            planned_net = base["metrics"]["units"] / max(base["metrics"].get("sellout_months") or 1, 1)
            if pace > 0 and abs(pace / planned_net - 1) > 0.02:
                cancel = g(a, "rev.cancellation_pct") / 100
                overrides["rev.absorption_per_month"] = max(round(pace / (1 - cancel), 2), 0.1)
                drivers.append({"driver": "Sales pace", "factor": pace / planned_net,
                                "detail": f"{pace:.2f} net units/month vs plan {planned_net:.2f}"})
        if act["avg_price_per_area"]:
            esc = g(a, "rev.escalation_pct") / 100
            mid = (start + as_of) / 2
            plan_price = a["rev.price_per_area"] * (1 + esc) ** (mid / 12) * (1 - g(a, "rev.discount_pct") / 100)
            pf = act["avg_price_per_area"] / plan_price
            if abs(pf - 1) > 0.005:
                overrides["rev.price_per_area"] = a["rev.price_per_area"] * pf
                drivers.append({"driver": "Selling price", "factor": pf,
                                "detail": f"{act['avg_price_per_area']:,.0f}/area achieved vs {plan_price:,.0f} underwritten"})
    if act["progress_pct"] is not None and as_of > sched["construction_start"]:
        gap = plan["progress_pct"] - act["progress_pct"]
        delay = round(gap / 100 * sched["construction_months"])
        if delay >= 1:
            overrides["sch.construction_months"] = int(a["sch.construction_months"] + delay)
            drivers.append({"driver": "Schedule", "factor": None,
                            "detail": f"progress {act['progress_pct']:.0f}% vs planned {plan['progress_pct']:.0f}% → +{delay} months"})

    updated = run_model(profile, a, overrides)
    um = updated["metrics"] if updated.get("status") == "ok" else None
    bm = base["metrics"]

    alerts = []

    def alert(level, area, msg):
        alerts.append({"level": level, "area": area, "message": msg})

    var = lambda x, y: (x / y - 1) if y else None
    cost_var = var(act["cost"], plan["cost"])
    if cost_var is not None and cost_var > 0.05:
        alert("red" if cost_var > 0.10 else "amber", "Construction budget", f"Costs to date are {cost_var * 100:.1f}% over plan.")
    if base["mode"] == "sale" and plan["units_sold"]:
        sv = act["units_sold"] / plan["units_sold"]
        if sv < 0.85:
            alert("red" if sv < 0.70 else "amber", "Sales", f"Units sold are {sv * 100:.0f}% of plan ({act['units_sold']:.0f} vs {plan['units_sold']:.0f}).")
    if any(d["driver"] == "Selling price" and d["factor"] < 0.97 for d in drivers):
        alert("amber", "Pricing", "Achieved prices are more than 3% below underwriting.")
    if "sch.construction_months" in overrides:
        delay = overrides["sch.construction_months"] - a["sch.construction_months"]
        alert("red" if delay >= 4 else "amber", "Schedule", f"Construction is tracking ~{delay} months late.")
    if um:
        if um["funding_gap"] > 1:
            alert("red", "Liquidity", f"Updated forecast needs {um['funding_gap']:,.0f} of additional equity (funding gap).")
        if um["maturity_shortfall"] > 1:
            alert("red", "Debt maturity", "Senior loan is forecast to mature before it is repaid.")
        for c in updated["covenants"]:
            if not c["ok"]:
                alert("red", "Covenant", f"{c['name']}: {c['actual']:.2f} vs limit {c['limit']:.2f}.")
        mat = um.get("maturity_month")
        if mat is not None and 0 <= mat - as_of <= 6 and (act["debt_balance"] or plan["debt_balance"]) > 0:
            alert("amber", "Debt maturity", f"Senior loan matures in month {mat}, within 6 months of the latest actuals.")
        if bm["equity_irr"] is not None and um["equity_irr"] is not None and um["equity_irr"] < bm["equity_irr"] - 0.03:
            alert("amber", "Returns", f"Equity IRR fell from {bm['equity_irr'] * 100:.1f}% to {um['equity_irr'] * 100:.1f}%.")
    if act["debt_balance"] is not None and plan["debt_balance"] and act["debt_balance"] > plan["debt_balance"] * 1.10:
        alert("amber", "Debt", f"Debt balance {act['debt_balance']:,.0f} is >10% above plan {plan['debt_balance']:,.0f}.")

    compare_keys = ["total_cost", "gdv", "profit", "net_margin", "project_irr", "equity_irr", "moic", "peak_equity",
                    "npv", "duration_months", "funding_gap"]
    comparison = [{"metric": k, "underwriting": bm.get(k), "updated": um.get(k) if um else None} for k in compare_keys]
    return {
        "status": "ok", "as_of_month": as_of, "plan_to_date": plan, "actual_to_date": act,
        "variances": {"cost": cost_var, "collections": var(act["collections"], plan["collections"]),
                      "units_sold": var(act["units_sold"], plan["units_sold"]) if plan["units_sold"] else None},
        "drivers": drivers, "overrides": overrides, "comparison": comparison, "alerts": alerts,
        "underwriting": bm, "updated": um, "updated_months": updated.get("months") if um else None,
        "actuals": actuals,
    }


def portfolio_summary(items: list[dict]) -> dict:
    """items: [{project, result (run_model), am (analyze or None)}]"""
    rows, total = [], {"equity": 0.0, "debt": 0.0, "gdv": 0.0, "profit": 0.0, "distributions": 0.0, "total_cost": 0.0}
    by_area: dict[str, float] = {}
    by_type: dict[str, float] = {}
    for it in items:
        p, r = it["project"], it["result"]
        if r.get("status") != "ok":
            rows.append({"id": p["id"], "name": p["name"], "status": r.get("status")})
            continue
        m = (it.get("am") or {}).get("updated") or r["metrics"]
        alerts = (it.get("am") or {}).get("alerts", [])
        rows.append({"id": p["id"], "name": p["name"], "status": "ok", "neighborhood": p.get("neighborhood"),
                     "business_model": p.get("business_model"), "equity": m["equity_contributed"], "debt": m["peak_debt"],
                     "gdv": m["gdv"], "profit": m["profit"], "equity_irr": m["equity_irr"], "moic": m["moic"],
                     "red_alerts": sum(a["level"] == "red" for a in alerts), "amber_alerts": sum(a["level"] == "amber" for a in alerts)})
        total["equity"] += m["equity_contributed"]
        total["debt"] += m["peak_debt"]
        total["gdv"] += m["gdv"]
        total["profit"] += m["profit"]
        total["distributions"] += m["equity_distributed"]
        total["total_cost"] += m["total_cost"]
        key = p.get("neighborhood") or "Other"
        by_area[key] = by_area.get(key, 0) + m["equity_contributed"]
        by_type[p.get("business_model") or "other"] = by_type.get(p.get("business_model") or "other", 0) + m["equity_contributed"]
    eq = total["equity"] or 1
    return {"rows": rows, "totals": total,
            "weighted_moic": total["distributions"] / eq if total["equity"] else None,
            "concentration_by_area": {k: v / eq for k, v in by_area.items()},
            "concentration_by_model": {k: v / eq for k, v in by_type.items()}}
