from invoices_pt import columns, layout


def test_expense_tab_structure():
    rows = layout.expense_values(2027, "Income_2027", opening_credit=12.5)
    assert rows[0] == ["EXPENSES 2027"]
    assert rows[2][0] == "Declaração Periódica" and rows[2][4:8] == ["Q1", "Q2", "Q3", "Q4"]
    boxes = {r[0]: i + 1 for i, r in enumerate(rows) if r and r[0].startswith("Box ")}
    assert boxes["Box 3"] == 4 and boxes["Box 61"] == 14 and boxes["Box 96"] == 21
    r61 = rows[boxes["Box 61"] - 1]
    assert r61[4] == 12.5 and r61[5:8] == ["=E21", "=F21", "=G21"]       # credit chained from box 96
    assert rows[boxes["Box 91"] - 1][4] == "=E12+E13+E14"                  # 20 + 24 + 61
    assert rows[layout.SUMS_ROW - 1][0] == "QUARTERS"
    assert rows[layout.EXP_HEADER_ROW - 1] == [h for h, _, _ in layout.EXPENSE_COLUMNS]
    assert "Income_2027'!$T$7:$T" in rows[boxes["Box 3"] - 1][4]           # sales at 23% come from the income tab


def test_income_tab_structure():
    rows = layout.income_values(2027, "Expenses_2027")
    assert rows[1] == ["IRS & SS", "", "Q1", "Q2", "Q3", "Q4", "2027"]
    assert rows[layout.INC_HEADER_ROW - 1] == [h for h, _, _ in layout.INCOME_COLUMNS]
    assert "Expenses_2027'!$AB$30:$AB" in rows[4][2]


def test_layout_matches_the_tools():
    exp_headers = {h for h, _, _ in layout.EXPENSE_COLUMNS}
    inc_headers = {h for h, _, _ in layout.INCOME_COLUMNS}
    assert set(columns.EXPENSE_FIELDS.values()) <= exp_headers
    assert set(columns.INCOME_FIELDS.values()) <= inc_headers
    f = layout.row_formulas("expenses", 40)
    assert f["Q"].startswith('=IF(A40=""') and f["Box 98"] == "=R40"
