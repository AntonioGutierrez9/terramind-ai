"""Capture full-page screenshots of every page (used for QA and for report.html / slides.html).

    python scripts/screenshots.py [base_url] [out_dir]
"""
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
OUT = Path(sys.argv[2] if len(sys.argv) > 2 else Path(__file__).resolve().parents[1] / "docs" / "screenshots")
OUT.mkdir(parents=True, exist_ok=True)
PAGES = [("portfolio", "/"), ("wizard", "/new"), ("usage", "/usage")] + [
    (f"p{pid}_{p}", f"/p/{pid}/{p}") for pid in (1,) for p in
    ("property", "design", "market", "budget", "financing", "model", "sustainability", "committee", "asset", "assumptions", "history")
] + [("p2_model", "/p/2/model"), ("p2_committee", "/p/2/committee"), ("p3_sustainability", "/p/3/sustainability"), ("p3_model", "/p/3/model")]
only = set(sys.argv[3:])

with sync_playwright() as pw:
    b = pw.chromium.launch()
    ctx = b.new_context(viewport={"width": 1600, "height": 1000}, device_scale_factor=1)
    page = ctx.new_page()
    page.goto(BASE + "/")
    page.evaluate("localStorage.setItem('tm-chat','closed')")
    errors = []
    page.on("console", lambda m: errors.append(f"{m.type}: {m.text}") if m.type == "error" else None)
    page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
    for name, path in PAGES:
        if only and name not in only:
            continue
        page.goto(BASE + path)
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(2500)
        # the app scrolls inside .content; expand it so the full page is captured
        page.evaluate("""() => { const c = document.querySelector('.content'); if (c) { c.style.overflow='visible'; c.style.height='auto'; }
                                 document.querySelectorAll('.main,.shell,#root,body,html').forEach(e => { e.style.height='auto'; e.style.overflow='visible'; }); }""")
        page.wait_for_timeout(400)
        page.screenshot(path=str(OUT / f"{name}.png"), full_page=True)
        print("shot", name)
    print("ERRORS:", errors[:20])
    b.close()
