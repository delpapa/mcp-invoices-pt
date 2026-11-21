from pathlib import Path
from unittest.mock import Mock
from zipfile import BadZipFile

import pytest

from invoices_pt.books import opening_credit


def test_missing_prior_workbook_is_a_first_year(cfg):
    assert opening_credit(cfg, 2026) == 0


def test_damaged_prior_workbook_cannot_silently_zero_credit(cfg):
    previous = Path(cfg.workbook(2025))
    previous.parent.mkdir(parents=True)
    previous.write_bytes(b"interrupted workbook")
    with pytest.raises(BadZipFile):
        opening_credit(cfg, 2026)


def test_sheets_carry_forward_failures(cfg, monkeypatch):
    pytest.importorskip("gspread")
    from invoices_pt import sheet

    cfg.data["backend"] = "google"
    cfg.google.update({"expenses_tab": "E{year}", "income_tab": "I{year}"})
    previous = Mock()
    monkeypatch.setattr(sheet, "open_spreadsheet", lambda cfg: previous)
    previous.worksheets.return_value = []
    assert opening_credit(cfg, 2026) == 0
    income = Mock(title="I2025")
    previous.worksheets.return_value = [income]
    with pytest.raises(ValueError, match="E2025"):
        opening_credit(cfg, 2026)
    expenses = Mock(title="E2025")
    previous.worksheets.return_value = [expenses, income]
    monkeypatch.setattr(sheet.ExpenseSheet, "declaration", lambda self, q: {"boxes": [{"box": 96, "value": None}]})
    with pytest.raises(ValueError, match="96"):
        opening_credit(cfg, 2026)
    previous.worksheets.side_effect = PermissionError("spreadsheet unavailable")
    with pytest.raises(PermissionError):
        opening_credit(cfg, 2026)
