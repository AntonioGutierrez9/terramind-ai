"""Deterministic parser for Mexico City zoning codes (e.g. "H/4/20/M", "HM 6/30/Z", "HC-3-20-B").

Format used by CDMX urban development programs: USE / STORIES / MIN OPEN AREA % / DENSITY LETTER.
Density letters per Norma General de Ordenación No. 11 (Gaceta Oficial, 8 Apr 2005; PAOT copy:
https://paot.mx/centro/normas_a/2015/NGO_11_08_04_2005.pdf):
  A  = one dwelling per 33 m² of land      M  = one per 50 m²
  B  = one per 100 m²                       MB = one per 200 m²
  R  = one per 500 or 1,000 m² (the program states which)
  Z  = whatever the program sets for that zone (no fixed ratio)
Dwellings = land area / ratio, rounding fractions of 0.5 or more up.
Programs are updated over time, so the result is labelled "parsed from code; confirm with the current program / certificate".
"""

from __future__ import annotations

import math
import re

DENSITY_M2_PER_DWELLING = {"A": 33.0, "M": 50.0, "B": 100.0, "MB": 200.0}
USES = {
    "H": "Habitacional (residential)", "HC": "Habitacional con comercio en planta baja", "HO": "Habitacional con oficinas",
    "HM": "Habitacional mixto (mixed use)", "CB": "Centro de barrio", "E": "Equipamiento", "I": "Industria",
    "EA": "Espacios abiertos", "AV": "Áreas verdes", "CS": "Comercio y servicios",
}
SOURCE_URL = "https://paot.mx/centro/normas_a/2015/NGO_11_08_04_2005.pdf"

_CODE = re.compile(r"^\s*([A-Za-z]{1,3})\s*[/\- ]\s*(\d{1,3})\s*[/\- ]\s*(\d{1,2}(?:\.\d+)?)\s*(?:[/\- ]\s*([A-Za-z]{1,2}))?\s*$")


class ZoningCodeError(ValueError):
    pass


def parse_cdmx_code(code: str, land_area: float | None = None) -> dict:
    m = _CODE.match(code or "")
    if not m:
        raise ZoningCodeError("Use the format USE/STORIES/OPEN-AREA%/DENSITY, e.g. H/4/20/M or HM/6/30/Z.")
    use, stories, open_pct, letter = m.group(1).upper(), int(m.group(2)), float(m.group(3)), (m.group(4) or "").upper() or None
    if not (1 <= stories <= 200):
        raise ZoningCodeError("Stories must be between 1 and 200.")
    if not (0 <= open_pct < 100):
        raise ZoningCodeError("Open area must be between 0 and 99%.")
    out: dict = {
        "code": f"{use}/{stories}/{open_pct:g}" + (f"/{letter}" if letter else ""),
        "use": use, "use_label": USES.get(use, "Use per the program's table"),
        "max_stories": stories, "min_open_area_pct": open_pct,
        "max_far": round(stories * (1 - open_pct / 100), 4),
        "density_letter": letter, "min_land_per_unit": None, "max_units": None, "notes": [],
    }
    if letter in DENSITY_M2_PER_DWELLING:
        ratio = DENSITY_M2_PER_DWELLING[letter]
        out["min_land_per_unit"] = ratio
        if land_area:
            q = land_area / ratio
            out["max_units"] = int(math.floor(q) + (1 if q - math.floor(q) >= 0.5 else 0))
    elif letter == "R":
        out["notes"].append("Density R is one dwelling per 500 or 1,000 m² depending on the program; enter the ratio manually.")
    elif letter == "Z":
        out["notes"].append("Density Z: the number of dwellings is set by the program for the zone (no fixed land ratio).")
    elif letter:
        out["notes"].append(f"Density letter '{letter}' is not in Norma 11's table; check the program.")
    out["notes"].append("Parsed deterministically from the code. Confirm against the current program or the Certificado Único de Zonificación.")
    return out


def zoning_code_changes(parsed: dict) -> list[dict]:
    """Registry changes implied by a parsed code."""
    ch = [{"key": "reg.max_stories", "value": parsed["max_stories"]},
          {"key": "reg.min_open_area_pct", "value": parsed["min_open_area_pct"]},
          {"key": "reg.max_far", "value": parsed["max_far"]}]
    if parsed.get("min_land_per_unit"):
        ch.append({"key": "reg.min_land_per_unit", "value": parsed["min_land_per_unit"]})
    return ch
