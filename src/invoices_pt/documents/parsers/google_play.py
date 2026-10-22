"""Google Play order receipts (the e-mail saved as PDF)."""

from __future__ import annotations

from ...model import Document
from ._common import date, find, money

NAME = "google_play"


def matches(text: str) -> bool:
    return "Google Play" in text and "Order number: GPA." in text


def parse(text: str, file: str = "") -> Document:
    vat = money(find(r"Includes VAT of\s+([\d.,]+)", text) or "0")
    return Document(
        layer=f"parser:{NAME}",
        file=file,
        doc_type="receipt",
        date=date(find(r"Order date:\s+([A-Z][a-z]{2} \d{1,2}, \d{4})", text)),
        supplier="Google Commerce Limited",
        country="IE",
        invoice_no=find(r"Order number:\s+(\S+)", text),
        currency="EUR" if "€" in find(r"Total:\s+(.+)", text) else "",
        amount=money(find(r"Total:\s+([\d.,]+)", text)),
        vat_included=vat,
        markers=["foreign_vat_charged"] if vat else [],
        extra={"item": find(r"\(by ([^)]+)\)", text)},
    )
