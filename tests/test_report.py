import datetime as dt
from pathlib import Path

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


def test_reconcile_same_number_and_payment_from_different_suppliers():
    day = dt.date(2026, 3, 4)
    suppliers = ["PT500000001", "PT500000002", "PT500000003"]
    docs = [Document(layer="efatura", date=day, invoice_no="FT 1", amount=10, vat_included=1,
                     supplier_vat=vat, supplier=name) for vat, name in zip(suppliers, ("Café A", "Café B", "Café C"))]
    rows = [rec(31, day.isoformat(), "Café A", "10", "ft1", vat="1", supplier_vat=suppliers[0]),
            rec(32, day.isoformat(), "Café B", "10", "FT 1", vat="1", supplier_vat=suppliers[1])]
    for entries in (docs, docs[::-1]):
        report = reconcile_efatura(entries, rows)
        assert [d["supplier"] for d in report["not_in_sheet"]] == ["Café C"]
        assert report["differences"] == []
        assert report["pt_rows_not_in_efatura"] == []


def test_reconcile_reserves_number_match_before_payment_fallback():
    day = dt.date(2026, 3, 4)
    docs = [Document(layer="efatura", date=day, invoice_no=number, amount=10, vat_included=1, supplier_vat="PT1")
            for number in ("FT 7", "FT 8")]
    rows = [rec(31, day.isoformat(), "Shop", "10", "FT 8", vat="1", supplier_vat="PT1")]
    report = reconcile_efatura(docs, rows)
    assert [d["invoice_no"] for d in report["not_in_sheet"]] == ["FT 7"]
    assert report["differences"] == []


def test_reconcile_leaves_ambiguous_legacy_rows_for_review():
    day = dt.date(2026, 3, 4)
    # Legacy expense rows may have no supplier VAT or invoice number.
    rows = [rec(31, day.isoformat(), "Shop A", "10"), rec(32, day.isoformat(), "Shop B", "10")]
    doc = Document(layer="efatura", date=day, invoice_no="FT 1", supplier_vat="PT1", amount=10, vat_included=1)
    report = reconcile_efatura([doc], rows)
    assert [d["invoice_no"] for d in report["not_in_sheet"]] == ["FT 1"]
    assert report["differences"] == []


def test_reconcile_rejects_a_unique_candidate_with_a_different_supplier_vat():
    doc = Document(layer="efatura", date=dt.date(2026, 1, 1), invoice_no="FT 1",
                   supplier_vat="PT500000001", amount=10, vat_included=1)
    row = rec(31, "01.01.2026", "Other", "10", "FT 1", vat="1", supplier_vat="PT500000002")
    report = reconcile_efatura([doc], [row])
    assert [d["invoice_no"] for d in report["not_in_sheet"]] == ["FT 1"]
    assert report["pt_rows_not_in_efatura"] == ["row 31 01.01.2026 Other 10"]


def test_reconcile_treats_xlsx_numeric_zero_as_recorded_vat():
    doc = Document(layer="efatura", date=dt.date(2026, 1, 1), invoice_no="FT 1",
                   supplier_vat="PT1", amount=10, vat_included=0)
    row = rec(31, "01.01.2026", "Shop", 10, "FT 1", vat=0, supplier_vat="PT1")
    assert reconcile_efatura([doc], [row])["differences"] == []
    doc.vat_included = 1.0
    assert reconcile_efatura([doc], [row])["differences"][0]["issues"] == ["VAT 0 vs 1.0"]


def test_reconcile_different_document_types_are_distinct():
    day = dt.date(2026, 1, 1)
    docs = [Document(layer="efatura", date=day, invoice_no="1", supplier_vat="PT1",
                     amount=0, vat_included=0, doc_type=kind) for kind in ("invoice", "credit_note")]
    row = dict(rec(31, day.isoformat(), "Shop", 0, "1", vat=0, supplier_vat="PT1"), doc_type="credit_note")
    report = reconcile_efatura(docs, [row])
    assert len(report["not_in_sheet"]) == 1
    assert report["pt_rows_not_in_efatura"] == []
    assert len(reconcile_efatura(docs[:1], [row])["not_in_sheet"]) == 1


def test_missing_does_not_hide_unrelated_or_ambiguous_documents(tmp_path):
    day = dt.date(2026, 1, 2)
    rows = [dict(rec(31, day.isoformat(), "Market", 20, "A1", supplier_vat="PT1"), currency="EUR", doc_type="invoice"),
            dict(rec(32, day.isoformat(), "Cafe", 20, "B1", supplier_vat="PT2"), currency="EUR", doc_type="invoice"),
            rec(33, day.isoformat(), "Zero", 0, "C1")]
    docs = {
        "ambiguous.pdf": Document("t", date=day, amount=20),
        "other_supplier.pdf": Document("t", date=day, amount=20, supplier_vat="PT3"),
        "other_currency.pdf": Document("t", date=day, amount=20, supplier="Cafe", currency="USD"),
        "different_invoice.pdf": Document("t", date=day, amount=20, supplier_vat="PT1", doc_type="invoice", invoice_no="A2"),
        "credit.pdf": Document("t", date=day, amount=20, supplier_vat="PT1", doc_type="credit_note", invoice_no="A1"),
        "unknown_amount.pdf": Document("t", date=day),
        "receipt.pdf": Document("t", date=day, amount=20, supplier_vat="PT2", doc_type="receipt", invoice_no="R1")}
    for name in docs:
        (tmp_path / name).touch()
    for order in (rows, rows[::-1]):
        result = missing(order, str(tmp_path), read=lambda path: docs[Path(path).name])
        assert result["companion_files"] == ["receipt.pdf (same payment as row 32)"]
        assert result["unbooked_files"] == sorted(docs.keys() - {"receipt.pdf"})


def test_reports_require_real_files_and_keep_zero_amounts(tmp_path):
    from invoices_pt.report import missing_income

    (tmp_path / "fake.pdf").mkdir()
    rows = [rec(1, "2026-01-01", "Shop", None, file="fake.pdf"),
            rec(2, "2026-01-02", "Zero", 0, invoice_no="Z1")]
    result = missing(rows, str(tmp_path))
    assert result["file_not_found"] == ["row 1 2026-01-01 Shop: fake.pdf"]
    assert result["incomplete"] == ["row 1 2026-01-01 Shop: no amount, invoice_no"]
    income = dict(row=1, invoice_date="2026-01-01", client="X", invoice_no="1", recibo_no="2",
                  invoice_file="fake.pdf", recibo_file="")
    assert missing_income([income], str(tmp_path))["file_not_found"] == ["row 1 2026-01-01 X 1: fake.pdf"]


def test_cancelled_exports_do_not_create_missing_invoices_or_hide_active_ones():
    date = dt.date(2026, 2, 10)
    def entry(number, status):
        return Document("efatura", date=date, invoice_no=number, supplier_vat="PT1", amount=11, vat_included=1,
                        extra={"status": status})
    active, cancelled = entry("1", "Registado"), entry("1", "Anulado")
    row = rec(31, date.isoformat(), "Shop", 11, "1", vat=1, supplier_vat="PT1")
    assert reconcile_efatura([cancelled], [])["not_in_sheet"] == []
    assert reconcile_efatura([cancelled, active], [row])["differences"] == []
    diff = reconcile_efatura([cancelled], [row])["differences"]
    assert [item["row"] for item in diff] == [31] and "cancelled" in diff[0]["issues"][0].lower()
