import datetime as dt

from invoices_pt.documents import qr


def test_parse_payload_rejects_other_qr_codes():
    assert qr.parse_payload("https://example.com") is None


def test_read_and_convert(qr_png):
    fields = qr.read_qr(qr_png())
    assert fields["supplier_nif"] == "500000000"
    doc = qr.to_document(fields, file="invoice.png")
    assert doc.layer == "qr"
    assert doc.doc_type == "invoice"
    assert doc.date == dt.date(2026, 1, 15)
    assert doc.supplier_vat == "PT500000000"
    assert doc.invoice_no == "FT A1/42"
    assert doc.atcud == "ABCD1234-42"
    assert (doc.amount, doc.vat_included) == (123.0, 23.0)
    assert doc.buyer_nif == "999999990"
    assert doc.extra["base_normal"] == "100.00"


def test_exempt_invoice_gets_marker(qr_png):
    payload = "A:500000001*B:999999990*D:FR*F:20260310*G:FR X/1*H:XYZ-1*I1:PT*I2:450.00*N:0.00*O:450.00"
    doc = qr.to_document(qr.read_qr(qr_png(payload)))
    assert doc.doc_type == "invoice_receipt"
    assert doc.markers == ["exempt"]
