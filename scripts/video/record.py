"""Records the TerraMind walkthrough scenes from the real running app (isolated demo DB on :8010).

Every value on screen is a real application output. AI waits are time-lapsed in the edit (badge shown on screen).

Usage (from a separate tools venv with playwright, imageio-ffmpeg, edge-tts, pymupdf):
  TERRAMIND_DB=scripts/video/demo.db python run.py --port 8010 --no-browser   # isolated server, repo root
  python scripts/video/record.py      # scenes/*/ frames + record_log.json (needs excel/*.png from excel_check.ps1)
  python scripts/video/tts.py         # narration audio
  python scripts/video/scenes.py      # per-scene clips
  python scripts/video/build.py output/terramind_demo.mp4
"""
import json
import sqlite3
from pathlib import Path
from urllib.parse import urlencode

from playwright.sync_api import sync_playwright

from rec import OVERLAY, Rec, cap, capoff, center, click, move, scroll_by, scroll_to, type_into, unzoom, zoom

ROOT = Path(__file__).parent
B = "http://127.0.0.1:8010"
DB = ROOT / "demo.db"
REPO = Path(__file__).resolve().parents[2]
EMAIL, PASSWORD = "demo.investor@terramind.example", "TerraMind-demo-2026"
LOG = {}


def reset_account():
    c = sqlite3.connect(DB)
    row = c.execute("SELECT id FROM users WHERE email=?", (EMAIL,)).fetchone()
    if row:
        owner = f"u:{row[0]}"
        for (pid,) in c.execute("SELECT id FROM projects WHERE owner=?", (owner,)).fetchall():
            c.execute("DELETE FROM message_translations WHERE message_id IN (SELECT id FROM chat_messages WHERE project_id=?)", (pid,))
            for t in ("chat_messages", "documents", "changes", "pending_changes", "variants", "research", "actuals", "ic_memos"):
                c.execute(f"DELETE FROM {t} WHERE project_id=?", (pid,))
            c.execute("DELETE FROM projects WHERE id=?", (pid,))
        c.execute("DELETE FROM chat_messages WHERE owner=?", (owner,))
        c.execute("DELETE FROM settings WHERE key LIKE ?", (f"%{owner}%",))
        c.execute("DELETE FROM users WHERE id=?", (row[0],))
    c.commit()
    c.close()


def nav(page, label, pause=800):
    click(page, page.locator("a.nav-item", has_text=label).first, pause=150)
    page.evaluate("document.querySelector('.content').scrollTo(0, 0)")
    page.wait_for_timeout(pause)


def kpis(page, n=8):
    return page.evaluate(f"[...document.querySelectorAll('.kpi')].slice(0,{n}).map(k=>k.innerText.replace(/\\n/g,' | '))")


def send_chat(page, rec, text, keep=1.2, timeout=150000):
    type_into(page, page.locator(".chat-input textarea"), text, delay=28)
    page.wait_for_timeout(300)
    x, y = center(page.locator(".chat-input .icon-btn.send"))
    page.evaluate(f"__rip({x},{y})")
    page.keyboard.press("Enter")
    page.wait_for_selector(".chat .typing", timeout=10000)
    page.wait_for_timeout(600)
    with rec.cut(keep=keep):
        page.wait_for_selector(".chat .typing", state="detached", timeout=timeout)
    page.wait_for_timeout(800)
    return page.locator(".chat-body .msg.assistant").last.inner_text()


def static_scene(ctx, name, url, seconds, setup=None):
    cp = ctx.new_page()
    r = Rec(cp)
    cp.goto(url)
    cp.wait_for_timeout(600)
    r.start(name)
    cp.reload()
    cp.evaluate("__curHide(true)")
    if setup:
        setup(cp)
    cp.wait_for_timeout(int(seconds * 1000))
    r.stop()
    cp.close()


def card(params):
    return (ROOT / "card.html").as_uri() + "?" + urlencode(params)


def main():
    reset_account()
    with sync_playwright() as pw:
        browser = pw.chromium.launch(args=["--force-color-profile=srgb"])
        ctx = browser.new_context(viewport={"width": 1920, "height": 1080}, accept_downloads=True, device_scale_factor=1)
        ctx.add_init_script(OVERLAY)
        r = ctx.request.post(B + "/api/auth/signup", data={"first_name": "Demo", "last_name": "Investor", "email": EMAIL,
                                                           "password": PASSWORD, "confirm_password": PASSWORD})
        assert r.ok, r.text()
        ctx.request.post(B + "/api/auth/logout")

        # ---------------- 0. title card
        static_scene(ctx, "s00_title", card({"sub": "AI-assisted real estate investment analysis, from zoning to the investment committee",
                                             "tag": "AI researches. The engine calculates. You decide.",
                                             "f1": "Antonio Gutiérrez García · Yale SOM", "f2": "AI Foundations for Managers · Fall 2026"}), 4.6)

        page = ctx.new_page()
        rec = Rec(page)
        page.goto(B + "/")
        page.evaluate("localStorage.setItem('tm-lang','en'); localStorage.setItem('tm-chat','closed')")
        page.goto(B + "/")
        page.wait_for_timeout(1500)
        page.evaluate("__cur(1500, 760, true)")

        # ---------------- 1. intro: welcome -> dashboard (sign-in itself is shown in scene 8)
        rec.start("s01_intro")
        page.wait_for_timeout(2600)
        with rec.cut(keep=0.35, badge=False):
            page.get_by_label("Email").fill(EMAIL)
            page.get_by_label("Password").fill(PASSWORD)
            page.locator("form button.primary").click()
            page.wait_for_selector("text=Portfolio Dashboard", timeout=20000)
            page.wait_for_timeout(1500)
        rec.mark("dashboard")
        cap(page, "Portfolio dashboard", "Three fictional demo projects in Mexico City")
        page.wait_for_timeout(1800)
        move(page, page.locator(".kpi").nth(1), ms=900)
        move(page, page.locator(".kpi").nth(4), ms=900)
        scroll_by(page, 420, ms=1400)
        page.wait_for_timeout(700)
        capoff(page)
        rec.stop()

        # ---------------- 2. creating an investment (wizard shown; the analysis then uses the Polanco demo)
        page.evaluate("document.querySelector('.content').scrollTo(0, 0)")
        rec.start("s02_create")
        nav(page, "New Investment", pause=700)
        cap(page, "New investment", "Location first: it drives zoning, market, cost and financing research")
        type_into(page, page.get_by_label("Project name"), "Roma Norte Residences (fictional)", delay=12)
        type_into(page, page.get_by_label("Neighborhood"), "Roma Norte", delay=20)
        page.wait_for_timeout(250)
        click(page, page.get_by_role("button", name="Next"), pause=600)
        cap(page, "Property types and strategies", "Residential, commercial, industrial or mixed-use; ground-up to value-add")
        move(page, page.get_by_role("button", name="Industrial", exact=True), ms=450)
        click(page, page.get_by_role("button", name="Residential", exact=True), pause=300)
        click(page, page.get_by_role("button", name="Ground-up development", exact=True), pause=300)
        click(page, page.get_by_role("button", name="Build-to-sell", exact=True), pause=400)
        click(page, page.get_by_role("button", name="Next"), pause=600)
        cap(page, "Questions adapt to the strategy", "Leave unknowns empty: the model lists what is missing")
        type_into(page, page.get_by_label("Land area"), "1500", delay=40)
        type_into(page, page.get_by_label("Land acquisition price"), "110m", delay=40)
        scroll_by(page, 520, ms=1300)
        page.wait_for_timeout(300)
        capoff(page)
        rec.stop()

        pid = page.evaluate("fetch('/api/projects').then(r=>r.json()).then(p=>p.find(x=>x.name.startsWith('Polanco')).id)")
        LOG["pid"] = pid

        # ---------------- 3. property intelligence + documents
        page.goto(f"{B}/p/{pid}/property")
        page.wait_for_timeout(2500)
        rec.start("s03_property")
        cap(page, "Property intelligence", "Polanco Residences: a fictional demo project")
        move(page, page.locator(".leaflet-container"), ms=700)
        facts = page.locator(".card", has=page.locator("text=Property facts")).first
        click(page, facts.get_by_role("button", name="Edit"), pause=450)
        type_into(page, facts.get_by_label("Alcaldía"), "Miguel Hidalgo", delay=25)
        click(page, facts.get_by_role("button", name="Save"), pause=700)
        cap(page, "Property facts are editable", "Every change is validated and logged")
        zoom(page, page.locator(".card", has=page.locator("text=Property facts")).first.get_by_role("cell", name="Miguel Hidalgo", exact=True), s=1.25)
        page.wait_for_timeout(300)
        unzoom(page, ms=800)
        zoning = page.locator(".card", has=page.locator("text=Zoning & development regulations")).first
        scroll_to(page, zoning, ms=1200)
        cap(page, "Regulatory research with sources", "The agent reports 'not verified' when it can't confirm the parcel's zoning")
        zoom(page, zoning.locator("text=Not verified").first, s=1.4)
        page.wait_for_timeout(1100)
        unzoom(page, ms=750)
        nav(page, "Documents & Files", pause=450)
        cap(page, "Upload your own documents", "Permits, zoning certificates, contracts, Excel models")
        with page.expect_file_chooser() as fc:
            click(page, page.get_by_role("button", name="Upload"), pause=200)
        fc.value.set_files(str(REPO / "docs" / "samples" / "sample_zoning_certificate_FICTIONAL.pdf"))
        page.wait_for_timeout(800)
        with rec.cut(keep=1.4):
            page.wait_for_function("!document.body.innerText.includes('analyzing it with the Document agent') && document.body.innerText.includes('sample_zoning_certificate')", timeout=120000)
            page.wait_for_timeout(1500)
        cap(page, "The Document agent extracts the facts", "Each proposed value is checked against the file and waits for your approval")
        page.wait_for_timeout(1500)
        scroll_by(page, 380, ms=1400)
        page.wait_for_timeout(1200)
        capoff(page)
        rec.stop()

        # ---------------- 4. financial modeling + Excel export
        rec.start("s04_model")
        nav(page, "Development Config", pause=700)
        cap(page, "Development configuration", "Unit mix and program calculated from the site")
        nav(page, "Budget & Schedule", pause=300)
        cap(page, "Construction costs and schedule")
        scroll_by(page, 560, ms=1100)
        nav(page, "Market & Revenue", pause=900)
        cap(page, "Projected revenues", "Comparables, pricing, absorption and buyer payment schedule")
        nav(page, "Financing", pause=900)
        cap(page, "Financing", "Capital stack, debt on the actual monthly balance, covenants")
        nav(page, "Financial Model", pause=200)
        cap(page, "Returns calculated, not estimated", "Deterministic Python engine: IRR, MOIC, NPV and monthly cash flows")
        zoom(page, page.locator(".kpi").nth(1), s=1.3)
        page.wait_for_timeout(1100)
        unzoom(page, ms=750)
        LOG["kpis_before"] = kpis(page)
        scroll_by(page, 470, ms=1200)
        cap(page, "Export to Excel", "A live workbook: formulas linked to one Assumptions tab")
        with page.expect_download() as dl:
            click(page, page.get_by_role("link", name="Excel model"), pause=300)
        dl.value.save_as(str(ROOT / "export.xlsx"))
        LOG["xlsx_name"] = dl.value.suggested_filename
        page.wait_for_timeout(600)
        capoff(page)
        rec.stop()

        # ---------------- 4b. the downloaded workbook (sheets rendered by Microsoft Excel into excel/)
        steps = [["Assumptions", "excel/Assumptions.png", 0, 100, 0, 1.0, 1.4], ["Construction", "excel/Construction.png", 0, 30, 0, 1.0, 1.0],
                 ["Sales", "excel/Sales.png", 0, 30, 0, 1.0, 1.0], ["Cash Flow", "excel/Cash_Flow.png", 0, 120, 0, 1.05, 1.3],
                 ["Outputs", "excel/Outputs.png", 0, 140, 0, 1.0, 1.3], ["Outputs", "excel/Outputs_charts.png", 30, 300, 0, 1.55, 1.8]]
        url = (ROOT / "excel_viewer.html").as_uri() + "?" + urlencode({"fn": LOG.get("xlsx_name", "TerraMind.xlsx"), "steps": json.dumps(steps)})
        static_scene(ctx, "s04b_excel", url, 8.3, setup=lambda p: (
            p.evaluate("__cap('The downloaded Excel model', 'Every tab is linked to the Assumptions tab (checked in Excel)')"),
            p.evaluate("__start()")))

        # ---------------- 5. chatbot changes the model
        nav(page, "Budget & Schedule")
        click(page, page.get_by_role("button", name="AI Assistant"), pause=900)
        drivers = page.locator(".card", has=page.locator("text=Cost drivers")).first
        scroll_to(page, drivers, block="center", ms=900)
        rec.start("s05_chat")
        cap(page, "Today's assumption", "Hard cost above ground, per m²")
        hard = drivers.locator(".row.between", has=page.get_by_text("Hard cost above ground", exact=True)).first
        zoom(page, hard, s=1.3)
        page.wait_for_timeout(900)
        unzoom(page, ms=700)
        cap(page, "Change the model in plain language")
        LOG["chat1"] = send_chat(page, rec, "Increase construction costs by 10%.")
        rec.mark("chat1_done")
        assert page.locator(".chat-body .callout.good").count(), "cost change was not applied; do not use this take"
        cap(page, "The assistant updates the assumptions and re-runs the engine")
        zoom(page, page.locator(".chat-body .callout.good").last, s=1.25)
        page.wait_for_timeout(1500)
        unzoom(page, ms=800)
        hard = page.locator(".card", has=page.locator("text=Cost drivers")).first.locator(".row.between", has=page.get_by_text("Hard cost above ground", exact=True)).first
        scroll_to(page, hard, block="center", ms=800)
        cap(page, "The budget now shows the new value")
        zoom(page, hard, s=1.3)
        page.wait_for_timeout(1300)
        unzoom(page, ms=800)
        nav(page, "Financial Model", pause=900)
        cap(page, "Returns update from the new assumptions")
        zoom(page, page.locator(".kpi").first, s=1.4)
        page.wait_for_timeout(1600)
        LOG["kpis_after_cost"] = kpis(page)
        unzoom(page, ms=800)
        rec.mark("chat2_start")
        cap(page, "More complex instructions: a time-varying sales schedule")
        LOG["chat2"] = send_chat(page, rec, "Update the model so sales are slower during the first six months and accelerate after construction is completed; keep the current pace in between.")
        rec.mark("chat2_done")
        saved = page.evaluate(f"fetch('/api/projects/{pid}').then(r=>r.json()).then(d=>(d.project.assumptions.sales_phases||[]).length)")
        assert saved, "sales phases were not saved; do not use this take"
        LOG["sales_phases_saved"] = saved
        page.wait_for_timeout(1200)
        LOG["kpis_after_sales"] = kpis(page)
        nav(page, "Market & Revenue", pause=500)
        phases = page.locator(".card", has=page.locator("text=Sales phases")).first
        scroll_to(page, phases, block="start", ms=1300)
        cap(page, "Saved as sales phases in the model", "Slower start, faster sales after delivery")
        zoom(page, phases, s=1.2)
        page.wait_for_timeout(1400)
        unzoom(page, ms=750)
        chart = page.locator(".card", has=page.locator("text=Monthly sales absorption")).first
        scroll_to(page, chart, block="center", ms=1100)
        page.wait_for_timeout(900)
        capoff(page)
        rec.stop()

        # ---------------- 6. microphone + Spanish
        rec.start("s06_voice_lang")
        mic = page.locator(".chat-input .icon-btn").nth(1)
        cap(page, "Speech-to-text, English or Spanish", "Tested by the author in Chrome (not recorded here)")
        move(page, mic, ms=800)
        zoom(page, mic, s=1.6)
        page.wait_for_timeout(1900)
        unzoom(page, ms=900)
        cap(page, "English or Spanish")
        click(page, page.get_by_role("button", name="ES", exact=True).first, pause=600)
        with rec.cut(keep=1.0):
            page.wait_for_function("!document.querySelector('.chat-body .toolchip svg.lucide-languages')", timeout=90000)
            page.wait_for_timeout(600)
        cap(page, "Interface and chat conversation now in Spanish", "Each message is translated once and cached")
        page.wait_for_timeout(1200)
        page.locator(".chat-body").evaluate("e => e.scrollTo({top: 0, behavior: 'smooth'})")
        page.wait_for_timeout(1800)
        page.locator(".chat-body").evaluate("e => e.scrollTo({top: e.scrollHeight, behavior: 'smooth'})")
        page.wait_for_timeout(1800)
        capoff(page)
        rec.stop()
        page.get_by_role("button", name="EN", exact=True).first.click()
        page.wait_for_timeout(3000)
        page.wait_for_function("!document.querySelector('.chat-body .toolchip svg.lucide-languages')", timeout=90000)
        click(page, page.get_by_role("button", name="AI Assistant"), pause=600, scroll=False)

        # ---------------- 7. sustainability + committee + recommendations
        nav(page, "Sustainability")
        rec.start("s07_sust_ic")
        cap(page, "Sustainability measures", "Cost, savings, CO₂ and the developer's return, from the full model")
        page.wait_for_timeout(400)
        rows = page.locator("table.t tbody tr", has=page.locator("input[type=checkbox]"))
        click(page, rows.nth(0).locator("input[type=checkbox]"), pause=900)
        zoom(page, page.locator(".kpi").nth(2), s=1.3)
        page.wait_for_timeout(1100)
        unzoom(page, ms=750)
        LOG["sust_kpis"] = kpis(page, 4)
        nav(page, "Investment Committee", pause=400)
        cap(page, "Investment Committee", "Two challenger agents review the deal, then a chair decides")
        click(page, page.get_by_role("button", name="Convene Investment Committee"), pause=500)
        with rec.cut(keep=1.4):
            page.wait_for_selector("text=Committee in session", timeout=8000)
            page.wait_for_selector("text=Committee in session", state="detached", timeout=180000)
            page.wait_for_timeout(2000)
        page.wait_for_timeout(1200)
        scroll_by(page, 400, ms=1400)
        page.wait_for_timeout(1100)
        LOG["ic_text"] = page.locator(".content").inner_text()[:1500]
        nav(page, "Recommendations", pause=400)
        cap(page, "Recommendations", "Levers tested on the full model and ranked by computed impact")
        move(page, page.locator("text=Recommended package").first, ms=900)
        scroll_by(page, 330, ms=1300)
        page.wait_for_timeout(600)
        capoff(page)
        rec.stop()

        # ---------------- 8. portfolio + accounts
        nav(page, "Portfolio", pause=900)
        page.evaluate("__cur(1300, 600, true)")
        rec.start("s08_portfolio_accounts")
        cap(page, "Portfolio monitoring", "Early warnings on cost, sales, liquidity and covenants")
        alerts = page.locator(".card", has=page.locator("text=Early-warning dashboard")).first
        zoom(page, alerts, s=1.18)
        page.wait_for_timeout(1500)
        unzoom(page, ms=750)
        cap(page, "Private accounts")
        click(page, page.locator(".topbar button", has_text="Demo"), pause=900)
        click(page, page.get_by_role("button", name="Sign out"), pause=1000)
        cap(page, "Sign in, or continue as a guest", "Guests get a private workspace in their browser")
        move(page, page.get_by_role("button", name="Continue as guest"), ms=900)
        click(page, page.get_by_label("Email"), pause=150)
        page.keyboard.type(EMAIL, delay=7)
        click(page, page.get_by_label("Password"), pause=120)
        page.keyboard.type(PASSWORD, delay=7)
        click(page, page.locator("form button.primary"), pause=1500)
        cap(page, "Saved projects come back", "Signed-in users can also remove projects they don't need")
        trash = page.locator("button[aria-label^='Remove Narvarte']")
        trash.scroll_into_view_if_needed()
        page.wait_for_timeout(500)
        move(page, trash, ms=800)
        zoom(page, trash, s=1.5)
        page.wait_for_timeout(1400)
        unzoom(page, ms=850)
        capoff(page)
        rec.stop()

        # ---------------- 9. conclusion
        page.goto(f"{B}/p/{pid}/model")
        page.wait_for_timeout(2500)
        rec.start("s09_outro_app")
        page.evaluate("__curHide(true)")
        page.wait_for_timeout(1000)
        scroll_by(page, 300, ms=2800)
        page.wait_for_timeout(1800)
        rec.stop()
        static_scene(ctx, "s10_end", card({"sub": "A prototype that brings feasibility, market research, financial modeling, financing, sustainability and asset management together",
                                           "tag": "github.com/AntonioGutierrez9/terramind-ai",
                                           "f1": "All demo projects and data are fictional", "f2": "Decision support, not investment advice"}), 9.5)
        browser.close()
    json.dump(LOG, open(ROOT / "record_log.json", "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    print(json.dumps(LOG, indent=1, ensure_ascii=False)[:3000])


if __name__ == "__main__":
    main()
