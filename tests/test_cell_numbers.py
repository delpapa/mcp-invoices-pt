from unittest.mock import Mock

import pytest

from invoices_pt import bookmath, columns, report
from invoices_pt.config import Config


@pytest.mark.parametrize("cell,expected", [
    (1234.56, 1234.56), ("1,234.56", 1234.56), ("-€1.234,56", -1234.56), ("1\u00a0234,56 €", 1234.56),
    ("12,5%", 0.125), ("1,234", 1234), ("1.234", 1.234), ("0,1234", 0.1234), ("unpaid 12,50", None),
])
def test_number_cell(cell, expected):
    assert bookmath.num(cell) == expected


def test_xlsx_and_reconciliation_read_decimal_comma(cfg):
    from invoices_pt.books import create_year, open_books

    create_year(cfg, 2026, 0)
    expenses, _ = open_books(cfg, 2026)
    row = {"date": "2026-01-03", "amount": "123,45", "vat_included": "23,45 €", "code": "PT"}
    expenses.add(row, dry_run=False)
    rec = expenses.records()[0]
    assert (rec["amount"], rec["vat_included"]) == (123.45, 23.45)
    assert report._amount("123,45") == rec["amount"]


def test_sheets_summary_and_declaration_use_numeric_values():
    pytest.importorskip("gspread")
    from invoices_pt.sheet import ExpenseSheet, IncomeSheet

    cfg = Config({"google": {"expenses_tab": "Purchases", "income_tab": "Sales"}})
    sh = Mock()
    sh.fetch_sheet_metadata.return_value = {"sheets": []}
    expenses = ExpenseSheet(cfg, 2026, sh)

    def values(value_render_option="FORMATTED_VALUE"):
        cell = {"FORMATTED_VALUE": "1.235 €", "UNFORMATTED_VALUE": 1234.56, "FORMULA": "=SUM(A8:A9)"}[value_render_option]
        return [["Box", "", "", "Q1"], ["Box 90", "", "Total", cell], ["Date"]]

    expenses.ws.get_all_values.side_effect = values
    result = expenses.declaration("Q1")
    assert result["boxes"][0]["value"] == 1234.56
    assert result["live_formulas"]

    income = IncomeSheet(cfg, 2026, sh)

    def summary(value_render_option="FORMATTED_VALUE"):
        cell = -1234.56 if value_render_option == "UNFORMATTED_VALUE" else "-1.235 €"
        return [["", "Q1", 2026], ["Income", cell, cell], list(columns.INCOME_FIELDS.values())]

    income.ws.get_all_values.side_effect = summary
    assert income.summary() == [{"item": "Income", "Q1": -1234.56, "2026": -1234.56}]
