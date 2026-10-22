"""Stripe-hosted invoices and receipts (the layout many software subscriptions are billed with)."""

from __future__ import annotations

import re

from ...model import Document
from ._common import SYMBOLS, country, date, find, left_column, money

NAME = "stripe"
AMOUNT = r"([€$£])\s?([\d,]+\.\d{2})"


def matches(text: str) -> bool:
    return ("Invoice number" in text and "Bill to" in text and "Subtotal" in text
            and bool(re.search(r"Date (of issue|paid)", text)))


def _invoice_no(text: str) -> str:
    no = find(r"Invoice number\s+([A-Z0-9-]+)", text)
    # pdftotext sometimes drops the hyphen of Stripe numbers (XXXXXXXX-NNNN)
    return re.sub(r"^([A-Z0-9]{8})(\d{4})$", r"\1-\2", no)


def parse(text: str, file: str = "") -> Document:
    lines = text.splitlines()
    head = next(i for i, ln in enumerate(lines) if "Bill to" in ln)
    supplier = re.sub(r"\s+@\S+$", "", lines[head].split("Bill to")[0].strip())   # drop a trailing @handle
    supplier_country = ""
    for ln in lines[head + 1: head + 9]:
        if (c := country(left_column(ln))):
            supplier_country = c
            break
    total_m = re.search(rf"^\s*Total\s+{AMOUNT}\s*$", text, re.M)
    excl_m = re.search(rf"Total excluding tax\s+{AMOUNT}", text) or re.search(rf"Subtotal\s+{AMOUNT}", text)
    total = money(total_m.group(2)) if total_m else None
    excl = money(excl_m.group(2)) if excl_m else total
    currency = SYMBOLS.get(total_m.group(1), "") if total_m else ""
    buyer = find(r"\b[A-Z]{2} VAT ((?:[A-Z]{2})?\d{8,12})\b", text)
    return Document(
        layer=f"parser:{NAME}",
        file=file,
        doc_type="receipt" if text.lstrip().startswith("Receipt") else "invoice",
        date=date(find(r"Date (?:of issue|paid)\s+(.+?\d{4})", text)),
        supplier=supplier,
        supplier_vat=find(r"(?:EU OSS VAT|EU VAT:)\s*([A-Z]{2}[0-9A-Z]{6,})", text),
        country=supplier_country,
        invoice_no=_invoice_no(text),
        currency=currency,
        amount=total,
        vat_included=round(total - excl, 2) if total is not None and excl is not None else None,
        buyer_nif=re.sub(r"^[A-Z]{2}", "", buyer),
    )
