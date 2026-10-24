"""Live test of the document features as a guest: upload the three fictional samples, analyze them, ask questions,
and ask the chatbot to use the Excel model. Writes docs/evidence/document_tests.json and .md.

    python scripts/run_document_evidence.py      # server running on http://127.0.0.1:8000
"""
import json
import time
from pathlib import Path

import httpx

BASE = "http://127.0.0.1:8000"
ROOT = Path(__file__).resolve().parents[1]
SAMPLES = ROOT / "docs" / "samples"
OUT = ROOT / "docs" / "evidence"

c = httpx.Client(base_url=BASE, timeout=300)
c.post("/api/auth/guest")
pid = next(p["id"] for p in c.get("/api/projects").json() if p["name"].startswith("Polanco"))
results = []
for name in ("sample_zoning_certificate_FICTIONAL.pdf", "sample_developer_model_FICTIONAL.xlsx", "sample_land_purchase_contract_FICTIONAL.docx"):
    t = time.time()
    with open(SAMPLES / name, "rb") as fh:
        r = c.post(f"/api/projects/{pid}/documents", files={"file": (name, fh)}, data={"analyze": "true"}).json()
    a = r.get("analysis") or {}
    results.append({"file": name, "seconds": round(time.time() - t, 1), "doc_id": r["document"]["id"], "doc_type": a.get("doc_type"),
                    "summary": a.get("summary"), "zoning_code": a.get("zoning_code"),
                    "accepted": [(p["key"], p.get("value")) for p in a.get("accepted_proposals", [])],
                    "rejected": [(p.get("key"), p.get("value"), p.get("reason")) for p in a.get("rejected_proposals", [])],
                    "contract_risks": [(x["severity"], x["clause"], x["issue"]) for x in ((a.get("contract_review") or {}).get("risks") or [])],
                    "suspicious_fields": a.get("suspicious_fields"), "usage": (r.get("turn_usage") or {}).get("total")})
    print(name, results[-1]["seconds"], "s", results[-1]["doc_type"], len(results[-1]["accepted"]), "proposals",
          len(results[-1]["rejected"]), "rejected", "suspicious:", bool(results[-1]["suspicious_fields"]))

contract_id = results[2]["doc_id"]
qa = c.post(f"/api/documents/{contract_id}/ask", json={"question": "What happens to the 10% deposit if we cannot close, and what clauses are risky for the buyer?"}).json()
print("Q&A:", qa.get("answer", "")[:300])

chat_events, final = [], None
with c.stream("POST", "/api/chat", json={"message": "Use the developer's Excel model I uploaded to update our model, and tell me what differs.",
                                         "project_id": pid}) as resp:
    for line in resp.iter_lines():
        if line.startswith("data: "):
            ev = json.loads(line[6:])
            if ev["type"] == "final":
                final = ev["data"]
print("Chat:", (final or {}).get("answer", "")[:400])
state = c.get(f"/api/projects/{pid}").json()["project"]
out = {"project_id": pid, "documents": results,
       "qa": {k: qa.get(k) for k in ("answer", "quotes", "found_in_document", "confidence")}, "qa_usage": (qa.get("turn_usage") or {}).get("total"),
       "chat": {"answer": (final or {}).get("answer"), "tools": [t["tool"] + ": " + t["summary"] for t in (final or {}).get("tool_log", [])],
                "usage": ((final or {}).get("usage") or {}).get("total")},
       "land_price_after (should be unchanged until approved)": state["assumptions"].get("site.land_price")}
(OUT / "document_tests.json").write_text(json.dumps(out, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
print("land price now:", out["land_price_after (should be unchanged until approved)"])
