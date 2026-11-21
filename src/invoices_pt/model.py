"""The one record every reader returns, whatever the source document."""

from __future__ import annotations

import datetime as dt
import json
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
    def _supplier_and_number(self) -> tuple[str, str]:
        who = (self.supplier_vat or self.supplier).replace(" ", "").upper()
        return who, self.invoice_no.replace(" ", "").upper()

    @property
    def legacy_key(self) -> str:
        """Key stored by ledgers created before document type was part of the identity."""
        return "|".join(self._supplier_and_number)

    @property
    def key(self) -> str:
        """A numbered document is identified by its issuer, document type and number."""
        who, number = self._supplier_and_number
        if not (who and self.doc_type and number):
            return ""
        return json.dumps([who, self.doc_type, number], ensure_ascii=False)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["date"] = self.date.isoformat() if self.date else None
        d["key"] = self.key
        if not self.text:
            d.pop("text")
        return d
