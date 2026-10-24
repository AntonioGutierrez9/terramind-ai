"""Live test: ask the chatbot for a two-peak sales shape and other non-standard changes (guest session, demo project).
Writes docs/evidence/schedule_tests.json.   python scripts/run_schedule_evidence.py"""
import json
from pathlib import Path

import httpx

BASE = "http://127.0.0.1:8000"
OUT = Path(__file__).resolve().parents[1] / "docs" / "evidence" / "schedule_tests.json"
c = httpx.Client(base_url=BASE, timeout=300)
c.post("/api/auth/guest")
pid = next(p["id"] for p in c.get("/api/projects").json() if p["name"].startswith("Polanco"))
MESSAGES = [
    "Why don't you assume a big selling point at the start of construction and then also a big selling point at the end of construction? I don't think selling 3 units per month the whole time is realistic.",
    "Also assume we pay the land 30% at closing and 70% six months later, and add a MXN 4 million road-mitigation fee at construction start.",
    "What if we gave an 8% launch discount during the first 4 months of sales? Don't save it, just show me.",
]
results = []
for msg in MESSAGES:
    final = None
    with c.stream("POST", "/api/chat", json={"message": msg, "project_id": pid}) as r:
        for line in r.iter_lines():
            if line.startswith("data: "):
                ev = json.loads(line[6:])
                if ev["type"] == "final":
                    final = ev["data"]
    proj = c.get(f"/api/projects/{pid}").json()
    a = proj["project"]["assumptions"]
    results.append({"message": msg, "answer": final["answer"], "tools": [t["tool"] + ": " + t["summary"] for t in final["tool_log"]],
                    "usage": final["usage"]["total"], "sales_phases": a.get("sales_phases"), "land_payments": a.get("land_payments"),
                    "custom_flows": a.get("custom_flows"), "price_phases": a.get("price_phases"),
                    "base_absorption": a.get("rev.absorption_per_month"), "equity_irr": proj["results"]["metrics"]["equity_irr"]})
    print("\n>>>", msg, "\n tools:", results[-1]["tools"], "\n cost:", round(final["usage"]["total"]["cost_usd"], 5))
    print(" answer:", final["answer"][:700])
OUT.write_text(json.dumps(results, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
