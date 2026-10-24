"""Variable registry: one definition per assumption.

Forms, chatbot validation, the Assumption Control Center and scenarios all read
this file. Percentages are stored as percent numbers (60 means 60%).
Areas and prices are in the project's area unit (m² by default) and currency.

Fields per variable
  label, section, unit, kind ("number" | "int" | "choice" | "bool" | "text")
  min / max         hard limits — values outside are rejected
  typical           (lo, hi) soft range — values outside get a warning
  material          change needs a confirmation click in the UI
  regulatory        legal limit — exceeding the researched value flags noncompliance
  required          needed before the model can run (for the listed modes)
  suggested         illustrative default the user can apply (source = "default", unverified)
"""

from __future__ import annotations

from typing import Any

SECTIONS = {
    "site": "Site & acquisition",
    "reg": "Regulation & zoning",
    "dev": "Development configuration",
    "rev": "Sales revenue",
    "rent": "Rental income",
    "cost": "Development budget",
    "sch": "Schedule",
    "fin": "Financing",
    "val": "Valuation",
}

SALE = ("sale",)
RENT = ("rent",)
BOTH = ("sale", "rent")


def _v(label, section, unit, kind="number", *, min=None, max=None, typical=None, material=False,
       regulatory=False, required=(), suggested=None, choices=None, help=""):
    return {
        "label": label, "section": section, "unit": unit, "kind": kind, "min": min, "max": max,
        "typical": typical, "material": material, "regulatory": regulatory,
        "required": list(required), "suggested": suggested, "choices": choices, "help": help,
    }


REGISTRY: dict[str, dict[str, Any]] = {
    # ---- Site & acquisition -------------------------------------------------
    "site.land_area": _v("Land area", "site", "area", min=1, max=10_000_000, typical=(150, 50_000), required=BOTH),
    "site.land_price": _v("Land / property acquisition price", "site", "currency", min=0, max=1e12, required=BOTH),
    "site.transfer_tax_pct": _v("Transfer tax (ISAI)", "site", "%", min=0, max=15, typical=(0, 6), suggested=4.5,
                                help="CDMX ISAI is progressive; ~4.5% is a common upper-bracket planning figure."),
    "site.legal_notary_pct": _v("Notary & legal fees", "site", "%", min=0, max=10, typical=(0.5, 3), suggested=1.5),
    "site.brokerage_pct": _v("Brokerage on acquisition", "site", "%", min=0, max=10, typical=(0, 4), suggested=0.0),
    "site.due_diligence": _v("Due diligence & closing (fixed)", "site", "currency", min=0, max=1e10, suggested=0.0),

    # ---- Regulation (legal limits) -----------------------------------------
    "reg.max_stories": _v("Maximum stories above ground", "reg", "stories", "int", min=1, max=200, required=SALE + RENT, regulatory=True),
    "reg.min_open_area_pct": _v("Minimum open (unbuilt) area", "reg", "%", min=0, max=95, typical=(10, 50), required=BOTH, regulatory=True,
                                help="CDMX zoning code H/4/20 means 4 stories and 20% open area."),
    "reg.max_far": _v("Maximum FAR (CUS)", "reg", "x land", min=0.1, max=60, regulatory=True,
                      help="Leave empty to derive as stories × (1 − open area %)."),
    "reg.max_height_m": _v("Maximum height", "reg", "m", min=3, max=1000, regulatory=True),
    "reg.min_land_per_unit": _v("Density: land area per dwelling", "reg", "area/unit", min=1, max=5000, regulatory=True,
                                help="e.g. CDMX density letter M = one dwelling per 50 m² of land."),
    "reg.max_units": _v("Maximum dwellings", "reg", "units", "int", min=1, max=100_000, regulatory=True),
    "reg.max_underground_levels": _v("Maximum underground levels", "reg", "levels", "int", min=0, max=20, regulatory=True),
    "reg.parking_min_per_unit": _v("Minimum parking per unit", "reg", "spaces/unit", min=0, max=5, regulatory=True),
    "reg.parking_max_per_unit": _v("Maximum parking per unit", "reg", "spaces/unit", min=0, max=5, regulatory=True),

    # ---- Development configuration -----------------------------------------
    "dev.buildings": _v("Number of buildings", "dev", "count", "int", min=1, max=100, suggested=1),
    "dev.stories": _v("Stories above ground", "dev", "stories", "int", min=1, max=200, required=BOTH),
    "dev.levels_below": _v("Underground levels", "dev", "levels", "int", min=0, max=20, suggested=1),
    "dev.footprint": _v("Building footprint", "dev", "area", min=1, max=10_000_000,
                        help="Leave empty to use the maximum allowed coverage."),
    "dev.efficiency_pct": _v("Saleable / gross efficiency", "dev", "%", min=30, max=98, typical=(70, 88), required=BOTH, suggested=80),
    "dev.parking_spaces": _v("Parking spaces", "dev", "spaces", "int", min=0, max=100_000),
    "dev.parking_area_per_space": _v("Gross area per parking space", "dev", "area/space", min=10, max=60, typical=(22, 35), suggested=28),
    "dev.amenity_area": _v("Amenity area (inside GBA)", "dev", "area", min=0, max=1_000_000, suggested=0),
    "dev.quality": _v("Construction quality", "dev", "", "choice", choices=["economic", "mid", "high", "luxury"], suggested="high"),
    "dev.existing_rentable_area": _v("Existing rentable area (acquisitions)", "dev", "area", min=0, max=10_000_000),

    # ---- Sales revenue -------------------------------------------------------
    "rev.price_per_area": _v("Base sale price", "rev", "currency/area", min=0, max=10_000_000, required=SALE, material=False),
    "rev.floor_view_premium_pct": _v("Average floor / view premium", "rev", "%", min=-30, max=50, typical=(0, 10), suggested=3),
    "rev.terrace_value_pct": _v("Terrace value vs interior m²", "rev", "%", min=0, max=100, typical=(25, 60), suggested=40),
    "rev.discount_pct": _v("Average discount", "rev", "%", min=0, max=50, typical=(0, 8), suggested=2),
    "rev.escalation_pct": _v("Annual price escalation", "rev", "%", min=-20, max=30, typical=(0, 8), suggested=5),
    "rev.absorption_per_month": _v("Sales absorption (gross)", "rev", "units/month", min=0.1, max=500, typical=(1, 20), required=SALE),
    "rev.cancellation_pct": _v("Cancellations", "rev", "%", min=0, max=60, typical=(0, 10), suggested=5),
    "rev.sales_start_offset": _v("Presales start vs construction start", "rev", "months", "int", min=-24, max=60, suggested=-3,
                                 help="Negative = presales before construction starts."),
    "rev.deposit_pct": _v("Deposit at contract", "rev", "%", min=0, max=100, suggested=10),
    "rev.installments_pct": _v("Installments during construction", "rev", "%", min=0, max=100, suggested=20),
    "rev.closing_pct": _v("Balance at delivery / closing", "rev", "%", min=0, max=100, suggested=70),
    "rev.commission_pct": _v("Sales commissions", "rev", "%", min=0, max=15, typical=(2, 6), suggested=3),
    "rev.marketing_pct": _v("Marketing & sales office", "rev", "% of revenue", min=0, max=15, typical=(1, 4), suggested=2),

    # ---- Rental income -------------------------------------------------------
    "rent.rent_per_area_month": _v("Market rent", "rent", "currency/area/month", min=0, max=100_000, required=RENT),
    "rent.vacancy_pct": _v("Stabilized vacancy", "rent", "%", min=0, max=80, typical=(3, 15), suggested=5),
    "rent.concessions_pct": _v("Rent concessions", "rent", "%", min=0, max=50, suggested=1),
    "rent.opex_pct_egi": _v("Operating expenses", "rent", "% of EGI", min=0, max=90, typical=(15, 45), suggested=30),
    "rent.growth_pct": _v("Annual rent growth", "rent", "%", min=-20, max=30, typical=(0, 6), suggested=4),
    "rent.lease_up_months": _v("Lease-up period", "rent", "months", "int", min=0, max=60, suggested=12),
    "rent.exit_cap_pct": _v("Exit cap rate", "rent", "%", min=2, max=20, typical=(5, 10), required=RENT),
    "rent.selling_costs_pct": _v("Exit selling costs", "rent", "%", min=0, max=10, suggested=2),
    "rent.hold_years": _v("Hold period after delivery", "rent", "years", "int", min=1, max=30, suggested=5),

    # ---- Development budget --------------------------------------------------
    "cost.hard_per_area": _v("Hard cost above ground", "cost", "currency/area GBA", min=0, max=1_000_000, required=BOTH),
    "cost.below_grade_per_area": _v("Hard cost below ground (parking)", "cost", "currency/area", min=0, max=1_000_000),
    "cost.demolition": _v("Demolition & site preparation (fixed)", "cost", "currency", min=0, max=1e11, suggested=0),
    "cost.infrastructure_fees": _v("Infrastructure / impact fees (fixed)", "cost", "currency", min=0, max=1e11, suggested=0),
    "cost.renovation_budget": _v("Renovation / CAPEX budget (acquisitions)", "cost", "currency", min=0, max=1e12),
    "cost.design_pct": _v("Architecture & engineering", "cost", "% of hard", min=0, max=20, typical=(3, 8), suggested=5),
    "cost.permits_pct": _v("Permits & licenses", "cost", "% of hard", min=0, max=15, typical=(1, 5), suggested=2.5),
    "cost.pm_supervision_pct": _v("Project management & supervision", "cost", "% of hard", min=0, max=15, typical=(2, 6), suggested=3.5),
    "cost.insurance_other_pct": _v("Insurance, consultants & other soft", "cost", "% of hard", min=0, max=10, suggested=1.5),
    "cost.contingency_pct": _v("Contingency", "cost", "% of hard + soft", min=0, max=30, typical=(3, 10), suggested=5),
    "cost.curve": _v("Construction spending curve", "cost", "", "choice", choices=["s_curve", "linear", "front_loaded", "back_loaded"],
                     suggested="s_curve", help="How hard costs are spread over the construction months."),
    "cost.escalation_pct": _v("Annual construction cost escalation", "cost", "%", min=-10, max=40, typical=(3, 8), suggested=5),
    "cost.developer_fee_pct": _v("Developer fee", "cost", "% of hard + soft", min=0, max=10, suggested=3),

    # ---- Schedule --------------------------------------------------------------
    "sch.predev_months": _v("Design & permits (pre-development)", "sch", "months", "int", min=0, max=60, typical=(4, 18), required=BOTH, suggested=8),
    "sch.construction_months": _v("Construction duration", "sch", "months", "int", min=1, max=120, typical=(12, 36), required=BOTH),

    # ---- Financing -------------------------------------------------------------
    "fin.senior_ltc_pct": _v("Senior debt (loan-to-cost)", "fin", "%", min=0, max=90, typical=(0, 70), material=True, suggested=50),
    "fin.senior_rate_type": _v("Senior rate type", "fin", "", "choice", choices=["floating", "fixed"], material=True, suggested="floating"),
    "fin.reference_rate_pct": _v("Reference rate (e.g. TIIE 28d)", "fin", "%", min=0, max=40, material=True),
    "fin.senior_spread_pct": _v("Senior spread over reference", "fin", "%", min=0, max=20, typical=(2, 6), material=True, suggested=3.5),
    "fin.senior_fixed_rate_pct": _v("Senior fixed rate", "fin", "%", min=0, max=40, material=True),
    "fin.origination_fee_pct": _v("Origination fee", "fin", "% of commitment", min=0, max=5, suggested=1.0),
    "fin.commitment_fee_pct": _v("Commitment fee on undrawn", "fin", "% p.a.", min=0, max=3, suggested=0.5),
    "fin.interest_capitalized": _v("Capitalize interest during construction", "fin", "", "bool", suggested=True),
    "fin.senior_term_months": _v("Senior loan maturity (from first draw)", "fin", "months", "int", min=6, max=360, suggested=36, material=True),
    "fin.sweep_pct": _v("Cash sweep to debt after delivery", "fin", "%", min=0, max=100, suggested=100),
    "fin.amortization_years": _v("Amortization (term loans, rentals)", "fin", "years", "int", min=0, max=40, suggested=25),
    "fin.mezz_ltc_pct": _v("Mezzanine (loan-to-cost)", "fin", "%", min=0, max=40, material=True, suggested=0),
    "fin.mezz_rate_pct": _v("Mezzanine rate", "fin", "%", min=0, max=40, material=True),
    "fin.sponsor_equity_share_pct": _v("Sponsor share of equity", "fin", "%", min=0, max=100, suggested=20, material=True),
    "fin.pref_return_pct": _v("Investor preferred return", "fin", "% p.a.", min=0, max=30, suggested=10),
    "fin.promote_pct": _v("Sponsor promote above pref", "fin", "%", min=0, max=50, suggested=20),
    "fin.max_ltc_covenant_pct": _v("Covenant: max LTC", "fin", "%", min=0, max=100, suggested=65),
    "fin.max_ltv_covenant_pct": _v("Covenant: max LTV (on GDV)", "fin", "%", min=0, max=100, suggested=50),
    "fin.min_presales_pct": _v("Covenant: presales before first draw", "fin", "% of units", min=0, max=100, suggested=30),
    "fin.min_dscr": _v("Covenant: minimum DSCR", "fin", "x", min=0.5, max=5, suggested=1.25),

    # ---- Valuation -----------------------------------------------------------
    "val.discount_rate_pct": _v("Discount rate (unlevered NPV)", "val", "% p.a.", min=0, max=50, typical=(8, 20), suggested=12),
    "val.equity_discount_rate_pct": _v("Equity discount rate / hurdle", "val", "% p.a.", min=0, max=60, typical=(12, 25), suggested=18),
}

# Hard-cost category split (shares of above-ground hard cost). Editable per project.
DEFAULT_HARD_COST_SPLIT = {
    "Demolition & excavation": 4.0,
    "Foundations": 8.0,
    "Structure": 27.0,
    "Façade & envelope": 9.0,
    "MEP systems": 18.0,
    "Elevators": 4.0,
    "Finishes": 19.0,
    "Amenities": 4.0,
    "Landscaping & exterior": 2.0,
    "Infrastructure & connections": 5.0,
}

# Time-varying inputs (lists). Anchors: closing (t=0), sales_start, construction_start, delivery; offset in months.
ANCHORS = ["closing", "sales_start", "construction_start", "delivery"]
SCHEDULE_KEYS = {
    "sales_phases": "Sales phases: periods with their own sales pace (units/month), e.g. a launch peak and a delivery peak",
    "price_phases": "Price phases: % price changes for contracts signed in a period, e.g. -8% launch discount, +5% at delivery",
    "land_payments": "Land payment schedule: % of the land price paid in given months (must add to 100%)",
    "custom_flows": "Custom one-off cash flows: any extra cost or revenue in a given month (fees, sale of a commercial unit, subsidy...)",
}

UNIT_TYPE_FIELDS = {
    "name": "text", "bedrooms": "int", "bathrooms": "number", "size": "number",
    "share_pct": "number", "terrace": "number", "premium_pct": "number",
}

PROFILE_CHOICES = {
    "property_type": ["residential", "commercial", "industrial", "mixed_use"],
    "strategy": ["ground_up", "acquisition", "renovation", "capex", "repositioning", "acquisition_renovation"],
    "business_model": ["build_to_sell", "develop_and_sell", "build_to_rent", "acquire_and_hold", "value_add"],
    "ownership_status": ["owned", "under_contract", "negotiating", "identified"],
}


def model_mode(profile: dict) -> str:
    """'sale' for for-sale business models, 'rent' for hold / rental models."""
    return "sale" if profile.get("business_model") in ("build_to_sell", "develop_and_sell") else "rent"


def is_ground_up(profile: dict) -> bool:
    return profile.get("strategy", "ground_up") == "ground_up"


def describe(key: str) -> dict:
    spec = REGISTRY[key]
    return {"key": key, **spec, "section_label": SECTIONS[spec["section"]]}


def keys_for_section(section: str) -> list[str]:
    return [k for k, v in REGISTRY.items() if v["section"] == section]
