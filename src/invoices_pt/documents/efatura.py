"""e-Fatura export: Portal das Finanças > e-Fatura > Adquirente > Verificar faturas > export (CSV)."""

from __future__ import annotations

import csv
import datetime as dt

from ..model import Document

DOC_TYPES = {"Fatura": "invoice", "Fatura simplificada": "simplified_invoice", "Fatura-recibo": "invoice_receipt",
             "Nota de crédito": "credit_note", "Nota de débito": "debit_note"}
HEADER = "Nº Fatura / ATCUD"


def _eur(s: str) -> float:
    """'1.234,56 €' -> 1234.56"""
    return float(s.replace("€", "").replace("\xa0", "").replace(" ", "").replace(".", "").replace(",", "."))


def is_export(path: str) -> bool:
    try:
        with open(path, encoding="utf-8-sig") as f:
            return HEADER in f.readline()
    except (OSError, UnicodeDecodeError):
        return False


def parse_csv(path: str) -> list[Document]:
    with open(path, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f, delimiter=";"))
    docs = []
    for r in rows:
        number, _, atcud = r[HEADER].partition(" / ")
        nif, _, name = r["Emitente"].partition(" - ")
        kind = DOC_TYPES.get(r["Tipo"].strip(), r["Tipo"].strip())
        sign = -1 if kind == "credit_note" else 1   # the export shows credit notes as positive totals
        docs.append(Document(
            layer="efatura",
            doc_type=kind,
            date=dt.date.fromisoformat(r["Data Emissão"].strip()),
            supplier=name.strip(),
            supplier_vat="PT" + nif.strip(),
            country="PT",
            invoice_no=number.strip(),
            atcud=atcud.strip(),
            amount=sign * _eur(r["Total"]),
            vat_included=sign * _eur(r["IVA"]),
            extra={"base": sign * _eur(r["Base Tributável"]), "sector": r["Setor"].strip(),
                   "status": r["Situação"].strip()},
        ))
    return docs
