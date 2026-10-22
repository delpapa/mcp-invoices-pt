"""GitHub invoices (INV...) and payment receipts."""

from __future__ import annotations

from ...model import Document
from ._common import date, find, money

NAME = "github"


def matches(text: str) -> bool:
    return "GitHub, Inc." in text and ("INVOICE TOTAL" in text or "We received payment for your GitHub" in text)


def parse(text: str, file: str = "") -> Document:
    common = dict(layer=f"parser:{NAME}", file=file, supplier="GitHub, Inc.", country="US")
    if "INVOICE TOTAL" in text:
        total = money(find(r"INVOICE TOTAL:\s+(\S+)", text))
        subtotal = money(find(r"SUBTOTAL:\s+(\S+)", text))   # the TAX: label is not always next to its amount
        return Document(
            **common,
            doc_type="invoice",
            date=date(find(r"Invoice Date\s+([A-Z][a-z]{2} \d{2}, \d{4})", text)),
            invoice_no=find(r"Invoice #\s+(\S+)", text),
            currency=find(r"Currency\s+([A-Z]{3})", text) or "USD",
            amount=total,
            vat_included=round(total - subtotal, 2),
        )
    return Document(
        **common,
        doc_type="receipt",
        date=date(find(r"^Date\s+(\d{4}-\d{2}-\d{2})", text)),
        invoice_no=find(r"Transaction ID\s+(\S+)", text),
        currency=find(r"^Total\s+\S+\s+([A-Z]{3})", text) or "USD",
        amount=money(find(r"^Total\s+(\S+)", text)),
        vat_included=money(find(r"^Tax\s+(\S+)", text) or "0"),
    )
