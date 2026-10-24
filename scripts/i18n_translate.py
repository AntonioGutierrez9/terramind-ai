"""Translate the extracted UI strings to Mexican Spanish with the course model (one-time; result is committed).

    python scripts/i18n_translate.py     → frontend/src/i18n/es.json   (keeps existing reviewed entries)
"""
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.config import cost_usd  # noqa: E402  (loads .env)
from openai import OpenAI  # noqa: E402

GLOSSARY = """Use Mexican Spanish for a professional real estate investment platform. Terminology:
IRR → TIR; NPV → VPN; MOIC → MOIC; equity → capital (equity IRR → TIR del capital); project IRR → TIR del proyecto;
hard costs → costos directos; soft costs → costos indirectos; developer fee → honorarios del desarrollador;
presales → preventas; absorption → absorción; sales pace → ritmo de ventas; GDV → valor total de ventas (GDV);
TDC → costo total de desarrollo (CTD); cap rate → tasa de capitalización (cap rate); NOI → NOI (ingreso operativo neto);
DSCR → DSCR; LTC/LTV → LTC/LTV; covenant → covenant; waterfall → cascada de distribuciones; preferred return → retorno preferente;
promote → promote; sponsor → sponsor; Investment Committee → Comité de Inversión; zoning → zonificación; FAR → CUS (FAR);
open area → área libre; saleable area → área vendible; GBA → área bruta (GBA); unit mix → mezcla de unidades;
build-to-sell → desarrollo para venta; build-to-rent → desarrollo para renta; guest → invitado; sign in → iniciar sesión;
Assumption Center → Centro de supuestos; Audit Trail → Bitácora de cambios; Portfolio → Portafolio; funding gap → faltante de financiamiento.
Keep brand names (TerraMind AI), acronyms, numbers, symbols (%, m², ×, →, ·, •), emoji and capitalization style (Title Case stays short).
If an item is not user-facing UI text (e.g. code, a CSS class, a variable name), return null for it."""

src = json.loads((ROOT / "frontend/src/i18n/strings_en.json").read_text(encoding="utf-8"))
out_path = ROOT / "frontend/src/i18n/es.json"
done = json.loads(out_path.read_text(encoding="utf-8")) if out_path.exists() else {}
todo = [s for s in src if s not in done]
key = os.environ["PORTKEY_API_KEY"]
client = OpenAI(api_key=key, base_url="https://api.portkey.ai/v1", default_headers={"x-portkey-api-key": key, "x-portkey-provider": "openai"})
total_cost = 0.0
for i in range(0, len(todo), 120):
    batch = todo[i:i + 120]
    prompt = (GLOSSARY + "\n\nTranslate each English UI string. Reply with ONLY a JSON object mapping each input string exactly to its "
              "Spanish translation (or null).\n\n" + json.dumps(batch, ensure_ascii=False))
    r = client.responses.create(model="gpt-6-luna", input=prompt, reasoning={"effort": "low"})
    total_cost += cost_usd(r.usage.input_tokens, r.usage.output_tokens)
    text = r.output_text.strip()
    text = text[text.find("{"): text.rfind("}") + 1]
    try:
        m = json.loads(text)
    except json.JSONDecodeError:
        print("batch", i, "unparseable; skipped")
        continue
    for s in batch:
        if m.get(s):
            done[s] = m[s]
    print(f"batch {i // 120 + 1}: {len(m)} items, running cost ${total_cost:.4f}")
    out_path.write_text(json.dumps(done, ensure_ascii=False, indent=0, sort_keys=True), encoding="utf-8")
print("entries:", len(done), "cost:", round(total_cost, 4))
