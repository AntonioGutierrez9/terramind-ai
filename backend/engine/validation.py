"""Validation of single values, unit mixes and model completeness.

Every write path (forms, chatbot tools, scenarios, actuals) goes through
validate_value(), so the chatbot cannot bypass the same checks a form uses.
"""

from __future__ import annotations

import math
import re
from typing import Any

from .registry import REGISTRY, is_ground_up, model_mode

TRUE_WORDS = {"true", "yes", "si", "sí", "1", "on"}
FALSE_WORDS = {"false", "no", "0", "off"}


class ValidationError(ValueError):
    pass


UNIT_TOKENS = ("m²", "m2", "sqm", "sq ft", "ft²", "ft2", "mxn", "usd", "$", "%", "months", "month", "x")


def _to_number(value: Any, allow_money_suffix: bool = False) -> float:
    if isinstance(value, bool):
        raise ValidationError("expected a number, got true/false")
    if isinstance(value, (int, float)):
        num = float(value)
    elif isinstance(value, str):
        text = value.strip().lower().replace(",", "").replace("_", "")
        for token in UNIT_TOKENS:
            text = text.replace(token, "").strip()
        mult = 1.0
        if allow_money_suffix:  # "120m" / "120 million" only make sense for money
            for suffix, m in (("million", 1e6), ("millones", 1e6), ("mm", 1e6), ("bn", 1e9), ("m", 1e6), ("k", 1e3)):
                if re.match(r"^[\d.\-]+\s*" + suffix + "$", text):
                    text, mult = text[: -len(suffix)].strip(), m
                    break
        try:
            num = float(text) * mult
        except ValueError as exc:
            raise ValidationError(f"'{value}' is not a number") from exc
    else:
        raise ValidationError(f"expected a number, got {type(value).__name__}")
    if math.isnan(num) or math.isinf(num):
        raise ValidationError("number must be finite")
    return num


def validate_value(key: str, value: Any) -> tuple[Any, list[str]]:
    """Return (normalized value, warnings). Raise ValidationError if invalid.

    None clears a value (allowed for every variable; completeness is checked separately).
    """
    if key not in REGISTRY:
        raise ValidationError(f"unknown variable '{key}'")
    spec = REGISTRY[key]
    if value is None or value == "":
        return None, []
    kind = spec["kind"]
    warnings: list[str] = []

    if kind == "bool":
        if isinstance(value, bool):
            return value, []
        text = str(value).strip().lower()
        if text in TRUE_WORDS:
            return True, []
        if text in FALSE_WORDS:
            return False, []
        raise ValidationError(f"{spec['label']}: expected yes/no")

    if kind == "choice":
        text = str(value).strip().lower().replace(" ", "_").replace("-", "_")
        if text not in spec["choices"]:
            raise ValidationError(f"{spec['label']}: must be one of {', '.join(spec['choices'])}")
        return text, []

    if kind == "text":
        return str(value).strip()[:500], []

    num = _to_number(value, allow_money_suffix=spec["unit"] == "currency")
    if kind == "int":
        if abs(num - round(num)) > 1e-9:
            raise ValidationError(f"{spec['label']}: must be a whole number")
        num = int(round(num))
    if spec["min"] is not None and num < spec["min"]:
        raise ValidationError(f"{spec['label']}: {num:g} is below the minimum {spec['min']:g} {spec['unit']}")
    if spec["max"] is not None and num > spec["max"]:
        raise ValidationError(f"{spec['label']}: {num:g} is above the maximum {spec['max']:g} {spec['unit']}")
    if spec["unit"].startswith("%") and 0 < num < 1 and spec["typical"] and spec["typical"][1] >= 5:
        warnings.append(
            f"{spec['label']} is stored in percent; {num:g} means {num:g}% (not {num * 100:g}%)."
        )
    typical = spec["typical"]
    if typical and not (typical[0] <= num <= typical[1]):
        warnings.append(f"{spec['label']} = {num:g} is outside the typical range {typical[0]:g}–{typical[1]:g} {spec['unit']}.")
    return num, warnings


def validate_unit_mix(unit_mix: list[dict]) -> tuple[list[dict], list[str]]:
    if not isinstance(unit_mix, list) or not unit_mix:
        raise ValidationError("unit mix must have at least one unit type")
    clean, warnings = [], []
    for i, row in enumerate(unit_mix):
        name = str(row.get("name") or f"Type {i + 1}").strip()[:40]
        size = _to_number(row.get("size", 0))
        share = _to_number(row.get("share_pct", 0))
        if size <= 0:
            raise ValidationError(f"unit type '{name}': size must be positive")
        if not (0 <= share <= 100):
            raise ValidationError(f"unit type '{name}': share must be between 0 and 100%")
        clean.append({
            "name": name,
            "bedrooms": int(_to_number(row.get("bedrooms", 0))),
            "bathrooms": _to_number(row.get("bathrooms", 0)),
            "size": size,
            "share_pct": share,
            "terrace": max(0.0, _to_number(row.get("terrace", 0) or 0)),
            "premium_pct": _to_number(row.get("premium_pct", 0) or 0),
        })
    total = sum(r["share_pct"] for r in clean)
    if abs(total - 100) > 0.5:
        raise ValidationError(f"unit mix shares add to {total:g}%, they must add to 100%")
    return clean, warnings


def missing_inputs(profile: dict, a: dict) -> list[str]:
    """Inputs the model needs but doesn't have. Empty list = model can run."""
    mode = model_mode(profile)
    ground_up = is_ground_up(profile)
    missing = []
    for key, spec in REGISTRY.items():
        if mode in spec["required"] and a.get(key) is None:
            if not ground_up and key in ("reg.max_stories", "reg.min_open_area_pct", "dev.stories",
                                         "sch.predev_months", "cost.hard_per_area"):
                continue
            missing.append(key)
    if not ground_up:
        if a.get("dev.existing_rentable_area") is None and mode == "rent":
            missing.append("dev.existing_rentable_area")
    if mode == "sale" and not a.get("unit_mix"):
        missing.append("unit_mix")
    if mode == "sale":
        parts = [a.get(k) or 0 for k in ("rev.deposit_pct", "rev.installments_pct", "rev.closing_pct")]
        if any(a.get(k) is not None for k in ("rev.deposit_pct", "rev.installments_pct", "rev.closing_pct")) and abs(sum(parts) - 100) > 0.5:
            missing.append("rev.payment_schedule (deposit + installments + closing must equal 100%)")
    if (a.get("fin.senior_ltc_pct") or 0) > 0:
        if a.get("fin.senior_rate_type", "floating") == "fixed":
            if a.get("fin.senior_fixed_rate_pct") is None:
                missing.append("fin.senior_fixed_rate_pct")
        elif a.get("fin.reference_rate_pct") is None:
            missing.append("fin.reference_rate_pct")
    if (a.get("fin.mezz_ltc_pct") or 0) > 0 and a.get("fin.mezz_rate_pct") is None:
        missing.append("fin.mezz_rate_pct")
    return missing


def compliance_issues(a: dict, design: dict) -> list[dict]:
    """Compare a computed design with legal limits. Returns list of issues."""
    issues = []

    def check(cond: bool, rule: str, detail: str):
        if cond:
            issues.append({"rule": rule, "detail": detail})

    if a.get("reg.max_stories") is not None:
        check((a.get("dev.stories") or 0) > a["reg.max_stories"], "reg.max_stories",
              f"{a.get('dev.stories')} stories designed vs {a['reg.max_stories']} allowed")
    if design.get("max_far_area") is not None:
        check(design["gba_above_requested"] > design["max_far_area"] * 1.0001, "reg.max_far",
              f"requested above-ground GBA {design['gba_above_requested']:,.0f} exceeds FAR limit {design['max_far_area']:,.0f}")
    if design.get("max_coverage_area") is not None and a.get("dev.footprint") is not None:
        check(a["dev.footprint"] > design["max_coverage_area"] * 1.0001, "reg.min_open_area_pct",
              f"footprint {a['dev.footprint']:,.0f} exceeds max coverage {design['max_coverage_area']:,.0f}")
    if design.get("max_units_density") is not None:
        check(design["units"] > design["max_units_density"], "reg.min_land_per_unit",
              f"{design['units']} units vs density limit {design['max_units_density']}")
    if a.get("reg.max_units") is not None:
        check(design["units"] > a["reg.max_units"], "reg.max_units", f"{design['units']} units vs {a['reg.max_units']} allowed")
    if a.get("reg.max_underground_levels") is not None:
        check((a.get("dev.levels_below") or 0) > a["reg.max_underground_levels"], "reg.max_underground_levels",
              f"{a.get('dev.levels_below')} underground levels vs {a['reg.max_underground_levels']} allowed")
    if a.get("reg.max_height_m") is not None and a.get("dev.stories"):
        est_height = a["dev.stories"] * 3.2
        check(est_height > a["reg.max_height_m"], "reg.max_height_m",
              f"~{est_height:.0f} m estimated (3.2 m per story) vs {a['reg.max_height_m']:g} m allowed")
    units = design.get("units") or 0
    spaces = a.get("dev.parking_spaces")
    if units and spaces is not None:
        if a.get("reg.parking_min_per_unit") is not None:
            check(spaces < a["reg.parking_min_per_unit"] * units, "reg.parking_min_per_unit",
                  f"{spaces} spaces vs minimum {a['reg.parking_min_per_unit'] * units:.0f}")
        if a.get("reg.parking_max_per_unit") is not None:
            check(spaces > a["reg.parking_max_per_unit"] * units, "reg.parking_max_per_unit",
                  f"{spaces} spaces vs maximum {a['reg.parking_max_per_unit'] * units:.0f}")
    return issues
