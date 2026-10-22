import datetime as dt

from invoices_pt.config import Config
from invoices_pt.documents import qr
from invoices_pt.income import propose
from invoices_pt.model import Document
from invoices_pt.report import missing_income

# A made-up recibo verde issued by the taxpayer (999999990) to a US client, not subject to PT IVA
RECIBO = "A:999999990*B:000000000*C:US*D:RG*E:N*F:20260210*G:RG A1/7*H:ABCD-7*I1:0*L:1000.00*N:0.00*O:1000.00"
PT_SALE = "A:999999990*B:500000000*C:PT*D:FR*E:N*F:20260305*G:FR A1/3*H:ABCD-3*I1:PT*I7:500.00*I8:115.00*N:115.00*O:615.00"


def invoice(day=dt.date(2026, 2, 4), amount=1250.0, currency="USD"):
    return Document(layer="parser:simple_invoice", doc_type="sales_invoice", date=day, invoice_no="JD001",
                    currency=currency, amount=amount, extra={"client": "Example Client Inc."}, file="/x/inv.pdf")


def at_doc(qr_png, payload=RECIBO):
    path = qr_png(payload)
    return qr.to_document(qr.read_qr(path), file=path)


def test_non_eu_sale(qr_png, cfg):
    out = propose(cfg, invoice(), at_doc(qr_png))
    row = out["row"]
    assert out["checks"] == []
    assert (row["invoice_date"], row["recibo_no"], row["recibo_date"]) == ("2026-02-04", "RG A1/7", "2026-02-10")
    assert (row["amount"], row["currency"], row["net_eur"], row["fx"]) == (1250.0, "USD", 1000.0, 1.25)
    assert (row["vat_case"], row["country"], row["vat_eur"], row["withheld"]) == ("NON-EU / C8", "US", 0.0, 0.0)
    assert out["file_names"] == {"invoice": "20260204_invoice_JD001.pdf", "recibo": "20260204_recibo_JD001.png"}


def test_client_rule(qr_png, cfg):
    cfg = Config({**cfg.data, "clients": [{"match": "Example Client", "name": "EXC", "tax_id": "12-3456789",
                                           "account": "bank-a"}],
                  "income_names": {"invoice": "{date:%Y%m%d} Invoice", "recibo": "{date:%Y%m%d} Recibo"}})
    out = propose(cfg, invoice(), at_doc(qr_png))
    assert (out["row"]["client"], out["row"]["client_tax_id"], out["row"]["account"]) == ("EXC", "12-3456789", "bank-a")
    assert out["file_names"]["invoice"] == "20260204 Invoice.pdf"
    assert any("tax ID" in c for c in out["checks"])


def test_checks_catch_mismatched_pairs(qr_png, cfg):
    out = propose(cfg, invoice(day=dt.date(2026, 3, 1), amount=5.0), at_doc(qr_png))
    assert any("before the invoice" in c for c in out["checks"])
    assert any("implied rate" in c for c in out["checks"])
    stranger = at_doc(qr_png, RECIBO.replace("A:999999990", "A:500000001"))
    assert any("not by your NIF" in c for c in propose(cfg, invoice(), stranger)["checks"])


def test_portuguese_client_with_iva(qr_png, cfg):
    out = propose(cfg, invoice(day=dt.date(2026, 3, 5), amount=615.0, currency="EUR"), at_doc(qr_png, PT_SALE))
    row = out["row"]
    assert (row["vat_case"], row["vat_eur"], row["net_eur"], row["vat_rate"], row["fx"]) == ("PT / C3", 115.0, 500.0, 23, 1.0)
    assert out["checks"] == []


def test_missing_income(tmp_path):
    (tmp_path / "inv1.pdf").write_bytes(b"x")
    (tmp_path / "stray.pdf").write_bytes(b"x")
    rows = [dict(row=8, invoice_date="04.02.2026", client="EXC", invoice_no="JD001", recibo_no="RG 1",
                 invoice_file="inv1.pdf", recibo_file="rec1.pdf"),
            dict(row=9, invoice_date="04.03.2026", client="EXC", invoice_no="JD002", recibo_no="",
                 invoice_file="", recibo_file="")]
    out = missing_income(rows, str(tmp_path))
    assert out["no_at_document"] == ["row 9 04.03.2026 EXC JD002"]
    assert out["file_not_found"] == ["row 8 04.02.2026 EXC JD001: rec1.pdf"]
    assert out["unbooked_files"] == ["stray.pdf"]
