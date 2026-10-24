"""File uploads: store the file privately and extract its text deterministically.

Supported: PDF (pypdf), Excel .xlsx/.xlsm (openpyxl, cached cell values), Word .docx (python-docx), CSV, TXT/MD,
and images (PNG/JPG/WEBP, read by the vision-capable model). Scanned PDFs with no text layer are sent to the
model as a file. Extracted text is UNTRUSTED input: it is only ever shown to the Document agent wrapped as data,
and anything it suggests becomes a pending proposal.
"""

from __future__ import annotations

import csv
import hashlib
import io
import re
import uuid
from pathlib import Path

from .config import DATA_DIR

UPLOAD_DIR = DATA_DIR / "uploads"
MAX_BYTES = 15 * 1024 * 1024
MAX_TEXT = 300_000
EXT_KIND = {".pdf": "pdf", ".xlsx": "excel", ".xlsm": "excel", ".docx": "word", ".csv": "csv", ".txt": "text", ".md": "text",
            ".png": "image", ".jpg": "image", ".jpeg": "image", ".webp": "image"}
IMAGE_MIME = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}


class UploadError(ValueError):
    pass


def kind_for(filename: str) -> str:
    ext = Path(filename).suffix.lower()
    if ext == ".xls":
        raise UploadError("Old .xls files aren't supported. Open the file in Excel and save it as .xlsx.")
    if ext == ".doc":
        raise UploadError("Old .doc files aren't supported. Save the file as .docx or PDF.")
    if ext not in EXT_KIND:
        raise UploadError(f"Unsupported file type '{ext}'. Use PDF, Excel (.xlsx), Word (.docx), CSV, TXT or an image.")
    return EXT_KIND[ext]


def save_file(owner: str | None, filename: str, data: bytes) -> Path:
    if len(data) > MAX_BYTES:
        raise UploadError("File is larger than 15 MB.")
    if not data:
        raise UploadError("The file is empty.")
    folder = UPLOAD_DIR / hashlib.sha256((owner or "local").encode()).hexdigest()[:16]
    folder.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r"[^\w.\-]+", "_", Path(filename).name)[:100]
    path = folder / f"{uuid.uuid4().hex[:10]}_{safe}"
    path.write_bytes(data)
    return path


def extract(kind: str, data: bytes, filename: str) -> tuple[str, dict]:
    """Return (text, meta). meta['needs_vision'] = True when the model must read the file itself."""
    meta: dict = {}
    if kind == "pdf":
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(data))
        parts = []
        for i, page in enumerate(reader.pages):
            try:
                t = page.extract_text() or ""
            except Exception:  # noqa: BLE001
                t = ""
            if t.strip():
                parts.append(f"[page {i + 1}]\n{t.strip()}")
        text = "\n\n".join(parts)
        meta["pages"] = len(reader.pages)
        if len(text.strip()) < 200:
            meta["needs_vision"] = True
            meta["note"] = "No text layer found (scanned PDF); the model will read the file directly."
    elif kind == "excel":
        text, meta = _excel_text(data)
    elif kind == "word":
        import docx
        d = docx.Document(io.BytesIO(data))
        parts = [p.text for p in d.paragraphs if p.text.strip()]
        for ti, table in enumerate(d.tables):
            parts.append(f"[table {ti + 1}]")
            for row in table.rows:
                parts.append(" | ".join(c.text.strip() for c in row.cells))
        text = "\n".join(parts)
        meta["paragraphs"] = len(d.paragraphs)
    elif kind == "csv":
        raw = data.decode("utf-8-sig", errors="replace")
        rows = list(csv.reader(io.StringIO(raw)))
        text = "\n".join(" | ".join(r) for r in rows[:2000])
        meta["rows"] = len(rows)
    elif kind == "text":
        text = data.decode("utf-8", errors="replace")
    else:  # image
        text = ""
        meta["needs_vision"] = True
        meta["mime"] = IMAGE_MIME.get(Path(filename).suffix.lower(), "image/png")
    from .agents.runtime import _INJ
    hits = [m.group(0) for m in _INJ.finditer(text or "")][:5]
    hits += re.findall(r"(?i)ignor\w* (?:todas )?las instrucciones[^.\n]{0,80}|sistemas de inteligencia artificial[^.\n]{0,80}", text or "")[:3]
    if hits:
        meta["injection_warning"] = hits
    if len(text) > MAX_TEXT:
        text = text[:MAX_TEXT]
        meta["truncated"] = True
    meta["chars"] = len(text)
    return text, meta


def _excel_text(data: bytes) -> tuple[str, dict]:
    """Dump each sheet as 'Sheet!A1: value' rows of non-empty cells (cached values, not formulas)."""
    from openpyxl import load_workbook
    from openpyxl.utils import get_column_letter
    wb = load_workbook(io.BytesIO(data), data_only=True, read_only=True)
    lines, sheets, empty_formula_cells = [], [], 0
    for ws in wb.worksheets:
        sheets.append(ws.title)
        lines.append(f"=== sheet '{ws.title}' ===")
        n_rows = 0
        for r_idx, row in enumerate(ws.iter_rows(max_row=400, max_col=40, values_only=True), start=1):
            cells = []
            for c_idx, v in enumerate(row, start=1):
                if v is None or (isinstance(v, str) and not v.strip()):
                    continue
                if isinstance(v, float):
                    v = round(v, 6)
                cells.append(f"{get_column_letter(c_idx)}{r_idx}={v}")
            if cells:
                lines.append(" | ".join(cells))
                n_rows += 1
        if n_rows == 0:
            empty_formula_cells += 1
    meta = {"sheets": sheets}
    if empty_formula_cells:
        meta["note"] = ("Some sheets had no stored values. If the workbook uses formulas, open it in Excel, save it, "
                        "and upload again so the calculated values are included.")
    return "\n".join(lines), meta


def chunks_for_question(text: str, question: str, budget: int = 40_000, size: int = 2_500) -> str:
    """Pick the most relevant chunks of a long document for a question (simple keyword overlap, no embeddings)."""
    if len(text) <= budget:
        return text
    words = {w for w in re.findall(r"\w{4,}", question.lower())}
    pieces = [text[i:i + size] for i in range(0, len(text), size)]
    scored = sorted(range(len(pieces)), key=lambda i: -sum(pieces[i].lower().count(w) for w in words))
    keep = sorted(scored[: max(1, budget // size)])
    return "\n…\n".join(pieces[i] for i in keep)
