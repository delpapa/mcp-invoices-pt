"""Open a tax year's books (expenses and income tables) in the configured backend: a local .xlsx workbook (default)
or a Google Sheet (`backend: google`, needs `pip install mcp-invoices-pt[google]`)."""

from __future__ import annotations

import math
import os
from pathlib import Path

from . import bookmath
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


def _receipt_rows(cfg: Config, year: int, income):
    """Yield receipt dates and amounts from each distinct configured income table through year."""
    if cfg.backend == "google":
        from .sheet import IncomeSheet
        titles = {w.title for w in income.sh.worksheets()}
        seen = set()
        for y in range(year, 0, -1):
            title = cfg.tab("income", y)
            if title in titles and title not in seen:
                seen.add(title)
                table = income if y == year else IncomeSheet(cfg, y, income.sh)
                yield from table.receipts()
        return

    from .xlsx import XlsxBook
    current_path = Path(cfg.workbook(year)).absolute()
    previous_path = Path(cfg.workbook(year - 1)).absolute()
    # List the first year-dependent component once. Only probe paths whose directory
    # entry actually exists (including older years separated by gaps).
    if current_path == previous_path:
        wb = income.book.load()
        try:
            titles = set(wb.sheetnames)
            for y in range(year, 0, -1):
                title = cfg.sheet_name("income", y)
                if title in titles:
                    titles.remove(title)
                    yield from XlsxBook(cfg, y).income._records(wb)
        finally:
            wb.close()
        return
    parent = Path(os.path.commonpath([current_path, previous_path]))
    entries = set(os.listdir(parent))
    for y in range(year, 0, -1):
        path = Path(cfg.workbook(y)).absolute()
        if path.relative_to(parent).parts[0] not in entries:
            continue
        try:
            path.stat()
        except FileNotFoundError:
            continue
        yield from XlsxBook(cfg, y).income.records()


def annual_income_totals(cfg: Config, year: int) -> list[dict]:
    """Keep the book's IRS/custom summaries; consolidate receipts by actual payment date."""
    _, income = open_books(cfg, year)
    summary = income.summary()
    receipts = bookmath.receipt_totals(_receipt_rows(cfg, year, income), year)
    for i, row in enumerate(summary):
        if row["item"] in (bookmath.RECEIPT_TOTAL, bookmath.RECEIPT_TOTAL + " — this book"):
            summary[i] = receipts
            break
    else:
        summary.append(receipts)
    return summary


def opening_credit(cfg: Config, year: int) -> float:
    """Credit carried into a year: box 96 of the previous year's Q4, if those books exist."""
    previous = year - 1
    if cfg.backend == "google":
        from .sheet import ExpenseSheet, open_spreadsheet
        sh = open_spreadsheet(cfg)
        titles = {tab.title for tab in sh.worksheets()}
        expense_tab = cfg.tab("expenses", previous)
        if expense_tab not in titles:
            if cfg.tab("income", previous) in titles:
                raise ValueError(f"missing expenses tab {expense_tab} for {previous}")
            return 0.0
        expenses = ExpenseSheet(cfg, previous, sh)
    else:
        try:
            os.stat(cfg.workbook(previous))
        except FileNotFoundError:
            return 0.0
        expenses, _ = open_books(cfg, previous)

    credit = next((b["value"] for b in expenses.declaration("Q4")["boxes"] if b["box"] == 96), None)
    if credit is None or not math.isfinite(credit):
        raise ValueError(f"missing or invalid Q4 box 96 in the books for {previous}")
    return credit


def create_year(cfg: Config, year: int, credit: float) -> dict:
    """The year's books, plus its folders for expense and income documents."""
    for folder in (cfg.expenses_dir(year), cfg.income_dir(year)):
        os.makedirs(folder, exist_ok=True)
    exp_name, inc_name = cfg.sheet_name("expenses", year), cfg.sheet_name("income", year)
    if cfg.backend == "google":
        from . import layout
        from .sheet import open_spreadsheet
        return layout.create_year(open_spreadsheet(cfg), year, exp_name, inc_name, opening_credit=credit)
    from .xlsx import create_workbook
    return create_workbook(cfg.workbook(year), year, exp_name, inc_name, opening_credit=credit)
