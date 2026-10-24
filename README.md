# TerraMind AI

**An AI-assisted real estate investment platform that follows the steps a development fund takes to evaluate a project:**
site → zoning capacity → design → market → budget → capital stack → monthly cash-flow model → investment committee → asset management.
AI agents research and propose assumptions with sources, the user approves them, and a **deterministic Python engine** calculates every financial number.

*Yale SOM · AI Foundations for Managers (MGT 409), Fall 2026 · Final project by Antonio Gutiérrez García*

> All demo projects are **fictional** and use illustrative assumptions. TerraMind is decision support, not investment advice.
> It never executes investments, payments or financing transactions.

---

## Quick start (about 3 minutes, Python only)

The React frontend is already built (`frontend/dist`) and is served by the Python backend, so **Node.js is not needed to run the app.**

**Requirements:** Python 3.11+ (tested with 3.12 and 3.14) and internet access for the AI features.

```bash
git clone https://github.com/AntonioGutierrez9/terramind-ai.git
cd terramind-ai
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS / Linux:
source .venv/bin/activate
pip install -r requirements.txt
python run.py
```

Then open **http://localhost:8000** (`run.py` opens it for you). Choose **Continue as guest** (fastest) or **Create account**. Each guest or account gets a private copy of three fictional demo projects. Signed-in users can remove projects they don't want (trash icon on the Portfolio page, with a confirmation); guest workspaces cannot remove projects.

### API key (.env)

TerraMind looks for a `.env` file **in the repo folder first, then in the folder above it** (then further parent folders). It reads either key:

```
PORTKEY_API_KEY=...     # course key, routed through Portkey, model gpt-6-luna
# or
OPENAI_API_KEY=...      # your own OpenAI key
```

See `.env.example`. **Without a key, the whole financial platform still works.** Only the AI features (chat, research agents, investment committee, AI commentary) are disabled, and the UI says so.

### Optional

```bash
python run.py --port 8001 --no-browser       # another port, no browser
cd backend && python -m pytest -q            # 67 tests: engine math, schedules, user variables, advisor, Excel export, safety controls, accounts and data isolation
cd frontend && npm install && npm run dev    # frontend dev server on :5173 (proxies /api to :8000)
cd frontend && npm run build                 # rebuild frontend/dist
```

To start from a clean database, delete `backend/data/terramind.db`. It is re-seeded on the next start.

---

## Accounts and guests

* **Create account / Sign in:** projects, chats and files are private to your account and available whenever you sign in again.
  Passwords are hashed with PBKDF2-SHA256 (standard library), and login is a signed HttpOnly session cookie (same approach as Homework 4).
* **Continue as guest:** a private workspace tied to this browser. Click **Save my work** anytime to create an account; your guest projects move into it.
* Every project, document and pending change is checked against the caller's session on every request. Other users' ids return 404.
* Optional `SESSION_SECRET` in `.env`; if absent, a random secret is generated once and stored in the local database.

## What you can do (a 5-minute tour)

1. **Portfolio**: three fictional CDMX projects with returns, equity concentration and early-warning alerts.
2. Open **Polanco Residences → Financial Model**: equity IRR, MOIC, NPV, peak equity, monthly cash flows, scenarios, a tornado chart, an IRR heatmap, break-even, and reverse underwriting ("max land price for an 18% equity IRR").
3. **Property & Zoning**: editable property facts, map, and zoning research by the Regulatory agent (verified vs. preliminary, from parcel level up to citywide rules, with sources). Type the zoning code from your certificate (e.g. `H/4/20/M`) and TerraMind converts it into legal limits deterministically. Also shows development capacity, and noncompliance flags if you override a legal limit.
4. **Development Config**: unit mix editor, unit-mix optimizer, saved alternative configurations.
5. **Excel model download** (top bar, or ask the assistant): a live financial model where every number is a formula linked to one Assumptions tab. Tabs: Outputs (KPIs, annual summary, charts for investors), Assumptions, Development, Construction, Sales or Rental, Cash Flow (with financing), Waterfall, Budget, Sensitivity. Change one assumption and everything updates. It was verified in Microsoft Excel against the engine (`docs/evidence/excel_reconciliation.md`); a sample is in `docs/samples/`.
6. **Recommendations**: the advisor tests levers (land, pricing, sales strategy, cost, schedule, design, leverage, sustainability) on the full model, ranks them by computed impact with blocking issues first, and applies any of them in one click; the AI writes an action plan. **New variables**: add your own inputs (e.g. a trust fee as % of sales, storage units sold per apartment) on any page or by chat; each has a defined effect on the model.
6. **Flexible model**: beyond single numbers, set **sales phases** (e.g. a launch peak and a delivery peak), **price phases** (launch discount, delivery premium), a **land payment schedule**, **custom one-off cash flows** and the **construction spending curve**, in the Market and Budget pages or just by asking the assistant.
6. **Market / Budget / Financing**: comparables (asking prices labeled as such), revenue forecast, detailed budget, S-curve schedule, capital stack, debt schedule on the actual monthly balance, covenants, equity waterfall.
6. **Sustainability**: measures with lifecycle NPV, CO₂ and beneficiary-aware developer impact, plus a budget optimizer.
7. **Investment Committee**: two challenger agents and a chair produce a memo. Every figure comes from the engine, and invented numbers are flagged.
8. **Asset Management**: actuals vs. underwriting, automatic reforecast, alerts.
9. **AI Assistant** (right panel): type or 🎤 dictate (English or Spanish), e.g. *"Increase construction costs by 10%"*, *"Change the financing structure to 40% equity and 60% debt"* (material, so you confirm with a button), *"What's the maximum we should pay for the land for an 18% equity IRR?"*
10. **Documents & Files**: upload permits, zoning certificates, contracts, appraisals, budgets or an Excel model (PDF incl. scans, XLSX, DOCX, CSV, TXT, photos). The Document agent extracts the facts, proposes values for your model (each checked verbatim against the file and pending until you approve it), reviews contracts (risks, deadlines, missing protections, questions for counsel), and answers questions with quotes. You can also attach files in the chat (📎). Fictional samples are in `docs/samples/`.
11. **Assumption Center**: every variable with its value, unit, source, date, verification and last change. You approve or reject AI proposals here. **Audit Trail** shows every change, with undo.
12. **English / Español**: the EN | ES switch in the top bar (and on the sign-in screen) changes the whole interface to Spanish; English is the default and the choice is remembered in the browser. In Spanish, the AI agents (chat, research, committee, documents, advisor) also answer in Spanish and voice input defaults to es-MX. The Spanish dictionary (`frontend/src/i18n/`) was generated once with the course model and reviewed, so switching the interface costs no tokens. The chat conversation is translated too (each message once per language, cached), so the whole thread reads in the selected language; every translated message has a *show original* link.

Voice input uses the browser's Web Speech API (Chrome or Edge). Audio is never stored. Other browsers show a fallback message.

---

## Architecture

| Layer | Tech |
|---|---|
| Frontend | React 19 + TypeScript + Vite, Recharts, Leaflet (OpenStreetMap), lucide-react |
| Backend | FastAPI, SQLite (`backend/data/terramind.db`) |
| AI | PydanticAI agents → OpenAI Responses API via Portkey (`gpt-6-luna`), native web search for research agents |
| Engine | `backend/engine/`: deterministic Python (no LLM arithmetic), 27 unit tests |

* `docs/ARCHITECTURE.md`: design, database schema, financial calculations, phases, risks, open-source review
* `docs/AGENTS_AND_TOOLS.md`: every agent, prompt, tool, limit and guardrail
* `backend/prompts/`: the actual agent prompts
* `docs/evidence/`: recorded live test runs (chatbot cases, research outputs, token usage)
* `report.html` and `slides.html`: final report and presentation (self-contained)

```
terramind-ai/
├── run.py                  # starts API + web app
├── requirements.txt
├── backend/
│   ├── app/                # FastAPI, store (validated write path), services, agents/
│   ├── engine/             # registry, validation, finance, model, analysis, sustainability, asset_mgmt
│   ├── prompts/            # agent prompts (markdown)
│   ├── seed/               # fictional demo cases
│   └── tests/              # test_engine.py, test_safety.py
├── frontend/               # React app (dist/ is committed)
└── docs/
```

## Safety controls (tested in `backend/tests/test_safety.py`)

* One validated write path for forms, chatbot and agents: types, ranges and units are checked, and unknown keys are rejected.
* **Material changes from the chatbot** (financing, rates, legal limits, approvals) become *pending* and need a UI click. The chatbot has no confirmation tool.
* **Relaxing a researched legal limit** needs explicit confirmation and flags the scenario as potentially noncompliant.
* **Research never changes the model directly.** Findings become pending proposals with source, date and verification level.
* **Prompt-injection hygiene:** web text is scrubbed and wrapped as untrusted data, and specialists have no write tools.
* Comparable prices per m² are computed by code. Web pages are never labeled as lender offers.
* IC guardrails: deterministic downgrade rules and a check that the memo's numbers match the engine.
* Limits on specialist calls, tool calls, requests, tokens and USD per turn. A run stops safely and asks permission to continue.
* Uploaded files are untrusted: text that tries to instruct AI is flagged, values need a verbatim quote that code finds in the file, and nothing changes until you approve it.
* Accounts and guests are isolated per session; data is never shared between owners.
* Full audit trail and undo.

## Open-source review and licenses

No code was copied from the suggested reference repos. They were reviewed for concepts only (see `docs/ARCHITECTURE.md` §8): pyforma (BSD-3, stale), rangekeeper (MPL-2.0, heavy dependencies), real-estate-datamap (MIT), Real-Estate-Valuation calculator (Apache-2.0), mern-yariga-dashboard (MIT).
Libraries used: pypdf (BSD-3), python-docx (MIT), openpyxl (MIT), itsdangerous (BSD-3), email-validator (Unlicense), python-multipart (Apache-2.0), FastAPI (MIT), PydanticAI (MIT), OpenAI Python SDK (Apache-2.0), Uvicorn (BSD-3), httpx (BSD-3), python-dotenv (BSD-3), React (MIT), Vite (MIT), Recharts (MIT), Leaflet (BSD-2), lucide-react (ISC), React Router (MIT). Map tiles © OpenStreetMap contributors. Geocoding by Nominatim (cached, low volume).

## Known limitations

* Parcel-level CDMX zoning usually needs the official SEDUVI portal or a *Certificado Único de Zonificación*. The agent reports what it can verify and falls back to manual entry.
* Commercial, industrial and mixed-use projects use the shared area-based rent model. Detailed multi-component mixed-use modeling is on the roadmap.
* The waterfall has one hurdle (return of capital → pref → promote). Multi-tier IRR hurdles are on the roadmap.
* Absorption is one total pace; the unit-mix optimizer holds it constant across mixes.
* Sustainability parameters are preliminary estimates, not engineering results.
