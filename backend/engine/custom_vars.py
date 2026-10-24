"""User-defined variables: new inputs a user (or the chatbot, on request) adds to a project, with a deterministic effect.

Each variable is {key, label, section, value, effect, timing, anchor, offset, months, note}. The effect says how the
engine uses the value; nothing is evaluated as free-form code (safe and auditable).

Effects (value units in brackets)
  cost_fixed            one-off cost [currency]                      timing: spread over construction, or at anchor+offset
  cost_per_area         cost per m² of above-ground GBA [cur/m²]     spread over construction
  cost_per_unit         cost per dwelling [cur/unit]                 spread over construction
  cost_pct_hard         % of hard cost [%]                           spread over construction
  cost_pct_revenue      % of sales collections [%]                   paid when cash is collected (e.g. a trust fee)
  cost_monthly          recurring cost per month [currency]          for `months` from anchor+offset
  revenue_fixed         one-off income [currency]                    at anchor+offset
  revenue_per_unit      income per unit sold [cur/unit]              collected with each sale (e.g. storage add-ons)
  revenue_monthly       recurring income per month [currency]        for `months` from anchor+offset
  price_pct             % change to the base sale price or rent [%]  whole project
  info                  tracked only (shown on the page and to the agents; no effect on the numbers)
"""

from __future__ import annotations

import re

from .registry import ANCHORS, SECTIONS
from .validation import ValidationError

EFFECTS = {
    "cost_fixed": ("One-off cost", "currency"), "cost_per_area": ("Cost per m² of GBA", "currency/area"),
    "cost_per_unit": ("Cost per unit", "currency/unit"), "cost_pct_hard": ("% of hard cost", "%"),
    "cost_pct_revenue": ("% of sales collections", "%"), "cost_monthly": ("Monthly cost", "currency/month"),
    "revenue_fixed": ("One-off income", "currency"), "revenue_per_unit": ("Income per unit sold", "currency/unit"),
    "revenue_monthly": ("Monthly income", "currency/month"), "price_pct": ("% change to sale price / rent", "%"),
    "info": ("Tracked only", ""),
}
SECTION_PAGE = {"site": "property", "reg": "property", "dev": "design", "rev": "market", "rent": "market", "cost": "budget",
                "sch": "budget", "fin": "financing", "val": "model"}


def slug(label: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_")[:40]
    return f"custom.{s or 'variable'}"


def validate_custom_vars(rows) -> list[dict]:
    if rows is None:
        return []
    if not isinstance(rows, list) or len(rows) > 40:
        raise ValidationError("custom variables must be a list of at most 40 items")
    out, keys = [], set()
    for i, r in enumerate(rows):
        label = str(r.get("label") or "").strip()[:60]
        if not label:
            raise ValidationError(f"custom variable {i + 1}: a name is required")
        effect = str(r.get("effect") or "info")
        if effect not in EFFECTS:
            raise ValidationError(f"{label}: effect must be one of {', '.join(EFFECTS)}")
        section = str(r.get("section") or "cost")
        if section not in SECTIONS:
            raise ValidationError(f"{label}: section must be one of {', '.join(SECTIONS)}")
        key = r.get("key") or slug(label)
        if not str(key).startswith("custom."):
            key = slug(str(key))
        if key in keys:
            raise ValidationError(f"duplicate custom variable '{label}'")
        keys.add(key)
        value = r.get("value")
        if effect != "info" or value not in (None, ""):
            try:
                value = float(str(value).replace(",", ""))
            except (TypeError, ValueError) as exc:
                if effect != "info":
                    raise ValidationError(f"{label}: value must be a number") from exc
                value = str(value)[:120]
        if isinstance(value, float):
            if effect in ("cost_pct_hard", "cost_pct_revenue", "price_pct") and not (-50 <= value <= 100):
                raise ValidationError(f"{label}: percent must be between -50 and 100")
            if effect not in ("price_pct", "info") and value < 0:
                raise ValidationError(f"{label}: use a positive amount (choose a cost or an income effect)")
            if abs(value) > 1e12:
                raise ValidationError(f"{label}: value too large")
        timing = str(r.get("timing") or ("construction" if effect in ("cost_fixed", "cost_per_area", "cost_per_unit", "cost_pct_hard") else "anchor"))
        if timing not in ("construction", "anchor"):
            raise ValidationError(f"{label}: timing must be construction or anchor")
        anchor = str(r.get("anchor") or "construction_start")
        if anchor not in ANCHORS:
            raise ValidationError(f"{label}: anchor must be one of {', '.join(ANCHORS)}")
        out.append({"key": key, "label": label, "section": section, "value": value, "effect": effect,
                    "unit": EFFECTS[effect][1], "timing": timing, "anchor": anchor,
                    "offset": int(float(r.get("offset") or 0)), "months": max(1, int(float(r.get("months") or 12))),
                    "note": str(r.get("note") or "")[:300], "created_by": str(r.get("created_by") or "user")[:20]})
    return out


def price_multiplier(a: dict, mode: str) -> float:
    m = 1.0
    for v in a.get("custom_variables") or []:
        if v["effect"] == "price_pct" and isinstance(v.get("value"), (int, float)):
            m *= 1 + v["value"] / 100
    return m
