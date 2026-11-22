"""The sheet's formulas, in Python: row amounts, IVA boxes and the quarter-by-quarter declaration.

The workbook keeps the formulas so you can read and edit it; the tools use this module to get the numbers, since a
file written by Python carries no calculated values. Rounding follows the spreadsheet ROUND (half away from zero),
so both agree to the cent.
"""

from __future__ import annotations

import datetime as dt
import math
import re
from decimal import ROUND_HALF_UP, Decimal

from .vat import NORMAL_RATE, RESULT_SUMS, REVERSE_CHARGE_BOXES, SALES_BOXES

QUARTERS = ("Q1", "Q2", "Q3", "Q4")
INPUT_BOXES = (1, 2, 3, 4, 5, 6, 7, 8, 12, 13, 16, 17, 20, 24, 61, 98)
RESULT_BOXES = (90, 91, 92, 93, 94, 96)


def _cents(amount: Decimal) -> Decimal:
    return amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def r2(x: float) -> float:
    return float(_cents(Decimal(str(x))))


def num(v) -> float | None:
    """Read a numeric cell or US/Portuguese numeric text, keeping '1,234' as a thousands grouping."""
    if v is None or v == "":
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).replace("€", "").replace("$", "").strip()
    pct = s.endswith("%")
    s = s.removesuffix("%").strip()
    if re.fullmatch(r"[+-]?\d{1,3}(?:[ \u00a0\u202f]\d{3})+(?:[.,]\d+)?", s):
        s = "".join(s.split())
    if "," in s:
        if re.fullmatch(r"[+-]?[1-9]\d{0,2}(?:,\d{3})+(?:\.\d+)?", s):
            s = s.replace(",", "")
        elif re.fullmatch(r"[+-]?(?:\d+|\d{1,3}(?:\.\d{3})+),\d+", s):
            s = s.replace(".", "").replace(",", ".")
        else:
            return None
    try:
        x = float(s)
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


EXPENSE_FX_ERROR = "fx must be a positive finite exchange rate; leave blank for 1"


def expense_fx(value) -> float | None:
    if value in (None, ""):
        return 1.0
    rate = num(value)
    return rate if rate is not None and math.isfinite(rate) and rate > 0 else None


def expense_row(rec: dict) -> dict:
    """Computed columns of one expense row, as the sheet formulas compute them."""
    amount = num(rec.get("amount"))
    out = {k: 0.0 for k in ("amount_eur", "net_eur", 3, 4, 12, 13, 16, 17, 20, 24, 98, "net_vat", "irs")}
    if amount is None:
        out["amount_eur"] = out["net_eur"] = out["irs"] = None
        return out
    # Preserve decimal half-cents through subtraction and multiplication before ROUND.
    amount = Decimal(str(amount))
    vat_incl = Decimal(str(num(rec.get("vat_included")) or 0))
    rate = expense_fx(rec.get("fx"))
    if rate is None:
        raise ValueError(f"Expense row {rec.get('row', '?')}: {EXPENSE_FX_ERROR}")
    fx = Decimal(str(rate))
    share = num(rec.get("business_pct"))
    biz = Decimal(str(share)) if share is not None else Decimal(1)
    code = (rec.get("code") or "").strip().upper()
    m, n = _cents(amount / fx), _cents((amount - vat_incl) / fx)
    out["amount_eur"], out["net_eur"] = m, n
    reverse_vat = Decimal(0)
    if code in REVERSE_CHARGE_BOXES:
        base_box, vat_box = REVERSE_CHARGE_BOXES[code]
        reverse_vat = _cents(n * Decimal(str(NORMAL_RATE)))
        out[base_box], out[vat_box] = n, reverse_vat
    domestic = _cents((m - n) * biz)
    out[20] = domestic if code == "PT-ASSET" else 0
    out[24] = (domestic if code == "PT" else 0) + _cents(reverse_vat * biz)
    out[98] = out[3]
    out["net_vat"] = out[20] + out[24] - reverse_vat
    out["irs"] = _cents(m * biz - out["net_vat"])
    return {key: float(value) for key, value in out.items()}


def income_row(rec: dict) -> dict:
    net = num(rec.get("net_eur")) or 0.0
    vat = num(rec.get("vat_eur")) or 0.0
    case = (rec.get("vat_case") or "").strip().upper()
    out = {box: 0.0 for pair in SALES_BOXES.values() for box in pair if box is not None}
    out.update(net_eur=net, withheld=num(rec.get("withheld")) or 0.0)
    if case in SALES_BOXES:
        base_box, tax_box = SALES_BOXES[case]
        out[base_box] = net
        if tax_box:
            out[tax_box] = vat
    return out


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
            for b, value in row.items():
                if b in boxes:
                    boxes[b] += value
    return {b: r2(v) for b, v in boxes.items()}


def results(boxes: dict[int, float]) -> dict[int, float]:
    out = {box: sum(boxes.get(b, 0.0) for b in fields) for box, fields in RESULT_SUMS.items()}
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
