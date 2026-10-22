"""The sheet's formulas, in Python: row amounts, IVA boxes and the quarter-by-quarter declaration.

The workbook keeps the formulas so you can read and edit it; the tools use this module to get the numbers, since a
file written by Python carries no calculated values. Rounding follows the spreadsheet ROUND (half away from zero),
so both agree to the cent.
"""

from __future__ import annotations

import datetime as dt
from decimal import ROUND_HALF_UP, Decimal

QUARTERS = ("Q1", "Q2", "Q3", "Q4")
INPUT_BOXES = (3, 4, 7, 8, 12, 13, 16, 17, 20, 24, 61, 98)
RESULT_BOXES = (90, 91, 92, 93, 94, 96)


def r2(x: float) -> float:
    return float(Decimal(repr(x)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def num(v) -> float | None:
    """A cell value (number or text like '1,234.56', '25%', '€3.10') as a float."""
    if v is None or v == "":
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().replace(",", "").replace("€", "").replace("$", "")
    pct = s.endswith("%")
    try:
        x = float(s.rstrip("%"))
    except ValueError:
        return None
    return x / 100 if pct else x


def day(v) -> dt.date | None:
    if isinstance(v, dt.datetime):
        return v.date()
    if isinstance(v, dt.date):
        return v
    for fmt in ("%d.%m.%Y", "%Y-%m-%d"):
        try:
            return dt.datetime.strptime(str(v).strip(), fmt).date()
        except ValueError:
            pass
    return None


def quarter(v) -> str:
    d = day(v)
    return f"Q{(d.month - 1) // 3 + 1}" if d else ""


def expense_row(rec: dict) -> dict:
    """Computed columns of one expense row, as the sheet formulas compute them."""
    amount = num(rec.get("amount"))
    out = {k: 0.0 for k in ("amount_eur", "net_eur", 3, 4, 12, 13, 16, 17, 20, 24, 98, "net_vat", "irs")}
    if amount is None:
        out["amount_eur"] = out["net_eur"] = out["irs"] = None
        return out
    vat_incl = num(rec.get("vat_included")) or 0.0
    fx = num(rec.get("fx")) or 1.0
    biz = num(rec.get("business_pct"))
    biz = 1.0 if biz is None else biz
    code = (rec.get("code") or "").strip()
    m, n = r2(amount / fx), r2((amount - vat_incl) / fx)
    out["amount_eur"], out["net_eur"] = m, n
    if code == "NON-EU-RC":
        out[3], out[4] = n, r2(n * 0.23)
    if code == "EU-RC-GOODS":
        out[12], out[13] = n, r2(n * 0.23)
    if code == "EU-RC":
        out[16], out[17] = n, r2(n * 0.23)
    if code == "PT-ASSET":
        out[20] = r2((m - n) * biz)
    out[24] = (r2((m - n) * biz) if code == "PT" else 0.0) + r2((out[4] + out[13] + out[17]) * biz)
    out[98] = out[3]
    out["net_vat"] = out[20] + out[24] - out[4] - out[13] - out[17]
    out["irs"] = r2(m * biz - out["net_vat"])
    return out


def income_row(rec: dict) -> dict:
    net = num(rec.get("net_eur")) or 0.0
    vat = num(rec.get("vat_eur")) or 0.0
    case = (rec.get("vat_case") or "").strip()
    return {3: net if case == "PT / C3" else 0.0, 4: vat if case == "PT / C3" else 0.0,
            7: net if case == "EU / C7" else 0.0, 8: net if case == "NON-EU / C8" else 0.0,
            "net_eur": net, "withheld": num(rec.get("withheld")) or 0.0}


def quarter_inputs(expenses: list[dict], income: list[dict], q: str) -> dict[int, float]:
    boxes = {b: 0.0 for b in INPUT_BOXES if b != 61}
    for rec in expenses:
        if quarter(rec.get("date")) == q:
            row = expense_row(rec)
            for b in (3, 4, 12, 13, 16, 17, 20, 24, 98):
                boxes[b] += row[b]
    for rec in income:
        if quarter(rec.get("invoice_date")) == q:
            row = income_row(rec)
            for b in (3, 4, 7, 8):
                boxes[b] += row[b]
    return {b: r2(v) for b, v in boxes.items()}


def results(boxes: dict[int, float]) -> dict[int, float]:
    b = boxes
    out = {90: b[3] + b[7] + b[8] + b[12] + b[16], 91: b[20] + b[24] + b[61], 92: b[4] + b[13] + b[17]}
    out[93] = max(out[92] - out[91], 0.0)
    out[94] = max(out[91] - out[92], 0.0)
    out[96] = out[94]
    return {k: r2(v) for k, v in out.items()}


def declaration(expenses: list[dict], income: list[dict], opening_credit: float,
                frozen: dict[str, dict[int, float]] | None = None) -> dict[str, dict[int, float]]:
    """All four quarters. Quarters in `frozen` (filed) keep their stored values; box 61 chains from box 96."""
    frozen = frozen or {}
    out, carried = {}, opening_credit
    for q in QUARTERS:
        if q in frozen:
            boxes = dict(frozen[q])
        else:
            boxes = quarter_inputs(expenses, income, q)
            boxes[61] = r2(carried)
            boxes.update(results(boxes))
        out[q] = boxes
        carried = boxes.get(96, 0.0)
    return out


def income_totals(expenses: list[dict], income: list[dict], year: int) -> list[dict]:
    """IRS / Segurança Social totals per quarter, as the income tab's top block computes them."""
    def by(rows, key, value):
        out = {q: 0.0 for q in QUARTERS}
        for rec in rows:
            q = quarter(rec.get(key))
            if q:
                out[q] += value(rec) or 0.0
        out = {q: r2(v) for q, v in out.items()}
        out[str(year)] = r2(sum(out.values()))
        return out
    return [
        {"item": "Gross income € (IRS Anexo B, by invoice date)", **by(income, "invoice_date", lambda r: num(r.get("net_eur")))},
        {"item": "Income € by recibo date (Segurança Social quarterly declaration)",
         **by(income, "recibo_date", lambda r: num(r.get("net_eur")))},
        {"item": "Business expenses € (IRS deductible, Anexo B quadro 17 if used)",
         **by(expenses, "date", lambda r: expense_row(r)["irs"])},
    ]


def text_id(v) -> str:
    """IDs typed as numbers come back as floats; keep them as text."""
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v)
