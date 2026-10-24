"""Core time-value-of-money helpers. Monthly periods throughout.

Convention: cash flow index t is the END of month t; t = 0 is the closing date.
IRRs are computed on monthly flows and annualized as (1 + r)^12 - 1.
"""

from __future__ import annotations

import math
from typing import Sequence


def monthly_rate(annual_pct: float) -> float:
    """Effective monthly rate for an effective annual rate in percent."""
    return (1 + annual_pct / 100) ** (1 / 12) - 1


def nominal_monthly(annual_pct: float) -> float:
    """Nominal annual rate (loan convention, e.g. TIIE + spread) divided by 12."""
    return annual_pct / 100 / 12


def npv(rate_monthly: float, flows: Sequence[float]) -> float:
    return sum(cf / (1 + rate_monthly) ** t for t, cf in enumerate(flows))


def irr_monthly(flows: Sequence[float]) -> float | None:
    """Monthly IRR, or None when undefined (no sign change / no root in range).

    Scans for the first sign change of NPV over a rate grid, then bisects.
    Returns the root closest to zero when several exist.
    """
    flows = list(flows)
    if not flows or not (any(cf > 1e-9 for cf in flows) and any(cf < -1e-9 for cf in flows)):
        return None
    # monthly rates: -60% .. -5% coarse, -5% .. +30% fine, 30% .. 100% coarse
    grid = [-0.60 + i * 0.01 for i in range(56)]
    grid += [-0.05 + i * 0.0025 for i in range(140)]
    grid += [0.30 + i * 0.02 for i in range(36)]

    rev = flows[::-1]

    def f(r: float) -> float:  # NPV by Horner's rule (fast, no powers)
        d = 1 / (1 + r)
        val = 0.0
        try:
            for cf in rev:
                val = val * d + cf
        except OverflowError:
            return math.nan
        return val

    roots = []
    prev_r, prev_v = grid[0], f(grid[0])
    for r in grid[1:]:
        v = f(r)
        if not (math.isnan(v) or math.isnan(prev_v)) and (prev_v == 0 or prev_v * v < 0):
            lo, hi, flo = prev_r, r, prev_v
            for _ in range(80):
                mid = (lo + hi) / 2
                fm = f(mid)
                if flo * fm <= 0:
                    hi = mid
                else:
                    lo, flo = mid, fm
            roots.append((lo + hi) / 2)
        prev_r, prev_v = r, v
    if not roots:
        return None
    return min(roots, key=abs)


def annualize(r_monthly: float | None) -> float | None:
    if r_monthly is None:
        return None
    return (1 + r_monthly) ** 12 - 1


def irr_annual(flows: Sequence[float]) -> float | None:
    """Annualized IRR as a fraction (0.18 = 18%), or None if undefined."""
    return annualize(irr_monthly(flows))


def s_curve(n: int) -> list[float]:
    """Weights summing to 1 over n months, shaped like a construction S-curve.

    Uses the increments of (1 - cos(pi * x)) / 2: slow start, peak mid-way, slow finish.
    """
    if n <= 0:
        return []
    cum = [(1 - math.cos(math.pi * i / n)) / 2 for i in range(n + 1)]
    return [cum[i + 1] - cum[i] for i in range(n)]


def even(n: int) -> list[float]:
    return [1 / n] * n if n > 0 else []


def payment(rate_monthly: float, n_months: int, principal: float) -> float:
    """Level monthly payment that amortizes principal over n months."""
    if n_months <= 0:
        return principal
    if abs(rate_monthly) < 1e-12:
        return principal / n_months
    return principal * rate_monthly / (1 - (1 + rate_monthly) ** -n_months)
