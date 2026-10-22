import datetime as dt

from invoices_pt.model import Document
from invoices_pt.report import missing, monthly_gaps, reconcile_efatura


def rec(row, date, supplier, amount, invoice_no="", document="PDF invoice", file="", vat="", supplier_vat="",
        expense=""):
    return dict(row=row, date=date, supplier=supplier, amount=amount, invoice_no=invoice_no, document=document,
                file=file, vat_included=vat, supplier_vat=supplier_vat, expense=expense or supplier)


def test_monthly_gaps():
    rows = [rec(m, f"01.{m:02d}.2026", "Phone Co", "10.00", f"F{m}") for m in (1, 2, 3, 5, 6)]
    rows.append(rec(9, "08.01.2026", "One-off", "5.00", "X"))
    assert monthly_gaps(rows) == [{"supplier": "Phone Co", "missing_months": ["2026-04"]}]


def test_missing(tmp_path):
    (tmp_path / "a.pdf").write_bytes(b"x")
    (tmp_path / "receipt.pdf").write_bytes(b"x")
    (tmp_path / "stray.pdf").write_bytes(b"x")
    rows = [rec(31, "01.01.2026", "A", "10.00", "F1", file="a.pdf"),
            rec(32, "02.01.2026", "B", "20.00", "F2", file="gone.pdf"),
            rec(33, "", "C", "", document="MISSING (no data yet)"),
            rec(34, "03.01.2026", "D", "5.00", document="No invoice"),
            rec(35, "04.01.2026", "E", "7.00")]

    def read(path):
        return Document(layer="t", date=dt.date(2026, 1, 2), amount=20.0) if path.endswith("receipt.pdf") else \
            Document(layer="t", date=dt.date(2026, 3, 3), amount=1.0)

    out = missing(rows, str(tmp_path), read=read)
    assert out["flagged"] == ["row 33  C"]
    assert out["file_not_found"] == ["row 32 02.01.2026 B: gone.pdf"]
    assert out["incomplete"] == ["row 35 04.01.2026 E: no invoice_no"]
    assert out["companion_files"] == ["receipt.pdf (same payment as row 32)"]
    assert out["unbooked_files"] == ["stray.pdf"]


def test_reconcile_efatura():
    rows = [rec(31, "04.03.2026", "Café", "8.70", "FS 1/10", vat="1.00", supplier_vat="PT500000002"),
            rec(32, "05.03.2026", "Shop", "45.00", "", supplier_vat="PT500000004"),
            rec(33, "09.03.2026", "Landlord", "500.00", "FR 9", supplier_vat="PT500000005")]
    docs = [Document(layer="efatura", date=dt.date(2026, 3, 4), invoice_no="FS 1/10", amount=8.70, vat_included=1.00),
            Document(layer="efatura", date=dt.date(2026, 3, 5), invoice_no="FS 7/1", amount=45.00, vat_included=2.55),
            Document(layer="efatura", date=dt.date(2026, 3, 7), supplier="New Shop", invoice_no="FS 8/1", amount=4.0,
                     vat_included=0.75)]
    out = reconcile_efatura(docs, rows)
    assert [d["invoice_no"] for d in out["not_in_sheet"]] == ["FS 8/1"]
    assert [d["row"] for d in out["differences"]] == [32]
    assert out["pt_rows_not_in_efatura"] == ["row 33 09.03.2026 Landlord 500.00"]
