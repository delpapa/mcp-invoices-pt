"""Amazon EU marketplace invoices issued by the seller (Spanish layout, Amazon.es)."""

from __future__ import annotations

from ...model import Document
from ._common import date, find, money

NAME = "amazon"


def matches(text: str) -> bool:
    return "amazon." in text.lower() and "Número de la factura" in text and "Vendido por" in text


def parse(text: str, file: str = "") -> Document:
    seller = find(r"Vendido por\s+(.+?)(?:\s{2,}|$)", text)
    vat_id = find(r"IVA\s+([A-Z]{2}[0-9A-Z]{7,})", text)
    store = find(r"www\.amazon\.(\w+)", text) or "es"
    return Document(
        layer=f"parser:{NAME}",
        file=file,
        doc_type="invoice",
        date=date(find(r"Fecha de la factura(?:/Fecha de la entrega)?\s+(\d{1,2} \w+ \d{4})", text)),
        supplier=f"{seller} (Amazon.{store})",
        supplier_vat=vat_id,
        country=vat_id[:2],
        invoice_no=find(r"Número de la factura\s+(\S+)", text),
        currency="EUR",
        amount=money(find(r"^\s*Total\s+([\d.,]+)\s*€", text)),
        vat_included=money(find(r"^\s*Total\s+[\d.,]+\s*€\s+([\d.,]+)\s*€", text) or "0"),
        buyer_nif=find(r"NIF sujeto de IVA\s+PT(\d{9})", text),
    )
