import datetime as dt

from invoices_pt.documents import text
from invoices_pt.extract import file_name, proposal, read_document
from invoices_pt.ledger import Ledger, sha256
from invoices_pt.model import Document


def test_qr_document_end_to_end(qr_png, cfg):
    doc = read_document(qr_png())
    p = proposal(doc, cfg)
    assert doc.layer == "qr"
    assert p["vat_code"] == "PT"
    assert p["nif_on_invoice"] == "Yes"
    assert p["document"] == "PDF ✓ QR-verified"
    assert p["file_name"] == "500000000_01_FT-A1-42.png"      # no rule: named after the NIF


def test_supplier_rule_and_card(cfg):
    doc = Document(layer="text", supplier="ACME Corp", country="US", date=dt.date(2026, 2, 1),
                   invoice_no="INV 7/2", markers=["reverse_charge"])
    p = proposal(doc, cfg)
    assert (p["account"], p["business_pct"], p["vat_code"]) == ("card-b", 0.3, "NON-EU-RC")
    assert file_name(doc, cfg.supplier_rule(doc)) == "acme_02_INV-7-2.pdf"
    doc.card_last4 = "4242"
    assert cfg.account(doc) == "card-a"


def test_config_rule_overrides_code(cfg):
    doc = Document(layer="text", supplier="Wise Europe SA", country="BE", vat_included=0)
    assert proposal(doc, cfg)["vat_code"] == "NONE"


def test_text_facts():
    sample = "Payment method Mastercard - 4242 May 3\nTax to be paid on reverse charge basis\nVAT - Portugal (23%)"
    assert text.card_last4(sample) == "4242"
    assert text.markers(sample) == ["reverse_charge", "pt_vat_charged"]
    assert text.card_last4("**** **** **** 1234") == "1234"


def test_ledger(tmp_path):
    f = tmp_path / "a.pdf"
    f.write_bytes(b"x")
    led = Ledger(str(tmp_path / "l.sqlite"))
    led.record(sha256(str(f)), str(f), "PT1|FT1", "qr", "extracted")
    assert led.get(sha256(str(f)))["status"] == "extracted"
    assert len(led.by_key("PT1|FT1")) == 1
