"""Google Cloud EMEA invoices."""

from __future__ import annotations

from ...model import Document
from ._common import date, find, money

NAME = "google_cloud"


def matches(text: str) -> bool:
    return "Google Cloud EMEA Limited" in text and "Total in EUR" in text


def parse(text: str, file: str = "") -> Document:
    vat = money(find(r"VAT \(\d+%\)\s+(\S+)", text) or "0")
    return Document(
        layer=f"parser:{NAME}",
        file=file,
        doc_type="invoice",
        date=date(find(r"Invoice\s+date\s+([A-Z][a-z]{2} \d{1,2}, \d{4})", text)),
        supplier="Google Cloud EMEA Limited",
        supplier_vat=find(r"VAT number:\s*(IE\w+)", text),
        country="IE",
        invoice_no=find(r"Invoice number:\s*(\d+)", text),
        currency="EUR",
        amount=money(find(r"^\s*Total in EUR\s+(\S+)\s*$", text)),
        vat_included=vat,
        buyer_nif=find(r"VAT number:\s*PT\s?(\d{9})", text),
        markers=["foreign_vat_charged"] if vat else [],
        extra={"vat_rate": find(r"VAT \((\d+)%\)", text)},
    )
