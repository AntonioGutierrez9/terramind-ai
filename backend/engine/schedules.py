"""Validation of the time-varying inputs (sales phases, price phases, land payments, custom cash flows).

Anchors: "closing" (month 0), "sales_start", "construction_start", "delivery". Offsets are months (can be negative).
An empty list removes the schedule (the model falls back to the scalar assumption).
"""

from __future__ import annotations

from .registry import ANCHORS
from .validation import ValidationError


def _num(v, name, lo=None, hi=None, integer=False):
    try:
        x = float(v)
    except (TypeError, ValueError) as exc:
        raise ValidationError(f"{name} must be a number") from exc
    if integer:
        if abs(x - round(x)) > 1e-9:
            raise ValidationError(f"{name} must be a whole number")
        x = int(round(x))
    if lo is not None and x < lo:
        raise ValidationError(f"{name} must be ≥ {lo}")
    if hi is not None and x > hi:
        raise ValidationError(f"{name} must be ≤ {hi}")
    return x


def _anchor(row, i):
    a = (row.get("anchor") or "closing").strip().lower().replace(" ", "_")
    if a not in ANCHORS:
        raise ValidationError(f"row {i + 1}: anchor must be one of {', '.join(ANCHORS)}")
    return a


def validate_schedule(key: str, rows) -> list[dict]:
    if rows is None:
        return []
    if not isinstance(rows, list):
        raise ValidationError(f"{key} must be a list")
    if len(rows) > 24:
        raise ValidationError(f"{key}: at most 24 rows")
    out = []
    for i, r in enumerate(rows):
        if not isinstance(r, dict):
            raise ValidationError(f"{key} row {i + 1} must be an object")
        name = str(r.get("name") or r.get("label") or f"Row {i + 1}")[:60]
        if key == "sales_phases":
            out.append({"name": name, "anchor": _anchor(r, i), "offset": _num(r.get("offset", 0), "offset", -60, 240, True),
                        "months": _num(r.get("months"), "months", 1, 240, True),
                        "units_per_month": _num(r.get("units_per_month"), "units_per_month", 0, 1000)})
        elif key == "price_phases":
            out.append({"name": name, "anchor": _anchor(r, i), "offset": _num(r.get("offset", 0), "offset", -60, 240, True),
                        "months": _num(r.get("months"), "months", 1, 240, True), "pct": _num(r.get("pct"), "pct", -50, 100)})
        elif key == "land_payments":
            out.append({"month": _num(r.get("month"), "month", 0, 240, True), "pct": _num(r.get("pct"), "pct", 0, 100)})
        elif key == "custom_flows":
            typ = str(r.get("type") or "cost").lower()
            if typ not in ("cost", "revenue"):
                raise ValidationError(f"custom flow {i + 1}: type must be cost or revenue")
            row = {"label": name, "type": typ, "amount": _num(r.get("amount"), "amount", 0, 1e12)}
            if r.get("anchor"):
                row.update(anchor=_anchor(r, i), offset=_num(r.get("offset", 0), "offset", -60, 240, True))
            else:
                row["month"] = _num(r.get("month", 0), "month", 0, 480, True)
            out.append(row)
    if key == "land_payments" and out and abs(sum(r["pct"] for r in out) - 100) > 0.5:
        raise ValidationError(f"land payments add to {sum(r['pct'] for r in out):g}%, they must add to 100%")
    return out
