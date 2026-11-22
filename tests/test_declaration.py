from invoices_pt.declaration import find_return_pdf, parse_return_text

# Shaped like the text of a submitted Declaração Periódica (made-up figures)
RETURN_TEXT = """
06 APURAMENTO DO IMPOSTO RESPEITANTE AO PERÍODO A QUE A DECLARAÇÃO SE REFERE
 À taxa normal de imposto e a outras taxas. 3 210,00 4 48,30
 Operações isentas ou não tributadas que conferem direito à dedução 8 5.432,10
 10 0,00 11 0,00
 Outros bens e serviços 24 61,75
7 - EXCESSO A REPORTAR DO PERÍODO ANTERIOR
 (Campo 96 da Declaração anterior - n.º 4 do Art.º 22.º)
 61
 100,00
 90 5.642,10 91 161,75 92 48,30
 93 0,00 ( 92 - 91 )
 94 113,45 ( 91 - 92 ) TAR», salvo comunicação em contrário da DSR
 EXCESSO A REPORTAR 96 113,45 Valor a inscrever no campo 61 da declaração do período seguinte
 comunitários (não inclui as 97 residentes em países ou 98 210,00
 SOMA DO QUADRO 06-A (97 + .......+ 105 + 107) 106 210,00
"""


def test_parse_return_text():
    b = parse_return_text(RETURN_TEXT)
    assert (b[3], b[4], b[8], b[24], b[98]) == (210.00, 48.30, 5432.10, 61.75, 210.00)
    assert (b[90], b[91], b[92], b[93], b[94], b[96]) == (5642.10, 161.75, 48.30, 0.0, 113.45, 113.45)
    assert b[61] == 100.00        # derived from box 91, since its value is printed apart from its label


def test_derive_opening_credit_after_annex_amounts():
    boxes = parse_return_text("20 5,00 24 10,00 40 3,00 65 21,00 67 13,00 91 152,00")
    assert boxes[61] == 100.0


def test_find_return_pdf(tmp_path):
    for name in ("IVA_2026_1TRI_000_1.pdf", "IVA_2026_Q1_substitution.pdf", "IVA_2026_2TRI_000_2.pdf", "IVA_2026_3TRI.pdf",
                 "notes.pdf"):
        (tmp_path / name).write_bytes(b"%PDF")
    assert find_return_pdf(str(tmp_path), "Q1", 2026).endswith("IVA_2026_Q1_substitution.pdf")
    assert find_return_pdf(str(tmp_path), "Q2", 2026).endswith("IVA_2026_2TRI_000_2.pdf")
    assert find_return_pdf(str(tmp_path), "Q3", 2026).endswith("IVA_2026_3TRI.pdf")
    assert find_return_pdf(str(tmp_path), "Q4", 2026) is None


def test_return_discovery_excludes_other_year_substitutions(tmp_path):
    right = tmp_path / "IVA_2026_Q1.pdf"
    right.touch()
    (tmp_path / "IVA_2025_Q1_SUBSTIT.pdf").touch()
    (tmp_path / "IVA_2026_Q1_SUBSTIT_folder.pdf").mkdir()
    assert find_return_pdf(str(tmp_path), "Q1", 2026) == str(right)
    right.unlink()
    assert find_return_pdf(str(tmp_path), "Q1", 2026) is None


def test_parse_ungrouped_thousands():
    assert parse_return_text("90 12345,67   91 0,00   92 2840,11")[90] == 12345.67


def test_mark_filed_applies_submitted_credit_in_one_save(cfg, monkeypatch):
    from invoices_pt import server
    from invoices_pt.books import create_year, open_books

    create_year(cfg, 2026, 10)
    expenses, income = open_books(cfg, 2026)
    monkeypatch.setattr(server, "_cfg", lambda: cfg)
    monkeypatch.setattr(server, "open_books", lambda *args: (expenses, income))
    monkeypatch.setattr(server, "parse_return_pdf", lambda path: {96: 20})
    save = expenses.book.save
    calls = []

    def save_once(wb):
        calls.append(1)
        assert len(calls) == 1, "filing a return attempted a second save"
        save(wb)

    monkeypatch.setattr(expenses.book, "save", save_once)
    result = server.mark_filed("Q1", 2026, "submitted.pdf", apply_pdf_values=True, dry_run=False)
    assert result["applied_pdf_values"]
    assert expenses.filed_quarters() == {"Q1"}
    q2 = {b["box"]: b["value"] for b in expenses.declaration("Q2")["boxes"]}
    assert q2[61] == 20


def test_mark_filed_leaves_quarter_open_when_submitted_values_are_unavailable(cfg, monkeypatch):
    from invoices_pt import server
    from invoices_pt.books import create_year, open_books

    create_year(cfg, 2026, 10)
    monkeypatch.setattr(server, "_cfg", lambda: cfg)
    monkeypatch.setattr(server, "parse_return_pdf", lambda path: {})
    for pdf in ("", "unreadable.pdf"):
        result = server.mark_filed("Q1", 2026, pdf, apply_pdf_values=True, dry_run=False)
        assert "error" in result
        assert open_books(cfg, 2026)[0].filed_quarters() == set()


def test_comparing_an_unrecognized_pdf_keeps_the_quarter_open(cfg, monkeypatch):
    from invoices_pt import server
    from invoices_pt.books import create_year, open_books

    create_year(cfg, 2026, 0)
    monkeypatch.setattr(server, "_cfg", lambda: cfg)
    # A quantity and price on an unrelated document can look like box 1.
    monkeypatch.setattr(server, "parse_return_pdf", lambda path: {1: 20})
    assert "error" in server.mark_filed("Q1", 2026, "invoice.pdf", dry_run=False)
    assert not open_books(cfg, 2026)[0].filed_quarters()
    assert server.mark_filed("Q1", 2026, dry_run=False)["freeze"]["frozen"]
