"""What is in the inbox, and a deterministic plan for filing and booking it."""

from __future__ import annotations

import datetime as dt
import os

from .config import Config
from .documents import efatura, text
from .extract import expense_row, proposal, read_document
from .income import propose as propose_income
from .ledger import Ledger, sha256
from .model import Document

DOC_EXT = (".pdf", ".png", ".jpg", ".jpeg", ".webp")


def scan(cfg: Config, ledger: Ledger) -> list[dict]:
    """Invoice-like files in the inbox, newest first: kind, whether they read like an invoice, ledger status, and
    whether a file is an exact copy of another one in the inbox."""
    inbox = cfg.paths(dt.date.today().year)["inbox"]
    if not os.path.isdir(inbox):
        raise FileNotFoundError(f"inbox folder {inbox} does not exist; set paths.inbox in the config")
    files = [os.path.join(inbox, f) for f in os.listdir(inbox)
             if not f.startswith(".") and os.path.isfile(os.path.join(inbox, f)) and f.lower().endswith(DOC_EXT + (".csv",))]
    files.sort(key=os.path.getmtime, reverse=True)
    seen: dict[str, str] = {}
    out = []
    for path in files:
        digest = sha256(path)
        low = path.lower()
        looks = None
        if low.endswith(".csv"):
            kind = "efatura_export" if efatura.is_export(path) else "other"
        else:
            kind = "document"
            if low.endswith(".pdf"):
                try:
                    looks = text.looks_like_invoice(text.pdf_text(path, pages=2))
                except Exception:
                    looks = None
                if looks is False:
                    kind = "not_an_invoice"
        known = ledger.get(digest)
        out.append({"path": path, "kind": kind, "looks_like_invoice": looks,
                    "status": known["status"] if known else "new",
                    "filed_as": known["path"] if known and known["status"] == "filed" else "",
                    "copy_of": seen.get(digest, ""),
                    "modified": dt.datetime.fromtimestamp(os.path.getmtime(path)).isoformat(timespec="minutes")})
        seen.setdefault(digest, path)
    return out


def _same_sale(invoice: Document, at_doc: Document) -> bool:
    """Your invoice and an AT document plausibly belong to the same sale."""
    if not (invoice.date and at_doc.date) or not 0 <= (at_doc.date - invoice.date).days <= 92:
        return False
    total, vat = at_doc.amount or 0.0, at_doc.vat_included or 0.0
    if invoice.currency in ("EUR", ""):
        return abs((invoice.amount or 0) - total) < 0.01
    return total - vat > 0 and 0.5 < (invoice.amount or 0) / (total - vat) < 2


def pair_sales(invoices: list[Document], at_docs: list[Document]) -> list[tuple[Document | None, Document | None]]:
    """Match each AT document with the latest earlier invoice of yours that fits it; leftovers stay alone."""
    pairs, used = [], set()
    for at in sorted(at_docs, key=lambda d: d.date or dt.date.min):
        fits = [i for i in invoices if id(i) not in used and _same_sale(i, at)]
        best = max(fits, key=lambda i: i.date) if fits else None
        if best:
            used.add(id(best))
        pairs.append((best, at))
    pairs += [(i, None) for i in invoices if id(i) not in used]
    return pairs


def _checks(doc: Document, prop: dict, row: dict) -> list[str]:
    out = []
    if not row["date"] or row["amount"] is None:
        out.append("no date or amount read: check the document")
    if isinstance(prop["fx_rate"], str):
        out.append(f"exchange rate {prop['fx_rate']}: give the rate")
    if not prop["supplier"]:
        out.append("no supplier name (QR codes carry only the NIF): add a supplier rule with a name, or give it")
    if not row["account"]:
        out.append("payment account unknown")
    if prop["nif_on_invoice"] == "No" and prop["vat_code"] == "PT":
        out.append("your NIF is not on the invoice, so its IVA is not deductible")
    return out


def plan(cfg: Config, ledger: Ledger) -> dict:
    """For everything in the inbox: the expense rows and sales to book (with file names), copies to drop, files that
    are not invoices, documents the assistant has to read itself, and e-Fatura exports. Nothing is written."""
    out = {"expenses": [], "sales": [], "needs_reading": [], "efatura_exports": [], "copies": [], "not_invoices": [],
           "errors": []}
    invoices, at_docs = [], []
    for item in scan(cfg, ledger):
        path = item["path"]
        if item["copy_of"] or item["filed_as"]:
            out["copies"].append({"path": path, "same_as": item["copy_of"] or item["filed_as"]})
            continue
        if item["kind"] == "efatura_export":
            out["efatura_exports"].append(path)
            continue
        if item["kind"] == "not_an_invoice":
            out["not_invoices"].append(path)
            continue
        if item["kind"] != "document":
            continue
        try:
            doc = read_document(path)
        except Exception as e:
            out["errors"].append({"path": path, "error": str(e)})
            continue
        if doc.layer == "text":
            out["needs_reading"].append({"path": path, "card_last4": doc.card_last4, "markers": doc.markers})
            continue
        if doc.doc_type == "sales_invoice" or (cfg.nif and doc.supplier_vat == "PT" + cfg.nif):
            (invoices if doc.doc_type == "sales_invoice" else at_docs).append(doc)
            continue
        filed = [r for r in ledger.by_key(doc.key) if r["status"] == "filed" and os.path.exists(r["path"])] \
            if doc.invoice_no else []
        if filed:                                   # the same invoice downloaded again (different file bytes)
            out["copies"].append({"path": path, "same_as": filed[0]["path"]})
            continue
        prop = proposal(doc, cfg)
        row = expense_row(doc, prop)
        out["expenses"].append({"path": path, "layer": doc.layer, "file_name": prop["file_name"], "row": row,
                                "checks": _checks(doc, prop, row)})
    for invoice, at in pair_sales(invoices, at_docs):
        sale = propose_income(cfg, invoice, at)
        out["sales"].append({"invoice": invoice.file if invoice else "", "at_document": at.file if at else "", **sale})
    return out
