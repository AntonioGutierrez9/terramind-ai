"""The Excel export is a live model: formulas linked to named Assumptions, no hard-coded results in calculation tabs."""
import io
from copy import deepcopy

from openpyxl import load_workbook

from app.excel_export import export_project
from engine.model import run_model
from seed.demo_cases import CASES


def _wb(case):
    proj = {"id": 1, "name": case["profile"]["name"], "profile": case["profile"], "assumptions": deepcopy(case["assumptions"]), "meta": {}}
    res = run_model(proj["profile"], proj["assumptions"])
    return load_workbook(io.BytesIO(export_project(proj, res, None))), res


def test_workbook_structure_and_named_inputs():
    wb, _ = _wb(CASES[0])
    for tab in ("Cover", "Outputs", "Assumptions", "Development", "Construction", "Sales", "Cash Flow", "Waterfall", "Budget", "Sensitivity"):
        assert tab in wb.sheetnames
    names = set(wb.defined_names.keys())
    assert {"in_site_land_price", "in_cost_hard_per_area", "in_rev_absorption_per_month", "TotalCost", "M_Lev", "M_Unlev"} <= names
    assert wb.calculation.iterate  # debt sizing is circular by design
    assert len(wb["Outputs"]._charts) >= 4


def test_calculation_tabs_contain_formulas_not_values():
    wb, _ = _wb(CASES[0])
    for tab in ("Construction", "Sales", "Cash Flow", "Waterfall"):
        ws = wb[tab]
        numeric_hardcodes = []
        for row in ws.iter_rows(min_row=5, min_col=4, max_col=40):
            for c in row:
                if isinstance(c.value, (int, float)) and not (c.row == 4):
                    numeric_hardcodes.append(c.coordinate)
        assert not numeric_hardcodes, f"{tab} has hard-coded numbers at {numeric_hardcodes[:5]}"
    out = wb["Outputs"]
    assert str(out["B6"].value).startswith("=")  # KPIs are formulas


def test_assumptions_carry_the_project_values():
    wb, _ = _wb(CASES[0])
    ref = wb.defined_names["in_site_land_price"].attr_text.split("!")[1].replace("$", "")
    assert wb["Assumptions"][ref].value == CASES[0]["assumptions"]["site.land_price"]
    ref = wb.defined_names["in_fin_senior_ltc_pct"].attr_text.split("!")[1].replace("$", "")
    assert abs(wb["Assumptions"][ref].value - CASES[0]["assumptions"]["fin.senior_ltc_pct"] / 100) < 1e-12  # percent as fraction


def test_rental_case_exports_rental_tab():
    wb, _ = _wb(CASES[2])
    assert wb["Rental"].sheet_state == "visible"
