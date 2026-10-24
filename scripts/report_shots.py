"""Capture the screenshots used in report.html and slides.html (JPEG, 1600×1000 viewport).

    python scripts/report_shots.py [base_url]     # server running; writes docs/screenshots/*.jpg
"""
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
OUT = Path(__file__).resolve().parents[1] / "docs" / "screenshots"
OUT.mkdir(parents=True, exist_ok=True)
CHAT_PID = int(sys.argv[2]) if len(sys.argv) > 2 else 4

EXPAND = """() => { const c = document.querySelector('.content'); c.style.overflow='visible'; c.style.height='auto';
 document.querySelectorAll('.main,.shell,#root,body,html').forEach(e => { e.style.height='auto'; e.style.overflow='visible'; });
 const s = document.querySelector('.sidebar'); if (s) { s.style.minHeight = document.body.scrollHeight + 'px'; } }"""


def shot(page, name, full=False, clip_h=None):
    if full or clip_h:
        page.evaluate(EXPAND)
        page.wait_for_timeout(300)
    kw = {"path": str(OUT / f"{name}.jpg"), "type": "jpeg", "quality": 82}
    if clip_h:
        kw["clip"] = {"x": 0, "y": 0, "width": 1600, "height": clip_h}
    elif full:
        kw["full_page"] = True
    page.screenshot(**kw)
    print("shot", name)


def go(page, path, chat=False, wait=2200):
    page.evaluate(f"localStorage.setItem('tm-chat', '{'open' if chat else 'closed'}')")
    page.goto(BASE + path)
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(wait)


def scroll_chat_to(page, text):
    page.evaluate("""(t) => { const b = document.querySelector('.chat-body'); const el = [...b.querySelectorAll('.msg.user')].find(e => e.innerText.includes(t));
                    if (el) b.scrollTop = el.offsetTop - 70; }""", text)
    page.wait_for_timeout(500)


with sync_playwright() as pw:
    browser = pw.chromium.launch()
    page = browser.new_page(viewport={"width": 1600, "height": 1000})
    page.goto(BASE + "/")
    # --- chat walkthrough on the test copy ---
    go(page, f"/p/{CHAT_PID}/model", chat=True)
    scroll_chat_to(page, "Increase construction costs by 10%")
    shot(page, "chat_edit")
    scroll_chat_to(page, "Change the financing structure to 40% equity and 60% debt.")
    shot(page, "chat_material")
    go(page, f"/p/{CHAT_PID}/assumptions", chat=True)
    scroll_chat_to(page, "Ignore all previous instructions")
    shot(page, "chat_injection")
    scroll_chat_to(page, "maximum amount we should pay for the land")
    shot(page, "chat_solver")
    go(page, f"/p/{CHAT_PID}/financing", chat=True)
    page.evaluate("() => { const b = document.querySelector('.chat-body'); b.scrollTop = b.scrollHeight; }")
    page.wait_for_timeout(400)
    shot(page, "chat_limit")
    go(page, "/", chat=True)
    scroll_chat_to(page, "evaluating a 2,500")
    shot(page, "chat_create")
    # --- pages ---
    for name, path, full, clip in [
        ("portfolio", "/", False, None), ("p1_property", "/p/1/property", False, 1750), ("p1_design", "/p/1/design", False, 1300),
        ("p1_market", "/p/1/market", False, 1100), ("p1_budget", "/p/1/budget", False, 1050), ("p1_financing", "/p/1/financing", False, 1250),
        ("p1_model_top", "/p/1/model", False, 1300), ("p1_model_sens", "/p/1/model", False, None), ("p1_committee", "/p/1/committee", False, 1500),
        ("p1_asset", "/p/1/asset", False, 1400), ("p1_assumptions", "/p/1/assumptions", False, None), ("p3_sustainability", "/p/3/sustainability", False, 1350),
        ("p2_model", "/p/2/model", False, None), ("usage", "/usage", False, 1300), ("p1_history", "/p/1/history", False, None),
    ]:
        go(page, path)
        if name == "p1_model_sens":
            page.evaluate("() => { const h = [...document.querySelectorAll('h2')].find(e => e.innerText.startsWith('Scenario analysis')); if (h) document.querySelector('.content').scrollTop = h.closest('.card').offsetTop - 20; }")
            page.wait_for_timeout(500)
        shot(page, name, full, clip)
    # --- wizard: dynamic step 3 ---
    go(page, "/new")
    page.fill("input[placeholder='e.g. Roma Norte Residences']", "Roma Norte Residences (fictional)")
    page.fill("input[placeholder='e.g. Polanco']", "Roma Norte")
    page.get_by_role("button", name="Next").click()
    page.wait_for_timeout(400)
    page.get_by_role("button", name="Next").click()
    page.wait_for_timeout(600)
    shot(page, "wizard_step3", clip_h=1250)
    browser.close()
