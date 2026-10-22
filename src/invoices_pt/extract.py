"""Read any document through the layers (QR, supplier parser, plain text) and propose how to book it."""

from __future__ import annotations

import os
import re

from . import fx, vat
from .config import Config
from .documents import parsers, qr, text
from .model import Document

SHEET_LABELS = {"qr": "PDF ✓ QR-verified", "efatura": "e-Fatura only"}


def read_document(path: str) -> Document:
    fields = qr.read_qr(path)
    if fields:
        return qr.to_document(fields, file=path)
    raw = text.pdf_text(path) if path.lower().endswith(".pdf") else ""
    parser = parsers.find(raw)
    doc = parser.parse(raw, path) if parser else Document(layer="text", file=path, text=raw[:6000])
    doc.card_last4 = doc.card_last4 or text.card_last4(raw)
    doc.markers = sorted(set(doc.markers) | set(text.markers(raw)))
    return doc


def _slug(doc: Document, rule: dict) -> str:
    """File-name prefix: the rule's slug, else the first word of the supplier's name, else its NIF / VAT number."""
    if rule.get("slug"):
        return rule["slug"]
    words = re.findall(r"[a-z0-9]+", (rule.get("name") or doc.supplier or "").lower())
    if words:
        return words[0]
    vat_id = re.sub(r"\W", "", doc.supplier_vat or "")
    return re.sub(r"^PT", "", vat_id) or "unknown"


def file_name(doc: Document, rule: dict, ext: str = ".pdf") -> str:
    """<supplier>_<MM>_<document id><ext>"""
    month = f"{doc.date.month:02d}" if doc.date else "00"
    doc_id = re.sub(r"[^\w.-]+", "-", doc.invoice_no.strip()).strip("-") or "noid"
    return f"{_slug(doc, rule)}_{month}_{doc_id}{ext}"


def expense_row(doc: Document, prop: dict, expense: str = "") -> dict:
    """The expense row add_expense takes, filled from a document and its proposal (any field can be changed)."""
    fx_rate = prop["fx_rate"] if isinstance(prop["fx_rate"], float) else (1 if doc.currency == "EUR" else "")
    return {
        "date": doc.date.isoformat() if doc.date else "", "expense": expense or _slug(doc, {"slug": prop.get("slug")}),
        "supplier": prop["supplier"], "country": doc.country, "supplier_vat": doc.supplier_vat,
        "invoice_no": doc.invoice_no, "currency": doc.currency, "amount": doc.amount,
        "vat_included": doc.vat_included, "fx": fx_rate, "nif": prop["nif_on_invoice"], "code": prop["vat_code"],
        "business_pct": prop["business_pct"], "document": prop["document"], "file": prop["file_name"],
        "account": prop["account"],
    }


def proposal(doc: Document, cfg: Config) -> dict:
    """Everything needed to file and book the document, as a suggestion the caller can change."""
    rule = cfg.supplier_rule(doc)
    fx_rate = doc.extra.get("fx_rate")     # a rate printed on the document (e.g. Wise) wins over the ECB's
    if fx_rate is None and doc.date and doc.currency not in ("EUR", ""):
        try:
            fx_rate = fx.rate(doc.currency, doc.date, cfg.paths(doc.date.year)["cache"])
        except Exception as e:      # network or missing day; the caller can still pass a rate
            fx_rate = f"unavailable: {e}"
    on_invoice = bool(cfg.nif) and (doc.buyer_nif == cfg.nif or cfg.nif in doc.text or doc.layer == "efatura")
    label = rule.get("document") or SHEET_LABELS.get(doc.layer) or (
        "PDF receipt" if doc.doc_type == "receipt" else "PDF invoice")
    ext = os.path.splitext(doc.file)[1].lower() or ".pdf"
    sale = doc.doc_type == "sales_invoice"
    return {
        "supplier": rule.get("name") or doc.supplier,     # QR codes carry only the NIF; the config can name it
        "vat_code": "" if sale else rule.get("code") or vat.suggest_code(doc),
        "region": vat.region(doc.country),
        "fx_rate": fx_rate,
        "account": cfg.account(doc),
        "business_pct": rule.get("business_pct", 1),
        "nif_on_invoice": "Yes" if on_invoice else "No",
        "document": label,
        "file_name": file_name(doc, rule, ext) if doc.file else "",
        "slug": _slug(doc, rule),
        "supplier_rule": rule.get("match", ""),
    }
