"""Scenario, sensitivity and solver tools on top of run_model. All deterministic."""

from __future__ import annotations

import math
from itertools import product
from typing import Any

from .model import g, run_model
from .registry import REGISTRY, model_mode
from .validation import ValidationError, validate_value

METRIC_LABELS = {
    "equity_irr": "Equity IRR", "project_irr": "Project IRR", "profit": "Development profit",
    "net_margin": "Net margin", "npv": "NPV", "moic": "MOIC", "profit_on_cost": "Profit on cost",
    "peak_equity": "Peak equity",
}


# --------------------------------------------------------------------------- scenario changes
def apply_changes(a: dict, changes: list[dict]) -> dict:
    """Turn [{key, op: set|pct|add, value}] into validated overrides."""
    overrides: dict[str, Any] = {}
    for ch in changes or []:
        key, op, value = ch["key"], ch.get("op", "set"), ch["value"]
        if key not in REGISTRY:
            raise ValidationError(f"unknown variable '{key}'")
        cur = overrides.get(key, a.get(key, REGISTRY[key].get("suggested")))
        if op == "set":
            new = value
        elif cur is None:
            raise ValidationError(f"{REGISTRY[key]['label']} has no value to adjust")
        elif op == "pct":
            new = cur * (1 + float(value) / 100)
        elif op == "add":
            new = cur + float(value)
        else:
            raise ValidationError(f"unknown op '{op}'")
        if REGISTRY[key]["kind"] == "int" and new is not None:
            new = int(round(new))
        new, _ = validate_value(key, new)
        overrides[key] = new
    return overrides


def default_scenarios(profile: dict) -> list[dict]:
    if model_mode(profile) == "sale":
        return [
            {"name": "Base", "changes": []},
            {"name": "Upside", "changes": [
                {"key": "rev.price_per_area", "op": "pct", "value": 7.5},
                {"key": "rev.absorption_per_month", "op": "pct", "value": 25},
                {"key": "cost.hard_per_area", "op": "pct", "value": -5}]},
            {"name": "Downside", "changes": [
                {"key": "rev.price_per_area", "op": "pct", "value": -10},
                {"key": "rev.absorption_per_month", "op": "pct", "value": -30},
                {"key": "cost.hard_per_area", "op": "pct", "value": 10},
                {"key": "sch.construction_months", "op": "add", "value": 6},
                {"key": "fin.reference_rate_pct", "op": "add", "value": 2}]},
        ]
    return [
        {"name": "Base", "changes": []},
        {"name": "Upside", "changes": [
            {"key": "rent.rent_per_area_month", "op": "pct", "value": 7.5},
            {"key": "rent.exit_cap_pct", "op": "add", "value": -0.5},
            {"key": "cost.hard_per_area", "op": "pct", "value": -5}]},
        {"name": "Downside", "changes": [
            {"key": "rent.rent_per_area_month", "op": "pct", "value": -10},
            {"key": "rent.vacancy_pct", "op": "add", "value": 5},
            {"key": "rent.exit_cap_pct", "op": "add", "value": 1},
            {"key": "cost.hard_per_area", "op": "pct", "value": 10},
            {"key": "sch.construction_months", "op": "add", "value": 6},
            {"key": "fin.reference_rate_pct", "op": "add", "value": 2}]},
    ]


def run_scenarios(profile: dict, a: dict, scenarios: list[dict]) -> list[dict]:
    out = []
    for sc in scenarios:
        try:
            ov = apply_changes(a, [c for c in sc.get("changes", []) if c["key"] in REGISTRY and
                                   (c.get("op", "set") == "set" or a.get(c["key"], REGISTRY[c["key"]].get("suggested")) is not None)])
            r = run_model(profile, a, ov)
            out.append({"name": sc["name"], "changes": sc.get("changes", []), "status": r["status"],
                        "metrics": r.get("metrics"), "warnings": r.get("warnings", []), "missing": r.get("missing", [])})
        except ValidationError as exc:
            out.append({"name": sc["name"], "changes": sc.get("changes", []), "status": "invalid", "error": str(exc)})
    return out


# --------------------------------------------------------------------------- sensitivity
def _drivers(profile: dict, a: dict) -> list[tuple[str, str, str, float]]:
    """(label, key, op, shock) — shocks applied symmetrically (−/+)."""
    common = [("Hard cost ±10%", "cost.hard_per_area", "pct", 10),
              ("Construction ±6 months", "sch.construction_months", "add", 6),
              ("Land price ±10%", "site.land_price", "pct", 10)]
    if a.get("fin.reference_rate_pct") is not None and (a.get("fin.senior_ltc_pct") or 0) > 0:
        common.append(("Interest rate ±200 bp", "fin.reference_rate_pct", "add", 2))
    if model_mode(profile) == "sale":
        return [("Sale price ±10%", "rev.price_per_area", "pct", 10),
                ("Absorption ±25%", "rev.absorption_per_month", "pct", 25)] + common
    return [("Rent ±10%", "rent.rent_per_area_month", "pct", 10), ("Exit cap ±50 bp", "rent.exit_cap_pct", "add", 0.5),
            ("Vacancy ±5 pts", "rent.vacancy_pct", "add", 5), ("Opex ±5 pts", "rent.opex_pct_egi", "add", 5)] + common


def tornado(profile: dict, a: dict, metric: str = "equity_irr") -> dict:
    base = run_model(profile, a)
    if base["status"] != "ok":
        return {"status": base["status"], "missing": base.get("missing", [])}
    b = base["metrics"][metric]
    bars = []
    for label, key, op, shock in _drivers(profile, a):
        vals = {}
        for sign in (-1, 1):
            try:
                ov = apply_changes(a, [{"key": key, "op": op, "value": sign * shock}])
                r = run_model(profile, a, ov)
                vals[sign] = r["metrics"][metric] if r["status"] == "ok" else None
            except ValidationError:
                vals[sign] = None
        bars.append({"driver": label, "key": key, "low_input": vals[-1], "high_input": vals[1],
                     "spread": abs((vals[1] or 0) - (vals[-1] or 0)) if None not in vals.values() else 0})
    bars.sort(key=lambda x: x["spread"], reverse=True)
    return {"status": "ok", "metric": metric, "metric_label": METRIC_LABELS.get(metric, metric), "base": b, "bars": bars}


def heatmap(profile: dict, a: dict, metric: str = "equity_irr", steps=(-15, -7.5, 0, 7.5, 15)) -> dict:
    sale = model_mode(profile) == "sale"
    x_key = "rev.price_per_area" if sale else "rent.rent_per_area_month"
    y_key = "cost.hard_per_area"
    if a.get(y_key) is None:
        y_key = "cost.renovation_budget"
    grid = []
    for dy in steps:
        row = []
        for dx in steps:
            try:
                ov = apply_changes(a, [{"key": x_key, "op": "pct", "value": dx}, {"key": y_key, "op": "pct", "value": dy}])
                r = run_model(profile, a, ov)
                row.append(r["metrics"][metric] if r["status"] == "ok" else None)
            except ValidationError:
                row.append(None)
        grid.append(row)
    return {"metric": metric, "metric_label": METRIC_LABELS.get(metric, metric),
            "x_label": REGISTRY[x_key]["label"], "y_label": REGISTRY[y_key]["label"],
            "x_steps": list(steps), "y_steps": list(steps), "grid": grid}


# --------------------------------------------------------------------------- solver
def solve_for(profile: dict, a: dict, key: str, metric: str, target: float, lo: float | None = None,
              hi: float | None = None, tol: float = 1e-4) -> dict:
    """Find the value of `key` at which `metric` hits `target` (bisection; metric must be monotone).

    Example: max land price for an 18% equity IRR → key='site.land_price', metric='equity_irr', target=0.18.
    """
    if key not in REGISTRY:
        raise ValidationError(f"unknown variable '{key}'")
    cur = a.get(key)
    spec = REGISTRY[key]
    lo = lo if lo is not None else (spec["min"] if spec["min"] is not None else 0)
    hi = hi if hi is not None else (max(cur * 3, 1) if cur else spec["max"])

    def f(x):
        r = run_model(profile, a, {key: int(round(x)) if spec["kind"] == "int" else x})
        if r["status"] != "ok":
            return None
        v = r["metrics"].get(metric)
        return None if v is None else v - target

    flo, fhi = f(lo), f(hi)
    if flo is None or fhi is None:
        # shrink toward the current value until defined
        for _ in range(20):
            if flo is None:
                lo = (lo + (cur or hi)) / 2; flo = f(lo)
            if fhi is None:
                hi = (hi + (cur or lo)) / 2; fhi = f(hi)
            if flo is not None and fhi is not None:
                break
    if flo is None or fhi is None:
        return {"status": "undefined", "message": f"{METRIC_LABELS.get(metric, metric)} is undefined across the search range."}
    if flo * fhi > 0:
        return {"status": "not_reachable", "message":
                f"{METRIC_LABELS.get(metric, metric)} of {target:.4g} is not reachable for {spec['label']} between {lo:,.0f} and {hi:,.0f}.",
                "at_low": flo + target, "at_high": fhi + target}
    for _ in range(60):
        mid = (lo + hi) / 2
        fm = f(mid)
        if fm is None:
            break
        if flo * fm <= 0:
            hi, fhi = mid, fm
        else:
            lo, flo = mid, fm
        if abs(hi - lo) <= max(abs(mid) * tol, 1e-6):
            break
    sol = (lo + hi) / 2
    if spec["kind"] == "int":
        sol = int(round(sol))
    check = run_model(profile, a, {key: sol})
    return {"status": "ok", "key": key, "label": spec["label"], "unit": spec["unit"], "value": sol, "current": cur,
            "metric": metric, "target": target, "achieved": check["metrics"].get(metric) if check["status"] == "ok" else None}


def breakeven(profile: dict, a: dict) -> dict:
    sale = model_mode(profile) == "sale"
    key = "rev.price_per_area" if sale else "rent.rent_per_area_month"
    out = {"price_key": key, "label": REGISTRY[key]["label"], "current": a.get(key)}
    zero = solve_for(profile, a, key, "profit", 0.0, lo=(a.get(key) or 1) * 0.2, hi=(a.get(key) or 1) * 2)
    out["breakeven_profit"] = zero
    hurdle = g(a, "val.equity_discount_rate_pct") / 100
    out["hurdle_equity_irr"] = solve_for(profile, a, key, "equity_irr", hurdle, lo=(a.get(key) or 1) * 0.3, hi=(a.get(key) or 1) * 2)
    if sale:
        out["absorption_for_hurdle"] = solve_for(profile, a, "rev.absorption_per_month", "equity_irr", hurdle,
                                                 lo=0.2, hi=max((a.get("rev.absorption_per_month") or 1) * 5, 5))
    return out


# --------------------------------------------------------------------------- unit mix optimizer
def optimize_unit_mix(profile: dict, a: dict, metric: str = "equity_irr", step: int = 10, top: int = 8) -> dict:
    """Enumerate share combinations (in `step`% increments) of the current unit types through the full model."""
    types = a.get("unit_mix") or []
    if not types:
        return {"status": "incomplete", "message": "Define at least one unit type first."}
    k = len(types)
    if k > 5:
        return {"status": "invalid", "message": "The optimizer handles up to 5 unit types."}
    levels = range(0, 101, step)
    results = []
    for combo in product(levels, repeat=k):
        if sum(combo) != 100:
            continue
        mix = [{**t, "share_pct": float(s)} for t, s in zip(types, combo)]
        r = run_model(profile, a, {"unit_mix": mix})
        if r["status"] != "ok":
            continue
        m = r["metrics"]
        results.append({"shares": list(combo), "units": m["units"], "gdv": m["gdv"], "profit": m["profit"],
                        "equity_irr": m["equity_irr"], "npv": m["npv"], "sellout_months": m.get("sellout_months"),
                        "compliant": r["compliant"]})
    key = lambda x: (x.get(metric) is not None, x.get(metric) or -math.inf)
    results.sort(key=key, reverse=True)
    current = run_model(profile, a)
    return {"status": "ok", "metric": metric, "types": [t["name"] for t in types], "evaluated": len(results),
            "top": results[:top], "current": {"shares": [t["share_pct"] for t in types],
                                              **({kk: current["metrics"].get(kk) for kk in ("units", "gdv", "profit", "equity_irr", "npv", "sellout_months")}
                                                 if current["status"] == "ok" else {})},
            "note": "Total absorption (units/month) is held constant, so mixes with more, smaller units take longer to sell out."}
