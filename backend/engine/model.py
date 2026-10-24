"""Deterministic monthly development pro forma.

run_model(profile, assumptions) -> dict with design, budget, monthly series,
capital stack, metrics, covenants, waterfall and warnings.

Timing (end-of-month convention, t = 0 is land closing):
  months 1..P              pre-development (design, permits)          P = sch.predev_months
  months P+1..P+C          construction (S-curve hard costs)          C = sch.construction_months
  month  D = P+C           delivery
  sale mode: presales start at P + rev.sales_start_offset (>= 1), collections end at last closing
  rent mode: lease-up after delivery, exit at D + 12 * hold_years

No number here comes from a language model. Missing inputs return status "incomplete".
"""

from __future__ import annotations

import math
from typing import Any

from .finance import annualize, irr_monthly, monthly_rate, nominal_monthly, npv, payment, s_curve
from .registry import DEFAULT_HARD_COST_SPLIT, REGISTRY, is_ground_up, model_mode
from .custom_vars import price_multiplier
from .validation import compliance_issues, missing_inputs

FIN_ITERATIONS = 8


def g(a: dict, key: str, default: float | None = None) -> Any:
    """Assumption value, falling back to the registry's suggested default, then `default`."""
    v = a.get(key)
    if v is None:
        v = REGISTRY.get(key, {}).get("suggested")
    return default if v is None else v


# --------------------------------------------------------------------------- design
def compute_design(profile: dict, a: dict) -> dict:
    ground_up = is_ground_up(profile)
    land = float(a.get("site.land_area") or 0)
    d: dict[str, Any] = {"land_area": land, "ground_up": ground_up}
    unit_mix = a.get("unit_mix") or []

    if not ground_up:
        leasable = float(a.get("dev.existing_rentable_area") or 0)
        d.update(gba_above=leasable / max(g(a, "dev.efficiency_pct") / 100, 0.01), saleable=leasable,
                 footprint=None, units=0, unit_types=[], below_area=0.0, parking_spaces=a.get("dev.parking_spaces") or 0,
                 max_far_area=None, max_coverage_area=None, max_units_density=None, gba_above_requested=0.0,
                 terrace_area=0.0, capacity_gba=None)
        return d

    open_pct = float(a.get("reg.min_open_area_pct") or 0)
    max_cov_area = land * (1 - open_pct / 100)
    max_far = a.get("reg.max_far")
    if max_far is None and a.get("reg.max_stories") is not None:
        max_far = a["reg.max_stories"] * (1 - open_pct / 100)
    max_far_area = land * max_far if max_far is not None else None
    footprint = float(a.get("dev.footprint") or max_cov_area)
    stories = int(a.get("dev.stories") or 0)
    gba_req = footprint * stories
    amenity = float(g(a, "dev.amenity_area", 0))
    eff = g(a, "dev.efficiency_pct") / 100
    saleable = max(gba_req - amenity, 0) * eff

    types, units, sold_area, terrace_area = [], 0, 0.0, 0.0
    for t in unit_mix:
        n = int(math.floor(saleable * t["share_pct"] / 100 / t["size"] + 1e-9))
        types.append({**t, "units": n, "area": n * t["size"]})
        units += n
        sold_area += n * t["size"]
        terrace_area += n * (t.get("terrace") or 0)

    spaces = a.get("dev.parking_spaces")
    if spaces is None and a.get("reg.parking_min_per_unit") is not None:
        spaces = int(math.ceil(a["reg.parking_min_per_unit"] * units))
    spaces = int(spaces or 0)
    below_area = spaces * g(a, "dev.parking_area_per_space", 28) if spaces else 0.0
    levels_needed = math.ceil(below_area / (land * 0.95)) if land and below_area else 0

    max_units_density = None
    if a.get("reg.min_land_per_unit"):
        max_units_density = int(math.floor(land / a["reg.min_land_per_unit"]))

    d.update(
        open_area_pct=open_pct, max_coverage_area=max_cov_area, max_far=max_far, max_far_area=max_far_area,
        capacity_gba=max_far_area, footprint=footprint, stories=stories, gba_above_requested=gba_req,
        gba_above=gba_req, amenity_area=amenity, efficiency_pct=eff * 100, saleable=saleable,
        sold_area=sold_area, unsold_remainder=saleable - sold_area, unit_types=types, units=units,
        terrace_area=terrace_area, parking_spaces=spaces, below_area=below_area,
        levels_below_needed=levels_needed, max_units_density=max_units_density,
        gba_total=gba_req + below_area, far_used=gba_req / land if land else None,
    )
    return d


# --------------------------------------------------------------------------- sustainability
def green_totals(a: dict) -> dict:
    """Totals of the ENABLED sustainability measures (see engine/sustainability.py)."""
    on = [m for m in (a.get("sustainability_measures") or []) if m.get("enabled")]
    return {
        "count": len(on), "capex": sum(float(m.get("capex") or 0) for m in on),
        "sale_premium_pct": sum(float(m.get("sale_premium_pct") or 0) for m in on),
        "rent_premium_pct": sum(float(m.get("rent_premium_pct") or 0) for m in on),
        "net_savings_annual": sum(float(m.get("savings_annual") or 0) - float(m.get("maintenance_annual") or 0) for m in on),
        "co2_t_annual": sum(float(m.get("co2_t_annual") or 0) for m in on),
    }


# --------------------------------------------------------------------------- schedules
def anchor_month(anchor: str | None, offset: float | int | None, marks: dict) -> int:
    """Resolve a schedule anchor (closing / sales_start / construction_start / delivery) plus an offset to a month index."""
    base = marks.get(anchor or "closing", 0)
    return max(0, int(round(base + (offset or 0))))


def _phase_value(phases: list[dict], t: int, marks: dict, field: str):
    for ph in phases:
        s = anchor_month(ph.get("anchor"), ph.get("offset"), marks)
        if s <= t < s + int(ph.get("months") or 0):
            return ph.get(field)
    return None


def curve_weights(kind: str, n: int) -> list[float]:
    if n <= 0:
        return []
    if kind == "linear":
        return [1 / n] * n
    if kind in ("front_loaded", "back_loaded"):
        raw = [(n - i) for i in range(n)] if kind == "front_loaded" else [(i + 1) for i in range(n)]
        tot = sum(raw)
        return [r / tot for r in raw]
    return s_curve(n)


# --------------------------------------------------------------------------- helpers
def _add(arr: list[float], t: int, value: float) -> None:
    if t >= len(arr):
        arr.extend([0.0] * (t + 1 - len(arr)))
    arr[t] += value


def _spread(arr: list[float], start: int, n: int, total: float, weights: list[float] | None = None) -> None:
    """Spread total over months start..start+n-1 (weights sum to 1)."""
    if n <= 0:
        _add(arr, start, total)
        return
    w = weights or [1 / n] * n
    for i in range(n):
        _add(arr, start + i, total * w[i])


def _pad(*arrs: list[float], length: int) -> None:
    for arr in arrs:
        if len(arr) < length:
            arr.extend([0.0] * (length - len(arr)))


# --------------------------------------------------------------------------- revenue
def _sale_revenue(a: dict, design: dict, con_start: int, delivery: int) -> dict:  # noqa: C901
    P = float(a["rev.price_per_area"]) * (1 + green_totals(a)["sale_premium_pct"] / 100) * price_multiplier(a, "sale")
    floor_prem = g(a, "rev.floor_view_premium_pct") / 100
    terrace_val = g(a, "rev.terrace_value_pct") / 100
    discount = g(a, "rev.discount_pct") / 100
    esc = g(a, "rev.escalation_pct") / 100
    cancel = g(a, "rev.cancellation_pct") / 100
    dep, inst, clo = (g(a, k) / 100 for k in ("rev.deposit_pct", "rev.installments_pct", "rev.closing_pct"))
    comm = g(a, "rev.commission_pct") / 100
    mkt = g(a, "rev.marketing_pct") / 100

    units_total = design["units"]
    gross_value = 0.0
    for t in design["unit_types"]:
        unit_price = t["size"] * P * (1 + t.get("premium_pct", 0) / 100) * (1 + floor_prem) + (t.get("terrace") or 0) * P * terrace_val
        t["unit_price"] = unit_price
        t["price_per_area_effective"] = unit_price / t["size"]
        gross_value += unit_price * t["units"]
    avg_price = gross_value / units_total if units_total else 0.0

    base_abs = float(a["rev.absorption_per_month"])
    net_abs = base_abs * (1 - cancel)
    start = max(1, con_start + int(g(a, "rev.sales_start_offset", 0)))
    marks = {"closing": 0, "sales_start": start, "construction_start": con_start, "delivery": delivery}
    phases = a.get("sales_phases") or []
    price_phases = a.get("price_phases") or []
    if phases:  # a phase may open sales earlier than the base presale start
        first = min(anchor_month(p.get("anchor"), p.get("offset"), marks) for p in phases)
        start = max(1, min(start, first))
    sold_by_month: list[float] = []
    contract: list[float] = []
    collections: list[float] = []
    commissions: list[float] = []
    remaining, t = float(units_total), start
    while remaining > 1e-9 and net_abs > 0:
        rate = _phase_value(phases, t, marks, "units_per_month") if phases else None
        n = min((base_abs if rate is None else float(rate)) * (1 - cancel), remaining)
        if n <= 1e-12:
            t += 1
            if t > 2000:
                break
            continue
        remaining -= n
        price_mult = 1.0
        for ph in price_phases:
            s = anchor_month(ph.get("anchor"), ph.get("offset"), marks)
            if s <= t < s + int(ph.get("months") or 0):
                price_mult *= 1 + float(ph.get("pct") or 0) / 100
        value = n * avg_price * (1 + esc) ** (t / 12) * (1 - discount) * price_mult
        _add(sold_by_month, t, n)
        _add(contract, t, value)
        _add(commissions, t, value * comm)
        if t >= delivery:
            _add(collections, t, value)
        else:
            _add(collections, t, value * dep)
            n_inst = delivery - t - 1
            if n_inst > 0:
                _spread(collections, t + 1, n_inst, value * inst)
                _add(collections, delivery, value * clo)
            else:
                _add(collections, delivery, value * (inst + clo))
        t += 1
        if t > 2000:
            break
    last_sale = t - 1
    total_contract = sum(contract)
    marketing: list[float] = []
    _spread(marketing, start, max(last_sale - start + 1, 1), total_contract * mkt)
    return {
        "inflows": collections, "contract": contract, "sold": sold_by_month, "commissions": commissions,
        "marketing": marketing, "gdv": total_contract, "gross_value_today": gross_value,
        "avg_unit_price_today": avg_price, "sales_start": start, "last_sale_month": last_sale,
        "net_absorption": net_abs, "sellout_months": last_sale - start + 1,
    }


def _rent_revenue(a: dict, design: dict, delivery: int, ground_up: bool) -> dict:
    leasable = design["saleable"]
    green = green_totals(a)
    rent = float(a["rent.rent_per_area_month"]) * (1 + green["rent_premium_pct"] / 100) * price_multiplier(a, "rent")
    vac = g(a, "rent.vacancy_pct") / 100
    conc = g(a, "rent.concessions_pct") / 100
    opex_pct = g(a, "rent.opex_pct_egi") / 100
    growth = g(a, "rent.growth_pct") / 100
    lease_up = int(g(a, "rent.lease_up_months")) if ground_up else 0
    hold = int(g(a, "rent.hold_years"))
    cap = float(a["rent.exit_cap_pct"]) / 100
    sell_cost = g(a, "rent.selling_costs_pct") / 100
    start = delivery + 1 if ground_up else 1
    exit_m = (delivery if ground_up else 0) + hold * 12

    def occ(t: int) -> float:
        if t < start:
            return 0.0
        if lease_up and t - start < lease_up:
            return (1 - vac) * (t - start + 1) / lease_up
        return 1 - vac

    def noi_at(t: int, stabilized: bool = False) -> dict:
        gpr = leasable * rent * (1 + growth) ** (t / 12)
        o = (1 - vac) if stabilized else occ(t)
        egi = gpr * o * (1 - conc)
        # landlord-side savings from sustainability measures lower opex once the building operates
        savings = green["net_savings_annual"] / 12 * (1 + growth) ** (t / 12) if t >= start else 0.0
        opex = egi * opex_pct - savings
        return {"gpr": gpr, "egi": egi, "opex": opex, "noi": egi - opex}

    gpr_s, egi_s, opex_s, noi_s, inflows = [], [], [], [], []
    for t in range(0, exit_m + 1):
        r = noi_at(t) if t >= start else {"gpr": 0, "egi": 0, "opex": 0, "noi": 0}
        _add(gpr_s, t, r["gpr"]); _add(egi_s, t, r["egi"]); _add(opex_s, t, r["opex"]); _add(noi_s, t, r["noi"])
        _add(inflows, t, r["noi"])
    fwd_noi = sum(noi_at(exit_m + i, stabilized=True)["noi"] for i in range(1, 13))
    exit_value = fwd_noi / cap if cap > 0 else 0.0
    _add(inflows, exit_m, exit_value * (1 - sell_cost))
    stab = noi_at(start + max(lease_up, 0), stabilized=True)
    return {
        "inflows": inflows, "gpr": gpr_s, "egi": egi_s, "opex": opex_s, "noi": noi_s, "exit_month": exit_m,
        "exit_value": exit_value, "exit_net": exit_value * (1 - sell_cost), "forward_noi": fwd_noi,
        "stabilized_noi_annual": stab["noi"] * 12, "stabilized_gpr_annual": stab["gpr"] * 12,
        "stabilized_egi_annual": stab["egi"] * 12, "selling_costs": exit_value * sell_cost,
        "gdv": exit_value, "lease_start": start,
    }


# --------------------------------------------------------------------------- costs
def _costs(profile: dict, a: dict, design: dict, predev: int, con_months: int, ground_up: bool) -> dict:
    con_start = predev
    land_price = float(a["site.land_price"])
    acq_pct = (g(a, "site.transfer_tax_pct") + g(a, "site.legal_notary_pct") + g(a, "site.brokerage_pct")) / 100
    esc = g(a, "cost.escalation_pct") / 100
    cats: dict[str, list[float]] = {k: [] for k in ("land", "acquisition", "hard", "soft", "contingency", "developer_fee")}
    budget_rows: list[dict] = []

    def row(group, item, amount, basis):
        budget_rows.append({"group": group, "item": item, "amount": amount, "basis": basis})

    land_sched = a.get("land_payments") or []
    if land_sched:
        for pay in land_sched:
            _add(cats["land"], int(pay["month"]), land_price * float(pay["pct"]) / 100)
        row("Acquisition", "Land / property price", land_price,
            "paid " + ", ".join(f"{float(p['pct']):g}% in M{int(p['month'])}" for p in land_sched))
    else:
        _add(cats["land"], 0, land_price)
        row("Acquisition", "Land / property price", land_price, "fixed")
    for key, label in (("site.transfer_tax_pct", "Transfer tax (ISAI)"), ("site.legal_notary_pct", "Notary & legal"),
                       ("site.brokerage_pct", "Brokerage")):
        amt = land_price * g(a, key) / 100
        _add(cats["acquisition"], 0, amt)
        row("Acquisition", label, amt, f"{g(a, key):g}% of price")
    dd = float(g(a, "site.due_diligence", 0))
    _add(cats["acquisition"], 0, dd)
    row("Acquisition", "Due diligence & closing", dd, "fixed")

    curve = curve_weights(str(g(a, "cost.curve", "s_curve")), con_months)
    hard_months = list(range(con_start + 1, con_start + con_months + 1))
    escal = [(1 + esc) ** (m / 12) for m in hard_months]

    if ground_up:
        hard_above = design["gba_above"] * float(a["cost.hard_per_area"])
        hard_below = design["below_area"] * float(g(a, "cost.below_grade_per_area", 0))
    else:
        hard_above = float(g(a, "cost.renovation_budget", 0))
        hard_below = 0.0
    fixed_site = float(g(a, "cost.demolition", 0)) + float(g(a, "cost.infrastructure_fees", 0))
    green_capex = green_totals(a)["capex"]
    hard_base = hard_above + hard_below + fixed_site + green_capex

    hard_escalated = 0.0
    for i, m in enumerate(hard_months):
        amt = (hard_above + hard_below + green_capex) * curve[i] * escal[i]
        _add(cats["hard"], m, amt)
        hard_escalated += amt
    _add(cats["hard"], con_start + 1 if con_months else con_start, fixed_site)
    escalation_amount = hard_escalated - (hard_above + hard_below + green_capex)

    split = a.get("hard_cost_split") or DEFAULT_HARD_COST_SPLIT
    total_share = sum(split.values()) or 1
    if ground_up:
        for name, share in split.items():
            row("Hard costs", name, hard_above * share / total_share,
                f"{share / total_share * 100:.1f}% of {a['cost.hard_per_area']:,.0f}/area above ground")
        if hard_below:
            row("Hard costs", "Parking & below-grade structure", hard_below,
                f"{design['below_area']:,.0f} area × {g(a, 'cost.below_grade_per_area', 0):,.0f}")
    else:
        row("Hard costs", "Renovation / CAPEX", hard_above, "fixed budget")
    if g(a, "cost.demolition", 0):
        row("Hard costs", "Demolition & site preparation", float(g(a, "cost.demolition", 0)), "fixed")
    if g(a, "cost.infrastructure_fees", 0):
        row("Hard costs", "Infrastructure / impact fees", float(g(a, "cost.infrastructure_fees", 0)), "fixed")
    if green_capex:
        row("Hard costs", "Sustainability measures", green_capex, f"{green_totals(a)['count']} enabled measures")
    row("Other", "Construction cost escalation", escalation_amount, f"{g(a, 'cost.escalation_pct'):g}% p.a. compounded monthly")

    design_fee = hard_base * g(a, "cost.design_pct") / 100
    permits = hard_base * g(a, "cost.permits_pct") / 100
    pm = hard_base * g(a, "cost.pm_supervision_pct") / 100
    other_soft = hard_base * g(a, "cost.insurance_other_pct") / 100
    if predev > 0:
        _spread(cats["soft"], 1, predev, design_fee * 0.6)
        _spread(cats["soft"], con_start + 1, con_months, design_fee * 0.4)
    else:
        _spread(cats["soft"], con_start + 1, con_months, design_fee)
    _add(cats["soft"], max(con_start, 1) if predev else con_start, permits)
    _spread(cats["soft"], con_start + 1, con_months, pm + other_soft)
    for label, amt, key in (("Architecture & engineering", design_fee, "cost.design_pct"),
                            ("Permits & licenses", permits, "cost.permits_pct"),
                            ("Project management & supervision", pm, "cost.pm_supervision_pct"),
                            ("Insurance, consultants & other", other_soft, "cost.insurance_other_pct")):
        row("Soft costs", label, amt, f"{g(a, key):g}% of hard")
    soft_total = design_fee + permits + pm + other_soft

    contingency = (hard_base + soft_total) * g(a, "cost.contingency_pct") / 100
    _spread(cats["contingency"], con_start + 1, con_months, contingency, curve)
    row("Other", "Contingency", contingency, f"{g(a, 'cost.contingency_pct'):g}% of hard + soft")
    dev_fee = (hard_base + soft_total) * g(a, "cost.developer_fee_pct") / 100
    _spread(cats["developer_fee"], con_start + 1, con_months, dev_fee)
    row("Other", "Developer fee", dev_fee, f"{g(a, 'cost.developer_fee_pct'):g}% of hard + soft")
    return {"cats": cats, "rows": budget_rows, "hard_base": hard_base, "hard_escalated": hard_escalated + fixed_site,
            "soft_total": soft_total, "curve": curve}


# --------------------------------------------------------------------------- capital stack
def _capital_stack(a: dict, mode: str, unlev_out: list[float], unlev_in: list[float], con_start: int,
                   delivery: int, total_cost_est: float, sold_cum: list[float], units: int, horizon: int,
                   rent_info: dict | None) -> dict:
    n = horizon + 1
    senior_ltc = g(a, "fin.senior_ltc_pct") / 100
    mezz_ltc = g(a, "fin.mezz_ltc_pct", 0) / 100
    if g(a, "fin.senior_rate_type") == "fixed":
        senior_rate_annual = float(a.get("fin.senior_fixed_rate_pct") or 0)
    else:
        senior_rate_annual = float(a.get("fin.reference_rate_pct") or 0) + float(g(a, "fin.senior_spread_pct"))
    rs = nominal_monthly(senior_rate_annual)
    rm = nominal_monthly(float(a.get("fin.mezz_rate_pct") or 0))
    capitalize = bool(g(a, "fin.interest_capitalized"))
    commit_fee_m = g(a, "fin.commitment_fee_pct") / 100 / 12
    sweep = g(a, "fin.sweep_pct") / 100

    senior_commit = senior_ltc * total_cost_est
    mezz_commit = mezz_ltc * total_cost_est
    equity_cap = max(total_cost_est - senior_commit - mezz_commit, 0)

    s_bal = m_bal = cash = 0.0
    eq_in = eq_contrib_total = 0.0
    out = {k: [0.0] * n for k in ("equity_contrib", "equity_dist", "senior_draw", "senior_repay", "senior_interest",
                                  "senior_balance", "mezz_draw", "mezz_repay", "mezz_interest", "mezz_balance",
                                  "fees", "cash_balance", "debt_service", "funding_gap")}
    first_draw = None
    maturity = None
    term = int(g(a, "fin.senior_term_months"))
    orig_paid = False
    amort_pmt = None
    rent_mode = mode == "rent"
    exit_m = rent_info["exit_month"] if rent_info else None
    gap_total = 0.0
    maturity_shortfall = 0.0

    for t in range(n):
        need = unlev_out[t] - unlev_in[t]
        # interest on opening balances
        si = s_bal * rs
        mi = m_bal * rm
        out["senior_interest"][t] = si
        out["mezz_interest"][t] = mi
        fees = 0.0
        if t <= delivery and t >= con_start and senior_commit > 0:
            fees += max(senior_commit - s_bal, 0) * commit_fee_m
        if not orig_paid and senior_commit > 0 and t == con_start:
            fees += senior_commit * g(a, "fin.origination_fee_pct") / 100
            orig_paid = True
        out["fees"][t] = fees
        need += fees
        if t <= delivery and capitalize:
            room_s = max(senior_commit - s_bal, 0)
            cap_s = min(si, room_s)
            s_bal += cap_s
            need += si - cap_s
            room_m = max(mezz_commit - m_bal, 0)
            cap_m = min(mi, room_m)
            m_bal += cap_m
            need += mi - cap_m
        else:
            need += si + mi
            out["debt_service"][t] += si + mi

        # term-loan amortization for rentals after delivery
        if rent_mode and t > delivery and s_bal > 0 and g(a, "fin.amortization_years"):
            if amort_pmt is None:
                amort_pmt = payment(rs, int(g(a, "fin.amortization_years")) * 12, s_bal) - s_bal * rs
            principal = min(max(amort_pmt, 0), s_bal)
            s_bal -= principal
            out["senior_repay"][t] += principal
            out["debt_service"][t] += principal
            need += principal

        if need > 0:  # deficit: use cash, then equity up to cap, then mezz, then senior, then extra equity
            use = min(cash, need); cash -= use; need -= use
            e = min(need, max(equity_cap - eq_in, 0)); eq_in += e; need -= e
            out["equity_contrib"][t] += e
            dm = min(need, max(mezz_commit - m_bal, 0)); m_bal += dm; need -= dm
            out["mezz_draw"][t] = dm
            ds = min(need, max(senior_commit - s_bal, 0)); s_bal += ds; need -= ds
            out["senior_draw"][t] = ds
            if ds > 0 and first_draw is None:
                first_draw = t
                maturity = t + term
            if need > 1e-6:  # beyond plan: additional equity required (funding gap)
                out["equity_contrib"][t] += need
                out["funding_gap"][t] = need
                gap_total += need
                need = 0.0
        else:
            surplus = -need
            if t >= delivery or t == horizon:
                # for-sale: sweep sales proceeds to debt; rentals amortize and repay at exit
                to_debt = surplus if t == horizon else (0.0 if rent_mode else surplus * sweep)
                r1 = min(to_debt, s_bal); s_bal -= r1; out["senior_repay"][t] += r1
                r2 = min(to_debt - r1, m_bal); m_bal -= r2; out["mezz_repay"][t] += r2
                rest = surplus - r1 - r2 + cash
                cash = 0.0
                out["equity_dist"][t] += rest
            else:
                cash += surplus

        if not rent_mode and maturity is not None and t == maturity and s_bal > 1e-6:
            use = min(cash, s_bal); cash -= use; s_bal -= use; out["senior_repay"][t] += use
            if s_bal > 1e-6:
                out["equity_contrib"][t] += s_bal
                out["funding_gap"][t] += s_bal
                out["senior_repay"][t] += s_bal
                maturity_shortfall += s_bal
                gap_total += s_bal
                s_bal = 0.0
        if t == horizon:  # final month: everything must be repaid
            for bal_name in ("s", "m"):
                bal = s_bal if bal_name == "s" else m_bal
                if bal > 1e-6:
                    dist_avail = out["equity_dist"][t]
                    pay = min(dist_avail, bal)
                    out["equity_dist"][t] -= pay
                    short = bal - pay
                    if short > 1e-6:
                        out["equity_contrib"][t] += short
                        out["funding_gap"][t] += short
                        gap_total += short
                    out["senior_repay" if bal_name == "s" else "mezz_repay"][t] += bal
                    if bal_name == "s":
                        s_bal = 0.0
                    else:
                        m_bal = 0.0
        out["senior_balance"][t] = s_bal
        out["mezz_balance"][t] = m_bal
        out["cash_balance"][t] = cash
        eq_contrib_total += out["equity_contrib"][t]

    interest_total = sum(out["senior_interest"]) + sum(out["mezz_interest"])
    fees_total = sum(out["fees"])
    presales_at_first_draw = None
    if first_draw is not None and units and sold_cum:
        presales_at_first_draw = (sold_cum[first_draw] if first_draw < len(sold_cum) else sold_cum[-1]) / units * 100
    out.update(
        senior_commit=senior_commit, mezz_commit=mezz_commit, equity_cap=equity_cap,
        senior_rate_annual_pct=senior_rate_annual, interest_total=interest_total, fees_total=fees_total,
        financing_cost=interest_total + fees_total, first_draw_month=first_draw, maturity_month=maturity,
        funding_gap_total=gap_total, maturity_shortfall=maturity_shortfall,
        presales_at_first_draw_pct=presales_at_first_draw,
        peak_senior=max(out["senior_balance"]) if n else 0.0,
        peak_debt=max(s + m for s, m in zip(out["senior_balance"], out["mezz_balance"])) if n else 0.0,
    )
    return out


# --------------------------------------------------------------------------- waterfall
def equity_waterfall(contrib: list[float], dist: list[float], sponsor_share: float, pref_annual_pct: float,
                     promote_pct: float) -> dict:
    """Return of capital → preferred return (compounded monthly) → promote split. Pari passu pref."""
    s = sponsor_share
    rp = monthly_rate(pref_annual_pct)
    promote = promote_pct / 100
    n = len(contrib)
    inv, spo = [0.0] * n, [0.0] * n
    uc = pref = 0.0  # unreturned capital, accrued pref (whole partnership)
    tiers = {"return_of_capital": 0.0, "preferred_return": 0.0, "residual_pro_rata": 0.0, "sponsor_promote": 0.0}
    for t in range(n):
        pref += (uc + pref) * rp
        c = contrib[t]
        if c:
            uc += c
            inv[t] -= c * (1 - s)
            spo[t] -= c * s
        d = dist[t]
        if d <= 0:
            continue
        roc = min(d, uc); uc -= roc; d -= roc
        inv[t] += roc * (1 - s); spo[t] += roc * s; tiers["return_of_capital"] += roc
        pp = min(d, pref); pref -= pp; d -= pp
        inv[t] += pp * (1 - s); spo[t] += pp * s; tiers["preferred_return"] += pp
        if d > 0:
            prom = d * promote
            rest = d - prom
            spo[t] += prom + rest * s
            inv[t] += rest * (1 - s)
            tiers["sponsor_promote"] += prom
            tiers["residual_pro_rata"] += rest

    def stats(flows):
        paid_in = -sum(f for f in flows if f < 0)
        out = sum(f for f in flows if f > 0)
        return {"irr": annualize(irr_monthly(flows)), "moic": out / paid_in if paid_in > 0 else None,
                "contributed": paid_in, "distributed": out, "profit": out - paid_in}

    return {"investor": stats(inv), "sponsor": stats(spo), "tiers": tiers, "investor_flows": inv, "sponsor_flows": spo}


# --------------------------------------------------------------------------- user-defined variables
def _apply_custom_vars(a: dict, mode: str, design: dict, costs: dict, rev: dict, cats: dict, marks: dict,
                       con_start: int, con_months: int, n: int, sales_collections: list | None = None) -> None:
    """Deterministic effects of user-defined variables (see engine/custom_vars.py). Writes into the custom cost
    bucket, the revenue inflows and the budget rows."""
    vars_ = [v for v in a.get("custom_variables") or [] if v["effect"] not in ("info", "price_pct") and isinstance(v.get("value"), (int, float))]
    if not vars_:
        return
    curve = costs.get("curve") or []
    sales_collections = list(sales_collections if sales_collections is not None else rev["inflows"])
    sold = rev.get("sold") or []
    units = design.get("units") or 0

    def clamp(t: int) -> int:
        return max(0, min(int(t), n - 1))

    def spread_construction(total: float) -> None:
        if con_months and curve:
            for i, w in enumerate(curve):
                _add(cats["custom"], clamp(con_start + 1 + i), total * w)
        else:
            _add(cats["custom"], clamp(con_start), total)

    for v in vars_:
        val, eff, label = float(v["value"]), v["effect"], v["label"]
        start = anchor_month(v.get("anchor"), v.get("offset"), marks)
        if eff.startswith("cost"):
            if eff == "cost_fixed":
                total, basis = val, "fixed"
            elif eff == "cost_per_area":
                total, basis = val * (design.get("gba_above") or 0), f"{val:,.0f} × {design.get('gba_above') or 0:,.0f} m² GBA"
            elif eff == "cost_per_unit":
                total, basis = val * units, f"{val:,.0f} × {units} units"
            elif eff == "cost_pct_hard":
                total, basis = val / 100 * costs.get("hard_base", 0), f"{val:g}% of hard cost"
            elif eff == "cost_pct_revenue":
                total = 0.0
                for t, c in enumerate(sales_collections[:n]):
                    if c:
                        _add(cats["custom"], t, c * val / 100)
                        total += c * val / 100
                costs["rows"].append({"group": "User-defined variables", "item": label, "amount": total, "basis": f"{val:g}% of sales collections"})
                continue
            else:  # cost_monthly
                months = int(v.get("months") or 12)
                for i in range(months):
                    _add(cats["custom"], clamp(start + i), val)
                costs["rows"].append({"group": "User-defined variables", "item": label, "amount": val * months, "basis": f"{val:,.0f}/month × {months} months"})
                continue
            if v.get("timing") == "anchor" and eff == "cost_fixed":
                _add(cats["custom"], clamp(start), total)
                basis += f", M{clamp(start)}"
            else:
                spread_construction(total)
            costs["rows"].append({"group": "User-defined variables", "item": label, "amount": total, "basis": basis})
        else:  # revenue
            if eff == "revenue_fixed":
                _add(rev["inflows"], clamp(start), val)
            elif eff == "revenue_per_unit":
                if mode == "sale" and sold:
                    for t, s in enumerate(sold[:n]):
                        if s:
                            _add(rev["inflows"], t, s * val)
                else:
                    _add(rev["inflows"], clamp(marks.get("sales_start", start)), val * units)
            else:  # revenue_monthly
                for i in range(int(v.get("months") or 12)):
                    _add(rev["inflows"], clamp(start + i), val)


# --------------------------------------------------------------------------- main
def run_model(profile: dict, assumptions: dict, overrides: dict | None = None) -> dict:
    a = {**assumptions, **(overrides or {})}
    missing = missing_inputs(profile, a)
    if missing:
        return {"status": "incomplete", "missing": missing,
                "missing_labels": [REGISTRY[m]["label"] if m in REGISTRY else m for m in missing]}

    mode = model_mode(profile)
    ground_up = is_ground_up(profile)
    warnings: list[str] = []
    design = compute_design(profile, a)
    if mode == "sale" and design["units"] <= 0:
        return {"status": "invalid", "missing": [], "errors": ["The design yields 0 units. Check land area, stories, efficiency and unit sizes."]}
    if design.get("saleable", 0) <= 0:
        return {"status": "invalid", "missing": [], "errors": ["Saleable / leasable area is zero."]}

    predev = int(g(a, "sch.predev_months", 0)) if ground_up else int(a.get("sch.predev_months") or 0)
    con_months = int(a.get("sch.construction_months") or (0 if not ground_up else 1))
    if not ground_up and not a.get("cost.renovation_budget"):
        con_months = int(a.get("sch.construction_months") or 0)
    con_start = predev
    delivery = predev + con_months

    costs = _costs(profile, a, design, predev, con_months, ground_up)
    custom = a.get("custom_flows") or []
    if mode == "sale":
        rev = _sale_revenue(a, design, con_start, delivery)
        commercial = [x + y for x, y in zip(*_aligned(rev["commissions"], rev["marketing"]))]
        horizon = max(len(rev["inflows"]) - 1, delivery, rev["last_sale_month"])
    else:
        rev = _rent_revenue(a, design, delivery, ground_up)
        commercial = [0.0]
        horizon = rev["exit_month"]
    sale_marks = {"closing": 0, "construction_start": con_start, "delivery": delivery,
                  "sales_start": rev.get("sales_start", delivery) if mode == "sale" else rev.get("lease_start", delivery)}
    sales_only_inflows = list(rev["inflows"])  # % of collections applies to sales collections only (not custom income)
    custom_resolved = []
    for cf in custom:
        m = anchor_month(cf.get("anchor"), cf.get("offset"), sale_marks) if cf.get("anchor") else int(cf.get("month") or 0)
        custom_resolved.append({**cf, "resolved_month": m})
        horizon = max(horizon, m)
    n = horizon + 1
    cats = costs["cats"]
    cats["custom"] = []
    for cf in custom_resolved:
        if cf.get("type", "cost") == "cost":
            _add(cats["custom"], cf["resolved_month"], float(cf["amount"]))
            costs["rows"].append({"group": "Custom items", "item": cf.get("label") or "Custom cost", "amount": float(cf["amount"]),
                                  "basis": f"M{cf['resolved_month']} (user-defined)"})
        else:
            _add(rev["inflows"], cf["resolved_month"], float(cf["amount"]))
    _apply_custom_vars(a, mode, design, costs, rev, cats, sale_marks, con_start, con_months, n, sales_only_inflows)
    _pad(*cats.values(), commercial, rev["inflows"], length=n)
    if mode == "sale":
        _pad(rev["sold"], rev["contract"], length=n)

    outflows = [sum(cats[k][t] for k in cats) + commercial[t] for t in range(n)]
    inflows = rev["inflows"][:n]
    unlev = [inflows[t] - outflows[t] for t in range(n)]

    sold_cum: list[float] = []
    if mode == "sale":
        acc = 0.0
        for t in range(n):
            acc += rev["sold"][t]
            sold_cum.append(acc)

    tdc = sum(outflows)
    # capital stack: iterate on financing cost (circular: debt sized on cost incl. financing)
    fin_cost = 0.0
    cap = None
    for _ in range(FIN_ITERATIONS):
        cap = _capital_stack(a, mode, outflows, inflows, con_start, delivery, tdc + fin_cost, sold_cum,
                             design.get("units", 0), horizon, rev if mode == "rent" else None)
        if abs(cap["financing_cost"] - fin_cost) < 1:
            fin_cost = cap["financing_cost"]
            break
        fin_cost = cap["financing_cost"]
    assert cap is not None
    total_cost = tdc + cap["financing_cost"]

    eq_flows = [cap["equity_dist"][t] - cap["equity_contrib"][t] for t in range(n)]
    contrib_total = sum(cap["equity_contrib"])
    dist_total = sum(cap["equity_dist"])

    # metrics
    if mode == "sale":
        revenue = sum(inflows)
        gdv = rev["gdv"]
    else:
        revenue = sum(inflows)
        gdv = rev["exit_value"]
    land_acq = sum(cats["land"]) + sum(cats["acquisition"])
    construction = sum(cats["hard"]) + sum(cats["soft"]) + sum(cats["contingency"]) + sum(cats["developer_fee"])
    commercial_total = sum(commercial)
    profit = revenue - total_cost
    gross_profit = revenue - land_acq - construction
    r_unlev = monthly_rate(g(a, "val.discount_rate_pct"))
    r_eq = monthly_rate(g(a, "val.equity_discount_rate_pct"))
    project_irr_m = irr_monthly(unlev)
    equity_irr_m = irr_monthly(eq_flows)
    cum, peak_funding = 0.0, 0.0
    for cf in unlev:
        cum += cf
        peak_funding = max(peak_funding, -cum)
    cum_e, peak_equity = 0.0, 0.0
    for t in range(n):
        cum_e += cap["equity_contrib"][t] - cap["equity_dist"][t]
        peak_equity = max(peak_equity, cum_e)

    if project_irr_m is None:
        warnings.append("Project IRR is undefined (cash flows never change sign).")
    if equity_irr_m is None:
        warnings.append("Equity IRR is undefined (equity flows never change sign).")
    if cap["funding_gap_total"] > 1:
        warnings.append(f"Funding gap: {cap['funding_gap_total']:,.0f} of additional equity is needed beyond the planned capital stack.")
    if cap["maturity_shortfall"] > 1:
        warnings.append(f"Senior loan matures before it is repaid from sales; {cap['maturity_shortfall']:,.0f} must be refinanced or covered by equity.")
    if design.get("unsold_remainder", 0) > 0 and mode == "sale" and design["saleable"]:
        rem = design["unsold_remainder"] / design["saleable"] * 100
        if rem > 3:
            warnings.append(f"{rem:.1f}% of saleable area is not allocated to whole units (rounding).")
    if ground_up and design.get("below_area") and not a.get("cost.below_grade_per_area"):
        warnings.append("Parking / below-grade area has no cost per area; it is costed at 0.")
    if ground_up and design.get("levels_below_needed", 0) > (a.get("dev.levels_below") or 0):
        warnings.append(f"Parking needs ~{design['levels_below_needed']} underground levels; the design has {a.get('dev.levels_below') or 0}.")

    dscr = None
    coc = None
    if mode == "rent":
        ds_annual = None
        stab_start = rev["lease_start"] + int(g(a, "rent.lease_up_months") if ground_up else 0)
        window = range(stab_start, min(stab_start + 12, n))
        ds = sum(cap["debt_service"][t] for t in window)
        noi_w = sum(rev["noi"][t] for t in window if t < len(rev["noi"]))
        if ds > 0:
            dscr = noi_w / ds
            ds_annual = ds
        hold_dist = [cap["equity_dist"][t] for t in range(stab_start, rev["exit_month"])]
        years = max(len(hold_dist) / 12, 1e-9)
        if contrib_total > 0:
            coc = (sum(hold_dist) / years) / contrib_total

    covenants = []
    if cap["senior_commit"] > 0:
        ltc = cap["senior_commit"] / total_cost * 100
        covenants.append({"name": "Max LTC", "limit": g(a, "fin.max_ltc_covenant_pct"), "actual": ltc,
                          "unit": "%", "ok": ltc <= g(a, "fin.max_ltc_covenant_pct") + 1e-9})
        ltv = cap["peak_debt"] / gdv * 100 if gdv else None
        if ltv is not None:
            covenants.append({"name": "Max LTV (peak debt / GDV)", "limit": g(a, "fin.max_ltv_covenant_pct"), "actual": ltv,
                              "unit": "%", "ok": ltv <= g(a, "fin.max_ltv_covenant_pct") + 1e-9})
        if mode == "sale" and cap["presales_at_first_draw_pct"] is not None:
            p = cap["presales_at_first_draw_pct"]
            covenants.append({"name": "Presales before first draw", "limit": g(a, "fin.min_presales_pct"), "actual": p,
                              "unit": "% units", "ok": p + 1e-9 >= g(a, "fin.min_presales_pct")})
        if dscr is not None:
            covenants.append({"name": "Min DSCR", "limit": g(a, "fin.min_dscr"), "actual": dscr, "unit": "x",
                              "ok": dscr >= g(a, "fin.min_dscr")})

    wf = equity_waterfall(cap["equity_contrib"], cap["equity_dist"], g(a, "fin.sponsor_equity_share_pct") / 100,
                          g(a, "fin.pref_return_pct"), g(a, "fin.promote_pct"))

    compliance = compliance_issues(a, design) if ground_up else []
    area_basis = design.get("gba_total") or design.get("gba_above") or 0
    units = design.get("units") or 0
    budget = costs["rows"] + (
        [{"group": "Commercial", "item": "Sales commissions", "amount": sum(rev["commissions"]), "basis": f"{g(a, 'rev.commission_pct'):g}% of contract value"},
         {"group": "Commercial", "item": "Marketing & sales office", "amount": sum(rev["marketing"]), "basis": f"{g(a, 'rev.marketing_pct'):g}% of revenue"}]
        if mode == "sale" else []
    ) + [{"group": "Financing", "item": "Interest (on actual monthly balance)", "amount": cap["interest_total"], "basis": f"{cap['senior_rate_annual_pct']:.2f}% senior"},
         {"group": "Financing", "item": "Loan fees", "amount": cap["fees_total"], "basis": "origination + commitment"}]
    for r in budget:
        r["per_area"] = r["amount"] / area_basis if area_basis else None
        r["per_unit"] = r["amount"] / units if units else None
        r["pct_total"] = r["amount"] / total_cost * 100 if total_cost else None

    months = []
    phase = lambda t: "Acquisition" if t == 0 else ("Pre-development" if t <= predev else ("Construction" if t <= delivery else ("Sales & closing" if mode == "sale" else "Operations")))
    for t in range(n):
        months.append({
            "month": t, "phase": phase(t),
            "land_acq": cats["land"][t] + cats["acquisition"][t], "hard": cats["hard"][t], "soft": cats["soft"][t],
            "other": cats["contingency"][t] + cats["developer_fee"][t] + cats["custom"][t], "commercial": commercial[t],
            "interest": cap["senior_interest"][t] + cap["mezz_interest"][t], "fees": cap["fees"][t],
            "outflow": outflows[t], "inflow": inflows[t], "unlevered_cf": unlev[t],
            "equity_contrib": cap["equity_contrib"][t], "equity_dist": cap["equity_dist"][t],
            "senior_draw": cap["senior_draw"][t], "senior_repay": cap["senior_repay"][t],
            "senior_balance": cap["senior_balance"][t], "mezz_balance": cap["mezz_balance"][t],
            "cash_balance": cap["cash_balance"][t], "funding_gap": cap["funding_gap"][t],
            "units_sold": rev["sold"][t] if mode == "sale" else None,
            "units_sold_cum": sold_cum[t] if mode == "sale" else None,
            "contract_value": rev["contract"][t] if mode == "sale" else None,
            "noi": rev["noi"][t] if mode == "rent" and t < len(rev["noi"]) else None,
            "levered_cf": eq_flows[t],
        })
    cum_cost = 0.0
    for m in months:
        cum_cost += m["outflow"]
        m["cumulative_cost"] = cum_cost

    metrics = {
        "mode": mode,
        "tdc": tdc, "financing_cost": cap["financing_cost"], "total_cost": total_cost,
        "land_and_acquisition": land_acq, "construction_cost": construction, "commercial_cost": commercial_total,
        "hard_cost": sum(cats["hard"]), "soft_cost": sum(cats["soft"]),
        "gdv": gdv, "revenue": revenue, "gross_profit": gross_profit, "profit": profit,
        "gross_margin": gross_profit / revenue if revenue else None,
        "net_margin": profit / revenue if revenue else None,
        "profit_on_cost": profit / total_cost if total_cost else None,
        "project_irr": annualize(project_irr_m), "equity_irr": annualize(equity_irr_m),
        "moic": dist_total / contrib_total if contrib_total > 0 else None,
        "npv": npv(r_unlev, unlev), "equity_npv": npv(r_eq, eq_flows),
        "discount_rate_pct": g(a, "val.discount_rate_pct"), "equity_discount_rate_pct": g(a, "val.equity_discount_rate_pct"),
        "peak_funding": peak_funding, "peak_equity": peak_equity, "equity_contributed": contrib_total,
        "equity_distributed": dist_total, "equity_profit": dist_total - contrib_total,
        "senior_commitment": cap["senior_commit"], "mezz_commitment": cap["mezz_commit"], "peak_debt": cap["peak_debt"],
        "ltc": cap["senior_commit"] / total_cost if total_cost else None,
        "ltv": cap["peak_debt"] / gdv if gdv else None,
        "senior_rate_pct": cap["senior_rate_annual_pct"],
        "dscr": dscr, "cash_on_cash": coc,
        "exit_value": rev.get("exit_value") if mode == "rent" else gdv,
        "funding_gap": cap["funding_gap_total"], "maturity_shortfall": cap["maturity_shortfall"],
        "first_draw_month": cap["first_draw_month"], "maturity_month": cap["maturity_month"],
        "duration_months": horizon, "delivery_month": delivery, "construction_start": con_start,
        "units": units, "saleable_area": design.get("saleable"), "gba_above": design.get("gba_above"),
        "cost_per_area_gba": total_cost / area_basis if area_basis else None,
        "revenue_per_area": revenue / design["saleable"] if design.get("saleable") else None,
        "investor_irr": wf["investor"]["irr"], "investor_moic": wf["investor"]["moic"],
        "sponsor_irr": wf["sponsor"]["irr"], "sponsor_moic": wf["sponsor"]["moic"],
    }
    if mode == "sale":
        metrics.update(sales_start=rev["sales_start"], sellout_month=rev["last_sale_month"],
                       sellout_months=rev["sellout_months"], avg_unit_price_today=rev["avg_unit_price_today"],
                       presales_at_first_draw_pct=cap["presales_at_first_draw_pct"])
    else:
        metrics.update(stabilized_noi=rev["stabilized_noi_annual"], stabilized_gpr=rev["stabilized_gpr_annual"],
                       stabilized_egi=rev["stabilized_egi_annual"], exit_month=rev["exit_month"],
                       yield_on_cost=rev["stabilized_noi_annual"] / total_cost if total_cost else None)

    return {
        "status": "ok", "mode": mode, "design": design, "metrics": metrics, "budget": budget,
        "months": months, "covenants": covenants, "waterfall": {k: wf[k] for k in ("investor", "sponsor", "tiers")},
        "compliance": compliance, "compliant": not compliance, "warnings": warnings,
        "schedule": {"predev_months": predev, "construction_start": con_start, "construction_months": con_months,
                     "delivery_month": delivery, "horizon": horizon,
                     "sales_start": rev.get("sales_start"), "sellout_month": rev.get("last_sale_month"),
                     "exit_month": rev.get("exit_month")},
    }


def _aligned(x: list[float], y: list[float]) -> tuple[list[float], list[float]]:
    n = max(len(x), len(y))
    return x + [0.0] * (n - len(x)), y + [0.0] * (n - len(y))
