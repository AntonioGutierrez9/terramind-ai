"""Validation tests for the deterministic financial engine."""

from copy import deepcopy

import pytest

from engine.analysis import apply_changes, optimize_unit_mix, solve_for, tornado
from engine.asset_mgmt import analyze
from engine.finance import annualize, irr_annual, irr_monthly, npv, payment, s_curve
from engine.model import equity_waterfall, run_model
from engine.sustainability import evaluate, optimize
from engine.validation import ValidationError, validate_unit_mix, validate_value
from seed.demo_cases import CASES

POLANCO = CASES[0]
DELVALLE = CASES[1]
NARVARTE = CASES[2]


def run(case, **over):
    return run_model(case["profile"], deepcopy(case["assumptions"]), over or None)


# ---------------------------------------------------------------- finance primitives
def test_irr_simple_and_annualized():
    assert irr_monthly([-100, 110]) == pytest.approx(0.10, abs=1e-9)
    assert annualize(0.01) == pytest.approx(1.01 ** 12 - 1)
    assert irr_annual([-100, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 112]) == pytest.approx(0.12, abs=1e-6)


def test_irr_undefined_without_sign_change():
    assert irr_monthly([100, 50, 20]) is None
    assert irr_monthly([-100, -50]) is None
    assert irr_monthly([]) is None


def test_npv_and_payment():
    assert npv(0.0, [-100, 50, 50]) == pytest.approx(0)
    assert npv(0.10, [0, 110]) == pytest.approx(100)
    pmt = payment(0.01, 12, 1000)
    bal = 1000.0
    for _ in range(12):
        bal = bal * 1.01 - pmt
    assert bal == pytest.approx(0, abs=1e-6)


def test_s_curve_sums_to_one_and_peaks_midway():
    w = s_curve(24)
    assert sum(w) == pytest.approx(1)
    assert max(w) == w[11] or max(w) == w[12]
    assert w[0] < w[11]


# ---------------------------------------------------------------- model identities
@pytest.mark.parametrize("case", CASES, ids=lambda c: c["profile"]["name"])
def test_model_accounting_identities(case):
    r = run(case)
    assert r["status"] == "ok"
    m = r["metrics"]
    # budget lines add up to total cost
    assert sum(b["amount"] for b in r["budget"]) == pytest.approx(m["total_cost"], rel=1e-9)
    # profit identity
    assert m["revenue"] - m["total_cost"] == pytest.approx(m["profit"], rel=1e-9)
    # unlevered flows sum to revenue - TDC
    assert sum(x["unlevered_cf"] for x in r["months"]) == pytest.approx(m["revenue"] - m["tdc"], rel=1e-9)
    # all debt repaid; equity profit == development profit
    assert r["months"][-1]["senior_balance"] == pytest.approx(0, abs=1e-3)
    assert m["equity_distributed"] - m["equity_contributed"] == pytest.approx(m["profit"], rel=1e-6)
    # waterfall shares add up
    wf = r["waterfall"]
    assert wf["investor"]["distributed"] + wf["sponsor"]["distributed"] == pytest.approx(m["equity_distributed"], rel=1e-9)


def test_interest_is_charged_on_actual_balance():
    r = run(POLANCO)
    rate = r["metrics"]["senior_rate_pct"] / 100 / 12
    months = r["months"]
    for t in range(1, len(months)):
        expected = months[t - 1]["senior_balance"] * rate
        assert months[t]["interest"] == pytest.approx(expected, rel=1e-9, abs=1e-6)


def test_no_debt_means_no_financing_cost_and_equal_irrs():
    r = run(POLANCO, **{"fin.senior_ltc_pct": 0})
    m = r["metrics"]
    assert m["financing_cost"] == pytest.approx(0, abs=1e-6)
    # presale cash collected before delivery stays in the project account (it can't be distributed
    # while construction costs remain), so equity IRR is at most the unlevered IRR
    assert m["equity_irr"] <= m["project_irr"] + 1e-9
    assert m["equity_profit"] == pytest.approx(m["revenue"] - m["tdc"], rel=1e-9)


def test_directional_sensitivities():
    base = run(POLANCO)["metrics"]
    higher_price = run(POLANCO, **{"rev.price_per_area": POLANCO["assumptions"]["rev.price_per_area"] * 1.1})["metrics"]
    higher_cost = run(POLANCO, **{"cost.hard_per_area": POLANCO["assumptions"]["cost.hard_per_area"] * 1.1})["metrics"]
    longer = run(POLANCO, **{"sch.construction_months": 30})["metrics"]
    assert higher_price["profit"] > base["profit"]
    assert higher_cost["profit"] < base["profit"]
    assert longer["equity_irr"] < base["equity_irr"]


def test_units_are_derived_from_design():
    r = run(POLANCO)
    d = r["design"]
    a = POLANCO["assumptions"]
    footprint = a["site.land_area"] * (1 - a["reg.min_open_area_pct"] / 100)
    assert d["footprint"] == pytest.approx(footprint)
    assert d["gba_above"] == pytest.approx(footprint * a["dev.stories"])
    assert d["saleable"] == pytest.approx((footprint * a["dev.stories"] - a["dev.amenity_area"]) * a["dev.efficiency_pct"] / 100)
    assert d["units"] == sum(t["units"] for t in d["unit_types"]) > 0


def test_missing_inputs_return_incomplete_not_numbers():
    a = deepcopy(POLANCO["assumptions"])
    a.pop("site.land_price")
    a.pop("rev.price_per_area")
    r = run_model(POLANCO["profile"], a)
    assert r["status"] == "incomplete"
    assert "site.land_price" in r["missing"] and "rev.price_per_area" in r["missing"]
    assert "metrics" not in r


def test_payment_schedule_must_sum_to_100():
    r = run(POLANCO, **{"rev.closing_pct": 50})
    assert r["status"] == "incomplete"


def test_compliance_flags_overrides():
    r = run(POLANCO, **{"dev.stories": 11})
    assert not r["compliant"]
    assert any(i["rule"] == "reg.max_stories" for i in r["compliance"])
    assert run(POLANCO)["compliant"]


def test_risky_case_breaches_presales_covenant():
    r = run(DELVALLE)
    assert any(not c["ok"] for c in r["covenants"])
    assert r["metrics"]["equity_irr"] < r["metrics"]["equity_discount_rate_pct"] / 100


# ---------------------------------------------------------------- waterfall
def test_waterfall_without_promote_is_pro_rata():
    contrib = [100, 0, 0, 0]
    dist = [0, 0, 0, 150]
    wf = equity_waterfall(contrib, dist, 0.2, 0.0, 0.0)
    assert wf["investor"]["moic"] == pytest.approx(1.5)
    assert wf["sponsor"]["moic"] == pytest.approx(1.5)


def test_waterfall_promote_rewards_sponsor():
    wf = equity_waterfall([100, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], [0] * 12 + [200], 0.1, 8.0, 20.0)
    assert wf["sponsor"]["moic"] > wf["investor"]["moic"]
    t = wf["tiers"]
    assert t["return_of_capital"] == pytest.approx(100)
    assert t["preferred_return"] == pytest.approx(8.0, rel=1e-6)
    assert sum(t.values()) == pytest.approx(200)


# ---------------------------------------------------------------- analysis tools
def test_reverse_underwriting_hits_target():
    s = solve_for(POLANCO["profile"], deepcopy(POLANCO["assumptions"]), "site.land_price", "equity_irr", 0.18)
    assert s["status"] == "ok"
    assert s["achieved"] == pytest.approx(0.18, abs=5e-4)
    assert s["value"] > POLANCO["assumptions"]["site.land_price"]  # base IRR is above 18%


def test_unreachable_target_is_reported_not_faked():
    s = solve_for(DELVALLE["profile"], deepcopy(DELVALLE["assumptions"]), "dev.efficiency_pct", "equity_irr", 2.0, lo=30, hi=98)
    assert s["status"] in ("not_reachable", "undefined")


def test_tornado_and_unit_mix():
    t = tornado(POLANCO["profile"], deepcopy(POLANCO["assumptions"]))
    assert t["status"] == "ok" and len(t["bars"]) >= 5
    u = optimize_unit_mix(POLANCO["profile"], deepcopy(POLANCO["assumptions"]))
    assert u["status"] == "ok" and u["evaluated"] > 10


def test_scenario_changes_are_validated():
    a = POLANCO["assumptions"]
    ov = apply_changes(a, [{"key": "cost.hard_per_area", "op": "pct", "value": 10}])
    assert ov["cost.hard_per_area"] == pytest.approx(a["cost.hard_per_area"] * 1.1)
    with pytest.raises(ValidationError):
        apply_changes(a, [{"key": "fin.senior_ltc_pct", "op": "set", "value": 150}])


# ---------------------------------------------------------------- validation
def test_value_validation():
    assert validate_value("site.land_price", "120m")[0] == 120_000_000
    assert validate_value("site.land_price", "MXN 120 million")[0] == 120_000_000
    assert validate_value("site.land_area", "2,500 m²")[0] == 2500
    assert validate_value("fin.senior_ltc_pct", "60%")[0] == 60
    with pytest.raises(ValidationError):
        validate_value("fin.senior_ltc_pct", 95)
    with pytest.raises(ValidationError):
        validate_value("dev.stories", 7.5)
    with pytest.raises(ValidationError):
        validate_value("not.a.field", 1)
    _, warns = validate_value("fin.senior_ltc_pct", 0.6)
    assert warns  # 0.6 for a percent field is flagged


def test_unit_mix_validation():
    with pytest.raises(ValidationError):
        validate_unit_mix([{"name": "A", "size": 80, "share_pct": 60}, {"name": "B", "size": 100, "share_pct": 30}])
    mix, _ = validate_unit_mix([{"name": "A", "size": 80, "share_pct": 100}])
    assert mix[0]["size"] == 80


# ---------------------------------------------------------------- sustainability
def test_build_to_sell_savings_go_to_buyer():
    p, a = POLANCO["profile"], deepcopy(POLANCO["assumptions"])
    ev = evaluate(p, a, [{**m, "sale_premium_pct": 0} for m in a["sustainability_measures"]])
    for row in ev["measures"]:
        assert row["beneficiary"] == "buyer"
        if row["capex"] > 0:
            assert row["delta_profit"] < 0  # no premium → developer only pays the capex


def test_build_to_rent_savings_raise_noi():
    p, a = NARVARTE["profile"], deepcopy(NARVARTE["assumptions"])
    off = run_model(p, {**a, "sustainability_measures": [{**m, "enabled": False} for m in a["sustainability_measures"]]})
    on = run_model(p, a)
    assert on["metrics"]["stabilized_noi"] > off["metrics"]["stabilized_noi"]


def test_sustainability_optimizer_respects_budget():
    p, a = NARVARTE["profile"], deepcopy(NARVARTE["assumptions"])
    res = optimize(p, a, a["sustainability_measures"], budget=5_000_000, objective="co2")
    assert res["best"]["capex"] <= 5_000_000
    assert res["evaluated"] > 1


# ---------------------------------------------------------------- asset management
def test_asset_management_flags_overrun_and_reforecasts():
    p, a = POLANCO["profile"], deepcopy(POLANCO["assumptions"])
    base = run_model(p, a)
    plan_cost = [m["outflow"] - m["land_acq"] for m in base["months"]]
    actuals = [{"month": t, "cost": plan_cost[t] * 1.15, "units_sold": 1.5 if t >= 5 else 0, "avg_price_per_area": 110_000,
                "progress_pct": None} for t in range(1, 15)]
    res = analyze(p, a, actuals, base)
    assert res["status"] == "ok"
    assert any(x["area"] == "Construction budget" and x["level"] == "red" for x in res["alerts"])
    assert res["updated"]["total_cost"] > base["metrics"]["total_cost"]
