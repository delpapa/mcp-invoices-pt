"""Wise transfer confirmations: the expense is the transfer fee, at Wise's own exchange rate."""

from __future__ import annotations

import re

from ...model import Document
from ._common import date, find, money

NAME = "wise"


def matches(text: str) -> bool:
    return "Transfer confirmation" in text and "Wise Europe SA" in text


def parse(text: str, file: str = "") -> Document:
    fees = text.split("Transfer fees", 1)[-1]
    fee = re.search(r"Total\s+([\d,]+\.\d{2})\s+([A-Z]{3})", fees)
    rate = re.search(r"1 ([A-Z]{3}) = ([\d.]+) EUR", text)
    currency = fee.group(2) if fee else ""
    extra = {}
    if rate and rate.group(1) == currency:
        extra["fx_rate"] = round(1 / float(rate.group(2)), 4)   # units of currency per EUR, like the ECB
    return Document(
        layer=f"parser:{NAME}",
        file=file,
        doc_type="receipt",
        date=date(find(r"Transfer created.*\n\s*([A-Z][a-z]+ \d{1,2}, \d{4})", text)),
        supplier="Wise Europe SA",
        supplier_vat="BE" + find(r"registered number (\d{10})", text),
        country="BE",
        invoice_no=find(r"#(\d{6,})", text),
        currency=currency,
        amount=money(fee.group(1)) if fee else None,
        vat_included=0.0,
        markers=["exempt"],      # payment services are VAT-exempt
        extra=extra,
    )
