"""The local workbook backend, end to end and offline. If LibreOffice is installed, the workbook is also
recalculated by it, to check that the sheet formulas give the same numbers the tools compute in Python."""

import errno
import os
import shutil
import subprocess
from pathlib import Path

import openpyxl
import pytest

from invoices_pt import bookmath, layout
from invoices_pt.books import create_year, open_books, opening_credit
from invoices_pt.config import Config
from invoices_pt.xlsx import WorkbookOpen

from test_live_layout import EXPECTED, PURCHASES, SALES


@pytest.fixture
def books(tmp_path):
    cfg = Config({"taxpayer": {"nif": "999999990"}, "paths": {"year_root": str(tmp_path / "{year}")}})
    create_year(cfg, 2099, 100.0)
    exp, inc = open_books(cfg, 2099)
    for row in PURCHASES:
        assert exp.add(row, dry_run=False)["written"], row
    for row in SALES:
        assert inc.add(row, dry_run=False)["written"], row
    return cfg, exp, inc


def boxes(exp, q):
    return {b["box"]: b["value"] for b in exp.declaration(q)["boxes"]}


def test_workbook_is_created_where_configured(tmp_path):
    cfg = Config({"paths": {"year_root": str(tmp_path / "{year}")}})
    out = create_year(cfg, 2099, 12.5)
    assert out["workbook"] == str(tmp_path / "2099" / "Bookkeeping_2099.xlsx") and os.path.exists(out["workbook"])
    with pytest.raises(FileExistsError):
        create_year(cfg, 2099, 0)
    wb = openpyxl.load_workbook(out["workbook"])
    assert wb.sheetnames[:2] == ["Expenses", "Income"]
    assert wb["Expenses"].cell(layout.EXP_HEADER_ROW, 1).value == "Date"


def test_boxes_and_totals(books):
    _, exp, inc = books
    for q, expected in EXPECTED.items():
        got = boxes(exp, q)
        assert all(abs(got[b] - v) < 0.005 for b, v in expected.items()), (q, got)
    totals = {t["item"][:12]: t for t in inc.summary()}
    assert totals["Gross income"]["Q1"] == 1500.0
    assert (totals["Income € by "]["Q1"], totals["Income € by "]["Q2"]) == (500.0, 1000.0)
    assert [r["quarter"] for r in exp.records()] == ["Q1", "Q1", "Q1", "Q2"]


def test_rows_sorted_duplicates_refused(books):
    _, exp, _ = books
    late = dict(PURCHASES[0], date="2099-01-02", invoice_no="A0")
    assert exp.add(late, dry_run=False)["row"] == layout.EXP_FIRST_ROW        # sorted in before the others
    assert "already in row" in exp.add(dict(PURCHASES[0]), dry_run=True)["error"]
    rec = exp.records()[0]
    assert (rec["invoice_no"], rec["amount"], rec["code"]) == ("A0", 20, "NON-EU-RC")


def test_freeze_locks_quarter_and_keeps_chain(books):
    cfg, exp, inc = books
    assert exp.freeze("Q1", dry_run=False)["frozen"]
    assert exp.filed_quarters() == {"Q1"} and inc.filed_quarters() == {"Q1"}
    assert "locked" in exp.add(dict(PURCHASES[0], invoice_no="late"), dry_run=True)["error"]
    assert exp.declaration("Q1")["filed"] and boxes(exp, "Q1")[96] == 0.0
    # a later correction to a Q1 row (e.g. by hand) no longer changes the filed values
    wb = openpyxl.load_workbook(exp.book.path)
    wb["Expenses"].cell(layout.EXP_FIRST_ROW, 10).value = 999
    wb.save(exp.book.path)
    assert boxes(exp, "Q1")[3] == EXPECTED["Q1"][3]
    assert opening_credit(cfg, 2100) == boxes(exp, "Q4")[96]


def test_refuses_to_write_an_open_workbook(books):
    _, exp, _ = books
    folder, name = os.path.split(exp.book.path)
    open(os.path.join(folder, f".~lock.{name}#"), "w").close()
    with pytest.raises(WorkbookOpen):
        exp.add(dict(PURCHASES[0], invoice_no="B1"), dry_run=False)


@pytest.mark.skipif(not shutil.which("soffice"), reason="LibreOffice not installed")
def test_formulas_agree_with_python(books, tmp_path):
    """Let LibreOffice calculate the workbook and compare its numbers with the tools' (the Python mirror)."""
    _, exp, inc = books
    out = tmp_path / "recalculated"
    subprocess.run(["soffice", "--headless", "--calc", "--convert-to", "xlsx", "--outdir", str(out), exp.book.path],
                   check=True, capture_output=True, timeout=180)
    wb = openpyxl.load_workbook(out / os.path.basename(exp.book.path), data_only=True)
    ws = wb["Expenses"]
    rows = {ws.cell(r, 1).value: r for r in range(1, layout.EXP_HEADER_ROW) if ws.cell(r, 1).value}
    for qi, q in enumerate(bookmath.QUARTERS):
        mine = boxes(exp, q)
        for box, value in mine.items():
            sheet = ws.cell(rows[f"Box {box}"], 5 + qi).value
            assert abs((sheet or 0) - value) < 0.005, (q, box, sheet, value)
    irs_col = [h for h, _, _ in layout.EXPENSE_COLUMNS].index("IRS deductible € (Anexo B)") + 1
    mine_irs = {t["item"][:8]: t for t in inc.summary()}["Business"]
    assert abs(ws.cell(layout.SUMS_ROW + 5, irs_col).value - mine_irs["2099"]) < 0.005
    totals = wb["Income"]
    assert abs(totals.cell(3, 3).value - 1500.0) < 0.005 and abs(totals.cell(4, 4).value - 1000.0) < 0.005
    assert totals.cell(4, 3).value == 500.0  # exclude the December invoice paid next January

def test_old_income_layout_refuses_unsupported_sales_before_writing(tmp_path):
    cfg = Config({"paths": {"year_root": str(tmp_path / "{year}")}})
    create_year(cfg, 2099, 0.0)
    _, inc = open_books(cfg, 2099)
    wb = inc.book.load()
    ws = wb["Income"]
    ws.delete_cols(ws.max_column - 3, 4)  # the last version ended at the Account column
    inc.book.save(wb)

    assert "upgrade" in inc.add(dict(invoice_date="2099-01-01", vat_case="PT / C1"), dry_run=False)["error"]
    assert inc.records() == []
    assert inc.add(dict(invoice_date="2099-01-01", vat_case="PT / C3"), dry_run=False)["written"]


@pytest.mark.parametrize("legacy", ["missing box", "stale total 90", "stale total 92"])
def test_partial_layout_upgrade_cannot_omit_reduced_sale_from_return(tmp_path, legacy):
    cfg = Config({"paths": {"year_root": str(tmp_path / "{year}")}})
    create_year(cfg, 2099, 0.0)
    exp, inc = open_books(cfg, 2099)
    wb = inc.book.load()
    ws = wb["Expenses"]
    boxes, cols = exp._block(ws)
    if legacy == "missing box":
        ws.cell(boxes[1], 1).value = None
    else:
        total = int(legacy.split()[-1])
        old_fields = (3, 7, 8, 12, 16) if total == 90 else (4, 13, 17)
        ws.cell(boxes[total], cols["Q1"]).value = "=" + "+".join(f"E{boxes[b]}" for b in old_fields)
    inc.book.save(wb)
    result = inc.add(dict(invoice_date="2099-01-01", vat_case="PT / C1"), dry_run=False)
    assert "upgrade" in result["error"]
    assert inc.records() == []


def test_failed_workbook_save_leaves_creation_and_update_retryable(cfg, monkeypatch):
    path = Path(cfg.workbook(2026))

    def fail_mid_save(workbook, filename):
        Path(filename).write_bytes(b"unfinished workbook")
        raise OSError("disk full")

    with monkeypatch.context() as patch:
        patch.setattr(openpyxl.Workbook, "save", fail_mid_save)
        with pytest.raises(OSError, match="disk full"):
            create_year(cfg, 2026, 0)
    assert not path.exists()
    create_year(cfg, 2026, 0)
    previous_contents = path.read_bytes()
    previous_files = set(path.parent.iterdir())
    expenses, _ = open_books(cfg, 2026)
    with monkeypatch.context() as patch:
        patch.setattr(openpyxl.Workbook, "save", fail_mid_save)
        with pytest.raises(OSError, match="disk full"):
            expenses.add({"date": "2026-01-05", "invoice_no": "42"}, dry_run=False)
    assert path.read_bytes() == previous_contents
    assert set(path.parent.iterdir()) == previous_files


@pytest.mark.parametrize("hard_links", [True, False])
def test_racing_creators_preserve_existing_workbook(cfg, monkeypatch, hard_links):
    if not hard_links:
        monkeypatch.setattr(os, "link", _unsupported_link)

    path = Path(cfg.workbook(2026))
    save = openpyxl.Workbook.save

    def competitor_finishes_before_save(workbook, filename):
        path.write_bytes(b"winning workbook")
        save(workbook, filename)

    monkeypatch.setattr(openpyxl.Workbook, "save", competitor_finishes_before_save)
    with pytest.raises(FileExistsError):
        create_year(cfg, 2026, 0)
    assert path.read_bytes() == b"winning workbook"


def _unsupported_link(*args):
    raise OSError(errno.ENOTSUP, "hard links unsupported")


@pytest.mark.skipif(os.name == "nt", reason="Windows supports exclusive rename")
def test_creation_without_hard_links_can_retry_failed_publication(cfg, monkeypatch):
    path = Path(cfg.workbook(2026))
    monkeypatch.setattr(os, "link", _unsupported_link)

    def failed_replace(*args):
        raise OSError("drive error")

    with monkeypatch.context() as patch:
        patch.setattr(os, "replace", failed_replace)
        with pytest.raises(OSError, match="drive error"):
            create_year(cfg, 2026, 0)
    assert not path.exists()
    create_year(cfg, 2026, 0)
    assert openpyxl.load_workbook(path).sheetnames[:2] == ["Expenses", "Income"]


def test_backdated_entry_preserves_annotations_and_custom_cells(cfg):
    from openpyxl.comments import Comment
    from openpyxl.styles import PatternFill

    create_year(cfg, 2026, 0)
    exp, _ = open_books(cfg, 2026)
    first = exp.add({"date": "2026-02-01", "invoice_no": "B", "amount": 12}, dry_run=False)["row"]
    wb = exp.book.load()
    ws = wb["Expenses"]
    ws[f"H{first}"].comment = Comment("Checked against paper", "Reviewer")
    ws[f"H{first}"].hyperlink = "https://example.org/invoice/B"
    ws[f"J{first}"].fill = PatternFill("solid", fgColor="FFFFCC00")
    ws[f"AG{first - 1}"] = "My total"
    ws[f"AG{first}"] = f"=J{first}+$J$1"
    ws[f"AH{first}"] = "Unlabelled attachment note"
    ws[f"AG{first+1}"] = "To classify"
    exp.book.save(wb)

    assert exp.add({"date": "2026-01-01", "invoice_no": "A"}, dry_run=False)["row"] == first
    ws = exp.book.load()["Expenses"]
    assert ws[f"H{first}"].comment is None and ws[f"H{first}"].hyperlink is None
    assert ws[f"H{first+1}"].comment.text == "Checked against paper"
    assert ws[f"H{first+1}"].hyperlink.target == "https://example.org/invoice/B"
    assert ws[f"H{first+1}"].hyperlink.ref == f"H{first+1}"
    assert ws[f"J{first+1}"].fill.fgColor.rgb == "FFFFCC00"
    assert ws[f"AG{first+1}"].value == f"=J{first+1}+$J$1"
    assert ws[f"AH{first+1}"].value == "Unlabelled attachment note"
    assert ws[f"AG{first+2}"].value == "To classify"


def test_literal_identifiers_survive_a_sort(cfg):
    create_year(cfg, 2026, 0)
    exp, _ = open_books(cfg, 2026)
    exp.add({"date": "2026-02-01", "invoice_no": "=FT123", "supplier": "#N/A"}, dry_run=False)
    exp.add({"date": "2026-01-01", "invoice_no": "Earlier"}, dry_run=False)
    ws = exp.book.load(data_only=True)["Expenses"]
    first = layout.EXP_FIRST_ROW + 1
    assert (ws[f"H{first}"].value, ws[f"H{first}"].data_type) == ("=FT123", "s")
    assert (ws[f"D{first}"].value, ws[f"D{first}"].data_type) == ("#N/A", "s")


def test_overlapping_sale_and_expense_cannot_overwrite_each_other(cfg, monkeypatch):
    create_year(cfg, 2026, 0)
    expenses, _ = open_books(cfg, 2026)
    _, separate_income_client = open_books(cfg, 2026)
    expense = {"date": "2026-01-10", "invoice_no": "P1"}
    original_save = expenses.book.save

    def commit_sale_first(wb):
        assert separate_income_client.add({"invoice_date": "2026-01-12", "invoice_no": "S1"}, dry_run=False)["written"]
        original_save(wb)

    with monkeypatch.context() as patch:
        patch.setattr(expenses.book, "save", commit_sale_first)
        with pytest.raises(WorkbookOpen, match="changed"):
            expenses.add(expense, dry_run=False)
    assert expenses.records() == []
    assert expenses.add(expense, dry_run=False)["written"]
    assert [r["invoice_no"] for r in separate_income_client.records()] == ["S1"]
    assert [r["invoice_no"] for r in expenses.records()] == ["P1"]


@pytest.mark.skipif(not shutil.which("soffice"), reason="LibreOffice not installed")
def test_workbook_totals_include_entries_past_row_5000(cfg, tmp_path):
    create_year(cfg, 2026, 0)
    expenses, _ = open_books(cfg, 2026)
    wb = expenses.book.load()
    late = 5001
    ws = wb["Income"]
    for header, value in {"Invoice date": bookmath.day("2026-01-07"), "Net € (AT recibo)": 200,
                          "IVA €": 46, "VAT case": "PT / C3", **layout.row_formulas("income", late)}.items():
        idx = [h for h, _, _ in layout.INCOME_COLUMNS].index(header) + 1
        ws.cell(late, idx, value)
    wb.save(expenses.book.path)  # equivalent to entering a new sale directly in the spreadsheet
    output = tmp_path / "recalculated"
    subprocess.run(["soffice", f"-env:UserInstallation={(tmp_path / 'profile').as_uri()}", "--headless",
                    "--convert-to", "xlsx", "--outdir", str(output), expenses.book.path],
                   check=True, capture_output=True, timeout=180)
    calculated = openpyxl.load_workbook(output / Path(expenses.book.path).name, data_only=True)
    assert calculated["Income"]["C3"].value == 200
    box_rows, quarters = expenses._block(calculated["Expenses"])
    assert calculated["Expenses"].cell(box_rows[4], quarters["Q1"]).value == 46


def test_save_upgrades_old_summary_ranges_and_preserves_custom_formulas(cfg, monkeypatch):
    from invoices_pt import xlsx

    with monkeypatch.context() as old:
        old.setattr(xlsx, "END_ROW", 5000)
        create_year(cfg, 2026, 0)
    exp, _ = open_books(cfg, 2026)
    wb = exp.book.load()
    ws = wb["Expenses"]
    boxes, quarters = exp._block(ws)
    ws.cell(boxes[96], quarters["Q1"]).value = 123
    ws["M1"] = "=SUM($J$34:$J$5000)"
    wb.save(exp.book.path)
    assert exp.add({"date": "2026-04-01", "invoice_no": "FT1"}, dry_run=False)["written"]
    saved = exp.book.load()
    assert "$1048576" in saved["Income"]["C3"].value
    assert "$1048576" in saved["Expenses"].cell(boxes[4], quarters["Q2"]).value
    assert saved["Expenses"].cell(boxes[96], quarters["Q1"]).value == 123
    assert saved["Expenses"]["M1"].value == "=SUM($J$34:$J$5000)"


def test_manual_quarter_amounts_survive_declaration_and_filing(cfg):
    create_year(cfg, 2026, 10)
    exp, _ = open_books(cfg, 2026)
    wb = exp.book.load()
    ws = wb["Expenses"]
    rows, quarters = exp._block(ws)
    ws.cell(rows[24], quarters["Q1"]).value = 75
    ws.cell(rows[94], quarters["Q1"]).value = 80
    exp.book.save(wb)
    q1 = boxes(exp, "Q1")
    assert (q1[24], q1[91], q1[94], q1[96]) == (75, 85, 80, 80)
    assert boxes(exp, "Q2")[61] == 80
    assert exp.freeze("Q1", dry_run=False)["frozen"]
    assert boxes(exp, "Q1") == q1 and boxes(exp, "Q2")[61] == 80


@pytest.mark.skipif(os.name != "posix", reason="POSIX file mode")
def test_saving_a_shared_workbook_preserves_its_access_mode(cfg):
    import stat

    create_year(cfg, 2026, 0)
    expenses, _ = open_books(cfg, 2026)
    path = Path(expenses.book.path)
    path.chmod(0o640)
    assert expenses.add({"date": "2026-01-10", "invoice_no": "P1"}, dry_run=False)["written"]
    assert stat.S_IMODE(path.stat().st_mode) == 0o640


def test_existing_caller_can_save_a_workbook_loaded_with_openpyxl(cfg):
    create_year(cfg, 2026, 0)
    exp, _ = open_books(cfg, 2026)
    wb = openpyxl.load_workbook(exp.book.path)
    wb["Expenses"]["D1"] = "Reviewed"
    exp.book.save(wb)
    assert exp.book.load()["Expenses"]["D1"].value == "Reviewed"
