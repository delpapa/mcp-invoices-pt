import datetime as dt

from invoices_pt.documents import efatura

CSV = (
    '﻿"Setor";"Emitente";"Nº Fatura / ATCUD";"Tipo";"Data Emissão";"Total";"IVA";"Base Tributável";'
    '"Situação";"Comunicação  Emitente";"Comunicação  Adquirente"\n'
    '"Alojamento, restauração e similares";"500000002 - Café Exemplo Lda";"FS 1/10 / JJJJ-10";'
    '"Fatura simplificada";"2026-03-04";"8,70 €";"1,00 €";"7,70 €";"Registado";"X";""\n'
    '"Outros";"500000003 - Banco Exemplo";"NC 9/7 / KKKK-7";"Nota de crédito";"2026-04-14";'
    '"1.250,00 €";"0,00 €";"1.250,00 €";"Registado";"X";""\n'
)


def test_parse_export(tmp_path):
    path = tmp_path / "e-fatura.csv"
    path.write_text(CSV, encoding="utf-8")
    assert efatura.is_export(str(path))
    meal, credit = efatura.parse_csv(str(path))
    assert meal.supplier == "Café Exemplo Lda"
    assert meal.supplier_vat == "PT500000002"
    assert (meal.invoice_no, meal.atcud) == ("FS 1/10", "JJJJ-10")
    assert meal.date == dt.date(2026, 3, 4)
    assert (meal.amount, meal.vat_included) == (8.70, 1.00)
    assert meal.extra["sector"].startswith("Alojamento")
    assert credit.doc_type == "credit_note"
    assert credit.amount == -1250.00


def test_other_csv_is_not_an_export(tmp_path):
    path = tmp_path / "other.csv"
    path.write_text("a;b\n1;2\n")
    assert not efatura.is_export(str(path))
