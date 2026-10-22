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


def test_find_return_pdf(tmp_path):
    for name in ("IVA_2026_1TRI_000_1.pdf", "IVA_2026_Q1_substitution.pdf", "IVA_2026_2TRI_000_2.pdf", "IVA_2026_3TRI.pdf",
                 "notes.pdf"):
        (tmp_path / name).write_bytes(b"%PDF")
    assert find_return_pdf(str(tmp_path), "Q1", 2026).endswith("IVA_2026_Q1_substitution.pdf")
    assert find_return_pdf(str(tmp_path), "Q2", 2026).endswith("IVA_2026_2TRI_000_2.pdf")
    assert find_return_pdf(str(tmp_path), "Q3", 2026).endswith("IVA_2026_3TRI.pdf")
    assert find_return_pdf(str(tmp_path), "Q4", 2026) is None
