"""Export a project as a LIVE Excel financial model.

Every number in the workbook is an Excel formula that traces back to one Assumptions tab (blue inputs), so changing
any assumption in Excel flows through the development program, construction schedule, sales schedule, cash flow,
financing, equity waterfall, budget and outputs (charts included). The workbook mirrors TerraMind's engine; the
Outputs tab includes a reconciliation against the engine's values at export.

Conventions (standard financial-model formatting): blue = inputs, black = formulas, yellow fill = key inputs,
percentages stored as fractions, negatives in parentheses. Debt is sized on total cost including financing, which is
circular by nature; the workbook enables iterative calculation (like most development models).
"""

from __future__ import annotations

import io
import math
from datetime import date

from openpyxl import Workbook
from openpyxl.chart import BarChart, LineChart, PieChart, Reference
from openpyxl.comments import Comment
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.workbook.defined_name import DefinedName

from engine.custom_vars import EFFECTS
from engine.registry import REGISTRY, is_ground_up, model_mode

FONT = "Arial"
BLUE = Font(name=FONT, color="0000FF", size=10)
BLACK = Font(name=FONT, color="000000", size=10)
BOLD = Font(name=FONT, bold=True, size=10)
HDR = Font(name=FONT, bold=True, color="FFFFFF", size=10)
TITLE = Font(name=FONT, bold=True, size=16, color="17345E")
SUB = Font(name=FONT, italic=True, size=9, color="666666")
NAVY = PatternFill("solid", fgColor="17345E")
SECTION = PatternFill("solid", fgColor="E6EDF7")
YELLOW = PatternFill("solid", fgColor="FFFF00")
TOTALFILL = PatternFill("solid", fgColor="F2F4F7")
THIN = Border(top=Side(style="thin", color="BFBFBF"))

MONEY = '#,##0;(#,##0);"-"'
MONEY_M = '#,##0.0,,"M";(#,##0.0,,"M");"-"'
PCT = '0.0%;(0.0%);"-"'
PCT2 = '0.00%;(0.00%);"-"'
NUM = '#,##0;(#,##0);"-"'
NUM1 = '#,##0.0;(#,##0.0);"-"'
MULT = '0.00"x"'

MONTH_COL0 = 4  # column D = month 0


def nm(key: str) -> str:
    return "in_" + key.replace(".", "_")


class Builder:
    def __init__(self, project: dict, result: dict, analysis: dict | None):
        self.p = project
        self.a = project["assumptions"]
        self.prof = project["profile"]
        self.res = result
        self.analysis = analysis
        self.mode = model_mode(self.prof)
        self.ground_up = is_ground_up(self.prof)
        self.cur = self.prof.get("currency") or "MXN"
        horizon = result["schedule"]["horizon"] if result.get("status") == "ok" else 60
        self.H = int(min(max(horizon + 36, 96), 240))  # month columns (0..H-1); extra room for edits in Excel
        self.wb = Workbook()
        self.names: dict[str, str] = {}

    # ------------------------------------------------------------------ helpers
    def col(self, t: int) -> str:
        return get_column_letter(MONTH_COL0 + t)

    @property
    def last_col(self) -> str:
        return self.col(self.H - 1)

    def define(self, name: str, ref: str) -> None:
        self.wb.defined_names[name] = DefinedName(name, attr_text=ref)
        self.names[name] = ref

    def sheet(self, title: str, tab_color: str = "17345E"):
        ws = self.wb.create_sheet(title)
        ws.sheet_properties.tabColor = tab_color
        ws.sheet_view.showGridLines = False
        return ws

    def header(self, ws, title: str, subtitle: str) -> None:
        ws["A1"] = title
        ws["A1"].font = TITLE
        ws["A2"] = subtitle
        ws["A2"].font = SUB

    def month_header(self, ws, row: int = 4) -> None:
        ws.cell(row=row, column=1, value="Month").font = HDR
        ws.cell(row=row, column=2, value="Total").font = HDR
        ws.cell(row=row, column=3, value="Unit / note").font = HDR
        for c in (1, 2, 3):
            ws.cell(row=row, column=c).fill = NAVY
        for t in range(self.H):
            c = ws.cell(row=row, column=MONTH_COL0 + t, value=t if t == 0 else f"={self.col(t - 1)}{row}+1")
            c.font, c.fill, c.alignment = HDR, NAVY, Alignment(horizontal="center")
            ws.column_dimensions[self.col(t)].width = 11
        ws.column_dimensions["A"].width = 46
        ws.column_dimensions["B"].width = 16
        ws.column_dimensions["C"].width = 22
        ws.freeze_panes = ws.cell(row=row + 1, column=MONTH_COL0)

    def mrow(self, ws, row: int, label: str, fn, fmt: str = MONEY, total: str | None = "sum", note: str = "", bold=False, name: str | None = None):
        """Monthly row: fn(col, prev_col, t_ref) -> formula (without '=')."""
        ws.cell(row=row, column=1, value=label).font = BOLD if bold else BLACK
        ws.cell(row=row, column=3, value=note).font = SUB
        for t in range(self.H):
            c = self.col(t)
            prev = self.col(t - 1) if t > 0 else None
            cell = ws.cell(row=row, column=MONTH_COL0 + t, value="=" + fn(c, prev, f"{c}$4"))
            cell.number_format, cell.font = fmt, BOLD if bold else BLACK
        if total == "sum":
            tc = ws.cell(row=row, column=2, value=f"=SUM({self.col(0)}{row}:{self.last_col}{row})")
            tc.number_format, tc.font = fmt, BOLD
        if name:
            self.define(name, f"'{ws.title}'!${self.col(0)}${row}:${self.last_col}${row}")
        if bold:
            for cc in range(1, MONTH_COL0 + self.H):
                ws.cell(row=row, column=cc).fill = TOTALFILL
        return f"{row}"

    def section_row(self, ws, row: int, label: str, width: int | None = None) -> None:
        ws.cell(row=row, column=1, value=label).font = BOLD
        for cc in range(1, (width or (MONTH_COL0 + self.H))):
            ws.cell(row=row, column=cc).fill = SECTION

    def scalar(self, ws, row: int, label: str, formula, fmt: str = MONEY, name: str | None = None, note: str = "", bold=False):
        ws.cell(row=row, column=1, value=label).font = BOLD if bold else BLACK
        c = ws.cell(row=row, column=2, value=formula if not isinstance(formula, str) or not formula.startswith("=") else formula)
        c.number_format, c.font = fmt, BOLD if bold else BLACK
        if note:
            ws.cell(row=row, column=3, value=note).font = SUB
        if name:
            self.define(name, f"'{ws.title}'!$B${row}")
        return f"'{ws.title}'!$B${row}"

    # ------------------------------------------------------------------ Assumptions
    def assumptions(self):
        ws = self.sheet("Assumptions", "0000FF")
        self.header(ws, "Assumptions", "All inputs of the model. Blue cells are inputs: change any of them and the whole workbook recalculates.")
        ws.column_dimensions["A"].width = 48
        ws.column_dimensions["B"].width = 18
        ws.column_dimensions["C"].width = 18
        ws.column_dimensions["D"].width = 60
        r = 4
        for h, ccol in (("Assumption", 1), ("Value", 2), ("Unit", 3), ("Source / note", 4)):
            c = ws.cell(row=r, column=ccol, value=h)
            c.font, c.fill = HDR, NAVY
        r += 1
        meta = self.p["meta"]
        sections = [("Project", None), ("Site & acquisition", "site"), ("Regulation & zoning (legal limits)", "reg"),
                    ("Development configuration", "dev"), ("Sales revenue", "rev"), ("Rental income", "rent"),
                    ("Development budget", "cost"), ("Schedule", "sch"), ("Financing", "fin"), ("Valuation", "val")]
        for title, sec in sections:
            self.section_row(ws, r, title, 5)
            r += 1
            if sec is None:
                for label, val, name in (("Project", self.p["name"], None), ("Currency", self.cur, None),
                                         ("For-sale model (1) or rental model (0)", 1 if self.mode == "sale" else 0, "in_mode_sale"),
                                         ("Ground-up development (1) or acquisition (0)", 1 if self.ground_up else 0, "in_ground_up"),
                                         ("Circuit breaker: size debt on cost incl. financing (1 = on, 0 = break the circular loop)", 1, "in_circ_switch")):
                    ws.cell(row=r, column=1, value=label).font = BLACK
                    c = ws.cell(row=r, column=2, value=val)
                    c.font = BLUE
                    if name:
                        self.define(name, f"Assumptions!$B${r}")
                        ws.cell(row=r, column=4, value="Switches the revenue logic; set by the project's business model").font = SUB
                    r += 1
                continue
            for key, spec in REGISTRY.items():
                if spec["section"] != sec:
                    continue
                v = self.a.get(key)
                src = (meta.get(key) or {}).get("source")
                if v is None and spec["suggested"] is not None:
                    v, src = spec["suggested"], "default (unverified)"
                pct = spec["unit"].startswith("%")
                ws.cell(row=r, column=1, value=spec["label"]).font = BLACK
                if spec["kind"] == "bool":
                    val = bool(v) if v is not None else None
                elif pct and isinstance(v, (int, float)):
                    val = v / 100
                else:
                    val = v
                c = ws.cell(row=r, column=2, value=val)
                c.font = BLUE
                if pct:
                    c.number_format = PCT2
                elif spec["unit"] in ("currency",) or spec["unit"].startswith("currency/"):
                    c.number_format = MONEY
                elif spec["kind"] in ("number", "int"):
                    c.number_format = '#,##0.##'
                if key in ("site.land_price", "rev.price_per_area", "cost.hard_per_area", "rev.absorption_per_month", "sch.construction_months",
                           "fin.senior_ltc_pct", "rent.rent_per_area_month", "rent.exit_cap_pct"):
                    c.fill = YELLOW
                unit = spec["unit"].replace("currency", self.cur).replace("area", "m²")
                ws.cell(row=r, column=3, value=unit).font = SUB
                note = f"Source: {src}" if src else ("Not set" if v is None else "")
                m = meta.get(key) or {}
                if m.get("source_url"):
                    note += f" · {m.get('source_title') or ''} {m['source_url']}"
                ws.cell(row=r, column=4, value=note).font = SUB
                if spec["help"]:
                    c.comment = Comment(spec["help"], "TerraMind")
                self.define(nm(key), f"Assumptions!$B${r}")
                r += 1
        # sustainability (enabled measures, summarized as inputs)
        on = [m for m in self.a.get("sustainability_measures") or [] if m.get("enabled")]
        self.section_row(ws, r, "Sustainability (enabled measures)", 5)
        r += 1
        for label, val, name, fmt in (
            ("Capex of enabled measures", sum(float(m.get("capex") or 0) for m in on), "in_green_capex", MONEY),
            ("Sale price premium", sum(float(m.get("sale_premium_pct") or 0) for m in on) / 100, "in_green_sale_prem", PCT2),
            ("Rent premium", sum(float(m.get("rent_premium_pct") or 0) for m in on) / 100, "in_green_rent_prem", PCT2),
            ("Net annual savings to the owner (rentals)", sum(float(m.get("savings_annual") or 0) - float(m.get("maintenance_annual") or 0) for m in on),
             "in_green_savings", MONEY)):
            ws.cell(row=r, column=1, value=label).font = BLACK
            c = ws.cell(row=r, column=2, value=val)
            c.font, c.number_format = BLUE, fmt
            ws.cell(row=r, column=4, value=", ".join(m["name"] for m in on) or "No measures enabled").font = SUB
            self.define(name, f"Assumptions!$B${r}")
            r += 1
        r += 1
        r = self.unit_mix_table(ws, r)
        r = self.split_table(ws, r)
        r = self.schedule_tables(ws, r)
        r = self.custom_var_table(ws, r)
        ws.cell(row=r + 1, column=1, value="Legend: blue = input · black = formula · yellow fill = key driver. Percentages are stored as fractions.").font = SUB

    def unit_mix_table(self, ws, r):
        self.section_row(ws, r, "Unit mix (shares of saleable area)", 9)
        r += 1
        heads = ["Type", "Size (m²)", "Share", "Terrace (m²)", "Price premium", "Bedrooms", "Bathrooms"]
        for i, h in enumerate(heads):
            c = ws.cell(row=r, column=1 + i, value=h)
            c.font, c.fill = HDR, NAVY
        r += 1
        start = r
        mix = self.a.get("unit_mix") or []
        for i in range(8):
            t = mix[i] if i < len(mix) else None
            vals = [t["name"], t["size"], t["share_pct"] / 100, t.get("terrace") or 0, (t.get("premium_pct") or 0) / 100,
                    t.get("bedrooms"), t.get("bathrooms")] if t else ["", 0, 0, 0, 0, None, None]
            for j, v in enumerate(vals):
                c = ws.cell(row=r, column=1 + j, value=v)
                c.font = BLUE
                c.number_format = PCT if j in (2, 4) else '#,##0.##'
            r += 1
        end = r - 1
        for nmn, cc in (("mix_name", "A"), ("mix_size", "B"), ("mix_share", "C"), ("mix_terrace", "D"), ("mix_prem", "E")):
            self.define(nmn, f"Assumptions!${cc}${start}:${cc}${end}")
        ws.cell(row=r, column=1, value="Total share (must be 100%)").font = BOLD
        c = ws.cell(row=r, column=3, value=f"=SUM(C{start}:C{end})")
        c.number_format, c.font = PCT, BOLD
        self.mix_rows = (start, end)
        return r + 2

    def split_table(self, ws, r):
        from engine.registry import DEFAULT_HARD_COST_SPLIT
        split = self.a.get("hard_cost_split") or DEFAULT_HARD_COST_SPLIT
        tot = sum(split.values()) or 1
        self.section_row(ws, r, "Hard-cost category split (share of above-ground hard cost)", 5)
        r += 1
        start = r
        for name, share in split.items():
            ws.cell(row=r, column=1, value=name).font = BLACK
            c = ws.cell(row=r, column=2, value=share / tot)
            c.font, c.number_format = BLUE, PCT
            r += 1
        self.split_rows = (start, r - 1)
        return r + 1

    def schedule_tables(self, ws, r):
        A = self.a
        # anchors (computed)
        self.section_row(ws, r, "Milestones (calculated, used by the schedules below)", 5)
        r += 1
        anchors = [("closing", "=0"), ("sales_start", "=Sales_Start"), ("construction_start", "=T_ConStart"), ("delivery", "=T_Delivery")]
        a0 = r
        for name, f in anchors:
            ws.cell(row=r, column=1, value=name).font = BLACK
            ws.cell(row=r, column=2, value=f).font = BLACK
            r += 1
        self.define("anchor_names", f"Assumptions!$A${a0}:$A${r - 1}")
        self.define("anchor_months", f"Assumptions!$B${a0}:$B${r - 1}")
        r += 1

        def table(title, cols, rows, n, prefix, start_fn=True):
            nonlocal r
            self.section_row(ws, r, title, len(cols) + 3)
            r += 1
            for i, h in enumerate(cols + (["Start month", "End month"] if start_fn else [])):
                c = ws.cell(row=r, column=1 + i, value=h)
                c.font, c.fill = HDR, NAVY
            r += 1
            s0 = r
            for i in range(n):
                row = rows[i] if i < len(rows) else None
                for j, (field, default) in enumerate(cols_map[prefix]):
                    v = (row.get(field) if row else default)
                    if field in ("pct",) and row is not None and v is not None and prefix != "land":
                        v = v / 100
                    if prefix == "land" and field == "pct" and row is not None:
                        v = v / 100
                    c = ws.cell(row=r, column=1 + j, value=v)
                    c.font = BLUE
                    if field == "pct":
                        c.number_format = PCT
                    elif field in ("amount",):
                        c.number_format = MONEY
                if start_fn:
                    an = len(cols) - 1
                    anchor_col = get_column_letter(cols_anchor[prefix])
                    off_col = get_column_letter(cols_anchor[prefix] + 1)
                    months_col = get_column_letter(cols_months[prefix]) if cols_months.get(prefix) else None
                    sc = get_column_letter(len(cols) + 1)
                    ws.cell(row=r, column=len(cols) + 1,
                            value=f'=IF({anchor_col}{r}="","",INDEX(anchor_months,MATCH({anchor_col}{r},anchor_names,0))+{off_col}{r})').number_format = NUM
                    if months_col:
                        ws.cell(row=r, column=len(cols) + 2, value=f'=IF({sc}{r}="","",{sc}{r}+{months_col}{r})').number_format = NUM
                r += 1
            s1 = r - 1
            r += 1
            return s0, s1

        cols_map = {
            "sales": [("name", ""), ("anchor", ""), ("offset", 0), ("months", 0), ("units_per_month", 0)],
            "price": [("name", ""), ("anchor", ""), ("offset", 0), ("months", 0), ("pct", 0)],
            "land": [("month", None), ("pct", 0)],
            "flows": [("label", ""), ("type", ""), ("amount", 0), ("anchor", ""), ("offset", 0)],
        }
        cols_anchor = {"sales": 2, "price": 2, "flows": 4}
        cols_months = {"sales": 4, "price": 4}
        s = table("Sales phases (units/month during a period; outside phases the base absorption applies)",
                  ["Phase", "Anchor", "Offset (months)", "Months", "Units / month"], A.get("sales_phases") or [], 8, "sales")
        self.define("sp_start", f"Assumptions!$F${s[0]}:$F${s[1]}")
        self.define("sp_end", f"Assumptions!$G${s[0]}:$G${s[1]}")
        self.define("sp_rate", f"Assumptions!$E${s[0]}:$E${s[1]}")
        p = table("Price phases (% change for contracts signed in the period)",
                  ["Phase", "Anchor", "Offset (months)", "Months", "Price change"], A.get("price_phases") or [], 6, "price")
        self.define("pp_start", f"Assumptions!$F${p[0]}:$F${p[1]}")
        self.define("pp_end", f"Assumptions!$G${p[0]}:$G${p[1]}")
        self.define("pp_pct", f"Assumptions!$E${p[0]}:$E${p[1]}")
        lp = table("Land payment schedule (empty = 100% at closing)", ["Month", "% of price"], A.get("land_payments") or [], 8, "land", start_fn=False)
        self.define("lp_month", f"Assumptions!$A${lp[0]}:$A${lp[1]}")
        self.define("lp_pct", f"Assumptions!$B${lp[0]}:$B${lp[1]}")
        flows = []
        for f in A.get("custom_flows") or []:
            flows.append(f if f.get("anchor") else {**f, "anchor": "closing", "offset": f.get("month", 0)})
        cf = table("Custom one-off cash flows", ["Item", "Type (cost/revenue)", "Amount", "Anchor", "Offset (months)"], flows, 10, "flows")
        self.define("cf_type", f"Assumptions!$B${cf[0]}:$B${cf[1]}")
        self.define("cf_amount", f"Assumptions!$C${cf[0]}:$C${cf[1]}")
        self.define("cf_month", f"Assumptions!$F${cf[0]}:$F${cf[1]}")
        return r

    def custom_var_table(self, ws, r):
        self.section_row(ws, r, "User-defined variables (effect types: " + ", ".join(EFFECTS) + ")", 10)
        r += 1
        heads = ["Variable", "Effect", "Value", "Timing", "Anchor", "Offset", "Months", "Start month", "End month"]
        for i, h in enumerate(heads):
            c = ws.cell(row=r, column=1 + i, value=h)
            c.font, c.fill = HDR, NAVY
        r += 1
        s0 = r
        rows = self.a.get("custom_variables") or []
        for i in range(12):
            v = rows[i] if i < len(rows) else None
            val = v.get("value") if v else 0
            if v and v["effect"] in ("cost_pct_hard", "cost_pct_revenue", "price_pct") and isinstance(val, (int, float)):
                val = val / 100
            if v and v["effect"] == "info":
                val = 0 if not isinstance(val, (int, float)) else val
            vals = [v["label"], v["effect"], val, v.get("timing"), v.get("anchor"), v.get("offset", 0), v.get("months", 12)] if v else ["", "", 0, "", "", 0, 0]
            for j, x in enumerate(vals):
                c = ws.cell(row=r, column=1 + j, value=x)
                c.font = BLUE
            ws.cell(row=r, column=8, value=f'=IF(E{r}="","",INDEX(anchor_months,MATCH(E{r},anchor_names,0))+F{r})')
            ws.cell(row=r, column=9, value=f'=IF(H{r}="","",H{r}+G{r})')
            r += 1
        s1 = r - 1
        for name, cc in (("cv_effect", "B"), ("cv_value", "C"), ("cv_timing", "D"), ("cv_start", "H"), ("cv_end", "I")):
            self.define(name, f"Assumptions!${cc}${s0}:${cc}${s1}")
        return r + 1

    # ------------------------------------------------------------------ Development program
    def development(self):
        ws = self.sheet("Development")
        self.header(ws, "Development program", "Areas, units and legal capacity calculated from the assumptions")
        ws.column_dimensions["A"].width = 46
        ws.column_dimensions["B"].width = 18
        ws.column_dimensions["C"].width = 50
        r = 4
        S = self.scalar
        S(ws, r, "Land area (m²)", "=in_site_land_area", NUM, "D_Land"); r += 1
        S(ws, r, "Maximum site coverage (m²)", "=D_Land*(1-in_reg_min_open_area_pct)", NUM, "D_MaxCov"); r += 1
        S(ws, r, "Maximum FAR", '=IF(in_reg_max_far="",in_reg_max_stories*(1-in_reg_min_open_area_pct),in_reg_max_far)', '0.00"x"', "D_MaxFAR"); r += 1
        S(ws, r, "Maximum buildable GBA (capacity, m²)", "=D_Land*D_MaxFAR", NUM, "D_Capacity"); r += 1
        S(ws, r, "Building footprint (m²)", '=IF(in_dev_footprint="",D_MaxCov,in_dev_footprint)', NUM, "D_Footprint"); r += 1
        S(ws, r, "Above-ground GBA (m²)", '=IF(in_ground_up=1,D_Footprint*in_dev_stories,IF(in_dev_efficiency_pct>0,in_dev_existing_rentable_area/in_dev_efficiency_pct,0))', NUM, "D_GBA"); r += 1
        S(ws, r, "Saleable / leasable area (m²)", '=IF(in_ground_up=1,MAX(D_GBA-in_dev_amenity_area,0)*in_dev_efficiency_pct,in_dev_existing_rentable_area)', NUM, "D_Saleable"); r += 1
        r += 1
        self.section_row(ws, r, "Units by type", 8); r += 1
        for i, h in enumerate(["Type", "Units", "Area (m²)", "Unit price today", "Price per m²"]):
            c = ws.cell(row=r, column=1 + i, value=h)
            c.font, c.fill = HDR, NAVY
        r += 1
        ms, me = self.mix_rows
        u0 = r
        for k in range(me - ms + 1):
            ar = ms + k
            ws.cell(row=r, column=1, value=f"=IF(Assumptions!A{ar}=\"\",\"\",Assumptions!A{ar})")
            ws.cell(row=r, column=2, value=f"=IF(Assumptions!B{ar}>0,INT(D_Saleable*Assumptions!C{ar}/Assumptions!B{ar}+1E-9),0)").number_format = NUM
            ws.cell(row=r, column=3, value=f"=B{r}*Assumptions!B{ar}").number_format = NUM
            ws.cell(row=r, column=4, value=f"=Assumptions!B{ar}*P_Eff*(1+Assumptions!E{ar})*(1+in_rev_floor_view_premium_pct)+Assumptions!D{ar}*P_Eff*in_rev_terrace_value_pct").number_format = MONEY
            ws.cell(row=r, column=5, value=f"=IF(Assumptions!B{ar}>0,D{r}/Assumptions!B{ar},0)").number_format = MONEY
            r += 1
        u1 = r - 1
        ws.cell(row=r, column=1, value="Total").font = BOLD
        ws.cell(row=r, column=2, value=f"=SUM(B{u0}:B{u1})").number_format = NUM
        ws.cell(row=r, column=3, value=f"=SUM(C{u0}:C{u1})").number_format = NUM
        self.define("D_Units", f"Development!$B${r}")
        self.define("D_SoldArea", f"Development!$C${r}")
        self.define("D_UnitsRange", f"Development!$B${u0}:$B${u1}")
        self.define("D_PriceRange", f"Development!$D${u0}:$D${u1}")
        r += 2
        S(ws, r, "Effective base price per m² (incl. green premium and user price variables)",
          "=IF(in_mode_sale=1,in_rev_price_per_area,0)*(1+in_green_sale_prem)*CV_PriceMult", MONEY, "P_Eff"); r += 1
        S(ws, r, "Price multiplier from user-defined variables", '=EXP(SUMPRODUCT((cv_effect="price_pct")*LN(1+cv_value)))', '0.0000', "CV_PriceMult"); r += 1
        S(ws, r, "Average unit price today", "=IF(D_Units>0,SUMPRODUCT(D_UnitsRange,D_PriceRange)/D_Units,0)", MONEY, "D_AvgPrice"); r += 1
        S(ws, r, "Terrace area (m²)", f"=SUMPRODUCT(B{u0}:B{u1},Assumptions!D{ms}:D{me})", NUM); r += 1
        S(ws, r, "Parking spaces", '=IF(in_dev_parking_spaces="",IF(in_reg_parking_min_per_unit="",0,ROUNDUP(in_reg_parking_min_per_unit*D_Units,0)),in_dev_parking_spaces)', NUM, "D_Parking"); r += 1
        S(ws, r, "Below-grade area (m²)", "=IF(in_ground_up=1,D_Parking*in_dev_parking_area_per_space,0)", NUM, "D_Below"); r += 1
        S(ws, r, "Underground levels needed", '=IF(AND(D_Land>0,D_Below>0),ROUNDUP(D_Below/(D_Land*0.95),0),0)', NUM); r += 1
        S(ws, r, "Density limit (max dwellings)", '=IF(in_reg_min_land_per_unit="","No limit entered",INT(D_Land/in_reg_min_land_per_unit))', NUM, "D_MaxUnits"); r += 1
        r += 1
        self.section_row(ws, r, "Compliance checks (TRUE = within the legal limit)", 4); r += 1
        for label, f in (("Stories ≤ maximum stories", '=IF(in_reg_max_stories="",TRUE,in_dev_stories<=in_reg_max_stories)'),
                         ("GBA ≤ FAR capacity", "=D_GBA<=D_Capacity*1.0001"),
                         ("Units ≤ density limit", '=IF(ISNUMBER(D_MaxUnits),D_Units<=D_MaxUnits,TRUE)'),
                         ("Underground levels ≤ maximum", '=IF(in_reg_max_underground_levels="",TRUE,in_dev_levels_below<=in_reg_max_underground_levels)')):
            ws.cell(row=r, column=1, value=label).font = BLACK
            ws.cell(row=r, column=2, value=f).font = BLACK
            r += 1

    # ------------------------------------------------------------------ Construction (monthly costs)
    def construction(self):
        ws = self.sheet("Construction")
        self.header(ws, "Construction & development cost schedule", f"Monthly, {self.cur}. Month 0 = land closing; construction follows pre-development.")
        self.month_header(ws)
        sc = self
        rows = {}
        top = [("Pre-development months", '=IF(in_ground_up=1,IF(in_sch_predev_months="",0,in_sch_predev_months),IF(in_sch_predev_months="",0,in_sch_predev_months))', NUM, "T_Predev"),
               ("Construction months", '=IF(in_sch_construction_months="",0,in_sch_construction_months)', NUM, "T_Con"),
               ("Construction start month", "=T_Predev", NUM, "T_ConStart"),
               ("Delivery month", "=T_Predev+T_Con", NUM, "T_Delivery"),
               ("Above-ground hard cost (today's prices)", '=IF(in_ground_up=1,D_GBA*in_cost_hard_per_area,IF(in_cost_renovation_budget="",0,in_cost_renovation_budget))', MONEY, "C_HardAbove"),
               ("Below-grade hard cost", '=IF(in_ground_up=1,D_Below*IF(in_cost_below_grade_per_area="",0,in_cost_below_grade_per_area),0)', MONEY, "C_HardBelow"),
               ("Fixed site costs (demolition + infrastructure)", '=N(in_cost_demolition)+N(in_cost_infrastructure_fees)', MONEY, "C_FixedSite"),
               ("Hard-cost base for % fees", "=C_HardAbove+C_HardBelow+C_FixedSite+in_green_capex", MONEY, "C_HardBase"),
               ("Soft costs (design + permits + PM + other)", "=C_HardBase*(in_cost_design_pct+in_cost_permits_pct+in_cost_pm_supervision_pct+in_cost_insurance_other_pct)", MONEY, "C_Soft"),
               ("Contingency", "=(C_HardBase+C_Soft)*in_cost_contingency_pct", MONEY, "C_Contingency"),
               ("Developer fee", "=(C_HardBase+C_Soft)*in_cost_developer_fee_pct", MONEY, "C_DevFee"),
               ("User-defined costs spread over construction", '=SUMPRODUCT((cv_effect="cost_fixed")*(cv_timing="construction")*cv_value)+SUMPRODUCT((cv_effect="cost_per_area")*cv_value)*D_GBA+SUMPRODUCT((cv_effect="cost_per_unit")*cv_value)*D_Units+SUMPRODUCT((cv_effect="cost_pct_hard")*cv_value)*C_HardBase', MONEY, "C_CVSpread")]
        ws.insert_rows(5, amount=len(top) + 2)
        for i, (label, f, fmt, name) in enumerate(top):
            sc.scalar(ws, 5 + i, label, f, fmt, name)
        # month header was at row 4 — keep it, monthly rows below the scalar block
        r = 5 + len(top) + 2
        self.con_first = r
        def add(key, label, fn, **kw):
            nonlocal r
            sc.mrow(ws, r, label, fn, **kw)
            rows[key] = r
            r += 1
        add("predev", "Pre-development month (flag)", lambda c, p, t: f"IF(AND({t}>=1,{t}<=T_Predev),1,0)", fmt=NUM, total=None)
        add("con", "Construction month (flag)", lambda c, p, t: f"IF(AND({t}>T_ConStart,{t}<=T_Delivery),1,0)", fmt=NUM, total=None)
        add("w", "Construction spending weight (curve)",
            lambda c, p, t: (f'IF({c}{rows["con"]}=1,IF(in_cost_curve="linear",1/T_Con,IF(in_cost_curve="front_loaded",(T_Con-({t}-T_ConStart)+1)/(T_Con*(T_Con+1)/2),'
                             f'IF(in_cost_curve="back_loaded",({t}-T_ConStart)/(T_Con*(T_Con+1)/2),(COS(PI()*({t}-T_ConStart-1)/T_Con)-COS(PI()*({t}-T_ConStart)/T_Con))/2))),0)'),
            fmt='0.0000', note="S-curve unless changed in Assumptions")
        add("esc", "Construction cost escalation factor", lambda c, p, t: f"(1+in_cost_escalation_pct)^({t}/12)", fmt='0.0000', total=None)
        self.section_row(ws, r, "Costs"); r += 1
        add("land", "Land / property price",
            lambda c, p, t: f"IF(SUM(lp_pct)=0,IF({t}=0,in_site_land_price,0),SUMPRODUCT((lp_month={t})*lp_pct)*in_site_land_price)")
        add("acq", "Acquisition taxes, notary, brokerage & due diligence",
            lambda c, p, t: f"IF({t}=0,in_site_land_price*(in_site_transfer_tax_pct+in_site_legal_notary_pct+in_site_brokerage_pct)+N(in_site_due_diligence),0)")
        add("hard", "Hard costs (escalated) incl. sustainability capex",
            lambda c, p, t: f"(C_HardAbove+C_HardBelow+in_green_capex)*{c}{rows['w']}*{c}{rows['esc']}+IF({t}=IF(T_Con>0,T_ConStart+1,T_ConStart),C_FixedSite,0)")
        add("soft", "Soft costs",
            lambda c, p, t: (f"IF(T_Predev>0,C_HardBase*in_cost_design_pct*0.6*{c}{rows['predev']}/T_Predev+C_HardBase*in_cost_design_pct*0.4*{c}{rows['con']}/MAX(T_Con,1),"
                             f"C_HardBase*in_cost_design_pct*{c}{rows['con']}/MAX(T_Con,1))+IF({t}=T_ConStart,C_HardBase*in_cost_permits_pct,0)"
                             f"+C_HardBase*(in_cost_pm_supervision_pct+in_cost_insurance_other_pct)*{c}{rows['con']}/MAX(T_Con,1)"))
        add("cont", "Contingency", lambda c, p, t: f"C_Contingency*{c}{rows['w']}")
        add("fee", "Developer fee", lambda c, p, t: f"C_DevFee*{c}{rows['con']}/MAX(T_Con,1)")
        add("cv", "User-defined variable costs",
            lambda c, p, t: (f'C_CVSpread*{c}{rows["w"]}+SUMPRODUCT((cv_effect="cost_fixed")*(cv_timing="anchor")*(cv_start={t})*cv_value)'
                             f'+SUMPRODUCT((cv_effect="cost_monthly")*(cv_start<={t})*(cv_end>{t})*cv_value)'))
        add("cflow", "Custom one-off costs", lambda c, p, t: f'SUMPRODUCT((cf_type="cost")*(cf_month={t})*cf_amount)')
        add("total", "Total development costs (before sales costs and financing)",
            lambda c, p, t: "+".join(f"{c}{rows[k]}" for k in ("land", "acq", "hard", "soft", "cont", "fee", "cv", "cflow")), bold=True, name="M_ConCost")
        add("cum", "Cumulative development costs", lambda c, p, t: f"{c}{rows['total']}" + (f"+{p}{r}" if p else ""), total=None)
        self.con_rows = rows
        for k in ("land", "acq", "hard", "soft", "cont", "fee", "cv", "cflow"):
            self.define(f"M_{k}", f"Construction!${self.col(0)}${rows[k]}:${self.last_col}${rows[k]}")

    # ------------------------------------------------------------------ Sales schedule
    def sales(self):
        ws = self.sheet("Sales")
        self.header(ws, "Sales schedule & cash collections", "Units sold per month (phases + base absorption, net of cancellations), contract value and buyer payments")
        self.month_header(ws)
        top = [("Base presales start month", "=MAX(1,T_ConStart+in_rev_sales_start_offset)", NUM, "Sales_BaseStart"),
               ("Sales start month (incl. phases)", "=MAX(1,MIN(Sales_BaseStart,IF(COUNT(sp_start)>0,MIN(sp_start),Sales_BaseStart)))", NUM, "Sales_Start"),
               ("Units for sale", "=IF(in_mode_sale=1,D_Units,0)", NUM, "S_Units"),
               ("Last month with sales", None, NUM, "Sales_Last"),
               ("Gross development value (contract value)", None, MONEY, "S_GDV")]
        ws.insert_rows(5, amount=len(top) + 2)
        for i, (label, f, fmt, name) in enumerate(top):
            self.scalar(ws, 5 + i, label, f, fmt, name)
        r = 5 + len(top) + 2
        rows = {}

        def add(key, label, fn, **kw):
            nonlocal r
            self.mrow(ws, r, label, fn, **kw)
            rows[key] = r
            r += 1
        add("rate", "Gross sales pace (units/month)",
            lambda c, p, t: (f"IF({t}<Sales_Start,0,IF(SUMPRODUCT((sp_start<={t})*(sp_end>{t})*1)>0,"
                             f"SUMPRODUCT((sp_start<={t})*(sp_end>{t})*sp_rate)/SUMPRODUCT((sp_start<={t})*(sp_end>{t})*1),in_rev_absorption_per_month))"),
            fmt=NUM1, total=None)
        add("sold", "Units sold (net of cancellations)",
            lambda c, p, t: f"IF(in_mode_sale=1,MIN({c}{rows['rate']}*(1-in_rev_cancellation_pct),{('S_Units' if p is None else f'{p}{r + 1}')}),0)",
            fmt=NUM1, name="M_Sold")
        add("remaining", "Units remaining (end of month)", lambda c, p, t: f"{('S_Units' if p is None else f'{p}{r}')}-{c}{rows['sold']}", fmt=NUM1, total=None)
        add("cumsold", "Cumulative units sold", lambda c, p, t: f"S_Units-{c}{rows['remaining']}", fmt=NUM1, total=None, name="M_CumSold")
        add("pmult", "Price phase multiplier", lambda c, p, t: f"EXP(SUMPRODUCT((pp_start<={t})*(pp_end>{t})*LN(1+pp_pct)))", fmt='0.0000', total=None)
        add("contract", "Contract value signed",
            lambda c, p, t: f"{c}{rows['sold']}*D_AvgPrice*(1+in_rev_escalation_pct)^({t}/12)*(1-in_rev_discount_pct)*{c}{rows['pmult']}", name="M_Contract")
        self.section_row(ws, r, "Cash collections (buyer payment plan)"); r += 1
        add("dep", "Deposits", lambda c, p, t: f"IF({t}<T_Delivery,{c}{rows['contract']}*in_rev_deposit_pct,0)")
        add("helper", "Installment per month generated by this month's sales (helper)",
            lambda c, p, t: f"IF(AND({t}<T_Delivery,T_Delivery-{t}-1>0),{c}{rows['contract']}*in_rev_installments_pct/(T_Delivery-{t}-1),0)", total=None)
        mrow = f"${self.col(0)}$4:${self.last_col}$4"
        hrow = f"${self.col(0)}${rows['helper']}:${self.last_col}${rows['helper']}"
        crow = f"${self.col(0)}${rows['contract']}:${self.last_col}${rows['contract']}"
        add("inst", "Construction-stage installments", lambda c, p, t: f"IF({t}<T_Delivery,SUMPRODUCT(({mrow}<{t})*{hrow}),0)")
        add("closing", "Balance at delivery (closing)",
            lambda c, p, t: f"IF({t}=T_Delivery,in_rev_closing_pct*SUMPRODUCT(({mrow}<T_Delivery)*{crow})+in_rev_installments_pct*SUMPRODUCT(({mrow}=T_Delivery-1)*{crow}),0)")
        add("post", "Sales after delivery (paid in full)", lambda c, p, t: f"IF({t}>=T_Delivery,{c}{rows['contract']},0)")
        add("units_income", "User-defined income per unit sold", lambda c, p, t: f'{c}{rows["sold"]}*SUMPRODUCT((cv_effect="revenue_per_unit")*cv_value)')
        add("coll", "Total sales collections", lambda c, p, t: f"{c}{rows['dep']}+{c}{rows['inst']}+{c}{rows['closing']}+{c}{rows['post']}", bold=True, name="M_SalesCash")
        self.section_row(ws, r, "Sales costs"); r += 1
        add("comm", "Sales commissions (paid at contract)", lambda c, p, t: f"{c}{rows['contract']}*in_rev_commission_pct")
        add("mkt", "Marketing & sales office",
            lambda c, p, t: f"IF(AND({t}>=Sales_Start,{t}<=Sales_Last),S_GDV*in_rev_marketing_pct/(Sales_Last-Sales_Start+1),0)")
        add("pctrev", "User-defined % of collections (e.g. trust fees)", lambda c, p, t: f'{c}{rows["coll"]}*SUMPRODUCT((cv_effect="cost_pct_revenue")*cv_value)')
        add("salescost", "Total sales costs", lambda c, p, t: f"{c}{rows['comm']}+{c}{rows['mkt']}+{c}{rows['pctrev']}", bold=True, name="M_SalesCost")
        srow = f"${self.col(0)}${rows['sold']}:${self.last_col}${rows['sold']}"
        ws["B8"] = f"=SUMPRODUCT(MAX(({srow}>1E-9)*{mrow}))"
        ws["B9"] = f"=SUM({crow})"
        ws["B9"].number_format = MONEY
        self.sales_rows = rows
        self.define("M_UnitsIncome", f"Sales!${self.col(0)}${rows['units_income']}:${self.last_col}${rows['units_income']}")

    # ------------------------------------------------------------------ Rental income
    def rental(self):
        ws = self.sheet("Rental")
        self.header(ws, "Rental operations & exit", "GPR − vacancy − concessions = EGI; EGI − opex (+ owner savings) = NOI; exit on forward NOI / cap rate")
        self.month_header(ws)
        top = [("Lease-up starts (month)", "=IF(in_ground_up=1,T_Delivery+1,1)", NUM, "R_Start"),
               ("Exit month", "=IF(in_ground_up=1,T_Delivery,0)+in_rent_hold_years*12", NUM, "R_Exit"),
               ("Effective rent per m²/month", "=IF(in_mode_sale=0,in_rent_rent_per_area_month,0)*(1+in_green_rent_prem)*CV_PriceMult", MONEY, "R_Rent"),
               ("Monthly rent growth factor q", "=(1+in_rent_growth_pct)^(1/12)", "0.000000", "R_q"),
               ("Forward 12-month stabilized NOI at exit",
                "=(D_Saleable*R_Rent*(1-in_rent_vacancy_pct)*(1-in_rent_concessions_pct)*(1-in_rent_opex_pct_egi)+in_green_savings/12)*IF(R_q=1,12,R_q^R_Exit*R_q*(R_q^12-1)/(R_q-1))",
                MONEY, "R_FwdNOI"),
               ("Exit value (gross)", "=IF(in_mode_sale=0,IF(in_rent_exit_cap_pct>0,R_FwdNOI/in_rent_exit_cap_pct,0),0)", MONEY, "R_ExitValue"),
               ("Stabilized NOI (annual)",
                "=12*(D_Saleable*R_Rent*(1+in_rent_growth_pct)^((R_Start+IF(in_ground_up=1,in_rent_lease_up_months,0))/12)*(1-in_rent_vacancy_pct)*(1-in_rent_concessions_pct)*(1-in_rent_opex_pct_egi)+in_green_savings/12*(1+in_rent_growth_pct)^((R_Start+IF(in_ground_up=1,in_rent_lease_up_months,0))/12))",
                MONEY, "R_StabNOI")]
        ws.insert_rows(5, amount=len(top) + 2)
        for i, (label, f, fmt, name) in enumerate(top):
            self.scalar(ws, 5 + i, label, f, fmt, name)
        r = 5 + len(top) + 2
        rows = {}

        def add(key, label, fn, **kw):
            nonlocal r
            self.mrow(ws, r, label, fn, **kw)
            rows[key] = r
            r += 1
        add("occ", "Occupancy",
            lambda c, p, t: f"IF(OR(in_mode_sale=1,{t}<R_Start,{t}>R_Exit),0,IF(AND(in_ground_up=1,in_rent_lease_up_months>0,{t}-R_Start<in_rent_lease_up_months),(1-in_rent_vacancy_pct)*({t}-R_Start+1)/in_rent_lease_up_months,1-in_rent_vacancy_pct))",
            fmt=PCT, total=None)
        add("gpr", "Gross potential rent", lambda c, p, t: f"IF(OR(in_mode_sale=1,{t}<R_Start,{t}>R_Exit),0,D_Saleable*R_Rent*(1+in_rent_growth_pct)^({t}/12))")
        add("egi", "Effective gross income", lambda c, p, t: f"{c}{rows['gpr']}*{c}{rows['occ']}*(1-in_rent_concessions_pct)")
        add("opex", "Operating expenses (net of owner savings)",
            lambda c, p, t: f"IF(OR(in_mode_sale=1,{t}<R_Start,{t}>R_Exit),0,{c}{rows['egi']}*in_rent_opex_pct_egi-in_green_savings/12*(1+in_rent_growth_pct)^({t}/12))")
        add("noi", "Net operating income", lambda c, p, t: f"{c}{rows['egi']}-{c}{rows['opex']}", bold=True, name="M_NOI")
        add("exit", "Exit proceeds (net of selling costs)", lambda c, p, t: f"IF(AND(in_mode_sale=0,{t}=R_Exit),R_ExitValue*(1-in_rent_selling_costs_pct),0)")
        add("income", "Total operating & exit inflows", lambda c, p, t: f"{c}{rows['noi']}+{c}{rows['exit']}", bold=True, name="M_RentCash")
        self.rent_rows = rows

    # ------------------------------------------------------------------ Cash flow & financing
    def cashflow(self):
        ws = self.sheet("Cash Flow", "1BAF7A")
        self.header(ws, "Cash flow & financing", "Unlevered cash flow, then equity first → mezzanine → senior debt; interest on the actual monthly balance")
        self.month_header(ws)
        top = [("End month (last cash flow)", None, NUM, "T_End"),
               ("Total development cost (TDC, excl. financing)", None, MONEY, "TDC"),
               ("Financing cost (interest + fees)", None, MONEY, "FinCost"),
               ("Total cost incl. financing", "=TDC+FinCost", MONEY, "TotalCost"),
               ("Senior rate (annual, nominal)", '=IF(in_fin_senior_rate_type="fixed",N(in_fin_senior_fixed_rate_pct),N(in_fin_reference_rate_pct)+in_fin_senior_spread_pct)', PCT2, "F_SeniorRate"),
               ("Senior commitment (LTC × cost incl. financing)", "=in_fin_senior_ltc_pct*(TDC+FinCostSizing)", MONEY, "F_SeniorCommit"),
               ("Mezzanine commitment", "=N(in_fin_mezz_ltc_pct)*(TDC+FinCostSizing)", MONEY, "F_MezzCommit"),
               ("Planned equity (cap before debt)", "=MAX(TDC+FinCostSizing-F_SeniorCommit-F_MezzCommit,0)", MONEY, "F_EquityCap"),
               ("Fixed monthly principal after delivery (rentals)", None, MONEY, "F_AmortPrincipal"),
               ("Financing cost used for debt sizing (circuit breaker)", "=IF(in_circ_switch=1,IFERROR(FinCost,0),0)", MONEY, "FinCostSizing")]
        ws.insert_rows(5, amount=len(top) + 2)
        for i, (label, f, fmt, name) in enumerate(top):
            self.scalar(ws, 5 + i, label, f, fmt, name)
        ws.cell(row=10, column=3, value="Circular by design (debt sized on cost incl. financing). Iterative calculation is on; set the circuit breaker on Assumptions to 0 to break the loop.").font = SUB
        r = 5 + len(top) + 2
        rows = {}

        def add(key, label, fn, **kw):
            nonlocal r
            self.mrow(ws, r, label, fn, **kw)
            rows[key] = r
            r += 1
        add("end", "End month (flag)", lambda c, p, t: f"IF({t}=T_End,1,0)", fmt=NUM, total=None)
        add("post", "On or after delivery (flag)", lambda c, p, t: f"IF(OR({t}>=T_Delivery,{t}=T_End),1,0)", fmt=NUM, total=None)
        self.section_row(ws, r, "Unlevered cash flow"); r += 1
        add("out", "Development costs", lambda c, p, t: f"Construction!{c}{self.con_rows['total']}")
        add("salescost", "Sales costs", lambda c, p, t: f"IF(in_mode_sale=1,Sales!{c}{self.sales_rows['salescost']},0)")
        add("outflow", "Total outflows", lambda c, p, t: f"IF({t}>T_End,0,{c}{rows['out']}+{c}{rows['salescost']})", bold=True, name="M_Outflow")
        add("sales", "Sales collections / operating income",
            lambda c, p, t: f"IF(in_mode_sale=1,Sales!{c}{self.sales_rows['coll']}+Sales!{c}{self.sales_rows['units_income']},Rental!{c}{self.rent_rows['income']})")
        add("other", "Other income (custom flows & user-defined)",
            lambda c, p, t: (f'SUMPRODUCT((cf_type="revenue")*(cf_month={t})*cf_amount)+SUMPRODUCT((cv_effect="revenue_fixed")*(cv_start={t})*cv_value)'
                             f'+SUMPRODUCT((cv_effect="revenue_monthly")*(cv_start<={t})*(cv_end>{t})*cv_value)+IF(AND(in_mode_sale=0,{t}=R_Start),D_Units*SUMPRODUCT((cv_effect="revenue_per_unit")*cv_value),0)'))
        add("inflow", "Total inflows", lambda c, p, t: f"IF({t}>T_End,0,{c}{rows['sales']}+{c}{rows['other']})", bold=True, name="M_Inflow")
        add("unlev", "Unlevered cash flow", lambda c, p, t: f"{c}{rows['inflow']}-{c}{rows['outflow']}", bold=True, name="M_Unlev")
        add("cumunlev", "Cumulative unlevered cash flow", lambda c, p, t: f"{c}{rows['unlev']}" + (f"+{p}{r}" if p else ""), total=None, name="M_CumUnlev")
        self.section_row(ws, r, "Financing"); r += 1
        rs, rm = "F_SeniorRate/12", "N(in_fin_mezz_rate_pct)/12"
        add("s_open", "Senior debt: opening balance", lambda c, p, t: "0" if p is None else f"{p}{rows_ref('s_close')}", total=None)
        add("s_int", "Senior interest", lambda c, p, t: f"{c}{rows['s_open']}*{rs}")
        add("m_open", "Mezzanine: opening balance", lambda c, p, t: "0" if p is None else f"{p}{rows_ref('m_close')}", total=None)
        add("m_int", "Mezzanine interest", lambda c, p, t: f"{c}{rows['m_open']}*{rm}")
        add("fees", "Loan fees (commitment on undrawn + origination)",
            lambda c, p, t: f"IF(AND({t}>=T_ConStart,{t}<=T_Delivery,F_SeniorCommit>0),MAX(F_SeniorCommit-{c}{rows['s_open']},0)*in_fin_commitment_fee_pct/12,0)+IF(AND({t}=T_ConStart,F_SeniorCommit>0),F_SeniorCommit*in_fin_origination_fee_pct,0)")
        add("s_cap", "Senior interest capitalized", lambda c, p, t: f"IF(AND({t}<=T_Delivery,in_fin_interest_capitalized),MIN({c}{rows['s_int']},MAX(F_SeniorCommit-{c}{rows['s_open']},0)),0)")
        add("m_cap", "Mezzanine interest capitalized", lambda c, p, t: f"IF(AND({t}<=T_Delivery,in_fin_interest_capitalized),MIN({c}{rows['m_int']},MAX(F_MezzCommit-{c}{rows['m_open']},0)),0)")
        add("cashint", "Interest paid in cash", lambda c, p, t: f"{c}{rows['s_int']}+{c}{rows['m_int']}-{c}{rows['s_cap']}-{c}{rows['m_cap']}")
        add("amort", "Scheduled principal (rentals after delivery)",
            lambda c, p, t: f"IF(AND(in_mode_sale=0,{t}>T_Delivery,{c}{rows['s_open']}>0,N(in_fin_amortization_years)>0),MIN(F_AmortPrincipal,{c}{rows['s_open']}),0)")
        add("need", "Funding need (+) / surplus (−)", lambda c, p, t: f"{c}{rows['outflow']}-{c}{rows['inflow']}+{c}{rows['fees']}+{c}{rows['cashint']}+{c}{rows['amort']}", total=None)
        add("cash_open", "Project cash reserve: opening", lambda c, p, t: "0" if p is None else f"{p}{rows_ref('cash_close')}", total=None)
        add("usecash", "Deficit paid from reserve", lambda c, p, t: f"MIN({c}{rows['cash_open']},MAX({c}{rows['need']},0))")
        add("eq_in", "Planned equity drawn", lambda c, p, t: "MIN(MAX({0}{1},0)-{0}{2},MAX(F_EquityCap-{3},0))".format(
            c, rows["need"], rows["usecash"], "0" if p is None else p + rows_ref("cum_eq")))
        add("cum_eq", "Cumulative planned equity", lambda c, p, t: f"{c}{rows['eq_in']}" + (f"+{p}{r}" if p else ""), total=None)
        add("m_draw", "Mezzanine drawn", lambda c, p, t: f"MIN(MAX({c}{rows['need']},0)-{c}{rows['usecash']}-{c}{rows['eq_in']},MAX(F_MezzCommit-{c}{rows['m_open']}-{c}{rows['m_cap']},0))")
        add("s_draw", "Senior debt drawn", lambda c, p, t: f"MIN(MAX({c}{rows['need']},0)-{c}{rows['usecash']}-{c}{rows['eq_in']}-{c}{rows['m_draw']},MAX(F_SeniorCommit-{c}{rows['s_open']}-{c}{rows['s_cap']},0))")
        add("gap", "Funding gap (additional equity required)", lambda c, p, t: f"MAX(MAX({c}{rows['need']},0)-{c}{rows['usecash']}-{c}{rows['eq_in']}-{c}{rows['m_draw']}-{c}{rows['s_draw']},0)")
        add("surplus", "Surplus cash", lambda c, p, t: f"MAX(-{c}{rows['need']},0)", total=None)
        add("todebt", "Cash swept to debt",
            lambda c, p, t: f"IF({c}{rows['post']}=1,IF({c}{rows['end']}=1,{c}{rows['surplus']},IF(in_mode_sale=0,0,{c}{rows['surplus']}*in_fin_sweep_pct)),0)", total=None)
        add("s_pre", "Senior balance before repayment", lambda c, p, t: f"{c}{rows['s_open']}+{c}{rows['s_cap']}+{c}{rows['s_draw']}-{c}{rows['amort']}", total=None)
        add("s_rep", "Senior repayment from sweep", lambda c, p, t: f"MIN({c}{rows['todebt']},{c}{rows['s_pre']})")
        add("m_pre", "Mezzanine balance before repayment", lambda c, p, t: f"{c}{rows['m_open']}+{c}{rows['m_cap']}+{c}{rows['m_draw']}", total=None)
        add("m_rep", "Mezzanine repayment from sweep", lambda c, p, t: f"MIN({c}{rows['todebt']}-{c}{rows['s_rep']},{c}{rows['m_pre']})")
        add("dist_pre", "Cash available to equity", lambda c, p, t: f"IF(AND({c}{rows['post']}=1,{c}{rows['surplus']}>0),{c}{rows['surplus']}-{c}{rows['s_rep']}-{c}{rows['m_rep']}+{c}{rows['cash_open']},0)", total=None)
        add("endpay", "Final repayment of remaining debt", lambda c, p, t: f"IF({c}{rows['end']}=1,{c}{rows['s_pre']}-{c}{rows['s_rep']}+{c}{rows['m_pre']}-{c}{rows['m_rep']},0)")
        add("endshort", "Final repayment shortfall (equity)", lambda c, p, t: f"MAX({c}{rows['endpay']}-{c}{rows['dist_pre']},0)")
        add("cash_close", "Project cash reserve: closing",
            lambda c, p, t: f"IF({c}{rows['surplus']}>0,IF({c}{rows['post']}=1,0,{c}{rows['cash_open']}+{c}{rows['surplus']}),{c}{rows['cash_open']}-{c}{rows['usecash']})", total=None)
        add("s_close", "Senior debt: closing balance", lambda c, p, t: f"IF({c}{rows['end']}=1,0,{c}{rows['s_pre']}-{c}{rows['s_rep']})", total=None, name="M_Senior")
        add("m_close", "Mezzanine: closing balance", lambda c, p, t: f"IF({c}{rows['end']}=1,0,{c}{rows['m_pre']}-{c}{rows['m_rep']})", total=None, name="M_Mezz")
        add("ds", "Debt service paid in cash (interest + principal)", lambda c, p, t: f"{c}{rows['cashint']}+{c}{rows['amort']}")
        self.section_row(ws, r, "Equity"); r += 1
        add("contrib", "Equity contributions", lambda c, p, t: f"{c}{rows['eq_in']}+{c}{rows['gap']}+{c}{rows['endshort']}", bold=True, name="M_Contrib")
        add("dist", "Equity distributions", lambda c, p, t: f"MAX({c}{rows['dist_pre']}-IF({c}{rows['end']}=1,{c}{rows['endpay']},0),0)", bold=True, name="M_Dist")
        add("lev", "Levered (equity) cash flow", lambda c, p, t: f"{c}{rows['dist']}-{c}{rows['contrib']}", bold=True, name="M_Lev")
        add("cumlev", "Cumulative net equity invested", lambda c, p, t: f"{c}{rows['contrib']}-{c}{rows['dist']}" + (f"+{p}{r}" if p else ""), total=None, name="M_NetEquity")
        self.cf_rows = rows
        mr = f"${self.col(0)}$4:${self.last_col}$4"
        cost_rows = f"${self.col(0)}${rows['outflow']}:${self.last_col}${rows['outflow']}"
        inc_rows = f"${self.col(0)}${rows['inflow']}:${self.last_col}${rows['inflow']}"
        ws["B5"] = (f"=MAX(IF(in_mode_sale=1,MAX(T_Delivery,Sales_Last),R_Exit),IF(COUNT(cf_month)>0,MAX(cf_month),0),"
                    f"SUMPRODUCT(MAX((Construction!${self.col(0)}${self.con_rows['total']}:${self.last_col}${self.con_rows['total']}<>0)*{mr})))")
        ws["B6"] = f"=SUM({cost_rows})"
        ws["B7"] = f"=B{rows['s_int']}+B{rows['m_int']}+B{rows['fees']}"
        dc = f"${self.col(0)}${rows['s_close']}:${self.last_col}${rows['s_close']}"
        ws["B13"] = (f"=IF(N(in_fin_amortization_years)>0,LET_BAL*IF({rs}=0,1/(in_fin_amortization_years*12),{rs}/(1-(1+{rs})^-(in_fin_amortization_years*12)))-LET_BAL*{rs},0)")
        ws["B13"] = ws["B13"].value.replace("LET_BAL", f"INDEX({dc},1,T_Delivery+1)")

    # ------------------------------------------------------------------ Equity waterfall
    def waterfall(self):
        ws = self.sheet("Waterfall")
        self.header(ws, "Equity waterfall", "Return of capital → preferred return (compounded monthly) → sponsor promote; pari passu contributions")
        self.month_header(ws)
        top = [("Sponsor share of equity", "=in_fin_sponsor_equity_share_pct", PCT, "W_s"),
               ("Monthly preferred return", "=(1+in_fin_pref_return_pct)^(1/12)-1", '0.0000%', "W_rp"),
               ("Sponsor promote above pref", "=in_fin_promote_pct", PCT, "W_promote")]
        ws.insert_rows(5, amount=len(top) + 2)
        for i, (label, f, fmt, name) in enumerate(top):
            self.scalar(ws, 5 + i, label, f, fmt, name)
        r = 5 + len(top) + 2
        rows = {}

        def add(key, label, fn, **kw):
            nonlocal r
            self.mrow(ws, r, label, fn, **kw)
            rows[key] = r
            r += 1
        cfr = self.cf_rows
        add("c", "Equity contributions", lambda c, p, t: f"'Cash Flow'!{c}{cfr['contrib']}")
        add("d", "Equity distributions", lambda c, p, t: f"'Cash Flow'!{c}{cfr['dist']}")
        add("uc_open", "Unreturned capital: opening", lambda c, p, t: "0" if p is None else f"{p}{rows_ref2('uc_close')}", total=None)
        add("pref_open", "Accrued preferred return: opening", lambda c, p, t: "0" if p is None else f"{p}{rows_ref2('pref_close')}", total=None)
        add("accr", "Preferred return accrued", lambda c, p, t: f"({c}{rows['uc_open']}+{c}{rows['pref_open']})*W_rp")
        add("roc", "Tier 1: return of capital", lambda c, p, t: f"MIN({c}{rows['d']},{c}{rows['uc_open']}+{c}{rows['c']})")
        add("pp", "Tier 2: preferred return", lambda c, p, t: f"MIN({c}{rows['d']}-{c}{rows['roc']},{c}{rows['pref_open']}+{c}{rows['accr']})")
        add("res", "Tier 3: residual", lambda c, p, t: f"{c}{rows['d']}-{c}{rows['roc']}-{c}{rows['pp']}")
        add("uc_close", "Unreturned capital: closing", lambda c, p, t: f"{c}{rows['uc_open']}+{c}{rows['c']}-{c}{rows['roc']}", total=None)
        add("pref_close", "Accrued preferred return: closing", lambda c, p, t: f"{c}{rows['pref_open']}+{c}{rows['accr']}-{c}{rows['pp']}", total=None)
        add("inv", "Investor cash flow", lambda c, p, t: f"(-{c}{rows['c']}+{c}{rows['roc']}+{c}{rows['pp']}+{c}{rows['res']}*(1-W_promote))*(1-W_s)", bold=True, name="M_Investor")
        add("spo", "Sponsor cash flow", lambda c, p, t: f"(-{c}{rows['c']}+{c}{rows['roc']}+{c}{rows['pp']}+{c}{rows['res']}*(1-W_promote))*W_s+{c}{rows['res']}*W_promote", bold=True, name="M_Sponsor")
        self.wf_rows = rows

    # ------------------------------------------------------------------ Budget
    def budget(self):
        ws = self.sheet("Budget")
        self.header(ws, "Development budget", f"{self.cur}. Every line links to the monthly schedules; per m² of total GBA and per unit")
        for i, h in enumerate(["Line item", f"Amount ({self.cur})", "Per m² GBA", "Per unit", "% of total", "Basis"]):
            c = ws.cell(row=4, column=1 + i, value=h)
            c.font, c.fill = HDR, NAVY
        ws.column_dimensions["A"].width = 44
        for col in "BCDE":
            ws.column_dimensions[col].width = 16
        ws.column_dimensions["F"].width = 44
        lines = [("Acquisition", None, None),
                 ("Land / property price", "=SUM(M_land)", "Land payment schedule"),
                 ("Taxes, notary, brokerage & due diligence", "=SUM(M_acq)", "% of land price + fixed"),
                 ("Construction", None, None),
                 ("Hard costs (escalated, incl. sustainability capex)", "=SUM(M_hard)", "per m² × GBA, S-curve, escalation"),
                 ("Soft costs", "=SUM(M_soft)", "% of hard-cost base"),
                 ("Contingency", "=SUM(M_cont)", "% of hard + soft"),
                 ("Developer fee", "=SUM(M_fee)", "% of hard + soft"),
                 ("User-defined variable costs", "=SUM(M_cv)", "Assumptions → user-defined variables"),
                 ("Custom one-off costs", "=SUM(M_cflow)", "Assumptions → custom cash flows"),
                 ("Sales & marketing", None, None),
                 ("Sales costs (commissions, marketing, % of collections)", "=IF(in_mode_sale=1,SUM(M_SalesCost),0)", "% of contract value / revenue"),
                 ("Financing", None, None),
                 ("Interest and loan fees", "=FinCost", "On actual monthly balances"),
                 ]
        r = 5
        first = r
        for label, f, basis in lines:
            if f is None:
                self.section_row(ws, r, label, 7)
            else:
                ws.cell(row=r, column=1, value=label).font = BLACK
                for col, ff in ((2, f), (3, f"=IF((D_GBA+D_Below)>0,B{r}/(D_GBA+D_Below),0)"), (4, f"=IF(D_Units>0,B{r}/D_Units,0)"), (5, f"=IF(TotalCost<>0,B{r}/TotalCost,0)")):
                    c = ws.cell(row=r, column=col, value=ff)
                    c.number_format, c.font = (PCT if col == 5 else MONEY), BLACK
                ws.cell(row=r, column=6, value=basis).font = SUB
            r += 1
        ws.cell(row=r, column=1, value="Total cost incl. financing").font = BOLD
        c = ws.cell(row=r, column=2, value=f"=SUM(B{first}:B{r - 1})")
        c.number_format, c.font = MONEY, BOLD
        ws.cell(row=r, column=6, value="Check vs Cash Flow:").font = SUB
        ws.cell(row=r, column=7, value=f"=ROUND(B{r}-TotalCost,0)").number_format = NUM
        for cc in range(1, 8):
            ws.cell(row=r, column=cc).fill = TOTALFILL
        self.budget_total_row = r
        r += 3
        self.section_row(ws, r, "Hard-cost breakdown by category (today's prices, above ground)", 7); r += 1
        s0, s1 = self.split_rows
        for k in range(s1 - s0 + 1):
            ws.cell(row=r, column=1, value=f"=Assumptions!A{s0 + k}").font = BLACK
            c = ws.cell(row=r, column=2, value=f"=C_HardAbove*Assumptions!B{s0 + k}")
            c.number_format = MONEY
            r += 1
        self.budget_ws = ws

    # ------------------------------------------------------------------ Outputs
    def outputs(self):
        ws = self.wb.create_sheet("Outputs", 1)
        ws.sheet_properties.tabColor = "EB6834"
        ws.sheet_view.showGridLines = False
        self.header(ws, f"{self.p['name']}: investment summary", f"{self.cur}. Every figure is a formula linked to the Assumptions tab.")
        ws.column_dimensions["A"].width = 40
        ws.column_dimensions["B"].width = 18
        ws.column_dimensions["C"].width = 18
        ws.column_dimensions["D"].width = 18
        ws.column_dimensions["E"].width = 14
        R = self.cf_rows
        lev, unlev = "M_Lev", "M_Unlev"
        kpis = [("Returns", None, None),
                ("Project IRR (unlevered, annualized)", f"=IFERROR((1+IRR({unlev},0.01))^12-1,\"n/a\")", PCT, "project_irr"),
                ("Equity IRR (levered, annualized)", f"=IFERROR((1+IRR({lev},0.01))^12-1,\"n/a\")", PCT, "equity_irr"),
                ("Equity multiple (MOIC)", "=IF(SUM(M_Contrib)>0,SUM(M_Dist)/SUM(M_Contrib),0)", MULT, "moic"),
                ("NPV at discount rate (unlevered)", f"=INDEX({unlev},1,1)+NPV((1+in_val_discount_rate_pct)^(1/12)-1,{self.cf_range(R['unlev'], 1)})", MONEY, "npv"),
                ("Investor IRR", "=IFERROR((1+IRR(M_Investor,0.01))^12-1,\"n/a\")", PCT, "investor_irr"),
                ("Sponsor IRR", "=IFERROR((1+IRR(M_Sponsor,0.01))^12-1,\"n/a\")", PCT, "sponsor_irr"),
                ("Profitability", None, None),
                ("Gross development value / exit value", "=IF(in_mode_sale=1,S_GDV,R_ExitValue)", MONEY, "gdv"),
                ("Total revenue (cash inflows)", "=SUM(M_Inflow)", MONEY, "revenue"),
                ("Total development cost (excl. financing)", "=TDC", MONEY, "tdc"),
                ("Financing cost", "=FinCost", MONEY, "financing_cost"),
                ("Total cost incl. financing", "=TotalCost", MONEY, "total_cost"),
                ("Development profit", "=SUM(M_Inflow)-TotalCost", MONEY, "profit"),
                ("Net margin (profit / revenue)", "=IF(SUM(M_Inflow)<>0,(SUM(M_Inflow)-TotalCost)/SUM(M_Inflow),0)", PCT, "net_margin"),
                ("Profit on cost", "=IF(TotalCost<>0,(SUM(M_Inflow)-TotalCost)/TotalCost,0)", PCT, "profit_on_cost"),
                ("Capital", None, None),
                ("Peak funding requirement (unlevered)", "=MAX(0,-MIN(M_CumUnlev))", MONEY, "peak_funding"),
                ("Peak equity", "=MAX(0,MAX(M_NetEquity))", MONEY, "peak_equity"),
                ("Equity contributed", "=SUM(M_Contrib)", MONEY, "equity_contributed"),
                ("Senior commitment", "=F_SeniorCommit", MONEY, "senior_commitment"),
                ("Peak senior debt", "=MAX(0,MAX(M_Senior))", MONEY, None),
                ("Loan-to-cost (LTC)", "=IF(TotalCost<>0,F_SeniorCommit/TotalCost,0)", PCT, "ltc"),
                ("Funding gap (additional equity)", f"=B{0}", MONEY, "funding_gap"),
                ("Program & timing", None, None),
                ("Units", "=D_Units", NUM, "units"),
                ("Saleable / leasable area (m²)", "=D_Saleable", NUM, "saleable_area"),
                ("Delivery month", "=T_Delivery", NUM, "delivery_month"),
                ("Project duration (months)", "=T_End", NUM, "duration_months")]
        r = 4
        for i, h in enumerate(["Metric", "Excel model", "TerraMind engine at export", "Difference", "Status"]):
            c = ws.cell(row=r, column=1 + i, value=h)
            c.font, c.fill = HDR, NAVY
        r += 1
        m = self.res.get("metrics", {}) if self.res.get("status") == "ok" else {}
        self.kpi_cells = {}
        for item in kpis:
            label, f, fmt = item[:3]
            key = item[3] if len(item) > 3 else None
            if f is None:
                self.section_row(ws, r, label, 6)
                r += 1
                continue
            if key == "funding_gap":
                f = f"='Cash Flow'!B{R['gap']}"
            ws.cell(row=r, column=1, value=label).font = BLACK
            c = ws.cell(row=r, column=2, value=f)
            c.number_format, c.font = fmt, BOLD
            if key and m.get(key) is not None:
                e = ws.cell(row=r, column=3, value=m[key])
                e.number_format, e.font = fmt, Font(name=FONT, size=10, color="7A8699")
                d = ws.cell(row=r, column=4, value=f'=IFERROR(B{r}-C{r},"")')
                d.number_format = fmt
                ws.cell(row=r, column=5, value=f'=IFERROR(IF(IF(ABS(C{r})<10,ABS(B{r}-C{r})<=0.0005,ABS(B{r}-C{r})<=MAX(1,ABS(C{r})*0.002)),"✓ matches","changed"),"")').font = SUB
            self.kpi_cells[key or label] = f"B{r}"
            r += 1
        ws.cell(row=r + 1, column=1, value="Column C is a snapshot of TerraMind's engine when the file was exported. After you edit assumptions in Excel, column B updates and Status shows 'changed'.").font = SUB
        self.out_row = r + 3
        self.annual_and_charts(ws, self.out_row)

    def cf_range(self, row: int, start_t: int = 0) -> str:
        return f"'Cash Flow'!${self.col(start_t)}${row}:${self.last_col}${row}"

    def _style(self, ch, colors, y_fmt='#,##0,,"M";(#,##0,,"M")'):
        """Visible axes (openpyxl hides them by default in recent Excel), brand palette, M-formatted values."""
        ch.x_axis.delete = False
        ch.y_axis.delete = False
        ch.y_axis.numFmt = y_fmt
        ch.y_axis.majorGridlines = ch.y_axis.majorGridlines
        ch.legend.position = "b"
        ch.x_axis.tickLblPos = "low"  # keep category labels at the bottom when values are negative
        for s, color in zip(ch.series, colors):
            s.graphicalProperties.solidFill = color
            s.graphicalProperties.line.solidFill = color
        return ch

    def annual_and_charts(self, ws, r):
        years = min(int(math.ceil(self.H / 12)) + 1, 21)
        horizon = self.res["schedule"]["horizon"] if self.res.get("status") == "ok" else self.H
        chart_years = min(years, int(math.ceil((horizon + 1) / 12)) + 1)
        chart_months = min(self.H, horizon + 4)
        self.section_row(ws, r, "Annual summary (Y0 = closing month, Y1 = months 1–12…)", 4 + years)
        r += 1
        ws.cell(row=r, column=1, value="Year").font = HDR
        ws.cell(row=r, column=1).fill = NAVY
        for y in range(years):
            c = ws.cell(row=r, column=2 + y, value=f"Y{y}")
            c.font, c.fill, c.alignment = HDR, NAVY, Alignment(horizontal="center")
            ws.column_dimensions[get_column_letter(2 + y)].width = max(ws.column_dimensions[get_column_letter(2 + y)].width or 0, 14)
        hdr_row = r
        r += 1
        mrow = self.cf_range(4)
        series = [("Total outflows", "M_Outflow"), ("Total inflows", "M_Inflow"), ("Unlevered cash flow", "M_Unlev"),
                  ("Equity contributions", "M_Contrib"), ("Equity distributions", "M_Dist"), ("Levered cash flow", "M_Lev")]
        if self.mode == "sale":
            series.insert(0, ("Units sold", "M_Sold"))
        first_series_row = r
        for label, name in series:
            ws.cell(row=r, column=1, value=label).font = BLACK
            for y in range(years):
                cond = f"({mrow}=0)" if y == 0 else f"({mrow}>={(y - 1) * 12 + 1})*({mrow}<={y * 12})"
                c = ws.cell(row=r, column=2 + y, value=f"=SUMPRODUCT({cond}*{name})")
                c.number_format = NUM1 if name == "M_Sold" else MONEY_M
            r += 1
        # cost by category (feeds the cost chart)
        r += 1
        self.section_row(ws, r, "Cost by category", 4)
        r += 1
        cost_first = r
        for label, f in (("Land & acquisition", "=SUM(M_land)+SUM(M_acq)"), ("Hard costs", "=SUM(M_hard)"), ("Soft costs", "=SUM(M_soft)"),
                         ("Contingency & developer fee", "=SUM(M_cont)+SUM(M_fee)"), ("Sales & marketing", "=IF(in_mode_sale=1,SUM(M_SalesCost),0)"),
                         ("User-defined & custom costs", "=SUM(M_cv)+SUM(M_cflow)"), ("Financing", "=FinCost")):
            ws.cell(row=r, column=1, value=label).font = BLACK
            c = ws.cell(row=r, column=2, value=f)
            c.number_format = MONEY
            ws.cell(row=r, column=3, value=f"=IF(TotalCost<>0,B{r}/TotalCost,0)").number_format = PCT
            r += 1
        cost_last = r - 1
        # ---- charts (they update automatically when assumptions change)
        r += 2
        anchor_row = r
        BLUE_, ORANGE, AQUA = "2A78D6", "EB6834", "1BAF7A"
        unlev_row = first_series_row + (3 if self.mode == "sale" else 2)
        out_row = first_series_row + (1 if self.mode == "sale" else 0)
        cats = Reference(ws, min_col=2, max_col=1 + chart_years, min_row=hdr_row)
        ch = BarChart()
        ch.title, ch.height, ch.width = f"Annual outflows vs inflows ({self.cur})", 7.5, 16
        ch.add_data(Reference(ws, min_col=1, max_col=1 + chart_years, min_row=out_row, max_row=out_row + 1), titles_from_data=True, from_rows=True)
        ch.set_categories(cats)
        ws.add_chart(self._style(ch, [ORANGE, BLUE_]), f"A{anchor_row}")
        ch2 = BarChart()
        ch2.title, ch2.height, ch2.width = "Unlevered vs levered cash flow by year", 7.5, 16
        ch2.add_data(Reference(ws, min_col=1, max_col=1 + chart_years, min_row=unlev_row, max_row=unlev_row), titles_from_data=True, from_rows=True)
        ch2.add_data(Reference(ws, min_col=1, max_col=1 + chart_years, min_row=unlev_row + 3, max_row=unlev_row + 3), titles_from_data=True, from_rows=True)
        ch2.set_categories(cats)
        ws.add_chart(self._style(ch2, [BLUE_, AQUA]), f"F{anchor_row}")
        cfws = self.wb["Cash Flow"]
        last = MONTH_COL0 + chart_months - 1
        mcat = Reference(cfws, min_col=MONTH_COL0, max_col=last, min_row=4)
        lc = LineChart()
        lc.title, lc.height, lc.width = "Cumulative cash flow, net equity and senior debt (monthly)", 7.5, 16
        for key in ("cumunlev", "cumlev", "s_close"):
            rr = self.cf_rows[key]
            lc.add_data(Reference(cfws, min_col=1, max_col=last, min_row=rr, max_row=rr), titles_from_data=True, from_rows=True)
        lc.set_categories(mcat)
        lc.x_axis.tickLblSkip = 6
        ws.add_chart(self._style(lc, [BLUE_, AQUA, ORANGE]), f"A{anchor_row + 16}")
        if self.mode == "sale":
            sws = self.wb["Sales"]
            bc = BarChart()
            bc.title, bc.height, bc.width = "Units sold per month", 7.5, 16
            rr = self.sales_rows["sold"]
            bc.add_data(Reference(sws, min_col=1, max_col=last, min_row=rr, max_row=rr), titles_from_data=True, from_rows=True)
            bc.set_categories(Reference(sws, min_col=MONTH_COL0, max_col=last, min_row=4))
            bc.x_axis.tickLblSkip = 6
            ws.add_chart(self._style(bc, [BLUE_], y_fmt="0.0"), f"F{anchor_row + 16}")
        else:
            rws = self.wb["Rental"]
            bc = LineChart()
            bc.title, bc.height, bc.width = "Monthly NOI", 7.5, 16
            rr = self.rent_rows["noi"]
            bc.add_data(Reference(rws, min_col=1, max_col=last, min_row=rr, max_row=rr), titles_from_data=True, from_rows=True)
            bc.set_categories(Reference(rws, min_col=MONTH_COL0, max_col=last, min_row=4))
            bc.x_axis.tickLblSkip = 6
            ws.add_chart(self._style(bc, [BLUE_], y_fmt='#,##0.0,,"M"'), f"F{anchor_row + 16}")
        cc = BarChart()
        cc.type = "bar"
        cc.title, cc.height, cc.width = "Total cost by category", 7.5, 16
        cc.add_data(Reference(ws, min_col=2, min_row=cost_first, max_row=cost_last), titles_from_data=False)
        cc.set_categories(Reference(ws, min_col=1, min_row=cost_first, max_row=cost_last))
        cc.legend = None
        cc.x_axis.delete = False
        cc.y_axis.delete = False
        cc.y_axis.numFmt = '#,##0,,"M"'
        cc.series[0].graphicalProperties.solidFill = "17345E"
        ws.add_chart(cc, f"A{anchor_row + 32}")

    # ------------------------------------------------------------------ Cover & engine snapshot
    def cover(self):
        ws = self.wb.active
        ws.title = "Cover"
        ws.sheet_view.showGridLines = False
        ws.sheet_properties.tabColor = "0B1A33"
        ws.column_dimensions["A"].width = 3
        ws.column_dimensions["B"].width = 34
        ws.column_dimensions["C"].width = 80
        ws["B2"] = "TerraMind AI · Financial model"
        ws["B2"].font = Font(name=FONT, bold=True, size=11, color="2A78D6")
        ws["B3"] = self.p["name"]
        ws["B3"].font = Font(name=FONT, bold=True, size=20, color="17345E")
        loc = ", ".join(x for x in (self.prof.get("address"), self.prof.get("neighborhood"), self.prof.get("city")) if x)
        rows = [("Location", loc), ("Strategy / business model", f"{self.prof.get('strategy')} · {self.prof.get('business_model')}"),
                ("Currency", self.cur), ("Exported", date.today().isoformat()),
                ("How it works", "Change any blue cell on the Assumptions tab. Every other number is a formula, so the development program, "
                                 "schedules, cash flow, financing, waterfall, budget, outputs and charts all update."),
                ("Circularity", "Debt is sized on total cost including financing, which is circular. Iterative calculation is enabled in this file "
                                "(File → Options → Formulas → Enable iterative calculation)."),
                ("Reconciliation", "The Outputs tab compares the Excel results with TerraMind's engine at the time of export."),
                ("Disclaimer", ("FICTIONAL DEMO PROJECT: all inputs are illustrative. " if self.prof.get("demo") else "") +
                 "Decision support only, not investment advice. Verify assumptions before relying on them.")]
        r = 5
        for k, v in rows:
            ws.cell(row=r, column=2, value=k).font = BOLD
            c = ws.cell(row=r, column=3, value=v)
            c.font, c.alignment = BLACK, Alignment(wrap_text=True, vertical="top")
            r += 1
        r += 1
        ws.cell(row=r, column=2, value="Tabs").font = BOLD
        r += 1
        tabs = [("Outputs", "Returns, profit, capital, reconciliation, annual summary and charts for investors"),
                ("Assumptions", "Every input (blue), unit mix, schedules, custom cash flows, user-defined variables"),
                ("Development", "Areas, units, legal capacity and compliance checks"),
                ("Construction", "Monthly development cost schedule (S-curve, escalation, land payments)"),
                ("Sales" if self.mode == "sale" else "Rental", "Monthly sales and buyer payments" if self.mode == "sale" else "Monthly rents, NOI and exit"),
                ("Cash Flow", "Unlevered cash flow, debt draws and repayments, interest, equity"),
                ("Waterfall", "Investor vs sponsor distributions"), ("Budget", "Development budget by line item"),
                ("Sensitivity", "Scenario, tornado and heatmap results from TerraMind's engine (snapshot)")]
        for k, v in tabs:
            ws.cell(row=r, column=2, value=k).font = Font(name=FONT, color="2A78D6", underline="single", size=10)
            ws.cell(row=r, column=2).hyperlink = f"#'{k}'!A1"
            ws.cell(row=r, column=3, value=v).font = BLACK
            r += 1
        r += 1
        ws.cell(row=r, column=2, value="Legend").font = BOLD
        ws.cell(row=r + 1, column=2, value="1,234").font = BLUE
        ws.cell(row=r + 1, column=3, value="Input (edit these)").font = BLACK
        ws.cell(row=r + 2, column=2, value="1,234").font = BLACK
        ws.cell(row=r + 2, column=3, value="Formula (do not overwrite)").font = BLACK
        ws.cell(row=r + 3, column=2, value="Key driver").fill = YELLOW
        ws.cell(row=r + 3, column=3, value="Most important inputs").font = BLACK

    def sensitivity(self):
        ws = self.sheet("Sensitivity", "6250D6")
        self.header(ws, "Sensitivity & scenarios (TerraMind engine snapshot)", "Values computed by TerraMind's engine at export. Re-export after major changes.")
        ws.column_dimensions["A"].width = 40
        an = self.analysis or {}
        r = 4
        if an.get("status") != "ok":
            ws.cell(row=r, column=1, value="Model incomplete at export.")
            return
        for i, h in enumerate(["Scenario", "Equity IRR", "Profit", "Net margin", "MOIC", "Peak equity"]):
            c = ws.cell(row=r, column=1 + i, value=h)
            c.font, c.fill = HDR, NAVY
        r += 1
        for s in an.get("scenarios", []):
            mm = s.get("metrics") or {}
            for j, (v, f) in enumerate(((s["name"], None), (mm.get("equity_irr"), PCT), (mm.get("profit"), MONEY), (mm.get("net_margin"), PCT),
                                        (mm.get("moic"), MULT), (mm.get("peak_equity"), MONEY))):
                c = ws.cell(row=r, column=1 + j, value=v)
                if f:
                    c.number_format = f
            r += 1
        r += 2
        t = an.get("tornado", {})
        ws.cell(row=r, column=1, value="Equity IRR sensitivity (tornado)").font = BOLD
        r += 1
        for i, h in enumerate(["Driver", "Low", "High"]):
            c = ws.cell(row=r, column=1 + i, value=h)
            c.font, c.fill = HDR, NAVY
        r += 1
        for b in t.get("bars", []):
            ws.cell(row=r, column=1, value=b["driver"])
            for j, k in enumerate(("low_input", "high_input")):
                c = ws.cell(row=r, column=2 + j, value=b.get(k))
                c.number_format = PCT
            r += 1
        r += 2
        h = an.get("heatmap", {})
        ws.cell(row=r, column=1, value=f"Equity IRR: {h.get('y_label')} (rows) × {h.get('x_label')} (columns), % change").font = BOLD
        r += 1
        ws.cell(row=r, column=1, value="Cost Δ \\ Price Δ").font = HDR
        ws.cell(row=r, column=1).fill = NAVY
        for j, x in enumerate(h.get("x_steps", [])):
            c = ws.cell(row=r, column=2 + j, value=x / 100)
            c.font, c.fill, c.number_format = HDR, NAVY, PCT
        r += 1
        for i, y in enumerate(h.get("y_steps", [])):
            c = ws.cell(row=r, column=1, value=y / 100)
            c.number_format, c.font = PCT, BOLD
            for j, v in enumerate(h["grid"][i]):
                cc = ws.cell(row=r, column=2 + j, value=v)
                cc.number_format = PCT
            r += 1

    def _resolve_refs(self) -> None:
        """Rows that refer to rows defined later in the same sheet use {ROW:key} / {WROW:key} placeholders."""
        for title, marker, rows in (("Cash Flow", "{ROW:", self.cf_rows), ("Waterfall", "{WROW:", self.wf_rows)):
            for row in self.wb[title].iter_rows(min_row=5):
                for c in row:
                    if isinstance(c.value, str) and marker in c.value:
                        v = c.value
                        for k, rr in rows.items():
                            v = v.replace(marker + k + "}", str(rr))
                        c.value = v

    # ------------------------------------------------------------------ build
    def build(self) -> bytes:
        self.cover()
        self.assumptions()
        self.development()
        self.construction()
        self.sales()
        self.rental()
        self.cashflow()
        self.waterfall()
        self.budget()
        self.outputs()
        self.sensitivity()
        self._resolve_refs()
        if self.mode == "sale":
            self.wb["Rental"].sheet_state = "hidden"
        self.wb.calculation.iterate = True
        self.wb.calculation.iterateCount = 200
        self.wb.calculation.iterateDelta = 0.01
        self.wb.calculation.fullCalcOnLoad = True
        for ws in self.wb.worksheets:
            for row in ws.iter_rows():
                for c in row:
                    if c.font and c.font.name != FONT:
                        c.font = Font(name=FONT, size=c.font.size or 10, bold=c.font.bold, italic=c.font.italic, color=c.font.color, underline=c.font.underline)
        buf = io.BytesIO()
        self.wb.save(buf)
        return buf.getvalue()


# row lookups for formulas that reference rows defined later in the same sheet (filled in at build time)
_ROW_REFS: dict[str, int] = {}


def rows_ref(key: str) -> str:
    return "{ROW:" + key + "}"


def rows_ref2(key: str) -> str:
    return "{WROW:" + key + "}"


def export_project(project: dict, result: dict, analysis: dict | None) -> bytes:
    return Builder(project, result, analysis).build()
