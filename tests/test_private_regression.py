"""Regression against your own verified sheet: every document in the year folder must read back exactly as booked.

Opt-in, because it needs your private config, documents and sheet:
    INVOICES_PT_PRIVATE=1 INVOICES_PT_YEAR=2026 pytest tests/test_private_regression.py -q
"""

import datetime as dt
import os
import re

import pytest

pytestmark = pytest.mark.skipif(os.environ.get("INVOICES_PT_PRIVATE") != "1", reason="needs private data")


def _num(s):
    s = str(s or "").replace(",", "").strip()
    return float(s) if re.fullmatch(r"-?\d+(\.\d+)?", s) else None


def _norm(s) -> str:
    return re.sub(r"\s+", "", str(s or "")).upper()


def test_documents_match_sheet():
    from invoices_pt.books import open_books
    from invoices_pt.config import Config
    from invoices_pt.extract import proposal, read_document

    year = int(os.environ.get("INVOICES_PT_YEAR", dt.date.today().year))
    cfg = Config.load()
    folder = cfg.expenses_dir(year)
    problems, checked, layers = [], 0, {}
    for r in open_books(cfg, year)[0].records():
        name = r["file"]
        path = os.path.join(folder, name)
        if not name or not os.path.exists(path):
            continue
        try:
            doc = read_document(path)
            prop = proposal(doc, cfg)
        except Exception as e:
            problems.append(f"{name}: crashed: {e!r}")
            continue
        layers[doc.layer] = layers.get(doc.layer, 0) + 1
        checked += 1
        expect = {
            "date": dt.datetime.strptime(r["date"], "%d.%m.%Y").date(),
            "amount": _num(r["amount"]), "currency": r["currency"],
            "invoice_no": _norm(r["invoice_no"]), "vat_included": _num(r["vat_included"]),
            "supplier_vat": _norm(r["supplier_vat"]), "code": r["code"],
            "account": r["account"], "fx": _num(r["fx"]),
        }
        got = {
            "date": doc.date, "amount": doc.amount, "currency": doc.currency, "invoice_no": _norm(doc.invoice_no),
            "vat_included": doc.vat_included, "supplier_vat": _norm(doc.supplier_vat), "code": prop["vat_code"],
            "account": prop["account"], "fx": prop["fx_rate"] if isinstance(prop["fx_rate"], float) else 1.0,
        }
        for k, want in expect.items():
            have = got[k]
            if k == "supplier_vat" and (not want or not have):
                continue
            if k == "account" and not have:
                continue        # nothing on the document says which account paid
            if k == "vat_included" and want is None:
                continue
            if isinstance(want, float) and isinstance(have, float):
                ok = abs(want - have) < (0.00015 if k == "fx" else 0.005)
            else:
                ok = want == have
            if not ok:
                problems.append(f"{name}: {k} sheet={want!r} read={have!r} ({doc.layer})")
    print(f"\nchecked {checked} documents by layer: {layers}")
    assert not problems, "\n" + "\n".join(problems)


def test_income_matches_sheet():
    """Each booked sale: reading its invoice and AT document must propose exactly the row in the income tab.
    Own invoice numbers are only reported, not failed on."""
    from invoices_pt.books import open_books
    from invoices_pt.config import Config
    from invoices_pt.extract import read_document
    from invoices_pt.income import propose

    year = int(os.environ.get("INVOICES_PT_YEAR", dt.date.today().year))
    cfg = Config.load()
    folder = cfg.income_dir(year)
    problems, notes, checked = [], [], 0
    for r in open_books(cfg, year)[1].records():
        if not r["invoice_file"] or not r["recibo_file"]:
            continue
        out = propose(cfg, read_document(os.path.join(folder, r["invoice_file"])),
                      read_document(os.path.join(folder, r["recibo_file"])))
        got = out["row"]
        checked += 1
        for k in ("invoice_date", "recibo_date"):
            if dt.date.fromisoformat(got[k]) != dt.datetime.strptime(r[k], "%d.%m.%Y").date():
                problems.append(f"row {r['row']}: {k} sheet={r[k]} read={got[k]}")
        for k in ("amount", "fx", "net_eur", "vat_eur", "withheld"):
            if abs((_num(r[k]) or 0) - float(got[k] or 0)) > (0.00015 if k == "fx" else 0.005):
                problems.append(f"row {r['row']}: {k} sheet={r[k]} read={got[k]}")
        for k in ("client", "country", "client_tax_id", "recibo_no", "currency", "vat_case", "invoice_file",
                  "recibo_file", "account"):
            if _norm(r[k]) != _norm(got[k]):
                problems.append(f"row {r['row']}: {k} sheet={r[k]!r} read={got[k]!r}")
        if _norm(r["invoice_no"]) != _norm(got["invoice_no"]):
            notes.append(f"row {r['row']}: invoice no. sheet={r['invoice_no']} printed={got['invoice_no']}")
    print(f"\nchecked {checked} sales", *notes, sep="\n  ")
    assert checked and not problems, "\n" + "\n".join(problems)
