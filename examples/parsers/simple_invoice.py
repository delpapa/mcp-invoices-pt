"""Example of a private parser for your own sales invoices: a common "INVOICE / INVOICE NO. / DATE / TO / TOTAL DUE"
template with US-style dates (MM.DD.YY). Copy it into your `parsers_dir` and adapt the patterns to your template."""

from __future__ import annotations

import os
import re

from invoices_pt.model import Document
from invoices_pt.documents.parsers._common import SYMBOLS, date, find, money

NAME = "simple_invoice"


def matches(text: str) -> bool:
    return "INVOICE NO." in text and "TOTAL DUE" in text


def parse(text: str, file: str = "") -> Document:
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    issuer = lines[1] if len(lines) > 1 and lines[0] == "INVOICE" else ""
    raw_date = find(r"\bDATE\s+(\d{1,2}[./]\d{1,2}[./]\d{2,4})", text)
    day = date(raw_date, order="mdy")
    # a yyyymmdd in the file name settles ambiguous dates such as 04.05.26
    if (m := re.search(r"(20\d{2})(\d{2})(\d{2})", os.path.basename(file))):
        day = date(f"{m.group(1)}-{m.group(2)}-{m.group(3)}")
    total = re.search(r"TOTAL DUE\s+([€$£])\s?([\d,]+\.\d{2})", text)
    return Document(
        layer=f"parser:{NAME}",
        file=file,
        doc_type="sales_invoice",
        date=day,
        supplier=issuer,
        invoice_no=find(r"INVOICE NO\.\s+(\S+)", text),
        currency=SYMBOLS.get(total.group(1), "") if total else "",
        amount=money(total.group(2)) if total else None,
        vat_included=0.0 if re.search(r"not (?:collected|charged)|art\.?\s*6", text, re.I) else None,
        markers=["not_taxed_in_pt"] if re.search(r"art\.?\s*6\.?\s*º?,?\s*n\.?\s*º?\s*6", text) else [],
        extra={"client": find(r"^\s*TO\s+(.+)$", text), "issuer_nif": find(r"NIF:\s*(\d{9})", text)},
    )
