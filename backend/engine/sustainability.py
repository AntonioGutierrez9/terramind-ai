"""Sustainability measures: lifecycle economics, developer impact and budget optimizer.

Each measure (all values are preliminary estimates unless marked verified):
  key, name, enabled, capex, life_years, maintenance_annual,
  energy_kwh_annual, water_m3_annual, co2_t_annual, savings_annual (currency, to the beneficiary),
  sale_premium_pct (price premium a developer can capture in for-sale), rent_premium_pct,
  status ("preliminary" | "verified"), source

Who benefits:
  build-to-sell  → operating savings go to the BUYER; the developer gets only a price premium (if any)
  build-to-rent  → savings lower opex (landlord) and any rent premium raises NOI
"""

from __future__ import annotations

from itertools import combinations
from typing import Any

from .finance import irr_monthly
from .model import run_model
from .registry import model_mode


def lifecycle(m: dict, discount_pct: float) -> dict:
    """Owner-of-the-asset view: capex today, net savings yearly over the useful life."""
    life = int(m.get("life_years") or 0)
    net = (m.get("savings_annual") or 0) - (m.get("maintenance_annual") or 0)
    flows = [-(m.get("capex") or 0)] + [net] * life
    r = discount_pct / 100
    lnpv = sum(cf / (1 + r) ** i for i, cf in enumerate(flows))
    payback = (m["capex"] / net) if net > 0 and m.get("capex") else None
    return {
        "lifecycle_npv": lnpv, "lifecycle_irr": irr_monthly(flows), "simple_payback_years": payback,
        "co2_t_life": (m.get("co2_t_annual") or 0) * life, "energy_mwh_life": (m.get("energy_kwh_annual") or 0) * life / 1000,
        "water_m3_life": (m.get("water_m3_annual") or 0) * life,
    }


def apply_measures(profile: dict, a: dict, measures: list[dict]) -> dict:
    """Overrides that replace the project's measure list (run_model applies enabled measures natively)."""
    return {"sustainability_measures": measures}


def evaluate(profile: dict, a: dict, measures: list[dict]) -> dict:
    """Per-measure lifecycle economics plus developer impact (full model with vs without)."""
    disc = a.get("val.discount_rate_pct") or 12
    measures = list(measures)
    base_a = {**a, "sustainability_measures": [{**m, "enabled": False} for m in measures]}
    base = run_model(profile, base_a)
    rows = []
    for m in measures:
        lc = lifecycle(m, disc)
        with_m = run_model(profile, base_a, apply_measures(profile, base_a, [{**x, "enabled": x["key"] == m["key"]} for x in measures]))
        dev = {}
        if base.get("status") == "ok" and with_m.get("status") == "ok":
            bm, wm = base["metrics"], with_m["metrics"]
            dev = {
                "delta_profit": wm["profit"] - bm["profit"],
                "delta_equity_irr": _delta(wm["equity_irr"], bm["equity_irr"]),
                "delta_project_irr": _delta(wm["project_irr"], bm["project_irr"]),
                "delta_npv": wm["npv"] - bm["npv"],
            }
        rows.append({**m, **lc, **dev, "beneficiary": "buyer" if model_mode(profile) == "sale" else "owner (landlord)"})
    combo = run_model(profile, base_a, apply_measures(profile, base_a, measures))
    return {
        "measures": rows,
        "base_metrics": base.get("metrics") if base.get("status") == "ok" else None,
        "with_enabled_metrics": combo.get("metrics") if combo.get("status") == "ok" else None,
        "beneficiary_note": (
            "Build-to-sell: operating savings accrue to buyers. The developer's return changes only through extra capex "
            "and any price premium buyers pay." if model_mode(profile) == "sale" else
            "Build-to-rent / hold: savings lower operating expenses and raise NOI and exit value for the owner."
        ),
    }


def optimize(profile: dict, a: dict, measures: list[dict], budget: float, objective: str = "co2") -> dict:
    """Best subset of measures within a capex budget (exhaustive for ≤ 12 measures).

    objective: "co2" (max lifetime CO2 avoided), "lifecycle_npv" (max owner NPV),
               "equity_irr" (max developer equity IRR, full model per subset).
    """
    disc = a.get("val.discount_rate_pct") or 12
    ms = measures[:12]
    lcs = [lifecycle(m, disc) for m in ms]
    candidates = []
    for k in range(0, len(ms) + 1):
        for idx in combinations(range(len(ms)), k):
            capex = sum(ms[i].get("capex") or 0 for i in idx)
            if capex > budget + 1e-6:
                continue
            candidates.append({
                "keys": [ms[i]["key"] for i in idx], "capex": capex,
                "co2_t_life": sum(lcs[i]["co2_t_life"] for i in idx),
                "lifecycle_npv": sum(lcs[i]["lifecycle_npv"] for i in idx),
            })
    if objective == "equity_irr":
        for c in candidates:
            sel = [{**m, "enabled": m["key"] in c["keys"]} for m in ms]
            r = run_model(profile, a, apply_measures(profile, a, sel + [{**m, "enabled": False} for m in measures[12:]]))
            c["equity_irr"] = r["metrics"]["equity_irr"] if r.get("status") == "ok" else None
        candidates.sort(key=lambda c: (c["equity_irr"] is not None, c["equity_irr"] or -9), reverse=True)
    else:
        field = {"co2": "co2_t_life", "lifecycle_npv": "lifecycle_npv"}.get(objective, "co2_t_life")
        candidates.sort(key=lambda c: (c[field], -c["capex"]), reverse=True)
    best = candidates[0] if candidates else None
    frontier = sorted(({"capex": c["capex"], "co2_t_life": c["co2_t_life"], "lifecycle_npv": c["lifecycle_npv"],
                        "keys": c["keys"]} for c in candidates), key=lambda c: c["capex"])
    return {"best": best, "objective": objective, "budget": budget, "evaluated": len(candidates), "frontier": frontier}


def _delta(x, y):
    return None if x is None or y is None else x - y
