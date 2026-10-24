"""Re-record only the workbook segment (s04b) from sheets rendered by Excel from the fixed exporter."""
import json
from urllib.parse import urlencode
from playwright.sync_api import sync_playwright
from rec import OVERLAY
from record import ROOT, static_scene
log = json.load(open(ROOT / "record_log.json", encoding="utf-8"))
steps = [["Assumptions", "excel/Assumptions.png", 0, 100, 0, 1.0, 1.4], ["Construction", "excel/Construction.png", 0, 30, 0, 1.0, 1.0],
         ["Sales", "excel/Sales.png", 0, 30, 0, 1.0, 1.0], ["Cash Flow", "excel/Cash_Flow.png", 0, 120, 0, 1.05, 1.3],
         ["Outputs", "excel/Outputs.png", 0, 140, 0, 1.0, 1.3], ["Outputs", "excel/Outputs_charts.png", 30, 300, 0, 1.55, 1.8]]
with sync_playwright() as pw:
    b = pw.chromium.launch(args=["--force-color-profile=srgb"])
    ctx = b.new_context(viewport={"width": 1920, "height": 1080}, device_scale_factor=1)
    ctx.add_init_script(OVERLAY)
    url = (ROOT / "excel_viewer.html").as_uri() + "?" + urlencode({"fn": log["xlsx_name"], "steps": json.dumps(steps)})
    static_scene(ctx, "s04b_excel", url, 8.3, setup=lambda p: (
        p.evaluate("__cap('The downloaded Excel model', 'Every tab is linked to the Assumptions tab (checked in Excel)')"),
        p.evaluate("__start()")))
    b.close()
