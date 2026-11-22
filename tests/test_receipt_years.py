from datetime import date
from unittest.mock import Mock

from invoices_pt import bookmath
from invoices_pt.books import annual_income_totals, create_year, open_books
from invoices_pt.config import Config


def _receipt(summary):
    return next(row for row in summary if row["item"] == bookmath.RECEIPT_TOTAL)


def test_receipt_year_across_older_books_and_gaps(tmp_path):
    cfg = Config({"paths": {"year_root": str(tmp_path / "Files [business]" / "{year}")}})
    for year in (2023, 2025, 2026):
        create_year(cfg, year, 0)
    for year, receipt, net in ((2023, "2026-01-15", 41), (2025, "2026-03-31", 50), (2026, "2026-04-01", 7)):
        _, income = open_books(cfg, year)
        assert income.add(dict(invoice_date=f"{year}-01-01", recibo_date=receipt, net_eur=net), dry_run=False)["written"]
    previous = annual_income_totals(cfg, 2025)
    assert previous[0]["2025"] == 50 and _receipt(previous)["2025"] == 0
    current = annual_income_totals(cfg, 2026)
    assert current[0]["2026"] == 7
    assert (_receipt(current)["Q1"], _receipt(current)["Q2"], _receipt(current)["2026"]) == (91, 7, 98)


def test_single_workbook_with_annual_tabs_counts_each_once(tmp_path):
    cfg = Config({"paths": {"workbook": str(tmp_path / "books.xlsx"), "year_root": str(tmp_path / "{year}")},
                  "xlsx": {"income_sheet": "Income {year}"}})
    create_year(cfg, 2026, 0)
    _, income = open_books(cfg, 2026)
    wb = income.book.load()
    old = wb.copy_worksheet(wb["Income 2026"])
    old.title = "Income 2024"
    income.book.save(wb)
    _, old_income = open_books(cfg, 2024)
    old_income.add(dict(invoice_date="2024-11-01", recibo_date="2026-06-02", net_eur=100), dry_run=False)
    assert _receipt(annual_income_totals(cfg, 2026))["Q2"] == 100


def test_receipts_read_date_serials_and_numbers_without_locale_conversion():
    import pytest
    pytest.importorskip("gspread")
    from invoices_pt.sheet import IncomeSheet
    table = Mock(columns={"recibo_date": "Date", "net_eur": "Amount"})
    serial = (date(2026, 2, 28) - date(1899, 12, 30)).days
    table._table.return_value = (1, {"Date": 0, "Amount": 1}, [["Date", "Amount"], [serial, 1234.56]])
    assert list(IncomeSheet.receipts(table)) == [{"recibo_date": date(2026, 2, 28), "net_eur": 1234.56}]
    table._table.assert_called_once_with("UNFORMATTED_VALUE")
