"""End-to-end check of the sheet layout against a real spreadsheet.

Creates temporary ZZTEST_* tabs for the year 2099 in the spreadsheet from your config, books a few purchases and
sales through the same code the tools use, checks every IVA box against hand-computed values, locks Q1, and
deletes the temporary tabs again. Opt-in:
    INVOICES_PT_LIVE_SHEET=1 pytest tests/test_live_layout.py -q -s
"""

import os

import pytest

pytestmark = pytest.mark.skipif(os.environ.get("INVOICES_PT_LIVE_SHEET") != "1", reason="writes to a real spreadsheet")

PURCHASES = [
    dict(date="2099-01-05", expense="SaaS", supplier="US SaaS Inc", country="US", invoice_no="A1", currency="USD",
         amount=20, vat_included=0, fx=1.25, nif="Yes", code="NON-EU-RC", business_pct=1, document="PDF invoice"),
    dict(date="2099-02-01", expense="Supplies", supplier="Office Shop Lda", country="PT", supplier_vat="PT500000000",
         invoice_no="FT 1/1", currency="EUR", amount=61.50, vat_included=11.50, fx=1, nif="Yes", code="PT",
         business_pct=1, document="PDF ✓ QR-verified"),
    dict(date="2099-03-16", expense="Software", supplier="DE Software GmbH", country="DE", invoice_no="X-9", currency="EUR",
         amount=30.00, vat_included=0, fx=1, nif="Yes", code="EU-RC", business_pct=1, document="PDF invoice"),
    dict(date="2099-04-08", expense="Cables", supplier="ES Shop", country="ES", invoice_no="ES1", currency="EUR",
         amount=20.00, vat_included=0, fx=1, nif="Yes", code="EU-RC-GOODS", business_pct=1, document="PDF invoice"),
]
SALES = [
    dict(invoice_date="2099-01-20", client="US Client", country="US", invoice_no="S1", recibo_no="RG 1",
         recibo_date="2099-04-02", currency="USD", amount=1250, fx=1.25, net_eur=1000, vat_rate=0, vat_eur=0,
         withheld=0, vat_case="NON-EU / C8"),
    dict(invoice_date="2099-03-03", client="PT Client", country="PT", invoice_no="S2", recibo_no="FR 1",
         recibo_date="2099-03-03", currency="EUR", amount=615, fx=1, net_eur=500, vat_rate=23, vat_eur=115, withheld=0,
         vat_case="PT / C3"),
]
EXPECTED = {  # hand-computed: opening credit 100; USD 20 at 1.25 = 16.00 self-charged at 23% = 3.68
    "Q1": {3: 516.0, 4: 118.68, 8: 1000.0, 16: 30.0, 17: 6.9, 24: 22.08, 61: 100.0, 98: 16.0, 90: 1546.0,
           91: 122.08, 92: 125.58, 93: 3.5, 94: 0.0, 96: 0.0},
    "Q2": {12: 20.0, 13: 4.6, 24: 4.6, 61: 0.0, 91: 4.6, 92: 4.6, 96: 0.0},
}


def test_layout_end_to_end():
    from invoices_pt import layout
    from invoices_pt.config import Config
    from invoices_pt.sheet import ExpenseSheet, IncomeSheet, open_spreadsheet

    real = Config.load()
    if real.backend != "google":
        pytest.skip("the configured backend is not a Google Sheet")
    cfg = Config({"backend": "google", "taxpayer": real.data.get("taxpayer", {}),
                  "google": {**real.google, "expenses_tab": "ZZTEST_Expenses_{year}", "income_tab": "ZZTEST_Income_{year}"}})
    sh = open_spreadsheet(cfg)
    try:
        layout.create_year(sh, 2099, "ZZTEST_Expenses_2099", "ZZTEST_Income_2099", opening_credit=100.0)
        exp, inc = ExpenseSheet(cfg, 2099, sh), IncomeSheet(cfg, 2099, sh)
        for row in PURCHASES:
            assert exp.add(row, dry_run=False).get("written"), row
        for row in SALES:
            assert inc.add(row, dry_run=False).get("written"), row
        got = {q: {b["box"]: b["value"] for b in exp.declaration(q)["boxes"]} for q in EXPECTED}
        bad = [(q, b, v, got[q].get(b)) for q, e in EXPECTED.items() for b, v in e.items()
               if abs((got[q].get(b) or 0) - v) > 0.005]
        assert not bad, bad
        totals = {t["item"][:12]: t for t in inc.summary()}
        assert totals["Gross income"]["Q1"] == 1500.0
        assert (totals["Income € by "]["Q1"], totals["Income € by "]["Q2"]) == (500.0, 1000.0)   # by recibo date
        assert [r["quarter"] for r in exp.records()] == ["Q1", "Q1", "Q1", "Q2"]
        frozen = exp.freeze("Q1", dry_run=False)
        assert frozen["expense_rows"] == "31-33" and frozen["income_rows"] == "8-9"
        assert exp.filed_quarters() == {"Q1"} and inc.filed_quarters() == {"Q1"}
        assert "locked" in exp.add(dict(date="2099-01-09", invoice_no="Z")).get("error", "")
        assert exp.declaration("Q1")["live_formulas"] is False
    finally:
        for name in ("ZZTEST_Expenses_2099", "ZZTEST_Income_2099"):
            try:
                sh.del_worksheet(sh.worksheet(name))
            except Exception:
                pass
