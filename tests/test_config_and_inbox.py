"""Config defaults and safety rules, and the inbox plan end to end (made-up documents only)."""

import os
import shutil

import pytest
import yaml

from invoices_pt.config import Config
from invoices_pt.documents.text import looks_like_invoice
from invoices_pt.model import Document

from conftest import text_pdf
from test_efatura import CSV
from test_income import RECIBO

EXAMPLES = os.path.join(os.path.dirname(__file__), "..", "examples", "parsers")
EXPENSE_QR = "A:500000000*B:999999990*C:PT*D:FT*E:N*F:20260115*G:FT A1/42*H:ABCD-42*I1:PT*I7:100.00*I8:23.00*N:23.00*O:123.00"
OWN_INVOICE = ["INVOICE", "Jane Doe", "INVOICE NO. JD001", "DATE 02.04.26", "NIF: 999999990", "TO Example Client Inc.",
               "TOTAL DUE $1,250.00", "* IVA: not charged (art. 6.º, n.º 6, a) do CIVA)"]


def test_path_defaults_and_cards():
    cfg = Config({"cards": {123: "bank-a", "0042": "bank-b"}})
    p = cfg.paths(2026)
    assert p["year_root"].endswith("Taxes/2026") and p["expenses_dir"].endswith("Taxes/2026/Expenses")
    assert p["ledger"].endswith("ledger.sqlite") and p["inbox"].endswith("Downloads")
    assert cfg.cards == {"0123": "bank-a", "0042": "bank-b"}      # unquoted 0123 in YAML arrives as 123


def test_income_dir(tmp_path):
    base = {"year_root": str(tmp_path / "{year}")}
    assert Config({"paths": base}).income_dir(2026) == str(tmp_path / "2026" / "Income")
    (tmp_path / "2026" / "Income (old)").mkdir(parents=True)
    globbed = Config({"paths": {**base, "income_glob": "{year_root}/Income*"}})
    assert globbed.income_dir(2026) == str(tmp_path / "2026" / "Income (old)")
    explicit = Config({"paths": {**base, "income_dir": "{year_root}/Sales", "income_glob": "{year_root}/Income*"}})
    assert explicit.income_dir(2026) == str(tmp_path / "2026" / "Sales")


def test_supplier_rules_never_match_document_text():
    cfg = Config({"suppliers": [{"match": "Landlord", "code": "NoVAT", "business_pct": 0.3}]})
    letter = Document(layer="text", text="Dear landlord, the heating is broken.")
    assert cfg.supplier_rule(letter) == {}
    assert cfg.supplier_rule(Document(layer="qr", supplier="My Landlord Lda")) != {}


def test_looks_like_invoice():
    assert looks_like_invoice("INVOICE\nInvoice number 12\nTotal 10.00\nVAT 0.00") is True
    assert looks_like_invoice("Dear landlord,\nthe heating is broken.") is False
    assert looks_like_invoice("  \n ") is None


@pytest.fixture
def user(tmp_path, monkeypatch, qr_png):
    """A user with a private config, an inbox full of things, and books for 2026."""
    from invoices_pt import server
    data = {"taxpayer": {"nif": "999999990"}, "parsers_dir": EXAMPLES,
            "paths": {"inbox": str(tmp_path / "inbox"), "year_root": str(tmp_path / "Taxes/{year}"),
                      "cache": str(tmp_path / "cache"), "ledger": str(tmp_path / "ledger.sqlite")},
            "suppliers": [{"match": "500000000", "name": "My Office Shop, Lda", "slug": "officeshop"}],
            "clients": [{"match": "Example Client", "name": "EXC", "country": "US", "account": "bank-a"}]}
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(data, allow_unicode=True))
    monkeypatch.setenv("INVOICES_PT_CONFIG", str(path))
    inbox = tmp_path / "inbox"
    qr_png(EXPENSE_QR, folder=inbox, name="officeshop.png")
    shutil.copy(inbox / "officeshop.png", inbox / "officeshop (1).png")           # downloaded twice
    qr_png(RECIBO, folder=inbox, name="recibo.png")
    text_pdf(inbox / "my_invoice.pdf", OWN_INVOICE)
    text_pdf(inbox / "letter.pdf", ["Dear neighbour,", "thanks for the dinner last week."])
    text_pdf(inbox / "odd_invoice.pdf", ["Invoice", "Mystery Ltd", "Total 10.00", "VAT 0.00"])
    (inbox / "e-fatura.csv").write_text(CSV, encoding="utf-8")
    server.create_year_sheet(2026, dry_run=False)
    return server, tmp_path


def test_plan_inbox(user):
    server, tmp = user
    plan = server.plan_inbox()
    assert [os.path.basename(e["path"]) for e in plan["expenses"]] in (["officeshop.png"], ["officeshop (1).png"])
    row = plan["expenses"][0]["row"]
    assert (row["date"], row["supplier"], row["amount"], row["vat_included"], row["code"]) == \
        ("2026-01-15", "My Office Shop, Lda", 123.0, 23.0, "PT")
    assert plan["expenses"][0]["file_name"] == "officeshop_01_FT-A1-42.png"
    assert len(plan["copies"]) == 1
    sale = plan["sales"][0]
    assert os.path.basename(sale["invoice"]) == "my_invoice.pdf" and os.path.basename(sale["at_document"]) == "recibo.png"
    assert (sale["row"]["client"], sale["row"]["fx"], sale["row"]["vat_case"]) == ("EXC", 1.25, "NON-EU / C8")
    assert [os.path.basename(p) for p in plan["not_invoices"]] == ["letter.pdf"]
    assert [os.path.basename(n["path"]) for n in plan["needs_reading"]] == ["odd_invoice.pdf"]
    assert [os.path.basename(p) for p in plan["efatura_exports"]] == ["e-fatura.csv"]


def test_extract_withholds_unrelated_text(user):
    server, tmp = user
    out = server.extract(str(tmp / "inbox" / "letter.pdf"))
    assert out["looks_like_invoice"] is False and "text" not in out["document"] and "warning" in out
    assert "dinner" in server.extract(str(tmp / "inbox" / "letter.pdf"), read_anyway=True)["document"]["text"]


def test_sales_go_to_the_income_folder(user):
    server, tmp = user
    sale = server.plan_inbox()["sales"][0]
    moved = server.file_document(sale["at_document"], name=sale["file_names"]["recibo"], dry_run=False)
    assert moved["to"] == str(tmp / "Taxes/2026/Income/20260204_recibo_JD001.png")
    alone = server.propose_income(at_document_path=moved["to"])
    assert alone["file_names"]["recibo"] == "20260210_recibo_RG-A1-7.png"      # no own invoice: AT number
    assert any("client" in c for c in alone["checks"])


def test_year_setup_creates_folders_and_clear_missing_message(user):
    server, tmp = user
    assert os.path.isdir(tmp / "Taxes/2026/Expenses") and os.path.isdir(tmp / "Taxes/2026/Income")
    assert "nothing set up for 2031" in server.missing(2031)["error"]
    assert set(server.missing(2026)) == {"expenses", "income"}
