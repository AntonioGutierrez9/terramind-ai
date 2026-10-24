"""Improvement advisor: tests concrete levers on the full model and ranks them by impact. Deterministic.

Each lever is a change a developer can actually make (negotiate land, phase payments, value-engineer, resequence sales,
re-mix units, use permitted capacity, adjust leverage, add sustainability measures...). For every lever the engine is
re-run, so the impact on equity IRR, profit, NPV and peak equity is computed, not guessed. Issues (noncompliance,
covenant breaches, funding gaps, returns below the hurdle) are detected and levers that fix them are flagged.
The LLM only explains and prioritizes this list (app/agents/advisor_agent); it never invents the numbers.
"""

from __future__ import annotations

from .analysis import optimize_unit_mix
from .model import g, run_model
from .registry import model_mode

KEYS = ("equity_irr", "project_irr", "profit", "net_margin", "npv", "peak_equity", "funding_gap", "moic")


def _metrics(r: dict) -> dict | None:
    return {k: r["metrics"].get(k) for k in KEYS} if r.get("status") == "ok" else None


def _issues(r: dict, a: dict) -> list[dict]:
    out = []
    if r.get("status") != "ok":
        return [{"kind": "incomplete", "detail": "The model is incomplete: " + ", ".join(r.get("missing_labels") or r.get("missing") or [])}]
    m = r["metrics"]
    for c in r["compliance"]:
        out.append({"kind": "compliance", "detail": c["detail"]})
    for c in r["covenants"]:
        if not c["ok"]:
            out.append({"kind": "covenant", "detail": f"{c['name']}: {c['actual']:.1f} vs limit {c['limit']:.1f}"})
    if m["funding_gap"] > 1:
        out.append({"kind": "funding_gap", "detail": f"Funding gap of {m['funding_gap']:,.0f}"})
    hurdle = g(a, "val.equity_discount_rate_pct") / 100
    if m["equity_irr"] is not None and m["equity_irr"] < hurdle:
        out.append({"kind": "below_hurdle", "detail": f"Equity IRR {m['equity_irr'] * 100:.1f}% is below the {hurdle * 100:.0f}% hurdle"})
    return out


def recommend(profile: dict, a: dict, comps_stats: dict | None = None, top: int = 10) -> dict:
    base = run_model(profile, a)
    issues = _issues(base, a)
    if base.get("status") != "ok":
        return {"status": "incomplete", "issues": issues, "levers": []}
    bm = _metrics(base)
    mode = model_mode(profile)
    levers: list[dict] = []

    def lever(id_, title, category, changes, risk, note, fixes=None):
        levers.append({"id": id_, "title": title, "category": category, "changes": changes, "risk": risk, "note": note,
                       "fixes": fixes or []})

    land = a.get("site.land_price")
    if land:
        lever("land_negotiation", "Negotiate the land price down 10%", "Land", [{"key": "site.land_price", "value": round(land * 0.9)}],
              "medium", "Use the max-land-price solver and the sensitivity results as negotiation evidence.")
        if not a.get("land_payments"):
            lever("land_installments", "Pay the land in installments (30% at closing, 70% at month 6)", "Land",
                  [{"key": "land_payments", "value": [{"month": 0, "pct": 30}, {"month": 6, "pct": 70}]}], "low",
                  "Common in CDMX land deals; defers equity and raises IRR. Needs the seller's agreement and a guarantee.")
    hard = a.get("cost.hard_per_area")
    if hard:
        lever("value_engineering", "Value-engineer hard costs by 5%", "Cost", [{"key": "cost.hard_per_area", "value": round(hard * 0.95)}],
              "medium", "Re-bid structure / MEP packages, standardize finishes, optimize parking geometry.")
    cm = a.get("sch.construction_months")
    if cm and cm >= 15:
        lever("faster_construction", "Shorten construction by 3 months", "Schedule", [{"key": "sch.construction_months", "value": int(cm - 3)}],
              "medium", "Fast-track design and permits, early procurement, more shifts; check contractor capacity.")
    if mode == "sale":
        p = a.get("rev.price_per_area")
        if p:
            risk, note = "medium", "Only if comparables support it (finishes, amenities, views)."
            if comps_stats and comps_stats.get("p75") and p * 1.05 > comps_stats["p75"]:
                risk, note = "high", f"A 5% increase would put the price above the 75th percentile of researched comps ({comps_stats['p75']:,.0f}/m²)."
            lever("price_increase", "Raise the base sale price 5%", "Pricing", [{"key": "rev.price_per_area", "value": round(p * 1.05)}], risk, note)
        if (a.get("rev.discount_pct") or 0) > 0:
            lever("no_discounts", "Eliminate average discounts", "Pricing", [{"key": "rev.discount_pct", "value": 0}], "medium",
                  "Replace discounts with payment-plan incentives; tighten the pricing policy.")
        if (a.get("rev.closing_pct") or 0) > 50:
            lever("payment_plan", "Collect more before delivery (20% deposit, 30% installments, 50% at closing)", "Sales",
                  [{"key": "rev.deposit_pct", "value": 20}, {"key": "rev.installments_pct", "value": 30}, {"key": "rev.closing_pct", "value": 50}],
                  "medium", "Lowers peak equity and debt; may slow presales if buyers can't fund more upfront.")
        off = int(g(a, "rev.sales_start_offset", 0))
        if off > -9:
            fixes = [i["detail"] for i in issues if i["kind"] == "covenant" and "Presales" in i["detail"]]
            lever("earlier_presales", "Start presales 3 months earlier", "Sales", [{"key": "rev.sales_start_offset", "value": off - 3}], "low",
                  "Launch the sales office during permitting; requires the project's commercial registration.", fixes)
        if not a.get("sales_phases") and a.get("rev.absorption_per_month"):
            ab = float(a["rev.absorption_per_month"])
            lever("launch_campaign", "Run a launch campaign (double sales pace for the first 3 months)", "Sales",
                  [{"key": "sales_phases", "value": [{"name": "Launch campaign", "anchor": "sales_start", "offset": 0, "months": 3,
                                                       "units_per_month": round(ab * 2, 1)}]}],
                  "medium", "Broker launch event, early-bird price list; budget extra marketing.")
        if a.get("unit_mix") and len(a["unit_mix"]) <= 4:
            mix = optimize_unit_mix(profile, a, "equity_irr", step=10, top=1)
            if mix.get("status") == "ok" and mix["top"]:
                best = mix["top"][0]
                cur = mix.get("current", {}).get("equity_irr")
                if cur is not None and best["equity_irr"] is not None and best["equity_irr"] > cur + 0.003:
                    new_mix = [{**t, "share_pct": float(s)} for t, s in zip(a["unit_mix"], best["shares"])]
                    concentrated = max(best["shares"]) >= 70
                    lever("unit_mix", "Re-mix units: " + ", ".join(f"{t['name']} {s}%" for t, s in zip(a["unit_mix"], best["shares"])),
                          "Design", [{"key": "unit_mix", "value": new_mix}], "high" if concentrated else "medium",
                          ("Concentrates the product in one unit type: absorption is held constant in the model, so validate demand "
                           "with a market study before adopting it." if concentrated else
                           "Optimizer result with constant total absorption; validate demand for the dominant unit type."))
    else:
        rent = a.get("rent.rent_per_area_month")
        if rent:
            lever("rent_increase", "Raise rents 5%", "Pricing", [{"key": "rent.rent_per_area_month", "value": round(rent * 1.05, 2)}], "medium",
                  "Only with amenity / service upgrades the market pays for.")
        if (a.get("rent.vacancy_pct") or 0) > 3:
            lever("lower_vacancy", "Cut stabilized vacancy by 2 points", "Operations", [{"key": "rent.vacancy_pct", "value": a["rent.vacancy_pct"] - 2}],
                  "medium", "Professional leasing, longer leases, resident retention program.")
        if (a.get("rent.opex_pct_egi") or 0) > 20:
            lever("lower_opex", "Reduce operating expenses by 3 points of EGI", "Operations",
                  [{"key": "rent.opex_pct_egi", "value": a["rent.opex_pct_egi"] - 3}], "medium", "Energy efficiency, procurement, tech-enabled management.")

    # design capacity / compliance
    st, mx = a.get("dev.stories"), a.get("reg.max_stories")
    if st and mx and st > mx:
        lever("fix_stories", f"Reduce stories from {st} to the permitted {mx}", "Compliance", [{"key": "dev.stories", "value": int(mx)}], "low",
              "Required: the current design exceeds the researched legal limit.", [i["detail"] for i in issues if i["kind"] == "compliance"])
    elif st and mx and st < mx:
        lever("use_capacity", f"Use the permitted height: {mx} stories instead of {st}", "Design", [{"key": "dev.stories", "value": int(mx)}],
              "medium", "Check FAR, density and parking limits, structure cost and market depth for the extra units.")

    # leverage
    ltc, cov = a.get("fin.senior_ltc_pct"), g(a, "fin.max_ltc_covenant_pct")
    has_debt_issue = any(i["kind"] in ("funding_gap", "covenant") for i in issues)
    if ltc is not None and cov and ltc < cov - 5 and not has_debt_issue:
        lever("more_leverage", f"Increase senior debt to {cov - 5:g}% LTC", "Financing", [{"key": "fin.senior_ltc_pct", "value": cov - 5}], "high",
              "Raises equity IRR but adds interest, presale requirements and downside risk. Material change.")
    if ltc and has_debt_issue:
        lever("less_leverage", f"Reduce senior debt to {max(ltc - 10, 0):g}% LTC", "Financing", [{"key": "fin.senior_ltc_pct", "value": max(ltc - 10, 0)}],
              "low", "Eases covenants and maturity pressure; needs more equity.", [i["detail"] for i in issues if i["kind"] in ("funding_gap", "covenant")])

    # sustainability: measures that improve developer returns but are off
    ms = a.get("sustainability_measures") or []
    if ms:
        good = []
        for m_ in ms:
            if m_.get("enabled"):
                continue
            trial = run_model(profile, a, {"sustainability_measures": [{**x, "enabled": x.get("enabled") or x["key"] == m_["key"]} for x in ms]})
            if trial.get("status") == "ok" and (trial["metrics"]["equity_irr"] or 0) > (bm["equity_irr"] or 0) + 1e-4:
                good.append(m_["key"])
        if good:
            names = [x["name"] for x in ms if x["key"] in good]
            lever("sustainability", "Enable sustainability measures that pay for themselves: " + ", ".join(names), "Sustainability",
                  [{"key": "sustainability_measures", "value": [{**x, "enabled": x.get("enabled") or x["key"] in good} for x in ms]}], "low",
                  "Each measure raises developer returns on its own in the model and cuts emissions.")

    # evaluate every lever on the full model
    for lv in levers:
        ov = {c["key"]: c["value"] for c in lv["changes"]}
        r = run_model(profile, a, ov)
        lv["after"] = _metrics(r)
        lv["status"] = r.get("status")
        if lv["after"]:
            lv["delta"] = {k: (lv["after"][k] - bm[k]) if lv["after"][k] is not None and bm[k] is not None else None for k in KEYS}
            lv["remaining_issues"] = [i["detail"] for i in _issues(r, a)]
            lv["compliant_after"] = r["compliant"]
            lv["covenant_breaches_after"] = [c["name"] for c in r["covenants"] if not c["ok"]]
    valid = [lv for lv in levers if lv.get("after")]
    valid.sort(key=lambda x: (bool(x["fixes"]), x["delta"]["equity_irr"] or -9), reverse=True)

    # a combined package: top 3 positive levers touching different inputs
    package, used = [], set()
    for lv in valid:
        keys = {c["key"] for c in lv["changes"]}
        if (lv["delta"]["equity_irr"] or 0) > 0 and not keys & used and lv["risk"] != "high":
            package.append(lv)
            used |= keys
        if len(package) == 3:
            break
    pkg = None
    if package:
        ov = {c["key"]: c["value"] for lv in package for c in lv["changes"]}
        r = run_model(profile, a, ov)
        if r.get("status") == "ok":
            pm = _metrics(r)
            pkg = {"lever_ids": [lv["id"] for lv in package], "titles": [lv["title"] for lv in package], "changes": [c for lv in package for c in lv["changes"]],
                   "after": pm, "delta": {k: (pm[k] - bm[k]) if pm[k] is not None and bm[k] is not None else None for k in KEYS}}
    return {"status": "ok", "base": bm, "issues": issues, "levers": valid[:top], "package": pkg,
            "note": "Each lever was tested on the full model; impacts are computed by the engine, not estimated by AI."}
