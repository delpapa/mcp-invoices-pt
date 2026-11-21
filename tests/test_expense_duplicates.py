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


def test_add_expense_books_a_credit_note_with_an_invoice_number(cfg, tmp_path, qr_png, monkeypatch):
    from invoices_pt import server
    from conftest import AT_PAYLOAD

    monkeypatch.setattr(server, "_cfg", lambda: cfg)
    create_year(cfg, 2026, 0)
    payload = AT_PAYLOAD.replace("G:FT A1/42", "G:A1/42")
    invoice = server.extract(qr_png(payload, folder=tmp_path, name="invoice.png"))["row"]
    credit = server.extract(qr_png(payload.replace("D:FT", "D:NC"), folder=tmp_path, name="credit.png"))["row"]
    assert invoice["doc_type"] == "invoice" and credit["doc_type"] == "credit_note"
    assert server.add_expense(invoice, dry_run=False)["written"]
    assert server.add_expense(credit, dry_run=False)["written"]
    assert "already in row" in server.add_expense(credit, dry_run=False)["error"]
    expenses, _ = open_books(cfg, 2026)
    assert [r["doc_type"] for r in expenses.records()] == ["invoice", "credit_note"]
    assert "already in row" in server.add_expense(dict(credit, doc_type=""))["error"]


def test_existing_workbook_without_document_type(cfg):
    from invoices_pt import layout

    create_year(cfg, 2026, 0)
    expenses, _ = open_books(cfg, 2026)
    wb = expenses.book.load()
    ws = wb["Expenses"]
    ws.cell(layout.EXP_HEADER_ROW, ws.max_column).value = None  # pre-document-type layout
    expenses.book.save(wb)
    row = {"date": "2026-01-05", "invoice_no": "42", "doc_type": "invoice", "supplier_vat": "PT123"}
    assert "Document type" not in expenses.add(row)["cells"]
    first = expenses.add(row, dry_run=False)["row"]
    assert f"already in row {first}" in expenses.add(dict(row, doc_type="credit_note"))["error"]


@pytest.mark.parametrize("typed_layout", [False, True])
def test_sheets_typed_expense_writes_and_duplicate_checks(typed_layout):
    gspread = pytest.importorskip("gspread")
    from invoices_pt.sheet import ExpenseSheet

    sheet = Mock()
    expenses = ExpenseSheet(Config({"google": {"expenses_tab": "Purchases"}}), 2026, sheet)
    expenses.ws.id = 1
    sheet.fetch_sheet_metadata.return_value = {"sheets": []}
    headers = [h for h in columns.EXPENSE_FIELDS.values() if typed_layout or h != "Document type"]
    rows = [headers]
    expenses.ws.get_all_values.return_value = rows

    def write_new_row(updates, **kwargs):
        cells = [""] * len(headers)
        for update in updates:
            r, c = gspread.utils.a1_to_rowcol(update["range"])
            assert r == len(rows) + 1
            cells[c - 1] = str(update["values"][0][0]).removeprefix("'")
        rows.append(cells)

    expenses.ws.batch_update.side_effect = write_new_row
    invoice = {"date": "2026-01-05", "invoice_no": "42", "doc_type": "invoice", "supplier_vat": "PT123"}
    credit = dict(invoice, doc_type="credit_note")
    assert expenses.add(invoice, dry_run=False)["row"] == 2
    if typed_layout:
        assert expenses.add(credit, dry_run=False)["row"] == 3
        assert [rec["doc_type"] for rec in expenses.records()] == ["invoice", "credit_note"]
        assert "already in row 3" in expenses.add(credit)["error"]
    else:
        assert "already in row 2" in expenses.add(credit)["error"]
