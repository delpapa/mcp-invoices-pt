"""Portuguese IVA rules for a freelancer in the normal regime (quarterly Declaração Periódica).

Box numbers follow the model approved by Portaria 221/2017 as amended in 2023. Portaria 298/2026 changes
the return for periods starting on or after 1 July 2027.
"""

from __future__ import annotations

from .model import Document

EU = {"AT", "BE", "BG", "HR", "CY", "CZ", "DK", "EE", "FI", "FR", "DE", "GR", "HU", "IE", "IT", "LV", "LT",
      "LU", "MT", "NL", "PL", "RO", "SK", "SI", "ES", "SE"}
NORMAL_RATE = 0.23
REVERSE_CHARGE_BOXES = {"NON-EU-RC": (3, 4), "EU-RC-GOODS": (12, 13), "EU-RC": (16, 17)}

# Purchase codes and the boxes they fill
CODES = {
    "PT": "Portuguese IVA, deductible: box 24",
    "PT-ASSET": "Portuguese IVA on a fixed asset, deductible: box 20",
    "PT-NONDED-MEAL": "meals: IVA not deductible (art. 21 CIVA)",
    "PT-NONDED-TRAVEL": "transport of people: IVA not deductible (art. 21 CIVA)",
    "NoVAT": "exempt operation, no IVA (e.g. rent)",
    "NONE": "no IVA and nothing to self-charge (e.g. bank fees, no invoice)",
    "EU-RC": "services from an EU supplier, reverse charge: boxes 16 + 17, deducted in 24",
    "EU-RC-GOODS": "goods from an EU supplier, reverse charge: boxes 12 + 13, deducted in 24",
    "NON-EU-RC": "services from outside the EU, reverse charge: boxes 3 + 4 and 98, deducted in 24",
    "OSS-PT-VAT-NONDED": "a foreign supplier charged Portuguese IVA: not deductible",
    "FOREIGN-VAT-NONDED": "another country's VAT was charged: not deductible in Portugal",
}

# e-Fatura sectors whose IVA a freelancer cannot deduct
NONDED_SECTORS = {"Alojamento, restauração": "PT-NONDED-MEAL", "Aquisição de passes": "PT-NONDED-TRAVEL"}

# Sales
SALES_CODES = {
    "PT / C1": "Portuguese client, 6%: boxes 1 + 2",
    "PT / C5": "Portuguese client, 13%: boxes 5 + 6",
    "PT / C3": "Portuguese client, 23%: boxes 3 + 4",
    "EU / C7": "EU business client, no IVA: box 7 and the Declaração Recapitulativa",
    "NON-EU / C8": "non-EU client, no IVA: box 8",
}

# Each sales code contributes its net amount and, where applicable, its IVA to these fields.
SALES_BOXES = {"PT / C1": (1, 2), "PT / C3": (3, 4), "PT / C5": (5, 6),
               "EU / C7": (7, None), "NON-EU / C8": (8, None)}

# Contributions from the fields supported by these books. In the official form, 12
# contributes via subtotal 10 and 13 via subtotal 11; neither is counted twice.
RESULT_SUMS = {90: (1, 3, 5, 7, 8, 12, 16), 91: (20, 24, 61), 92: (2, 4, 6, 13, 17)}


def region(country: str) -> str:
    country = (country or "").upper()
    return "PT" if country == "PT" else "EU" if country in EU else "OutEU" if country else ""


def credit_note_checks(doc: Document | None) -> list[str]:
    if doc and doc.doc_type == "credit_note" and doc.vat_included and doc.country == "PT":
        return ["review the VAT adjustment for this credit note before booking it"]
    return []


def suggest_code(doc: Document) -> str:
    """Best guess from the document alone; personal supplier rules in the config override it."""
    if doc.country == "PT" or doc.layer in ("qr", "efatura"):
        sector = doc.extra.get("sector", "")
        for prefix, code in NONDED_SECTORS.items():
            if sector.startswith(prefix):
                return code
        return "PT" if (doc.vat_included or 0) > 0 else "NoVAT"
    marks = set(doc.markers)
    if "intra_eu_goods" in marks:
        return "EU-RC-GOODS"
    if "pt_vat_charged" in marks:
        return "OSS-PT-VAT-NONDED"
    if "foreign_vat_charged" in marks or (doc.vat_included or 0) > 0:
        return "FOREIGN-VAT-NONDED"
    if "exempt" in marks:
        return "NONE"
    return "EU-RC" if region(doc.country) == "EU" else "NON-EU-RC"
