# Build status (as of 24 Oct 2026)

## Complete and tested

| Area | What works | Evidence |
|---|---|---|
| Project creation | 4-step wizard with dynamic questions (residential ground-up, acquisition/renovation, industrial details, mixed-use primary component); chat can create a project from a sentence | wizard screenshot; chat test "Natural-language project creation" |
| Property & zoning | Map (Leaflet/OSM + geocoding), Regulatory agent with verified / preliminary / not-found labels and sources, manual fallback, capacity calculation, compliance checks, legal-override confirmation and noncompliance flag, hypothetical copy | `research_polanco_regulatory.json`, `test_relaxing_a_researched_legal_limit_requires_confirmation` |
| Development config | Building inputs, unit-mix editor, calculated units / saleable area / parking, unit-mix optimizer, saved configurations with side-by-side comparison | page screenshot, `test_units_are_derived_from_design` |
| Market & revenue | Market agent comps (asking vs transaction), code-computed price/m² stats, exclude/include, proposal of base price; sales model (premiums, discounts, escalation, absorption, cancellations, presales, deposit/installments/closing, commissions, marketing); rental model (GPR → EGI → NOI, lease-up, growth, exit cap) | `research_polanco_market.json` |
| Budget & schedule | Acquisition, hard (category split), soft, commercial, contingency, escalation, developer fee; per m² / per unit / % columns; S-curve monthly spend; timeline | engine tests (budget sums to total) |
| Financing | Equity → mezz → senior with LTC sizing (iterative), interest on actual monthly balance, capitalization, fees, sweep, maturity/balloon, funding gap, covenants (LTC, LTV, presales, DSCR), waterfall (ROC → pref → promote) | `test_interest_is_charged_on_actual_balance`, waterfall tests |
| Financial model | Monthly cash flow, TDC, GDV, profit, margins, project/equity IRR, MOIC, NPV, peak funding/equity, DSCR, cash-on-cash; scenarios (base/upside/downside + custom saved), tornado, heatmap, break-even, reverse underwriting | 27 engine tests |
| Sustainability | 8 measures, beneficiary-aware (BTS buyer vs BTR owner), lifecycle NPV/IRR/payback/CO₂, per-measure developer impact, budget optimizer (exhaustive), frontier chart | `test_build_to_sell_savings_go_to_buyer`, `test_build_to_rent_savings_raise_noi` |
| Investment Committee | 2 parallel challengers → chair; deterministic guardrails; number check; memo page with print | `ic_project_1.json` (Invest with conditions), `ic_project_2.json` (Reject) |
| Asset management | Actuals entry, variance vs plan, deterministic reforecast, alerts (overrun, sales, schedule, liquidity, maturity, covenants), AI commentary, portfolio dashboard with concentration | `test_asset_management_flags_overrun_and_reforecasts` |
| Chatbot | 14 tools on the real store/engine; auto-applies ordinary edits; material → pending + confirm card; undo; clarification; English/Spanish; links to pages; live tool chips | `docs/evidence/chat_tests.md` (12 live cases) |
| Speech-to-text | Mic button (Web Speech API, en-US / es-MX), status, permission errors, fallback message, transcript editable before send, no audio stored | **manual test in Chrome still to be done by the user** |
| Assumption Control Center & audit | All variables with value/unit/source/date/verification/last change, approve/reject proposals, suggested defaults (labeled unverified), history with undo, pending confirmations | `test_undo_restores_previous_values_and_provenance` |
| Token efficiency | Limits (specialists, tool calls, requests, tokens, USD), safe stop + continue with permission, research cache, ledger, Usage page with projections | `test_specialist_call_limit_stops_the_turn`, live limit demo |
| Deliverables | README, `.env.example`, public repo, report.html (14 printed pages), slides.html (9 slides, reveal.js), fresh-clone dry run (47 s, 43 tests pass) | repo |

## Partially implemented (simpler working version, documented)

* Commercial / industrial / mixed-use: shared area-based rent model; industrial and commercial physical attributes are captured as information; mixed-use models the primary component.
* Waterfall: one hurdle (no multi-tier IRR hurdles or catch-up).
* Absorption: one total pace (the optimizer holds it constant across mixes).
* Lender comparison: the Financing agent lists public lender programs; no lender quotes (by design).

## Not done / needs the user

* **Real user test** (protocol in report §7.3): run with a real estate professional, record time before/after and feedback in `docs/evidence/user_test.md`.
* **Microphone test** in Chrome/Edge (the headless test browser cannot speak).
* Optional: 2–3 minute demo video; online hosting.
