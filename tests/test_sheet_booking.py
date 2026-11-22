from unittest.mock import Mock

import pytest

from invoices_pt import columns, layout
from invoices_pt.config import Config


@pytest.fixture
def expenses():
    pytest.importorskip("gspread")
    from invoices_pt.sheet import ExpenseSheet

    sheet = Mock()
    sheet.fetch_sheet_metadata.return_value = {"sheets": []}
    expenses = ExpenseSheet(Config({"google": {"expenses_tab": "Purchases"}}), 2026, sheet)
    expenses.ws.id = 17
    return expenses


def test_rejected_batch_leaves_no_copied_invoice(expenses):
    headers = list(columns.EXPENSE_FIELDS.values())
    row = [""] * len(headers)
    row[0], row[headers.index("Invoice no.")] = "2026-01-05", "FIRST"
    rows = [headers, row]
    expenses.ws.get_all_values.return_value = rows

    def reject_values(body):
        requests = body["requests"]
        if any("updateCells" in r for r in requests):
            raise RuntimeError("invalid cell update")
        # A separate insert/copy batch would have been committed.
        if "insertDimension" in requests[0]:
            rows.append(list(row))

    expenses.sh.batch_update.side_effect = reject_values
    expenses.ws.batch_update.side_effect = RuntimeError("invalid cell update")
    with pytest.raises(RuntimeError, match="invalid cell"):
        expenses.add({"date": "2026-02-05", "invoice_no": "SECOND"}, dry_run=False)
    assert rows == [headers, row]
    expenses.sh.batch_update.assert_called_once()
    expenses.ws.batch_update.assert_not_called()


@pytest.mark.parametrize("template", [False, True])
def test_atomic_request_preserves_types_formulas_and_sort(expenses, template):
    headers = [h for h, _, _ in layout.EXPENSE_COLUMNS]
    rows = [headers, ["01.02.2026"]] if template else [headers]
    expenses.ws.get_all_values.return_value = rows
    expenses.add({"date": "2026-01-05", "invoice_no": "000123", "supplier": "Example",
                  "amount": "-€12,34", "business_pct": "25%"}, dry_run=False)

    expenses.sh.batch_update.assert_called_once()
    expenses.ws.batch_update.assert_not_called()
    requests = expenses.sh.batch_update.call_args.args[0]["requests"]
    start = len(rows)
    assert requests[0]["insertDimension"]["range"] == {
        "sheetId": 17, "dimension": "ROWS", "startIndex": start, "endIndex": start + 1}
    sort = requests[-1]["sortRange"]
    assert sort == {"range": {"sheetId": 17, "startRowIndex": 1, "endRowIndex": start + 1,
                              "startColumnIndex": 0, "endColumnIndex": len(headers)},
                    "sortSpecs": [{"dimensionIndex": 0, "sortOrder": "ASCENDING"}]}
    cells = {}
    for request in requests:
        if "updateCells" in request:
            update = request["updateCells"]
            assert update["fields"] == "userEnteredValue"
            assert update["start"]["rowIndex"] == start and update["start"]["sheetId"] == 17
            cells[headers[update["start"]["columnIndex"]]] = update["rows"][0]["values"][0]
    assert cells["Date"]["userEnteredValue"] == {"numberValue": 46027}
    assert cells["Amount paid"]["userEnteredValue"] == {"numberValue": -12.34}
    assert cells["Business %"]["userEnteredValue"] == {"numberValue": 0.25}
    assert cells["Invoice no."]["userEnteredValue"] == {"stringValue": "000123"}
    assert cells["Supplier"]["userEnteredValue"] == {"stringValue": "Example"}
    assert cells["Payment account"] == {}
    copies = [r["copyPaste"] for r in requests if "copyPaste" in r]
    if template:
        assert [c["pasteType"] for c in copies] == ["PASTE_FORMAT", "PASTE_FORMULA"]
        assert all(c["source"]["startRowIndex"] == 1 and c["destination"]["startRowIndex"] == 2 for c in copies)
        assert "Q" not in cells
    else:
        assert not copies
        assert cells["Q"]["userEnteredValue"] == {"formulaValue": layout.row_formulas("expenses", 2)["Q"]}


def test_quarter_with_no_sales_still_locks_income():
    pytest.importorskip("gspread")
    from invoices_pt.sheet import IncomeSheet

    spreadsheet = Mock()
    tabs = {title: Mock(id=sid) for title, sid in (("Income 2026", 11), ("Expenses 2026", 12))}
    spreadsheet.worksheet.side_effect = tabs.__getitem__
    cfg = Config({"google": {"income_tab": "Income {year}", "expenses_tab": "Expenses {year}"}})
    income = IncomeSheet(cfg, 2026, spreadsheet)
    spreadsheet.fetch_sheet_metadata.return_value = {"sheets": [
        {"protectedRanges": [{"range": {"sheetId": 12}, "description": "Q1 filed: declaration values"},
                             {"range": {"sheetId": 3}, "description": "Q2 filed: declaration values"}]}]}
    assert income.filed_quarters() == {"Q1"}
    assert "locked" in income.add({"invoice_date": "2026-01-15"}, dry_run=False)["error"]
    spreadsheet.batch_update.assert_not_called()


def test_freeze_commits_submitted_values_and_protections_in_one_request(expenses, monkeypatch):
    from invoices_pt import sheet

    expenses._block = Mock(return_value=([["Box 96", 10]], [["Box 96", "=10"]], {"96": 0}, {"Q1": 1}))
    expenses.records = Mock(return_value=[])
    expenses._table = Mock(return_value=(1, {"Date": 0}, []))
    income = Mock()
    income._table.return_value = (1, {"Date": 0}, [])
    income.records.return_value = []
    monkeypatch.setattr(sheet, "IncomeSheet", Mock(return_value=income))
    assert expenses.freeze("Q1", dry_run=True, box_values={96: 20})["dry_run"]
    expenses.sh.batch_update.assert_not_called()
    assert expenses.freeze("Q1", dry_run=False, box_values={96: 20})["frozen"]
    expenses.ws.update.assert_not_called()
    expenses.sh.batch_update.assert_called_once()
    requests = expenses.sh.batch_update.call_args.args[0]["requests"]
    updates = [r["updateCells"] for r in requests if "updateCells" in r]
    assert updates[0]["rows"][0]["values"][0]["userEnteredValue"] == {"numberValue": 20}
    assert updates[0]["start"] == {"sheetId": 17, "rowIndex": 0, "columnIndex": 1}
    assert any("addProtectedRange" in r for r in requests)


def test_missing_foreign_exchange_rate_does_not_write_to_sheets(expenses):
    result = expenses.add({"date": "2026-01-05", "currency": "JPY", "amount": 15000}, dry_run=False)
    assert "fx" in result["error"]
    expenses.sh.batch_update.assert_not_called()
