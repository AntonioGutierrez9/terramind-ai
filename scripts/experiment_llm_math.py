"""Why a deterministic engine: ask gpt-6-luna to compute the equity IRR of demo project #1 from its monthly
cash flows (3 runs) and compare with the engine. Writes docs/evidence/llm_math_experiment.json."""
import json, os, sys, time
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.config import ENV_FILES_FOUND, cost_usd  # noqa  (loads .env)
from engine.model import run_model
from seed.demo_cases import CASES
from openai import OpenAI

r = run_model(CASES[0]["profile"], CASES[0]["assumptions"])
flows = [round(m["levered_cf"]) for m in r["months"]]
engine_irr = r["metrics"]["equity_irr"]
key = os.environ["PORTKEY_API_KEY"]
client = OpenAI(api_key=key, base_url="https://api.portkey.ai/v1", default_headers={"x-portkey-api-key": key, "x-portkey-provider": "openai"})
prompt = ("These are the monthly equity cash flows of a real estate project in MXN, month 0 first (negative = equity in):\n"
          f"{flows}\nCompute the annualized equity IRR, i.e. (1+monthly IRR)^12-1. Answer with just the percentage to two decimals.")
runs = []
for i in range(3):
    t = time.time()
    resp = client.responses.create(model="gpt-6-luna", input=prompt, reasoning={"effort": "low"})
    u = resp.usage
    runs.append({"answer": resp.output_text.strip(), "seconds": round(time.time() - t, 1), "input_tokens": u.input_tokens,
                 "output_tokens": u.output_tokens, "cost_usd": cost_usd(u.input_tokens, u.output_tokens)})
    print(runs[-1])
out = {"engine_equity_irr_pct": round(engine_irr * 100, 2), "flows": flows, "llm_runs": runs}
(ROOT / "docs" / "evidence" / "llm_math_experiment.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
print("engine:", out["engine_equity_irr_pct"])
