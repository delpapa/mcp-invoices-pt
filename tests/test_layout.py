from invoices_pt import columns, layout


def test_expense_tab_structure():
    rows = layout.expense_values(2027, "Income_2027", opening_credit=12.5)
    assert rows[0] == ["EXPENSES 2027"]
    assert rows[2][0] == "Declaração Periódica" and rows[2][4:8] == ["Q1", "Q2", "Q3", "Q4"]
    boxes = {r[0]: i + 1 for i, r in enumerate(rows) if r and r[0].startswith("Box ")}
    assert boxes["Box 1"] == 4 and boxes["Box 61"] == 18 and boxes["Box 96"] == 25
    r61 = rows[boxes["Box 61"] - 1]
    assert r61[4] == 12.5 and r61[5:8] == ["=E25", "=F25", "=G25"]       # credit chained from box 96
    assert rows[boxes["Box 91"] - 1][4] == "=E16+E17+E18"                  # 20 + 24 + 61
    assert rows[layout.SUMS_ROW - 1][0] == "QUARTERS"
    assert rows[layout.EXP_HEADER_ROW - 1] == [h for h, _, _ in layout.EXPENSE_COLUMNS]
    assert "Income_2027'!$T$7:$T" in rows[boxes["Box 3"] - 1][4]           # sales at 23% come from the income tab


def test_income_tab_structure():
    rows = layout.income_values(2027, "Expenses_2027")
    assert rows[1] == ["IRS & SS", "", "Q1", "Q2", "Q3", "Q4", "2027"]
    assert rows[layout.INC_HEADER_ROW - 1] == [h for h, _, _ in layout.INCOME_COLUMNS]
    assert "Expenses_2027'!$AB$34:$AB" in rows[4][2]


def test_layout_matches_the_tools():
    exp_headers = {h for h, _, _ in layout.EXPENSE_COLUMNS}
    inc_headers = {h for h, _, _ in layout.INCOME_COLUMNS}
    assert set(columns.EXPENSE_FIELDS.values()) <= exp_headers
    assert set(columns.INCOME_FIELDS.values()) <= inc_headers
    f = layout.row_formulas("expenses", 40)
    assert f["Q"].startswith('=IF(A40=""') and f["Box 98"] == "=R40"


def test_year_setup_is_a_single_atomic_sheets_request():
    from types import SimpleNamespace
    from unittest.mock import Mock

    import pytest

    sh = Mock()
    sh.worksheets.return_value = [SimpleNamespace(id=0, title="Other")]
    sh.batch_update.side_effect = OSError("batch rejected")
    with pytest.raises(OSError, match="batch rejected"):
        layout.create_year(sh, 2027, "Purchases", "Sales", opening_credit=12.5)
    sh.add_worksheet.assert_not_called()  # No tabs committed before the failing batch.
    requests = sh.batch_update.call_args.args[0]["requests"]
    properties = [request["addSheet"]["properties"] for request in requests if "addSheet" in request]
    assert [p["title"] for p in properties] == ["Purchases", "Sales"]
    ids = {p["sheetId"] for p in properties}
    assert len(ids) == 2 and 0 not in ids
    updates = [request["updateCells"] for request in requests if "updateCells" in request]
    assert {u["start"]["sheetId"] for u in updates} == ids
    rows = updates[0]["rows"]
    credit = next(r["values"] for r in rows if r["values"] and
                  r["values"][0].get("userEnteredValue", {}).get("stringValue") == "Box 61")
    assert credit[4]["userEnteredValue"] == {"numberValue": 12.5}
    assert credit[5]["userEnteredValue"]["formulaValue"].startswith("=")


def test_apostrophe_in_tab_names():
    purchases = layout.expense_values(2027, "Jack's income", 0)
    sales = layout.income_values(2027, "Jack's expenses")
    assert "'Jack''s income'!" in next(row for row in purchases if row and row[0] == "Box 3")[4]
    assert "'Jack''s expenses'!" in sales[4][2]
