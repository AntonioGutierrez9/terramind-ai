"""Build the self-contained report.html and slides.html: replace src="shot:NAME" with base64-embedded JPEGs.

    python scripts/build_docs.py
"""
import base64
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SHOTS = ROOT / "docs" / "screenshots"


def embed(src: Path, out: Path) -> None:
    html = src.read_text(encoding="utf-8")

    def repl(m):
        name = m.group(1)
        data = base64.b64encode((SHOTS / f"{name}.jpg").read_bytes()).decode()
        return f'src="data:image/jpeg;base64,{data}"'

    html, n = re.subn(r'src="shot:([\w\-]+)"', repl, html)
    out.write_text(html, encoding="utf-8")
    print(f"{out.name}: {n} images embedded, {out.stat().st_size / 1e6:.1f} MB")


embed(ROOT / "docs" / "report_src.html", ROOT / "report.html")
if (ROOT / "docs" / "slides_src.html").exists():
    embed(ROOT / "docs" / "slides_src.html", ROOT / "slides.html")
