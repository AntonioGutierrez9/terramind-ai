# Agents, prompts and tools

The prompts live in `backend/prompts/*.md` and are loaded at runtime, so this document and the code cannot drift apart.
Model: **gpt-6-luna** through Portkey (OpenAI Responses API, which this model needs for tools), with `reasoning_effort=low`.

## Organization

```
User ── chat panel (text or 🎤 speech-to-text) ──► Investment Manager (only agent in the chat loop)
                                                   │  structured tools ──► store (validated write path) ──► SQLite
                                                   │                    └► deterministic engine (Financial Modeling "agent")
                                                   └─ request_research (depth 1, ≤ N per turn, cached)
                                                         ├─ Regulatory & Development ─┐
                                                         ├─ Market Research           │ web_search only,
                                                         ├─ Cost & Construction       │ structured output,
                                                         ├─ Financing                 │ no write tools,
                                                         └─ Sustainability ───────────┘ cannot delegate
UI button / chat ──► Investment Committee: [Underwriting challenger ‖ Capital & Risk challenger] ──► Chair ──► guardrails
UI button ─────────► Asset Management: deterministic variance + reforecast ──► LLM commentary
```

There are no cycles. Specialists have no delegation tool, so delegation depth is 1 by construction, and the HW5 problem of runaway delegation loops can't happen.

## 1. Investment Manager (`backend/app/agents/manager.py`, prompt `investment_manager.md`)

| Tool | What it does | Writes? |
|---|---|---|
| `describe_variables(section?, search?)` | Registry keys, labels, units, materiality and current values | no |
| `get_results(view)` | Engine outputs: summary, budget, schedule, covenants, sensitivity, scenarios, waterfall, design | no |
| `update_assumptions(changes[], reason)` | Validated edits (`set` / `pct` / `add`). Ordinary edits apply now; **material edits become pending** | yes (through `store.apply_changes`) |
| `update_profile(fields)` | Location, type, strategy, business model, checked against allowed choices | yes |
| `apply_zoning_code(code)` | Parses a CDMX code such as `H/4/20/M` (deterministic, `engine/zoning.py`) into legal limits; regulatory, so always **pending** | pending only |
| `scale_unit_sizes(target_average_size)` | "Change the average apartment size to 110 m²" | yes |
| `set_unit_mix(unit_types[], reason)` | Replace the unit mix (shares must add to 100%) | yes |
| `set_sales_phases(phases[], reason)` | Sales pace with a shape over time (e.g. launch peak + delivery peak), anchored to closing / sales start / construction start / delivery | yes |
| `set_price_phases(phases[], reason)` | Launch discounts or delivery premiums for contracts signed in a period | yes |
| `set_land_payments(payments[], reason)` | Land paid in installments (must add to 100%) | yes |
| `set_custom_cash_flows(flows[], reason)` | Any one-off cost or revenue the standard inputs do not cover | yes |
| `add_custom_variable(variable, reason)` / `remove_custom_variable(key)` | New user-defined inputs with a deterministic effect (cost per unit / m², % of hard cost or of collections, monthly or one-off cost/income, income per unit sold, price %, or tracked only) | yes |
| `export_excel_model()` | Link to download the live Excel model (`app/excel_export.py`) | no |
| `recommend_improvements()` | Ranked levers tested on the full model, blocking issues first, plus a combined package (`engine/advisor.py`) | no |
| `apply_recommendation(lever_id)` | Applies a lever or the package (material changes stay pending) | yes |
| `undo_last_change()` | Reverts the last batch of changes | yes |
| `request_status_change(status, reason)` | Approve / add to portfolio. **Always pending** | pending only |
| `create_project(...)` | New project from a natural-language description | yes |
| `what_if(changes[], schedules…)` | Full model re-run with temporary scalar and/or schedule overrides; nothing saved | no |
| `solve_for_target(key, metric, target)` | Reverse underwriting by bisection on the full model | no |
| `compare_sustainability(measure_keys?)` | With vs. without measures, beneficiary-aware | no |
| `request_research(kind, request?)` | Delegate to one specialist. Results become pending proposals | proposals only |
| `run_investment_committee()` | IC process (three LLM calls) | memo |
| `list_documents()` | Files uploaded to the project with their analysis summary | no |
| `analyze_document(document_id)` | Runs the Document agent (or reuses the stored analysis) | proposals only |
| `ask_document(document_id, question)` | Answer from the file with verbatim quotes (contract questions, permit dates, model inputs) | no |

There is **no tool that confirms pending changes or approves proposals.** Those endpoints are reachable only from UI buttons.

## 2. Research specialists (`backend/app/agents/specialists.py`)

| Agent | Output schema | Post-processing (deterministic) |
|---|---|---|
| Regulatory & Development | `ZoningFindings`: findings tagged `verified` / `preliminary` / `not_found` and a **level** (parcel → corridor/colonia → alcaldía program → citywide rule) with source URLs, plus a list of what is missing | Numeric `reg.*` findings become pending proposals. A zoning code found by research is expanded by code into FAR and density. Approving one sets the legal reference used to detect overrides |
| Market Research | `Comparables` (asking vs. transaction) | Comps without a URL are dropped. **Price per m², median and quartiles are computed by code.** The proposed base price is the median of included comps, labeled preliminary |
| Cost & Construction | `CostBenchmark` (published benchmark / indicative) | Mapped to `cost.*` proposals, labeled "estimate, not a contractor quote" |
| Financing | `RateBenchmark` (published rate / indicative / lender offer) | Anything labeled `lender_offer` is relabeled `indicative_assumption`, because a web page is not an offer |
| Sustainability | `SusBenchmark` | Informational table with sources |

All specialist text is **scrubbed** for instruction-like phrases (`runtime.scrub_obj`), and suspicious fields are flagged in the UI. Results are **cached** by a hash of agent + normalized request (14 days), and an identical request in the same turn is blocked.

## 2b. Document agent (`backend/app/agents/document_agent.py`, prompt `document.md`)

Reads uploaded files: zoning certificates, permits, contracts, appraisals, budgets and Excel models. Text is extracted deterministically with pypdf, openpyxl and python-docx; scans and photos are read by the vision-capable model. Output `DocumentAnalysis`: type, summary, key facts with locations, value proposals (registry keys) each with a **verbatim quote**, zoning code, permit details, contract review (parties, key terms, deadlines, payment terms, risks with severity and suggestion, missing protections, questions for counsel) and Excel model notes. Guardrails:

* no tools; file text is wrapped as untrusted data and scrubbed; instruction-like text in the file is flagged to the user
* every proposed value is validated by the registry, and code checks that the quote **and its number** appear in the extracted text, otherwise the value is discarded
* a zoning code found in the document is expanded deterministically (`engine/zoning.py`)
* accepted values become pending proposals (approve or reject on the Documents page or in the Assumption Center)
* `ask_document` picks relevant chunks of long files by keyword overlap and marks each quote verified or not

## 3. Financial Modeling (deterministic, no LLM)

`backend/engine/`: `registry.py` (variables), `validation.py`, `finance.py` (IRR / NPV / S-curve), `model.py` (monthly pro forma, capital stack, waterfall, covenants), `analysis.py` (scenarios, tornado, heatmap, solver, unit-mix optimizer), `sustainability.py`, `asset_mgmt.py`. It has 27 unit tests, including accounting identities.

## 4. Investment Committee (`backend/app/agents/committee.py`, prompt `committee.md`)

1. Code builds a **packet** from the engine: metrics, covenants, scenarios, top sensitivities, assumption provenance counts, comps statistics.
2. **Underwriting challenger** and **Capital & Risk challenger** run in parallel and return structured concerns with evidence and a suggested test.
3. The **Chair** returns `ICMemo` (recommendation, rationale, conditions, risks and mitigations, diligence).
4. **Guardrails (code):** no complete model → "Insufficient information" with no LLM call. A covenant breach, funding gap or noncompliance downgrades "Invest". Every percentage in the memo text is checked against the packet, and unmatched numbers are flagged as `unverified_numbers`.

## 5. Asset Management

`engine/asset_mgmt.analyze` compares actuals with the underwriting, derives reforecast drivers (cost factor, sales pace, price factor, schedule delay), re-runs the full model and raises alerts. The LLM (`asset_manager.md`) only explains the variance table and recommends actions.

## 6. Limits and the token ledger (`backend/app/agents/runtime.py`)

| Limit (per chat turn) | Default | Enforced by |
|---|---|---|
| Specialist calls | 2 | `run_specialist` raises `LimitReached` |
| Tool calls | 12 | PydanticAI `UsageLimits(tool_calls_limit)` |
| Model requests | 10 | `UsageLimits(request_limit)` |
| Tokens | 250,000 | `UsageLimits(total_tokens_limit)` + ledger |
| USD | $0.05 | ledger checked after each model step and before each specialist |

When a limit is hit, the turn stops safely. Changes already made are kept and listed, and the chat offers **Continue with higher limits (2×)**, which is the user's permission (capped at 4×). Every model call is written to `token_usage` with input, cached, output, web searches, USD and seconds. The **AI Usage** page and the report use these measured numbers.
