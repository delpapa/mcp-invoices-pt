"""Google Sheets backend (optional: pip install mcp-invoices-pt[google]). The sheet does the VAT maths with formulas; this only fills the input columns.

New rows copy the formulas and formats of the last row, then the table is re-sorted by date.
Quarters marked filed (protected ranges named "Qn filed: ...") are never written to.
"""

from __future__ import annotations

import datetime as dt
import os
import re

import gspread
from google.oauth2.service_account import Credentials

from . import bookmath, columns, layout
from .config import Config

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
QUARTER_HEADER = re.compile(r"^(Q|Quarter)\b", re.I)    # "Q", "Q (IVA)", "Quarter (IVA/IRS)"
GREY = {"red": 0.93, "green": 0.93, "blue": 0.93}


def quarter(day: dt.date) -> str:
    return f"Q{(day.month - 1) // 3 + 1}"


def _col(j: int) -> str:
    return gspread.utils.rowcol_to_a1(1, j + 1)[:-1]


def _input_value(field: str, value) -> dict:
    """Convert a booking field to a Sheets ExtendedValue without relying on the spreadsheet locale."""
    if value is None or value == "":
        return {}
    if field in columns.DATE_FIELDS and (day := bookmath.day(value)):
        return {"numberValue": (day - dt.date(1899, 12, 30)).days}
    if field in columns.NUMBER_FIELDS and (number := bookmath.num(value)) is not None:
        return {"numberValue": number}
    return {"stringValue": str(value)}


def _span(rows: list[int]) -> str:
    return f"{min(rows)}-{max(rows)}" if rows else "none"


def _bounds(rows: list[int]) -> tuple[int, int]:
    """0-based [start, end) row bounds covering `rows` (1-based)."""
    return (min(rows) - 1, max(rows)) if rows else (0, 0)


def open_spreadsheet(cfg: Config) -> gspread.Spreadsheet:
    creds = Credentials.from_service_account_file(os.path.expanduser(cfg.google["service_account"]), scopes=SCOPES)
    return gspread.authorize(creds).open_by_key(cfg.google["spreadsheet_id"])


class Table:
    """One tab whose table starts at the row whose first cell is the first column's header.
    COLUMNS maps input fields to header texts; the first field is the date the table is sorted by."""

    KIND = ""
    COLUMNS: dict[str, str] = {}
    UNIQUE: tuple[str, ...] = ()        # fields that identify a row; a second row with the same value is refused

    def __init__(self, cfg: Config, year: int, sh: gspread.Spreadsheet | None = None):
        self.cfg, self.year = cfg, year
        self.sh = sh or open_spreadsheet(cfg)
        self.ws = self.sh.worksheet(cfg.tab(self.KIND, year))
        self.columns = {**self.COLUMNS, **cfg.column_overrides(self.KIND)}
        self.date_field = next(iter(self.COLUMNS))

    def _table(self, value_render_option: str = "FORMATTED_VALUE") -> tuple[int, dict[str, int], list[list]]:
        values = self.ws.get_all_values(value_render_option=value_render_option)
        first = self.columns[self.date_field]
        head = next(i for i, r in enumerate(values) if r and str(r[0]).strip() == first)
        index = {str(h).strip(): j for j, h in enumerate(values[head]) if str(h).strip()}
        missing = [h for h in columns.table_fields(self.columns, index).values() if h.strip() not in index]
        if missing:
            raise KeyError(f"{self.ws.title}: headers not found: {missing}; map them in the config")
        return head + 1, index, values

    def records(self) -> list[dict]:
        """Every table row as {field: value}, plus its row number and quarter."""
        head, idx, values = self._table()
        qcol = next((j for h, j in idx.items() if QUARTER_HEADER.match(h)), None)
        mapped = columns.table_fields(self.columns, idx)
        out = []
        for rn, r in enumerate(values[head:], head + 1):
            if not any(r):
                continue
            rec = {f: (r[idx[h.strip()]] if idx[h.strip()] < len(r) else "") for f, h in mapped.items()}
            rec["row"] = rn
            rec["quarter"] = r[qcol] if qcol is not None and qcol < len(r) else ""
            out.append(rec)
        return out

    def _protections(self) -> list[dict]:
        meta = self.sh.fetch_sheet_metadata()
        return [p for s in meta["sheets"] for p in s.get("protectedRanges", [])]

    def filed_quarters(self) -> set[str]:
        # A quarter is filed even when it had no sales and hence no protected income rows.
        sheet_ids = {self.ws.id}
        if self.KIND == "income":
            sheet_ids.add(self.sh.worksheet(self.cfg.tab("expenses", self.year)).id)
        return {m.group(1) for p in self._protections() if p["range"]["sheetId"] in sheet_ids
                and (m := re.match(r"^(Q\d) filed", p.get("description", "")))}

    def find(self, value: str, field: str = "invoice_no", supplier_vat: str = "", doc_type: str = "") -> int | None:
        return columns.find_row(self.records(), value, field, supplier_vat, doc_type)

    def add(self, row: dict, dry_run: bool = True, allow_filed: bool = False) -> dict:
        if self.KIND == "expenses" and bookmath.expense_fx(row.get("fx"), row.get("currency")) is None:
            return {"error": bookmath.EXPENSE_FX_ERROR}
        day = dt.date.fromisoformat(str(row[self.date_field]))
        q = quarter(day)
        filed = q in self.filed_quarters()
        if filed and not allow_filed:
            return {"error": f"{q} is filed and locked; pass allow_filed only for a deliberate correction"}
        supplier_vat = row.get("supplier_vat", "")
        doc_type = row.get("doc_type", "")
        for field in self.UNIQUE:
            if row.get(field) not in (None, "") and (dup := self.find(row[field], field, supplier_vat, doc_type)):
                return {"error": f"{field} {row[field]} is already in row {dup}"}
        head, idx, values = self._table()
        case = (row.get("vat_case") or "").strip().upper()
        if self.KIND == "income" and case in ("PT / C1", "PT / C5"):
            expenses = ExpenseSheet(self.cfg, self.year, self.sh)
            _, formulas, boxes, quarters = expenses._block()
            col = quarters[q]
            cells = {int(b): (gspread.utils.rowcol_to_a1(i + 1, col + 1),
                              formulas[i][col] if col < len(formulas[i]) else "") for b, i in boxes.items()}
            if error := layout.sales_layout_error(case, idx, cells, filed):
                return {"error": error}
        mapped = columns.table_fields(self.columns, idx)
        cells = {mapped[k]: v for k, v in row.items() if k in mapped and v not in (None, "")}
        if dry_run:
            return {"dry_run": True, "tab": self.ws.title, "quarter": q, "cells": cells}
        filled = [i + 1 for i, r in enumerate(values) if i >= head and any(r)]
        dated = [i + 1 for i, r in enumerate(values) if i >= head and r and r[0]]
        last = max(filled) if filled else head          # an empty table: insert right under the header
        template = max(dated) if dated else None
        width = max(idx.values()) + 1
        sid = self.ws.id
        reqs = [{"insertDimension": {"range": {"sheetId": sid, "dimension": "ROWS", "startIndex": last, "endIndex": last + 1},
                                     "inheritFromBefore": template is not None}}]
        new = last + 1
        values_by_header = {}
        if template:
            source = {"sheetId": sid, "startRowIndex": template - 1, "endRowIndex": template,
                      "startColumnIndex": 0, "endColumnIndex": width}
            dest = {**source, "startRowIndex": last, "endRowIndex": new}
            for paste in ("PASTE_FORMAT", "PASTE_FORMULA"):
                reqs.append({"copyPaste": {"source": source, "destination": dest, "pasteType": paste}})
        else:
            for header, formula in layout.row_formulas(self.KIND, new).items():
                if header in idx:
                    values_by_header[header] = {"formulaValue": formula}
        for field, header in mapped.items():
            values_by_header[header.strip()] = _input_value(field, row.get(field))
        for header, value in values_by_header.items():
            reqs.append({"updateCells": {
                "start": {"sheetId": sid, "rowIndex": last, "columnIndex": idx[header]},
                "rows": [{"values": [{"userEnteredValue": value} if value else {}]}],
                "fields": "userEnteredValue"}})
        reqs.append({"sortRange": {
            "range": {"sheetId": sid, "startRowIndex": head, "endRowIndex": new, "startColumnIndex": 0,
                      "endColumnIndex": width},
            "sortSpecs": [{"dimensionIndex": 0, "sortOrder": "ASCENDING"}]}})
        # A rejected booking must leave the sheet untouched, including the template and its values.
        self.sh.batch_update({"requests": reqs})
        key = next((f for f in self.UNIQUE if row.get(f) not in (None, "")), None)
        new_row = self.find(row[key], key, supplier_vat, doc_type) if key else None
        return {"written": True, "tab": self.ws.title, "quarter": q, "row": new_row}


class IncomeSheet(Table):
    KIND = "income"
    COLUMNS = columns.INCOME_FIELDS
    UNIQUE = columns.UNIQUE["income"]

    def receipts(self):
        """Read date serials and monetary values without display-locale conversion."""
        head, idx, rows = self._table("UNFORMATTED_VALUE")
        date_col, amount_col = (idx[self.columns[k].strip()] for k in ("recibo_date", "net_eur"))
        for r in rows[head:]:
            if len(r) > max(date_col, amount_col):
                date = r[date_col]
                if isinstance(date, (int, float)):
                    date = dt.date(1899, 12, 30) + dt.timedelta(days=int(date))
                yield {"recibo_date": date, "net_eur": r[amount_col]}

    def summary(self) -> list[dict]:
        """The rows above the table (IRS and Segurança Social totals): label and the values per quarter."""
        head, _, values = self._table(value_render_option="UNFORMATTED_VALUE")
        quarters = None
        out = []
        for r in values[:head - 1]:
            cells = [str(c).strip() for c in r]
            if "Q1" in cells:
                quarters = {c: j for j, c in enumerate(cells) if re.fullmatch(r"Q[1-4]|\d{4}", c)}
                continue
            if quarters and cells and cells[0]:
                out.append({"item": cells[0], **{q: bookmath.num(r[j]) if j < len(r) else None
                                               for q, j in quarters.items()}})
        return out


class ExpenseSheet(Table):
    KIND = "expenses"
    COLUMNS = columns.EXPENSE_FIELDS
    UNIQUE = columns.UNIQUE["expenses"]

    # ---- the "Declaração Periódica" block above the table: rows "Box n", one column per quarter
    def _block(self) -> tuple[list[list], list[list], dict[str, int], dict[str, int]]:
        values = self.ws.get_all_values(value_render_option="UNFORMATTED_VALUE")
        formulas = self.ws.get_all_values(value_render_option="FORMULA")
        head = next(i for i, r in enumerate(values) if r and str(r[0]).strip() == self.columns["date"])
        boxes = {m.group(1): i for i, r in enumerate(values[:head])
                 if r and (m := re.match(r"^Box (\d+)$", str(r[0]).strip()))}
        if not boxes:
            raise KeyError("no 'Box n' rows above the table")
        top = min(boxes.values())
        header = next(row for row in reversed(values[:top]) if any(str(c).strip() in bookmath.QUARTERS for c in row))
        quarters = {str(c).strip(): j for j, c in enumerate(header) if str(c).strip() in bookmath.QUARTERS}
        return values, formulas, boxes, quarters

    def declaration(self, q: str) -> dict:
        """Box values of one quarter as shown in the block, and whether they are still live formulas."""
        values, formulas, boxes, quarters = self._block()
        j = quarters[q]
        rows = [{"box": int(b), "label": values[i][2] if len(values[i]) > 2 else "",
                 "value": bookmath.num(values[i][j]) if j < len(values[i]) else None}
                for b, i in sorted(boxes.items(), key=lambda kv: kv[1])]
        live = any(j < len(formulas[i]) and str(formulas[i][j]).startswith("=") for i in boxes.values())
        return {"quarter": q, "boxes": rows, "filed": q in self.filed_quarters(), "live_formulas": live}

    def set_declaration(self, q: str, box_values: dict[int, float]) -> None:
        """Overwrite a quarter's block cells with fixed values (used to apply the submitted return)."""
        _, _, boxes, quarters = self._block()
        j = quarters[q]
        self.ws.batch_update([{"range": gspread.utils.rowcol_to_a1(boxes[str(b)] + 1, j + 1), "values": [[v]]}
                              for b, v in box_values.items() if str(b) in boxes], value_input_option="RAW")

    def freeze(self, q: str, dry_run: bool = True, box_values: dict[int, float] | None = None) -> dict:
        """Mark a quarter filed: fixed values in the block, greyed, and warning-only protection on the block column,
        that quarter's expense rows and its income rows."""
        values, formulas, boxes, quarters = self._block()
        j = quarters[q]
        first, last = min(boxes.values()), max(boxes.values())
        live = [i for i in boxes.values() if j < len(formulas[i]) and str(formulas[i][j]).startswith("=")]
        exp_rows = [r["row"] for r in self.records() if r["quarter"] == q]
        income = IncomeSheet(self.cfg, self.year, self.sh)
        i_head, i_idx, _ = income._table()
        inc_rows = [r["row"] for r in income.records() if r["quarter"] == q]
        have = {(p["range"]["sheetId"], p.get("description", "")) for p in self._protections()}
        plan = {"quarter": q, "formulas_to_freeze": len(live), "expense_rows": _span(exp_rows),
                "income_rows": _span(inc_rows), "already_filed": q in self.filed_quarters()}
        reqs = []
        overrides = box_values or {}
        for box, i in boxes.items():
            if int(box) in overrides:
                amount = overrides[int(box)]
            elif i in live:
                amount = bookmath.num(values[i][j]) if j < len(values[i]) else None
                if amount is None:
                    raise ValueError(f"Cannot freeze {q} box {box}: the formula has no numeric result")
            else:
                continue
            reqs.append({"updateCells": {
                "start": {"sheetId": self.ws.id, "rowIndex": i, "columnIndex": j},
                "rows": [{"values": [{"userEnteredValue": {"numberValue": amount}}]}],
                "fields": "userEnteredValue"}})
        if dry_run:
            return {"dry_run": True, **plan}
        reqs.append({"repeatCell": {
            "range": {"sheetId": self.ws.id, "startRowIndex": first, "endRowIndex": last + 1,
                      "startColumnIndex": j, "endColumnIndex": j + 1},
            "cell": {"userEnteredFormat": {"backgroundColor": GREY}}, "fields": "userEnteredFormat.backgroundColor"}})
        width = max(self._table()[1].values()) + 1
        for desc, sid, r0, r1, c0, c1 in [
                (f"{q} filed: declaration values", self.ws.id, first, last + 1, j, j + 1),
                (f"{q} filed: invoice rows", self.ws.id, *_bounds(exp_rows), 0, width),
                (f"{q} filed: income rows", income.ws.id, *_bounds(inc_rows), 0, max(i_idx.values()) + 1)]:
            if (sid, desc) not in have and r1 > r0:
                reqs.append({"addProtectedRange": {"protectedRange": {
                    "range": {"sheetId": sid, "startRowIndex": r0, "endRowIndex": r1, "startColumnIndex": c0,
                              "endColumnIndex": c1}, "description": desc, "warningOnly": True}}})
        self.sh.batch_update({"requests": reqs})
        return {"frozen": True, **plan}
