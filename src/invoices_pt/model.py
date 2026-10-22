"""The one record every reader returns, whatever the source document."""

from __future__ import annotations

import datetime as dt
from dataclasses import asdict, dataclass, field

# Facts read from a document that drive the VAT coding (see vat.suggest_code).
MARKERS = {
    "reverse_charge": "the document says the buyer accounts for the VAT",
    "intra_eu_goods": "exempt intra-EU supply of goods (art. 138 VAT Directive)",
    "pt_vat_charged": "a foreign supplier charged Portuguese VAT",
    "foreign_vat_charged": "a foreign supplier charged another country's VAT",
    "exempt": "VAT-exempt operation",
}


@dataclass
class Document:
    layer: str                      # how it was read: "qr", "efatura", "parser:<name>" or "text"
    file: str = ""
    doc_type: str = ""              # invoice, simplified_invoice, invoice_receipt, receipt, credit_note
    date: dt.date | None = None
    supplier: str = ""
    supplier_vat: str = ""          # with country prefix, e.g. PT500000000
    country: str = ""               # supplier country, ISO 3166-1 alpha-2
    invoice_no: str = ""
    atcud: str = ""
    currency: str = "EUR"
    amount: float | None = None     # total paid, in `currency`
    vat_included: float | None = None
    buyer_nif: str = ""
    card_last4: str = ""
    markers: list[str] = field(default_factory=list)
    extra: dict = field(default_factory=dict)
    text: str = ""                  # raw text, only kept when no structured layer matched

    @property
    def key(self) -> str:
        """Identity used to spot the same invoice arriving twice."""
        who = (self.supplier_vat or self.supplier).replace(" ", "").upper()
        return f"{who}|{self.invoice_no.replace(' ', '').upper()}"

    def to_dict(self) -> dict:
        d = asdict(self)
        d["date"] = self.date.isoformat() if self.date else None
        d["key"] = self.key
        if not self.text:
            d.pop("text")
        return d
