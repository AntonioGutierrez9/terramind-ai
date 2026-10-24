# TerraMind AI walkthrough video: what was actually demonstrated

Video: `output/terramind_demo.mp4` (1920×1080, 30 fps, H.264 + AAC, 2:54). Subtitles: `output/terramind_demo.srt`.
Recorded on 2026-10-24 from the real running app: a separate local server with an empty database and a fictional demo account (`demo.investor@terramind.example`). No real user data, keys or private files are visible.

## How it was made

- Every screen is a real interaction with the running app. A Playwright browser captured Chrome's screencast frames at 1920×1080.
- A presentation layer was drawn on top of the page only while recording: cursor, click ripples, caption chips and zooms. It does not change the app.
- AI waits (document analysis, two chat turns, translation, committee) are time-lapsed. A "Waiting time shortened" badge is on screen during each one.
- Some scenes are played 1.05–1.25× faster so the visuals fit the narration.
- **The narration is a synthetic voice (Microsoft neural voice "Andrew", via edge-tts), not Antonio's voice.** The words are the script you provided, plus one sentence with the real numbers in the chatbot scene. To use your own voice, record `demo_script.md` and swap the audio track. Instructions are at the end of the script.

## Feature checklist

| Feature | Shown? | Evidence on screen / notes |
|---|---|---|
| Logo, welcome page, dashboard | ✅ Real | Title card, then the sign-in page, then the Portfolio dashboard |
| Create an investment: property types, strategies, Mexico City | ✅ Real | Wizard: name, neighborhood, then type / strategy / model, then fundamentals. **Not saved.** The analysis then uses the existing fictional Polanco demo project, as you asked. |
| Property intelligence: map, editable facts | ✅ Real | Map; "Alcaldía" edited to Miguel Hidalgo and saved |
| Regulatory research | ✅ Real (stored demo research) | The agent's result shows **"Not verified"**: it could not confirm the parcel's zoning. No regulation is claimed as verified. The Regulatory agent was not re-run (to save cost). |
| Document upload + extraction | ✅ Real AI call | `sample_zoning_certificate_FICTIONAL.pdf` uploaded; the Document agent extracted facts and proposed values pending approval |
| Development config, budget, revenues, financing | ✅ Real | Each page shown briefly |
| Financial dashboard (IRR, MOIC, NPV, cash flows) | ✅ Real | Equity IRR 24.9%, project IRR 25.2%, MOIC 1.68x, NPV MXN 122.5M |
| Excel export | ✅ Real download | `TerraMind_Polanco_Residences_fictional.xlsx`, downloaded by clicking "Excel model" (sheets re-rendered after the chart/column-width fixes, same values). Its sheets (Assumptions, Construction, Sales, Cash Flow, Outputs + charts) were rendered by Microsoft Excel and shown in a viewer. This is not a live Excel window. |
| "Workbook is linked" claim | ✅ Verified | In Microsoft Excel, hard cost above ground 24,000 → 26,400 in the Assumptions tab moved the workbook's equity IRR from 24.91% to 21.75% (matches `docs/evidence/excel_reconciliation.md`) |
| Chatbot changes an assumption | ✅ Real AI call | "Increase construction costs by 10%." Hard cost 24,000 → 26,400/m² (and below-grade 14,000 → 15,400), shown in the chat, on the Budget page, then equity IRR **24.9% → 21.2%** on the Financial Model page |
| Chatbot: complex cash-flow schedule | ✅ Real AI call, saved | "Update the model so sales are slower during the first six months and accelerate after construction is completed; keep the current pace in between." Saved 2 sales phases (1.5 units/month for 6 months; 5/month after delivery; 3/month in between). Equity IRR 21.22% → 21.59%. The recording script checked that the phases were saved before keeping the take. |
| Microphone / speech-to-text | ⚠️ Shown, not recorded | Mic button highlighted with the caption "Tested by the author in Chrome (not recorded here)". Speech recognition can't run in the automated browser, so no dictation is simulated. |
| English → Spanish switch | ✅ Real | The whole interface switches to Spanish |
| Chat conversation translated | ✅ Real AI call | All four chat messages are shown in Spanish after the switch |
| Sustainability alternatives + financial impact | ✅ Real | Rooftop solar enabled: capex MXN 2.4M, 41 tCO₂/yr, equity IRR 21.6% → 21.5% (−0.06 pts) |
| Investment Committee | ✅ Real AI call | Recommendation **"Invest with conditions"**, with summary, metrics, conditions and risks |
| Improvement recommendations | ✅ Real (deterministic) | Recommendations page: levers tested on the full model, ranked by impact |
| Portfolio monitoring + alerts | ✅ Real | Early-warning dashboard |
| Login, guest access, saved projects | ✅ Real | Sign out, then the welcome page with "Continue as guest" highlighted, then sign back in; the projects are still there |
| Project management for signed-in users | ✅ Real | Trash (remove project) button highlighted. **Not clicked.** No project was deleted on camera. |
| Conclusion + logo | ✅ | Financial Model view, then the end card with the repo link and disclaimers |

## Final checks

- [x] Duration 2:54 (between 2 and 3 minutes)
- [x] Narration matches the actions shown; each segment was placed against the real on-screen moments (see `demo_script.md`)
- [x] All financial values on screen are real application outputs (engine and agent results from this run)
- [x] Chatbot updates are real and saved (checked automatically during recording)
- [x] Microphone: not simulated; disclosed on screen
- [x] Excel export and document upload work as shown
- [x] Language switch and chat translation work as shown
- [x] No confidential information: fictional account and projects, masked password, no API keys
- [x] Plays correctly: full decode pass with no errors; loudness −16 LUFS
- [x] AI cost of the recording runs: about $0.01 each (document analysis, 2 chat turns, translation, committee), on `gpt-6-luna`

## Issues found while producing the video (fixed)

1. **Excel export, monthly charts:** the series read each row from column A, so they also pulled in the Total and note columns.
   - The "Units sold per month" chart showed the 75-unit total as a spike at month 0.
   - The cumulative cash-flow and rental NOI charts were shifted by two months.
   - The single-series units chart listed every month in its legend.

   Fixed: series now start at month 0 (column D) with the label linked from column A; single-series charts use one color and no legend.
2. **Excel export, `########` cells:** a full scan in Microsoft Excel found 134 cells across Cash Flow, Waterfall, Sensitivity and Development showing `###` because columns were too narrow. Monthly columns are now 14 wide, Sensitivity and Development value columns 16–18. The same scan of all three demo projects exported from the app now finds **0**.
3. The video's Excel segment was re-rendered from the fixed export. A regression test (`test_monthly_charts_start_at_month_zero_and_columns_fit_values`) covers both bugs, and the sample in `docs/samples/` was regenerated.

One small UX fix was made during production: the chat panel no longer flashes "Translating the conversation…" after every reply in English. It now appears only when the language is switched or a conversation loads.
