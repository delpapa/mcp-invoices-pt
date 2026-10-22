"""Plain-text layer: the PDF text plus the facts any layout reveals (card ending, VAT wording)."""

from __future__ import annotations

import re
import subprocess

CARD = re.compile(r"(?:mastercard|visa|amex|card|cart[ãa]o)[^0-9\n]{0,25}(\d{4})\b|\*{3}[ *]+(\d{4})\b", re.I)
MARKER_PATTERNS = {
    "reverse_charge": re.compile(r"reverse.?charge|autoliquida|tax liability of the recipient|"
                                 r"steuerschuldnerschaft|inversi[oó]n del sujeto pasivo", re.I),
    "intra_eu_goods": re.compile(r"art[ií]culo\s*138|article\s*138|art\.\s*138", re.I),
    "pt_vat_charged": re.compile(r"VAT\s*-\s*Portugal|IVA\s*-\s*Portugal", re.I),
}


DASHES = re.compile(r"[‐-―−]")
# Some PDF fonts draw hyphens with private-use glyphs (e.g. U+E022 in Stripe invoice numbers)
PRIVATE_GLYPH = re.compile(r"(?<=[A-Za-z0-9])[-](?=[A-Za-z0-9])")


def clean(text: str) -> str:
    return PRIVATE_GLYPH.sub("-", DASHES.sub("-", text)).replace("­", "")


def pdf_text(path: str, pages: int | None = None) -> str:
    cmd = ["pdftotext", "-layout", *(["-l", str(pages)] if pages else []), path, "-"]
    return clean(subprocess.run(cmd, capture_output=True, text=True, check=True).stdout)


INVOICE_WORDS = re.compile(
    r"\b(invoices?|receipts?|fatura|factura|facture|rechnung|quittung|recibo|nota de cr[ée]dito|credit note|"
    r"subtotal|total|vat|iva|nif|nipc|atcud|tax|amount (?:due|paid)|transfer fees?|order number|payment)\b", re.I)


def looks_like_invoice(text: str) -> bool | None:
    """True if the text reads like an invoice or receipt (at least two distinct invoice words), False if not,
    None if there is no text (a scan or photo: it may still carry an AT QR code)."""
    if not text.strip():
        return None
    return len({m.group(1).lower() for m in INVOICE_WORDS.finditer(text)}) >= 2


def card_last4(text: str) -> str:
    m = CARD.search(text)
    return (m.group(1) or m.group(2)) if m else ""


def markers(text: str) -> list[str]:
    return [name for name, rx in MARKER_PATTERNS.items() if rx.search(text)]
