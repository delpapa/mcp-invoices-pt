"""Open a tax year's books (expenses and income tables) in the configured backend: a local .xlsx workbook (default)
or a Google Sheet (`backend: google`, needs `pip install mcp-invoices-pt[google]`)."""

from __future__ import annotations

from .config import Config


def open_books(cfg: Config, year: int):
    """(expenses, income) tables for a year. Both offer records, find, add and filed_quarters; expenses also
    declaration, set_declaration and freeze; income also summary."""
    if cfg.backend == "google":
        from .sheet import ExpenseSheet, IncomeSheet
        expenses = ExpenseSheet(cfg, year)
        return expenses, IncomeSheet(cfg, year, expenses.sh)
    from .xlsx import XlsxBook
    book = XlsxBook(cfg, year)
    return book.expenses, book.income


def where(cfg: Config, year: int) -> str:
    if cfg.backend == "google":
        return f"Google Sheet {cfg.google.get('spreadsheet_id', '')}, tabs {cfg.sheet_name('expenses', year)} / {cfg.sheet_name('income', year)}"
    return cfg.workbook(year)


def opening_credit(cfg: Config, year: int) -> float:
    """Credit carried into a year: box 96 of the previous year's Q4, if those books exist."""
    try:
        expenses, _ = open_books(cfg, year - 1)
        return next(b["value"] for b in expenses.declaration("Q4")["boxes"] if b["box"] == 96) or 0.0
    except Exception:
        return 0.0


def create_year(cfg: Config, year: int, credit: float) -> dict:
    """The year's books, plus its folders for expense and income documents."""
    import os
    for folder in (cfg.expenses_dir(year), cfg.income_dir(year)):
        os.makedirs(folder, exist_ok=True)
    exp_name, inc_name = cfg.sheet_name("expenses", year), cfg.sheet_name("income", year)
    if cfg.backend == "google":
        from . import layout
        from .sheet import open_spreadsheet
        return layout.create_year(open_spreadsheet(cfg), year, exp_name, inc_name, opening_credit=credit)
    from .xlsx import create_workbook
    return create_workbook(cfg.workbook(year), year, exp_name, inc_name, opening_credit=credit)
