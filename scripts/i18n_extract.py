"""Collect user-visible English strings from the frontend source and the variable registry (for the Spanish dictionary).

    python scripts/i18n_extract.py      → frontend/src/i18n/strings_en.json
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

strings: set[str] = set()


def add(s: str) -> None:
    s = re.sub(r"\s+", " ", s).strip()
    if len(s) < 2 or len(s) > 400:
        return
    if not re.search(r"[A-Za-z]{2}", s):
        return
    if re.fullmatch(r"[\w.\-/]+", s) and (" " not in s) and (s.islower() or "_" in s or "." in s or "/" in s):
        return  # identifiers, css classes, keys, paths
    if re.search(r"^(https?:|/api/|#|var\(|rgba?\(|\$\{)", s) or "=>" in s or "{" in s or "}" in s:
        return
    strings.add(s)


SRC = ROOT / "frontend" / "src"
for f in SRC.rglob("*.tsx"):
    text = f.read_text(encoding="utf-8")
    # JSX text between tags
    for m in re.finditer(r">([^<>{}]*[A-Za-z][^<>{}]*)<", text):
        add(m.group(1))
    # JSX text segments split by {expressions}: take literal pieces inside tags
    for m in re.finditer(r">([^<>]*\{[^<>]*)<", text):
        for piece in re.split(r"\{[^{}]*\}", m.group(1)):
            add(piece)
    # common string props / object fields
    for m in re.finditer(r"""(?:title|sub|label|placeholder|eyebrow|hint|msg|summary|note|tooltip|aria-label|header|caption|text|content|description)\s*[:=]\s*(['"`])((?:(?!\1).){2,300})\1""", text):
        add(m.group(2))
    # string literals inside arrays of [key, 'Label'] pairs and ternaries
    for m in re.finditer(r"""['"]([A-Z][^'"\n]{2,160})['"]""", text):
        add(m.group(1))
    for m in re.finditer(r"`([A-Z][^`$\n]{2,160})`", text):
        add(m.group(1))

from engine.registry import REGISTRY, SECTIONS, PROFILE_CHOICES  # noqa: E402
from engine.custom_vars import EFFECTS  # noqa: E402
for spec in REGISTRY.values():
    add(spec["label"])
    if spec["help"]:
        add(spec["help"])
for v in SECTIONS.values():
    add(v)
for v, _ in EFFECTS.values():
    add(v)

out = ROOT / "frontend" / "src" / "i18n"
out.mkdir(exist_ok=True)
data = sorted(strings)
(out / "strings_en.json").write_text(json.dumps(data, indent=0, ensure_ascii=False), encoding="utf-8")
print(len(data), "strings")
