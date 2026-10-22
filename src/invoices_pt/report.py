"""What is still missing for a year, and how the sheet compares with e-Fatura."""

from __future__ import annotations

import collections
import datetime as dt
import os
import re

from .model import Document

DOC_EXT = (".pdf", ".png", ".jpg", ".jpeg", ".webp")


def _n(s) -> str:
    return re.sub(r"\s+", "", str(s or "")).upper()


def _amount(s) -> float | None:
    try:
        return round(float(str(s).replace(",", "")), 2)
    except ValueError:
        return None


def _date(s: str) -> dt.date | None:
    for fmt in ("%d.%m.%Y", "%Y-%m-%d"):
        try:
            return dt.datetime.strptime(s, fmt).date()
        except (TypeError, ValueError):
            pass
    return None


def monthly_gaps(records: list[dict], min_months: int = 3) -> list[dict]:
    """Suppliers billed in at least `min_months` months, with months missing between their first and last."""
    months = collections.defaultdict(set)
    for r in records:
        d = _date(r["date"])
        if d and r["supplier"]:
            months[r["supplier"]].add((d.year, d.month))
    gaps = []
    for supplier, seen in months.items():
        if len(seen) < min_months:
            continue
        (y0, m0), (y1, m1) = min(seen), max(seen)
        expected = {(y0 + (m0 - 1 + k) // 12, (m0 - 1 + k) % 12 + 1) for k in range((y1 - y0) * 12 + m1 - m0 + 1)}
        if hole := sorted(expected - seen):
            gaps.append({"supplier": supplier, "missing_months": [f"{y}-{m:02d}" for y, m in hole]})
    return gaps


def missing(records: list[dict], folder: str, read=None) -> dict:
    """Rows flagged MISSING, rows whose file is gone, incomplete rows, files nobody booked, and monthly gaps.
    `read(path)` reads an unbooked file so it can be matched to a row it merely duplicates (e.g. a receipt)."""
    files = {f for f in os.listdir(folder) if f.lower().endswith(DOC_EXT)} if os.path.isdir(folder) else set()
    booked = {r["file"] for r in records if r["file"]}
    out = {"flagged": [], "file_not_found": [], "incomplete": [], "unbooked_files": [], "companion_files": [],
           "monthly_gaps": monthly_gaps(records)}
    for r in records:
        tag = f"row {r['row']} {r['date']} {r['expense'] or r['supplier']}".strip()
        if r["document"].upper().startswith("MISSING"):
            out["flagged"].append(tag)
        if r["file"] and r["file"] not in files:
            out["file_not_found"].append(f"{tag}: {r['file']}")
        need = ["date", "amount"] + ([] if r["document"] == "No invoice" else ["invoice_no"])
        if (gaps := [f for f in need if not str(r[f]).strip()]) and not r["document"].upper().startswith("MISSING"):
            out["incomplete"].append(f"{tag}: no {', '.join(gaps)}")
    by_day_amount = {(_date(r["date"]), _amount(r["amount"])): r for r in records}
    for f in sorted(files - booked):
        row = None
        if read:
            try:
                doc: Document = read(os.path.join(folder, f))
                row = by_day_amount.get((doc.date, round(doc.amount or 0, 2)))
            except Exception:
                row = None
        if row:
            out["companion_files"].append(f"{f} (same payment as row {row['row']})")
        else:
            out["unbooked_files"].append(f)
    return out


def missing_income(records: list[dict], folder: str) -> dict:
    """Income rows without an AT document (not paid or not issued yet), rows whose files are gone, unbooked files."""
    files = {f for f in os.listdir(folder) if f.lower().endswith(DOC_EXT)} if os.path.isdir(folder) else set()
    out = {"no_at_document": [], "file_not_found": [], "unbooked_files": []}
    for r in records:
        tag = f"row {r['row']} {r['invoice_date']} {r['client']} {r['invoice_no']}".strip()
        if not r["recibo_no"]:
            out["no_at_document"].append(tag)
        for f in (r["invoice_file"], r["recibo_file"]):
            if f and f not in files:
                out["file_not_found"].append(f"{tag}: {f}")
    booked = {r[k] for r in records for k in ("invoice_file", "recibo_file") if r[k]}
    out["unbooked_files"] = sorted(files - booked)
    return out


def reconcile_efatura(docs: list[Document], records: list[dict]) -> dict:
    """Match e-Fatura documents to sheet rows by invoice number, else by date and amount."""
    by_inv = {_n(r["invoice_no"]): r for r in records if r["invoice_no"]}
    by_day_amount = {(_date(r["date"]), _amount(r["amount"])): r for r in records}
    matched, out = set(), {"not_in_sheet": [], "differences": [], "pt_rows_not_in_efatura": []}
    for d in docs:
        r = by_inv.get(_n(d.invoice_no)) or by_day_amount.get((d.date, round(d.amount or 0, 2)))
        if not r:
            out["not_in_sheet"].append({"date": d.date.isoformat(), "supplier": d.supplier, "invoice_no": d.invoice_no,
                                        "amount": d.amount, "vat": d.vat_included, "sector": d.extra.get("sector", "")})
            continue
        matched.add(r["row"])
        diffs = []
        if _amount(r["amount"]) != round(d.amount or 0, 2):
            diffs.append(f"amount {r['amount']} vs {d.amount}")
        if r["vat_included"] and _amount(r["vat_included"]) != round(d.vat_included or 0, 2):
            diffs.append(f"VAT {r['vat_included']} vs {d.vat_included}")
        if r["invoice_no"] and _n(r["invoice_no"]) != _n(d.invoice_no):
            diffs.append(f"invoice no. {r['invoice_no']} vs {d.invoice_no}")
        if not r["invoice_no"] or not r["vat_included"] or not r["supplier_vat"]:
            diffs.append("sheet is missing fields e-Fatura has")
        if diffs:
            out["differences"].append({"row": r["row"], "efatura": d.to_dict(), "issues": diffs})
    for r in records:
        if r["row"] not in matched and _n(r["supplier_vat"]).startswith("PT") and r["document"] != "No invoice":
            out["pt_rows_not_in_efatura"].append(f"row {r['row']} {r['date']} {r['supplier']} {r['amount']}")
    return out
