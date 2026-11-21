from unittest.mock import Mock

import pytest

from invoices_pt import columns
from invoices_pt.books import create_year, open_books
from invoices_pt.config import Config


def test_xlsx_matches_expenses_by_supplier_and_number(cfg):
    create_year(cfg, 2026, 0)
    expenses, _ = open_books(cfg, 2026)
    first = {"date": "2026-01-05", "invoice_no": "INV 1", "supplier_vat": "PT123"}
    second = dict(first, date="2026-01-06", supplier_vat="PT456")
    first_row = expenses.add(first, dry_run=False)["row"]
    assert expenses.add(second)["dry_run"]
    second_row = expenses.add(second, dry_run=False)["row"]
    assert second_row == first_row + 1
    assert expenses.find("inv1", supplier_vat="pt 456") == second_row
    assert f"already in row {second_row}" in expenses.add(dict(second, invoice_no="inv1", supplier_vat="pt 456"))["error"]
    assert f"already in row {first_row}" in expenses.add(dict(second, supplier_vat=""))["error"]


def test_sheets_returns_row_for_correct_supplier_and_handles_short_rows():
    pytest.importorskip("gspread")
    from invoices_pt.sheet import ExpenseSheet

    cfg = Config({"google": {"expenses_tab": "Purchases {year}"}})
    sheet = Mock()
    expenses = ExpenseSheet(cfg, 2026, sheet)
    sheet.fetch_sheet_metadata.return_value = {"sheets": []}
    # A custom layout with the VAT column after the invoice number.
    headers = ["Date", "Invoice no.", "VAT"]
    headers += [header for header in columns.EXPENSE_FIELDS.values() if header not in headers]
    rows = [headers, ["2026-01-05", "INV 1", "PT123"], []]
    expenses.ws.get_all_values.return_value = rows
    second = {"date": "2026-01-06", "invoice_no": "inv1", "supplier_vat": "PT456"}
    # After inserting the new row and sorting by date, the empty row is last.

    def write_new_row(*args, **kwargs):
        rows.insert(2, ["2026-01-06", "inv1", "PT456"])

    expenses.ws.batch_update.side_effect = write_new_row

    assert expenses.add(second, dry_run=False)["row"] == 3
    assert "already in row 3" in expenses.add(dict(second, supplier_vat="pt 456"))["error"]
    rows.append(["2026-01-07", "INV 2"])  # old row with no VAT cell
    assert expenses.find("inv2", supplier_vat="PT789") == 5
