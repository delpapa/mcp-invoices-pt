"""Sales: pair your own invoice with the AT document (recibo verde, fatura or fatura-recibo) and propose the row."""

from __future__ import annotations

import os
import re

from . import bookmath, vat
from .config import Config
from .model import Document, signed_amount


def _f(x) -> float:
    try:
        return float(x or 0)
    except (TypeError, ValueError):
        return 0.0


def _tax_id(value) -> str:
    identifier = re.sub(r"[^A-Z0-9]", "", str(value or "").upper())
    return identifier[2:] if re.fullmatch(r"PT\d{9}", identifier) else identifier


def client_conflict(cfg: Config | None, invoice: Document, at_doc: Document) -> str:
    """Describe contradictory client evidence before combining two sales documents."""
    own_rule = cfg.client_rule(invoice.extra.get("client", ""), invoice.buyer_nif) if cfg else {}
    at_id = _tax_id(at_doc.buyer_nif)
    if at_id in ("", "000000000", "999999990"):
        return ""
    at_rule = cfg.client_rule(at_doc.buyer_nif) if cfg else {}
    expected = invoice.buyer_nif or own_rule.get("tax_id")
    if _tax_id(expected) not in ("", "000000000", "999999990", at_id):
        return f"the invoice client tax ID is {expected} and the AT document gives {at_doc.buyer_nif}"
    if own_rule and at_rule and own_rule != at_rule:
        return "the invoice and AT document match different client rules"
    return ""


def vat_case(vat_eur: float, not_subject: float, country: str, *,
             extra: dict | None = None, net_eur: float | None = None) -> str:
    """Sales code: IVA charged -> PT; no IVA -> box 7 for EU business clients, box 8 outside the EU."""
    if vat_eur > 0:
        if not extra or extra.get("fiscal_space", "PT") != "PT":
            return ""
        # Use the printed bases, not a blended rate derived from totals.
        for band, case in (("normal", "PT / C3"), ("reduced", "PT / C1"), ("intermediate", "PT / C5")):
            if (net_eur and abs(_f(extra.get(f"base_{band}")) - net_eur) < 0.005
                    and abs(_f(extra.get(f"vat_{band}")) - vat_eur) < 0.005):
                return case
        return ""
    if not_subject > 0 or country:
        return {"EU": "EU / C7", "OutEU": "NON-EU / C8"}.get(vat.region(country), "")
    return ""


def propose(cfg: Config, invoice: Document | None, at_doc: Document | None) -> dict:
    """The income row for one sale, file names for both documents, and checks that the two belong together."""
    if not invoice and not at_doc:
        return {"error": "give the invoice, the AT document, or both"}
    if any(d.cancelled for d in (invoice, at_doc) if d):
        return {"error": "Cancelled document: review the sale before booking"}
    checks = []
    if at_doc and cfg.nif and at_doc.supplier_vat != "PT" + cfg.nif:
        checks.append(f"the AT document was issued by {at_doc.supplier_vat}, not by your NIF")
    if invoice and invoice.doc_type != "sales_invoice":
        checks.append("the invoice file does not look like one of your sales invoices")

    extra = at_doc.extra if at_doc else {}
    client_text = (invoice.extra.get("client", "") if invoice else "")
    invoice_tax_id = invoice.buyer_nif if invoice else ""
    rule = cfg.client_rule(client_text, invoice_tax_id, at_doc.buyer_nif if at_doc else "")
    total = at_doc.amount if at_doc else None
    vat_eur = _f(at_doc.vat_included) if at_doc else 0.0
    net_eur = round(total - vat_eur, 2) if total is not None and at_doc.vat_included is not None else None
    withheld = signed_amount(_f(extra.get("withholding")), at_doc.doc_type) if at_doc else 0.0
    country = rule.get("country") or extra.get("buyer_country", "")
    amount = invoice.amount if invoice else total
    currency = invoice.currency if invoice else "EUR"
    fx = 1.0 if currency == "EUR" else ""
    if amount is None:
        checks.append("no amount read from the document; check the total before booking")
    if not currency:
        checks.append("no invoice currency read; check the currency before booking")
    elif currency != "EUR" and total and amount is not None:
        fx = round(amount / total, 4)
        if not 0.5 < fx < 2:
            checks.append(f"implied rate {fx} {currency}/EUR looks wrong; are these the same sale?")
    elif currency == "EUR" and total is not None and invoice and amount is not None and bookmath.r2(amount) != bookmath.r2(total):
        checks.append(f"invoice total {amount} differs from the AT document total {total}")
    if invoice and at_doc and at_doc.date and invoice.date and at_doc.date < invoice.date:
        checks.append("the AT document is dated before the invoice")

    invoice_date = invoice.date if invoice else at_doc.date
    if not invoice_date:
        checks.append("no invoice date read; give the issue date before booking")
    if at_doc and not at_doc.date and invoice:
        checks.append("no date read from the AT document; check its issue date")
    receipt = at_doc if at_doc and at_doc.doc_type in ("receipt", "invoice_receipt") else None
    invoice_no = invoice.invoice_no if invoice else (at_doc.invoice_no if at_doc and not receipt else "")
    name_no = invoice_no or (at_doc.invoice_no if at_doc else "")    # no invoice of your own: the AT number
    names = {}
    if invoice_date and invoice and invoice.file:
        names["invoice"] = cfg.income_name("invoice", invoice_date, name_no, os.path.splitext(invoice.file)[1] or ".pdf")
    if invoice_date and at_doc and at_doc.file:
        ext = os.path.splitext(at_doc.file)[1] or ".pdf"
        if receipt:
            names["recibo"] = cfg.income_name("recibo", invoice_date, name_no, ext)
        else:
            if at_doc.doc_type in ("invoice", "simplified_invoice"):
                at_name = cfg.income_name("invoice", at_doc.date or invoice_date, at_doc.invoice_no, ext)
            else:
                at_name = os.path.basename(at_doc.file)
            if "invoice" in names:
                names["at_document"] = "AT_" + at_name if at_name == names["invoice"] else at_name
            else:
                names["invoice"] = at_name
    if at_doc and at_doc.doc_type in ("invoice", "simplified_invoice"):
        checks.append("this AT invoice has no receipt; enter the payment on this row when the receipt is issued")
    if receipt and receipt.doc_type == "receipt" and not invoice:
        checks.append("match this receipt to its invoice before booking; if the sale is already in the books, "
                      "update its receipt details on the existing row")
    case = vat_case(vat_eur, _f(extra.get("not_subject")), country, extra=extra, net_eur=net_eur)
    client_case = rule.get("vat_case")
    if vat_eur > 0:
        if not case:
            checks.append("the AT amounts do not identify a single mainland IVA rate; review the rate breakdown before booking")
        elif client_case and client_case != case:
            checks.append(f"the AT document shows {case}; check the client rule specifying {client_case}")
    else:
        case = client_case or case
    row = {
        "invoice_date": invoice_date.isoformat() if invoice_date else "",
        "client": rule.get("name") or client_text,
        "country": country,
        "client_tax_id": rule.get("tax_id") or (at_doc.buyer_nif if at_doc else "") or invoice_tax_id,
        "invoice_no": invoice_no,
        "recibo_no": receipt.invoice_no if receipt else "",
        "recibo_date": receipt.date.isoformat() if receipt and receipt.date else "",
        "currency": currency,
        "amount": amount if amount is not None else "",
        "fx": fx,
        "net_eur": net_eur if net_eur is not None else "",
        "vat_rate": round(vat_eur / net_eur * 100) if net_eur else 0,
        "vat_eur": vat_eur,
        "withheld": withheld,
        "vat_case": case,
        "invoice_file": names.get("invoice", ""),
        # The second attachment column also holds the Portal invoice when both files exist.
        "recibo_file": names.get("recibo") or names.get("at_document", ""),
        "account": rule.get("account", ""),
    }
    if credit_checks := vat.credit_note_checks(at_doc):
        row["vat_case"] = ""
        checks.extend(credit_checks)
    if not row["client"]:
        checks.append("no client name: add a client rule in the config, or give the name")
    conflict = client_conflict(cfg, invoice, at_doc) if invoice and at_doc else ""
    if conflict:
        checks.append(conflict)
    elif at_doc and at_doc.buyer_nif and rule.get("tax_id") and _tax_id(rule["tax_id"]) != _tax_id(at_doc.buyer_nif):
        checks.append(f"the AT document gives the client tax ID as {at_doc.buyer_nif}; the config says {rule['tax_id']}")
    return {"row": row, "file_names": names, "checks": checks, "client_rule": rule.get("match", "")}
