import pytest

from invoices_pt.model import Document
from invoices_pt.vat import region, suggest_code


@pytest.mark.parametrize("doc, code", [
    (Document(layer="qr", country="PT", vat_included=12.34), "PT"),
    (Document(layer="qr", country="PT", vat_included=0), "NoVAT"),
    (Document(layer="efatura", country="PT", vat_included=1.00, extra={"sector": "Alojamento, restauração e similares"}),
     "PT-NONDED-MEAL"),
    (Document(layer="efatura", country="PT", vat_included=2.55, extra={"sector": "Aquisição de passes mensais"}),
     "PT-NONDED-TRAVEL"),
    (Document(layer="text", country="US", vat_included=0, markers=["reverse_charge"]), "NON-EU-RC"),
    (Document(layer="text", country="DE", vat_included=0, markers=["reverse_charge"]), "EU-RC"),
    (Document(layer="text", country="ES", vat_included=0, markers=["intra_eu_goods"]), "EU-RC-GOODS"),
    (Document(layer="text", country="US", vat_included=9.20, markers=["pt_vat_charged"]), "OSS-PT-VAT-NONDED"),
    (Document(layer="text", country="IE", vat_included=9.56), "FOREIGN-VAT-NONDED"),
])
def test_suggest_code(doc, code):
    assert suggest_code(doc) == code


def test_region():
    assert [region(c) for c in ("PT", "de", "US", "")] == ["PT", "EU", "OutEU", ""]
