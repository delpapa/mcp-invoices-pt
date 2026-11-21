"""The input fields of each table and the default header they live under (shared by the xlsx and Google backends)."""

EXPENSE_FIELDS = {
    "date": "Date", "expense": "Expense", "supplier": "Supplier", "country": "Country", "supplier_vat": "VAT",
    "invoice_no": "Invoice no.", "currency": "Currency", "amount": "Amount paid", "vat_included": "VAT included",
    "fx": "FX to EUR", "nif": "NIF?", "code": "VAT code", "business_pct": "Business %", "document": "Document",
    "file": "File", "account": "Payment account", "doc_type": "Document type",
}
INCOME_FIELDS = {
    "invoice_date": "Invoice date", "client": "Client", "country": "Country", "client_tax_id": "Client tax ID",
    "invoice_no": "Your invoice no.", "recibo_no": "AT Recibo no.", "recibo_date": "Recibo date",
    "currency": "Currency", "amount": "Amount (orig.)", "fx": "FX (per €)", "net_eur": "Net € (AT recibo)",
    "vat_rate": "IVA %", "vat_eur": "IVA €", "withheld": "IRS withheld €", "vat_case": "VAT case",
    "invoice_file": "Invoice file", "recibo_file": "Recibo file", "account": "Account",
}
TEXT_FIELDS = {"expenses": ("supplier_vat", "invoice_no"), "income": ("client_tax_id", "invoice_no", "recibo_no")}
# Expenses also compare the supplier VAT number when available. Own invoice numbers can repeat when a
# template is not updated, so sales are identified by the AT document number and the invoice file.
UNIQUE = {"expenses": ("invoice_no",), "income": ("recibo_no", "invoice_file")}
DATE_FIELDS = {"date", "invoice_date", "recibo_date"}
NUMBER_FIELDS = {"amount", "vat_included", "fx", "business_pct", "net_eur", "vat_rate", "vat_eur", "withheld"}


def fields(kind: str) -> dict[str, str]:
    return dict(EXPENSE_FIELDS if kind == "expenses" else INCOME_FIELDS)


def table_fields(mapping: dict[str, str], headers: dict[str, int]) -> dict[str, str]:
    """Older expense tables have no document type column; their rows keep the original matching rules."""
    return {field: header for field, header in mapping.items() if field != "doc_type" or header.strip() in headers}


def _identifier(value) -> str:
    return "" if value is None else "".join(str(value).split()).upper()


def find_row(records: list[dict], value, field: str, supplier_vat: str = "", doc_type: str = "") -> int | None:
    """Missing supplier or type on either row is treated as a possible duplicate."""
    wanted = _identifier(value)
    if not wanted:
        return None
    vat = _identifier(supplier_vat)
    kind = _identifier(doc_type)
    for rec in records:
        if _identifier(rec.get(field)) != wanted:
            continue
        if vat and _identifier(rec.get("supplier_vat")) not in ("", vat):
            continue
        if kind and _identifier(rec.get("doc_type")) not in ("", kind):
            continue
        return rec["row"]
    return None
