"""Live test: add new variables by chat and ask for recommendations (guest session, risky demo project Del Valle).
Writes docs/evidence/advisor_tests.json.   python scripts/run_advisor_evidence.py"""
import json
from pathlib import Path

import httpx

BASE = "http://127.0.0.1:8000"
OUT = Path(__file__).resolve().parents[1] / "docs" / "evidence" / "advisor_tests.json"
c = httpx.Client(base_url=BASE, timeout=300)
c.post("/api/auth/guest")
pid = next(p["id"] for p in c.get("/api/projects").json() if p["name"].startswith("Del Valle"))
MESSAGES = [
    "Add a new variable: the bank's trust (fideicomiso) fee is 0.4% of all sales collections. Also add storage units that we sell for MXN 120,000 with each apartment.",
    "What should we change to improve this project?",
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
    results.append({"message": msg, "answer": final["answer"], "tools": [t["tool"] + ": " + t["summary"] for t in final["tool_log"]],
                    "usage": final["usage"]["total"], "custom_variables": proj["project"]["assumptions"].get("custom_variables"),
                    "equity_irr": proj["results"]["metrics"]["equity_irr"]})
    print("\n>>>", msg, "\n tools:", results[-1]["tools"], "\n cost:", round(final["usage"]["total"]["cost_usd"], 5))
    print(" answer:", final["answer"][:900])
plan = c.post(f"/api/projects/{pid}/recommendations/commentary").json()
print("\nPLAN:", plan.get("headline"), [p["lever_id"] for p in plan.get("priorities", [])], "cost", plan.get("turn_usage", {}).get("total", {}).get("cost_usd"))
results.append({"advisor_plan": plan})
OUT.write_text(json.dumps(results, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
