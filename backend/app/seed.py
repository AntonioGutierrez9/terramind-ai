"""Seed the database with the three fictional demo cases (only when it is empty)."""

from __future__ import annotations

import json
from pathlib import Path

from engine.model import run_model
from seed.demo_cases import CASES

from . import store

SNAPSHOTS = Path(__file__).resolve().parents[1] / "seed" / "research_snapshots.json"


def _demo_actuals(profile: dict, a: dict) -> list[dict]:
    """Fictional actuals for months 1–14: costs ~8% over plan in construction, slower sales, slightly higher prices."""
    base = run_model(profile, a)
    hard_total = sum(m["hard"] for m in base["months"]) or 1
    rows, cum_hard = [], 0.0
    for m in base["months"]:
        t = m["month"]
        if t == 0 or t > 14:
            continue
        cum_hard += m["hard"]
        over = 1.08 if m["phase"] == "Construction" else 1.0
        sold = 2.0 if (m["units_sold"] or 0) > 0 else 0.0
        rows.append({
            "month": t, "cost": round((m["outflow"] - m["land_acq"]) * over),
            "units_sold": sold, "avg_price_per_area": 112_500 if sold else None,
            "collections": round(m["inflow"] * (2.0 / max(m["units_sold"] or 1, 0.01)) * 1.02) if sold else round(m["inflow"]),
            "debt_balance": round(m["senior_balance"] * 1.06),
            "progress_pct": round(cum_hard / hard_total * 100 * 0.85, 1),
        })
    return rows


def seed_if_empty() -> list[int]:
    if store.list_projects():
        return []
    snapshots = json.loads(SNAPSHOTS.read_text(encoding="utf-8")) if SNAPSHOTS.exists() else {}
    ids = []
    for case in CASES:
        pid = store.create_project(case["profile"], case["assumptions"], source="demo", actor="system",
                                   status="portfolio" if case.get("actuals") else "draft")
        if case.get("actuals"):
            store.set_status(pid, "portfolio", in_portfolio=True, actor="system")
            for row in _demo_actuals(case["profile"], case["assumptions"]):
                store.upsert_actual(pid, row["month"], row)
        for kind, snap in (snapshots.get(case["profile"]["name"]) or {}).items():
            store.save_research(pid, kind, snap.get("request", ""), snap["payload"], from_cache=True)
            from .agents.specialists import _proposals  # researched values arrive as PENDING proposals
            store.propose_values(pid, kind, _proposals(kind, snap["payload"]))
        ids.append(pid)
    return ids
