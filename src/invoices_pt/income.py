"""Sales: pair your own invoice with the AT document (recibo verde, fatura or fatura-recibo) and propose the row."""

from __future__ import annotations

import os

from . import vat
from .config import Config
from .model import Document


def _f(x) -> float:
    try:
        return float(x or 0)
    except (TypeError, ValueError):
        return 0.0


def vat_case(vat_eur: float, not_subject: float, country: str) -> str:
    """Sales code: IVA charged -> PT; no IVA -> box 7 for EU business clients, box 8 outside the EU."""
    if vat_eur > 0:
        return "PT / C3"
    if not_subject > 0 or country:
        return {"EU": "EU / C7", "OutEU": "NON-EU / C8"}.get(vat.region(country), "")
    return ""


def propose(cfg: Config, invoice: Document | None, at_doc: Document | None) -> dict:
    """The income row for one sale, file names for both documents, and checks that the two belong together."""
    if not invoice and not at_doc:
        return {"error": "give the invoice, the AT document, or both"}
    checks = []
    if at_doc and cfg.nif and at_doc.supplier_vat != "PT" + cfg.nif:
        checks.append(f"the AT document was issued by {at_doc.supplier_vat}, not by your NIF")
    if invoice and invoice.doc_type != "sales_invoice":
        checks.append("the invoice file does not look like one of your sales invoices")

    extra = at_doc.extra if at_doc else {}
    client_text = (invoice.extra.get("client", "") if invoice else "")
    rule = cfg.client_rule(client_text, at_doc.buyer_nif if at_doc else "")
    total = _f(at_doc.amount) if at_doc else 0.0
    vat_eur = _f(at_doc.vat_included) if at_doc else 0.0
    net_eur = round(total - vat_eur, 2) if at_doc else None
    withheld = _f(extra.get("withholding"))
    country = rule.get("country") or extra.get("buyer_country", "")
    amount = invoice.amount if invoice and invoice.amount is not None else total
    currency = (invoice.currency if invoice else "") or "EUR"
    fx = 1.0
    if currency != "EUR" and net_eur:
        fx = round(amount / net_eur, 4)
        if not 0.5 < fx < 2:
            checks.append(f"implied rate {fx} {currency}/EUR looks wrong; are these the same sale?")
    elif currency == "EUR" and net_eur is not None and invoice and abs(amount - total) > 0.005:
        checks.append(f"invoice total {amount} differs from the AT document total {total}")
    if invoice and at_doc and at_doc.date and invoice.date and at_doc.date < invoice.date:
        checks.append("the AT document is dated before the invoice")

    invoice_date = (invoice.date if invoice else None) or (at_doc.date if at_doc else None)
    invoice_no = invoice.invoice_no if invoice else ""
    name_no = invoice_no or (at_doc.invoice_no if at_doc else "")    # no invoice of your own: the AT number
    names = {}
    if invoice and invoice.file:
        names["invoice"] = cfg.income_name("invoice", invoice_date, name_no, os.path.splitext(invoice.file)[1] or ".pdf")
    if at_doc and at_doc.file:
        names["recibo"] = cfg.income_name("recibo", invoice_date, name_no, os.path.splitext(at_doc.file)[1] or ".pdf")
    row = {
        "invoice_date": invoice_date.isoformat() if invoice_date else "",
        "client": rule.get("name") or client_text,
        "country": country,
        "client_tax_id": rule.get("tax_id") or (at_doc.buyer_nif if at_doc else ""),
        "invoice_no": invoice_no,
        "recibo_no": at_doc.invoice_no if at_doc else "",
        "recibo_date": at_doc.date.isoformat() if at_doc and at_doc.date else "",
        "currency": currency,
        "amount": amount,
        "fx": fx,
        "net_eur": net_eur if net_eur is not None else "",
        "vat_rate": round(vat_eur / net_eur * 100) if net_eur else 0,
        "vat_eur": vat_eur,
        "withheld": withheld,
        "vat_case": rule.get("vat_case") or vat_case(vat_eur, _f(extra.get("not_subject")), country),
        "invoice_file": names.get("invoice", ""),
        "recibo_file": names.get("recibo", ""),
        "account": rule.get("account", ""),
    }
    if not row["client"]:
        checks.append("no client name: add a client rule in the config, or give the name")
    if at_doc and at_doc.buyer_nif and rule.get("tax_id") and rule["tax_id"] != at_doc.buyer_nif:
        checks.append(f"the AT document gives the client tax ID as {at_doc.buyer_nif}; the config says {rule['tax_id']}")
    return {"row": row, "file_names": names, "checks": checks, "client_rule": rule.get("match", "")}
