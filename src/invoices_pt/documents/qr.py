"""AT QR code (Portaria 195/2020). Every invoice from certified Portuguese software carries one."""

from __future__ import annotations

import datetime as dt
import os
import subprocess
import tempfile
from collections.abc import Iterator

import zxingcpp
from PIL import Image

from ..model import Document

# Field codes from the AT technical specification
FIELDS = {
    "A": "supplier_nif", "B": "buyer_nif", "C": "buyer_country", "D": "doc_type", "E": "status", "F": "date",
    "G": "doc_id", "H": "atcud", "I1": "fiscal_space", "I2": "base_exempt", "I3": "base_reduced",
    "I4": "vat_reduced", "I5": "base_intermediate", "I6": "vat_intermediate", "I7": "base_normal",
    "I8": "vat_normal", "L": "not_subject", "M": "stamp_duty", "N": "total_vat", "O": "total",
    "P": "withholding", "Q": "hash", "R": "certificate", "S": "other",
}
DOC_TYPES = {"FT": "invoice", "FS": "simplified_invoice", "FR": "invoice_receipt", "NC": "credit_note",
             "ND": "debit_note", "RG": "receipt", "RC": "receipt"}
IMAGE_EXT = (".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff")
KEEP = ("buyer_country", "not_subject", "withholding", "base_exempt", "base_reduced", "vat_reduced",
        "base_intermediate", "vat_intermediate", "base_normal", "vat_normal")


def parse_payload(text: str) -> dict | None:
    """Split an AT payload ("A:123*B:456*...") into named fields; None if it is not one."""
    kv = dict(part.split(":", 1) for part in text.split("*") if ":" in part)
    if "A" not in kv or "H" not in kv:
        return None
    return {FIELDS.get(k, k): v for k, v in kv.items()}


def _pages(path: str, dpi: int) -> Iterator[Image.Image]:
    if path.lower().endswith(IMAGE_EXT):
        with Image.open(path) as img:
            yield img
        return
    with tempfile.TemporaryDirectory() as d:
        subprocess.run(["pdftoppm", "-r", str(dpi), "-png", path, f"{d}/p"], check=True, capture_output=True)
        for name in sorted(os.listdir(d)):
            with Image.open(os.path.join(d, name)) as img:
                yield img


def read_qr(path: str, dpi: int = 250) -> dict | None:
    """Fields of the first AT QR code in a PDF or image, or None."""
    for img in _pages(path, dpi):
        for code in zxingcpp.read_barcodes(img):
            fields = parse_payload(code.text)
            if fields:
                return fields
    return None


def to_document(fields: dict, file: str = "") -> Document:
    def num(k: str) -> float:
        return float(fields.get(k) or 0)

    return Document(
        layer="qr",
        file=file,
        doc_type=DOC_TYPES.get(fields.get("doc_type", ""), fields.get("doc_type", "")),
        date=dt.datetime.strptime(fields["date"], "%Y%m%d").date(),
        supplier_vat="PT" + fields["supplier_nif"],
        country="PT",
        invoice_no=fields.get("doc_id", ""),
        atcud=fields.get("atcud", ""),
        amount=num("total"),
        vat_included=num("total_vat"),
        buyer_nif=fields.get("buyer_nif", ""),
        markers=["exempt"] if num("total_vat") == 0 and num("base_exempt") > 0 else [],
        extra={k: fields[k] for k in KEEP if k in fields},
    )
