"""Trade-off experiment: Investment Manager with reasoning effort "low" vs "medium".

Runs the same 5 instructions on fresh copies of demo project #1 in a temporary database and records
tokens, cost, latency and whether the right tool / values were used. Writes docs/evidence/reasoning_experiment.json.

    python scripts/experiment_reasoning.py
"""

import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ["TERRAMIND_DB"] = os.path.join(tempfile.mkdtemp(), "exp.db")
sys.path.insert(0, str(ROOT / "backend"))

from app import store  # noqa: E402
from app.agents.manager import run_chat  # noqa: E402
from app.agents.runtime import TurnContext  # noqa: E402
from app.config import DEFAULT_LIMITS  # noqa: E402
from app.seed import seed_if_empty  # noqa: E402

CASES = [
    ("Increase construction costs by 10%.", lambda a0, a1, log: abs(a1["cost.hard_per_area"] - a0["cost.hard_per_area"] * 1.1) < 1),
    ("Assume we sell 4 apartments per month.", lambda a0, a1, log: a1["rev.absorption_per_month"] == 4),
    ("What happens to our equity IRR if construction takes six months longer?", lambda a0, a1, log: any(t["tool"] == "what_if" for t in log) and a0 == a1),
    ("What's the maximum amount we should pay for the land if we want an 18% equity IRR?", lambda a0, a1, log: any(t["tool"] == "solve_for_target" for t in log) and a0 == a1),
    ("Change the average apartment size to 110 m².", lambda a0, a1, log: any(t["tool"] == "scale_unit_sizes" for t in log)),
]


async def main():
    seed_if_empty()
    rows = []
    for effort in ("low", "medium"):
        for msg, check in CASES:
            pid = store.duplicate_project(1, f"exp {effort}")
            a0 = store.get_project(pid)["assumptions"]
            ctx = TurnContext(project_id=pid, limits={**DEFAULT_LIMITS, "reasoning_effort": effort})
            res = await run_chat(pid, msg, ctx)
            a1 = store.get_project(pid)["assumptions"]
            t = res["usage"]["total"]
            ok = bool(check(a0, a1, res["tool_log"]))
            rows.append({"effort": effort, "message": msg, "correct": ok, "seconds": res["usage"]["seconds"], **t,
                         "tools": [x["tool"] for x in res["tool_log"]]})
            print(effort, ok, t["input_tokens"], t["output_tokens"], f"${t['cost_usd']:.5f}", res["usage"]["seconds"], "s", msg[:40])
    summary = {}
    for effort in ("low", "medium"):
        r = [x for x in rows if x["effort"] == effort]
        summary[effort] = {"correct": sum(x["correct"] for x in r), "n": len(r),
                           "avg_cost_usd": sum(x["cost_usd"] for x in r) / len(r),
                           "avg_output_tokens": sum(x["output_tokens"] for x in r) / len(r),
                           "avg_input_tokens": sum(x["input_tokens"] for x in r) / len(r),
                           "avg_seconds": sum(x["seconds"] for x in r) / len(r)}
    out = ROOT / "docs" / "evidence" / "reasoning_experiment.json"
    out.write_text(json.dumps({"summary": summary, "rows": rows}, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


asyncio.run(main())
