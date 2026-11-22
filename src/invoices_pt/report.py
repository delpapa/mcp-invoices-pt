"""What is still missing for a year, and how the sheet compares with e-Fatura."""

from __future__ import annotations

import collections
import datetime as dt
import os
import re

from .bookmath import num
from .documents import DOC_EXT
from .model import Document


def _n(s) -> str:
    return re.sub(r"\s+", "", str(s or "")).upper()


def _amount(s) -> float | None:
    value = num(s)
    return round(value, 2) if value is not None else None


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


def _document_files(folder: str) -> set[str]:
    if not os.path.isdir(folder):
        return set()
    with os.scandir(folder) as entries:
        return {entry.name for entry in entries if entry.name.lower().endswith(DOC_EXT) and entry.is_file()}


def _compatible_payment(doc: Document, row: dict) -> bool:
    def conflict(a, b):
        return bool(_n(a) and _n(b) and _n(a) != _n(b))

    if doc.cancelled:
        return False
    if conflict(doc.currency, row.get("currency")) or conflict(doc.supplier_vat, row.get("supplier_vat")):
        return False
    if not (doc.supplier_vat and row.get("supplier_vat")) and conflict(doc.supplier, row.get("supplier")):
        return False
    # A payment receipt normally has a different document number from its invoice.
    if "receipt" in (doc.doc_type, row.get("doc_type")):
        return True
    return not (conflict(doc.doc_type, row.get("doc_type")) or conflict(doc.invoice_no, row.get("invoice_no")))


def missing(records: list[dict], folder: str, read=None) -> dict:
    """Rows flagged MISSING, rows whose file is gone, incomplete rows, files nobody booked, and monthly gaps.
    `read(path)` reads an unbooked file so it can be matched to a row it merely duplicates (e.g. a receipt)."""
    files = _document_files(folder)
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
        if (gaps := [f for f in need if r[f] is None or not str(r[f]).strip()]) and not r["document"].upper().startswith("MISSING"):
            out["incomplete"].append(f"{tag}: no {', '.join(gaps)}")
    by_day_amount = collections.defaultdict(list)
    for r in records:
        day, amount = _date(r["date"]), _amount(r["amount"])
        if day and amount is not None:
            by_day_amount[day, amount].append(r)
    for f in sorted(files - booked):
        row = None
        if read:
            try:
                doc: Document = read(os.path.join(folder, f))
                candidates = [r for r in by_day_amount.get((doc.date, _amount(doc.amount)), ())
                              if _compatible_payment(doc, r)]
                if len(candidates) == 1:
                    row = candidates[0]
            except Exception:
                row = None
        if row:
            out["companion_files"].append(f"{f} (same payment as row {row['row']})")
        else:
            out["unbooked_files"].append(f)
    return out


def missing_income(records: list[dict], folder: str) -> dict:
    """Income rows without an AT document (not paid or not issued yet), rows whose files are gone, unbooked files."""
    files = _document_files(folder)
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


def _reconciliation_keys(supplier_vat, invoice_no, doc_type, day, amount):
    supplier, number = _n(supplier_vat), _n(invoice_no)
    payment = (day, amount) if day and amount is not None else None
    identity = (supplier, number) if supplier and number else None
    return {"document": (identity, _n(doc_type)) if identity and doc_type else None,
            "supplier_number": identity, "number": number,
            "supplier_payment": (supplier, payment) if supplier and payment else None, "payment": payment}


def _unique_positions(keys, field, used):
    positions = {}
    for index, alternatives in enumerate(keys):
        key = alternatives[field]
        if key and index not in used:
            positions[key] = None if key in positions else index
    return positions


def _efatura_pairs(docs, records, identity_only=False):
    """Reserve unambiguous number matches before matching the remaining payments."""
    doc_keys = [_reconciliation_keys(d.supplier_vat, d.invoice_no, d.doc_type, d.date, _amount(d.amount)) for d in docs]
    row_keys = [_reconciliation_keys(r["supplier_vat"], r["invoice_no"], r.get("doc_type"),
                                     _date(r["date"]), _amount(r["amount"]))
                for r in records]
    pairs, used_rows = {}, set()
    fields = ("document", "supplier_number", "number")
    if not identity_only:
        fields += ("supplier_payment", "payment")
    for field in fields:
        invoices = _unique_positions(doc_keys, field, pairs)
        rows = _unique_positions(row_keys, field, used_rows)
        for key, i in invoices.items():
            j = rows.get(key)
            if i is None or j is None:
                continue
            doc_vat, row_vat = _n(docs[i].supplier_vat), _n(records[j]["supplier_vat"])
            if doc_vat and row_vat and doc_vat != row_vat:
                continue
            kind = _n(records[j].get("doc_type"))
            if kind and docs[i].doc_type and kind != _n(docs[i].doc_type):
                continue
            pairs[i] = records[j]
            used_rows.add(j)
    return pairs


def reconcile_efatura(docs: list[Document], records: list[dict]) -> dict:
    """Match e-Fatura documents one-to-one with supplier-compatible rows by number, then date and amount."""
    cancelled = [d for d in docs if d.cancelled]
    docs = [d for d in docs if not d.cancelled]
    pairs = _efatura_pairs(docs, records)
    matched, out = set(), {"not_in_sheet": [], "differences": [], "pt_rows_not_in_efatura": []}
    for i, d in enumerate(docs):
        r = pairs.get(i)
        if not r:
            out["not_in_sheet"].append({"date": d.date.isoformat(), "supplier": d.supplier, "invoice_no": d.invoice_no,
                                        "amount": d.amount, "vat": d.vat_included, "sector": d.extra.get("sector", "")})
            continue
        matched.add(r["row"])
        diffs = []
        if d.date and _date(r["date"]) != d.date:
            diffs.append(f"date {r['date']} vs {d.date.isoformat()}")
        if _amount(r["amount"]) != round(d.amount or 0, 2):
            diffs.append(f"amount {r['amount']} vs {d.amount}")
        has_vat = r["vat_included"] not in (None, "")
        if has_vat and _amount(r["vat_included"]) != round(d.vat_included or 0, 2):
            diffs.append(f"VAT {r['vat_included']} vs {d.vat_included}")
        if r["invoice_no"] and _n(r["invoice_no"]) != _n(d.invoice_no):
            diffs.append(f"invoice no. {r['invoice_no']} vs {d.invoice_no}")
        if not r["invoice_no"] or not has_vat or not r["supplier_vat"]:
            diffs.append("sheet is missing fields e-Fatura has")
        if diffs:
            out["differences"].append({"row": r["row"], "efatura": d.to_dict(), "issues": diffs})
    # Only a document identity ties a cancellation to a booked invoice. A payment
    # on the same day for the same amount could be an unrelated active invoice.
    remaining = [r for r in records if r["row"] not in matched]
    for i, r in _efatura_pairs(cancelled, remaining, identity_only=True).items():
        matched.add(r["row"])
        out["differences"].append({"row": r["row"], "efatura": cancelled[i].to_dict(),
                                   "issues": ["e-Fatura marks the booked document as cancelled"]})
    for r in records:
        if r["row"] not in matched and _n(r["supplier_vat"]).startswith("PT") and r["document"] != "No invoice":
            out["pt_rows_not_in_efatura"].append(f"row {r['row']} {r['date']} {r['supplier']} {r['amount']}")
    return out
