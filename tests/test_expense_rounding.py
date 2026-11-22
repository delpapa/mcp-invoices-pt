import shutil
import subprocess

import openpyxl
import pytest

from invoices_pt import bookmath, layout
from invoices_pt.xlsx import XlsxBook

# (gross, VAT included, exchange rate, code, work share, deductible box, VAT deduction, IRS cost)
CASES = [
    (1.23, .23, None, "PT", None, 24, 0.23, 1.00),
    (1.23, .23, None, "PT", 0.0, 24, 0.00, 0.00),
    (1.23, .23, None, "PT-ASSET", 0.5, 20, 0.12, 0.50),
    (1.23, 0, None, "EU-RC", None, 24, 0.28, 1.23),
    (3977.62, 194.03, None, "PT", .5, 24, 97.02, 1891.79),
    (-1848.84, -90.19, None, "PT", .5, 24, -45.10, -879.32),
    (315.57, 15.39, 1.26, "PT-ASSET", .5, 20, 6.11, 119.12),
]


@pytest.mark.parametrize("gross,included,fx,code,share,box,vat,irs", CASES)
def test_expense_share_and_half_cent_rounding(gross, included, fx, code, share, box, vat, irs):
    result = bookmath.expense_row({"code": code, "amount": gross, "business_pct": share,
                                   "vat_included": included, "fx": fx})
    assert (result[box], result["irs"]) == (vat, irs)


@pytest.mark.skipif(not shutil.which("soffice"), reason="LibreOffice not installed")
def test_expense_formulas_match_hand_calculated_rows(tmp_path):
    workbook = openpyxl.Workbook()
    ws = workbook.active
    headers = [h for h, _, _ in layout.EXPENSE_COLUMNS]
    for rn, (gross, included, fx, code, share, *_) in enumerate(CASES, 1):
        cells = {"Amount paid": gross, "VAT included": included, "FX to EUR": fx,
                 "VAT code": code, "Business %": share, **layout.row_formulas("expenses", rn)}
        for name, value in cells.items():
            ws.cell(rn, headers.index(name) + 1, value)

    path = tmp_path / "expenses.xlsx"
    out = tmp_path / "calculated"
    workbook.save(path)
    subprocess.run(["soffice", f"-env:UserInstallation={(tmp_path / 'profile').as_uri()}", "--headless",
                    "--convert-to", "xlsx", "--outdir", str(out), str(path)], check=True, timeout=120)
    calculated = openpyxl.load_workbook(out / path.name, data_only=True).active
    for rn, (*_, box, vat, irs) in enumerate(CASES, 1):
        assert calculated.cell(rn, headers.index(f"Box {box}") + 1).value == vat
        assert calculated.cell(rn, headers.index("IRS deductible € (Anexo B)") + 1).value == irs


@pytest.mark.parametrize("rate", [0, -2, "NaN", "unavailable"])
def test_invalid_expense_fx(cfg, rate):
    row = {"date": "2026-01-01", "amount": 20, "fx": rate}
    with pytest.raises(ValueError, match="fx must be a positive finite"):
        bookmath.expense_row(row)
    # Validation precedes workbook access in dry runs and writes.
    expenses = XlsxBook(cfg, 2026).expenses
    assert expenses.add(row, dry_run=False) == {"error": bookmath.EXPENSE_FX_ERROR}


def test_missing_foreign_exchange_rate_cannot_be_booked_at_par(cfg):
    from invoices_pt.extract import expense_row
    from invoices_pt.model import Document

    doc = Document(layer="parser:test", currency="JPY", amount=15000)
    prop = dict(fx_rate="unavailable", supplier="", nif_on_invoice="No", vat_code="NONE", business_pct=1,
                document="PDF invoice", file_name="", account="")
    row = dict(expense_row(doc, prop), date="2026-01-05")
    with pytest.raises(ValueError, match="fx"):
        bookmath.expense_row(row)
    assert "fx" in XlsxBook(cfg, 2026).expenses.add(row, dry_run=False)["error"]
    for rate in (150, "150.0"):
        proposed = expense_row(doc, dict(prop, fx_rate=rate))
        assert bookmath.expense_row(proposed)["amount_eur"] == 100
