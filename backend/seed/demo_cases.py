"""Three FICTIONAL demonstration cases (Mexico City). Not real projects, not investment advice.

Assumption values are illustrative planning figures chosen to be plausible for CDMX in 2026.
Every value is tagged source="demo" so the UI labels it as fictional.
"""

from __future__ import annotations

from copy import deepcopy

COMMON_SALE = {
    "site.transfer_tax_pct": 4.5, "site.legal_notary_pct": 1.5, "site.brokerage_pct": 1.0, "site.due_diligence": 1_500_000,
    "dev.buildings": 1, "dev.parking_area_per_space": 28, "dev.quality": "high",
    "rev.floor_view_premium_pct": 3, "rev.terrace_value_pct": 40, "rev.discount_pct": 2, "rev.escalation_pct": 5,
    "rev.cancellation_pct": 5, "rev.sales_start_offset": -3, "rev.deposit_pct": 10, "rev.installments_pct": 20,
    "rev.closing_pct": 70, "rev.commission_pct": 3, "rev.marketing_pct": 2,
    "cost.design_pct": 5, "cost.permits_pct": 2.5, "cost.pm_supervision_pct": 3.5, "cost.insurance_other_pct": 1.5,
    "cost.contingency_pct": 5, "cost.escalation_pct": 5, "cost.developer_fee_pct": 3,
    "fin.senior_rate_type": "floating", "fin.reference_rate_pct": 7.25, "fin.senior_spread_pct": 3.5,
    "fin.origination_fee_pct": 1.0, "fin.commitment_fee_pct": 0.5, "fin.interest_capitalized": True,
    "fin.senior_term_months": 42, "fin.sweep_pct": 100, "fin.mezz_ltc_pct": 0,
    "fin.sponsor_equity_share_pct": 20, "fin.pref_return_pct": 10, "fin.promote_pct": 20,
    "fin.max_ltc_covenant_pct": 60, "fin.max_ltv_covenant_pct": 45, "fin.min_presales_pct": 30, "fin.min_dscr": 1.25,
    "val.discount_rate_pct": 12, "val.equity_discount_rate_pct": 18,
}

SUSTAINABILITY_MEASURES = [
    {"key": "solar_pv", "name": "Rooftop solar PV (common areas)", "enabled": False, "capex": 2_400_000, "life_years": 25,
     "maintenance_annual": 30_000, "energy_kwh_annual": 95_000, "water_m3_annual": 0, "co2_t_annual": 41,
     "savings_annual": 330_000, "sale_premium_pct": 0.3, "rent_premium_pct": 0.0, "status": "preliminary",
     "source": "Fictional demo estimate: ~60 kWp at ~1,580 kWh/kWp/yr; CFE commercial tariff ~3.5 MXN/kWh; grid factor 0.438 tCO2/MWh (CRE 2024 factor; verify current)."},
    {"key": "efficient_hvac", "name": "High-efficiency HVAC / heat pumps", "enabled": False, "capex": 3_100_000, "life_years": 15,
     "maintenance_annual": 25_000, "energy_kwh_annual": 120_000, "water_m3_annual": 0, "co2_t_annual": 52,
     "savings_annual": 300_000, "sale_premium_pct": 0.4, "rent_premium_pct": 0.5, "status": "preliminary",
     "source": "Fictional demo estimate: inverter heat pumps vs standard split units, ~30% HVAC energy saving."},
    {"key": "insulation", "name": "Improved envelope insulation & glazing", "enabled": False, "capex": 4_200_000, "life_years": 40,
     "maintenance_annual": 0, "energy_kwh_annual": 70_000, "water_m3_annual": 0, "co2_t_annual": 31,
     "savings_annual": 180_000, "sale_premium_pct": 0.5, "rent_premium_pct": 0.5, "status": "preliminary",
     "source": "Fictional demo estimate: low-e double glazing + roof insulation."},
    {"key": "water_saving", "name": "Low-flow fixtures & water metering", "enabled": False, "capex": 650_000, "life_years": 15,
     "maintenance_annual": 5_000, "energy_kwh_annual": 6_000, "water_m3_annual": 4_200, "co2_t_annual": 3,
     "savings_annual": 160_000, "sale_premium_pct": 0.1, "rent_premium_pct": 0.0, "status": "preliminary",
     "source": "Fictional demo estimate: ~25% potable water reduction; SACMEX tariff assumption ~35 MXN/m³."},
    {"key": "rainwater", "name": "Rainwater harvesting & reuse", "enabled": False, "capex": 1_300_000, "life_years": 25,
     "maintenance_annual": 20_000, "energy_kwh_annual": 0, "water_m3_annual": 1_800, "co2_t_annual": 1,
     "savings_annual": 65_000, "sale_premium_pct": 0.1, "rent_premium_pct": 0.0, "status": "preliminary",
     "source": "Fictional demo estimate: CDMX ~800 mm/yr rainfall on ~1,350 m² roof, 85% capture, mostly May–Oct."},
    {"key": "led_controls", "name": "LED lighting & occupancy controls", "enabled": False, "capex": 450_000, "life_years": 12,
     "maintenance_annual": 0, "energy_kwh_annual": 38_000, "water_m3_annual": 0, "co2_t_annual": 17,
     "savings_annual": 130_000, "sale_premium_pct": 0.0, "rent_premium_pct": 0.0, "status": "preliminary",
     "source": "Fictional demo estimate: common-area and parking lighting."},
    {"key": "low_carbon_concrete", "name": "Low-carbon concrete & steel", "enabled": False, "capex": 2_800_000, "life_years": 50,
     "maintenance_annual": 0, "energy_kwh_annual": 0, "water_m3_annual": 0, "co2_t_annual": 0,
     "embodied_co2_t": 950, "savings_annual": 0, "sale_premium_pct": 0.2, "rent_premium_pct": 0.0, "status": "preliminary",
     "source": "Fictional demo estimate: ~20% embodied-carbon reduction in structure (one-time, not operating)."},
    {"key": "edge_cert", "name": "EDGE / LEED certification", "enabled": False, "capex": 900_000, "life_years": 10,
     "maintenance_annual": 40_000, "energy_kwh_annual": 0, "water_m3_annual": 0, "co2_t_annual": 0,
     "savings_annual": 0, "sale_premium_pct": 1.0, "rent_premium_pct": 1.0, "status": "preliminary",
     "source": "Fictional demo estimate: certification and commissioning fees; premium is an assumption to test, not a verified market fact."},
]


CASES = [
    {
        "profile": {
            "name": "Polanco Residences (fictional)", "country": "Mexico", "state": "Ciudad de México", "city": "Mexico City",
            "neighborhood": "Polanco V Sección", "address": "Fictional lot near Calle Lope de Vega, Polanco, Miguel Hidalgo",
            "lat": 19.4335, "lon": -99.1950, "currency": "MXN", "area_unit": "m²", "property_type": "residential",
            "strategy": "ground_up", "business_model": "build_to_sell", "ownership_status": "under_contract",
            "horizon_years": 5, "demo": True, "demo_story": "Attractive returns: prime location, moderate leverage, strong presales.",
        },
        "assumptions": {
            **COMMON_SALE,
            "site.land_area": 1_800, "site.land_price": 265_000_000,
            "reg.max_stories": 8, "reg.min_open_area_pct": 25, "reg.max_underground_levels": 4,
            "reg.parking_max_per_unit": 3,
            "dev.stories": 8, "dev.levels_below": 3, "dev.efficiency_pct": 82, "dev.amenity_area": 250,
            "dev.parking_spaces": 112, "cost.hard_per_area": 24_000, "cost.below_grade_per_area": 14_000,
            "cost.demolition": 2_500_000, "cost.infrastructure_fees": 6_000_000,
            "rev.price_per_area": 108_000, "rev.absorption_per_month": 3.0,
            "sch.predev_months": 8, "sch.construction_months": 24,
            "fin.senior_ltc_pct": 45,
            "unit_mix": [
                {"name": "1 BR", "bedrooms": 1, "bathrooms": 1.5, "size": 75, "share_pct": 20, "terrace": 8, "premium_pct": 6},
                {"name": "2 BR", "bedrooms": 2, "bathrooms": 2, "size": 115, "share_pct": 50, "terrace": 12, "premium_pct": 0},
                {"name": "3 BR", "bedrooms": 3, "bathrooms": 3.5, "size": 165, "share_pct": 30, "terrace": 20, "premium_pct": -3},
            ],
            "sustainability_measures": deepcopy(SUSTAINABILITY_MEASURES),
        },
        "actuals": "polanco",
    },
    {
        "profile": {
            "name": "Del Valle Tower (fictional)", "country": "Mexico", "state": "Ciudad de México", "city": "Mexico City",
            "neighborhood": "Del Valle Centro", "address": "Fictional lot near Av. Insurgentes Sur, Del Valle, Benito Juárez",
            "lat": 19.3870, "lon": -99.1700, "currency": "MXN", "area_unit": "m²", "property_type": "residential",
            "strategy": "ground_up", "business_model": "build_to_sell", "ownership_status": "negotiating",
            "horizon_years": 5, "demo": True,
            "demo_story": "High risk: thin margin, 60% LTC, slow absorption, long construction, short loan maturity.",
        },
        "assumptions": {
            **COMMON_SALE,
            "site.land_area": 1_200, "site.land_price": 96_000_000,
            "reg.max_stories": 10, "reg.min_open_area_pct": 20, "reg.min_land_per_unit": 12,
            "dev.stories": 10, "dev.levels_below": 3, "dev.efficiency_pct": 80, "dev.amenity_area": 180,
            "dev.parking_spaces": 100, "cost.hard_per_area": 21_500, "cost.below_grade_per_area": 13_500,
            "cost.escalation_pct": 7, "cost.contingency_pct": 4,
            "rev.price_per_area": 68_000, "rev.absorption_per_month": 2.0, "rev.escalation_pct": 3.5,
            "sch.predev_months": 10, "sch.construction_months": 28,
            "fin.senior_ltc_pct": 60, "fin.senior_spread_pct": 4.25, "fin.senior_term_months": 36,
            "unit_mix": [
                {"name": "1 BR", "bedrooms": 1, "bathrooms": 1, "size": 58, "share_pct": 35, "terrace": 0, "premium_pct": 5},
                {"name": "2 BR", "bedrooms": 2, "bathrooms": 2, "size": 82, "share_pct": 50, "terrace": 4, "premium_pct": 0},
                {"name": "3 BR", "bedrooms": 3, "bathrooms": 2, "size": 110, "share_pct": 15, "terrace": 6, "premium_pct": -3},
            ],
            "sustainability_measures": deepcopy(SUSTAINABILITY_MEASURES),
        },
    },
    {
        "profile": {
            "name": "Narvarte Green Rentals (fictional)", "country": "Mexico", "state": "Ciudad de México", "city": "Mexico City",
            "neighborhood": "Narvarte Poniente", "address": "Fictional lot near Calle Diagonal San Antonio, Narvarte, Benito Juárez",
            "lat": 19.3985, "lon": -99.1580, "currency": "MXN", "area_unit": "m²", "property_type": "residential",
            "strategy": "ground_up", "business_model": "build_to_rent", "ownership_status": "owned",
            "horizon_years": 8, "demo": True,
            "demo_story": "Sustainability matters: build-to-rent, so energy and water savings accrue to the owner's NOI.",
        },
        "assumptions": {
            **COMMON_SALE,
            "site.land_area": 1_500, "site.land_price": 70_000_000,
            "reg.max_stories": 7, "reg.min_open_area_pct": 25,
            "dev.stories": 7, "dev.levels_below": 2, "dev.efficiency_pct": 80, "dev.amenity_area": 200,
            "dev.parking_spaces": 70, "cost.hard_per_area": 18_500, "cost.below_grade_per_area": 13_000,
            "rent.rent_per_area_month": 420, "rent.vacancy_pct": 5, "rent.concessions_pct": 1, "rent.opex_pct_egi": 28,
            "rent.growth_pct": 4.5, "rent.lease_up_months": 12, "rent.exit_cap_pct": 6.25, "rent.selling_costs_pct": 2,
            "rent.hold_years": 5, "sch.predev_months": 8, "sch.construction_months": 22,
            "fin.senior_ltc_pct": 50, "fin.senior_term_months": 120, "fin.amortization_years": 25,
            "unit_mix": [
                {"name": "Studio", "bedrooms": 0, "bathrooms": 1, "size": 45, "share_pct": 30, "terrace": 0, "premium_pct": 0},
                {"name": "1 BR", "bedrooms": 1, "bathrooms": 1, "size": 60, "share_pct": 45, "terrace": 0, "premium_pct": 0},
                {"name": "2 BR", "bedrooms": 2, "bathrooms": 2, "size": 85, "share_pct": 25, "terrace": 0, "premium_pct": 0},
            ],
            "sustainability_measures": [
                {**m, "enabled": m["key"] in ("solar_pv", "efficient_hvac", "water_saving", "led_controls", "edge_cert")}
                for m in deepcopy(SUSTAINABILITY_MEASURES)
            ],
        },
    },
]
