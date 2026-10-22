"""The input fields of each table and the default header they live under (shared by the xlsx and Google backends)."""

EXPENSE_FIELDS = {
    "date": "Date", "expense": "Expense", "supplier": "Supplier", "country": "Country", "supplier_vat": "VAT",
    "invoice_no": "Invoice no.", "currency": "Currency", "amount": "Amount paid", "vat_included": "VAT included",
    "fx": "FX to EUR", "nif": "NIF?", "code": "VAT code", "business_pct": "Business %", "document": "Document",
    "file": "File", "account": "Payment account",
}
INCOME_FIELDS = {
    "invoice_date": "Invoice date", "client": "Client", "country": "Country", "client_tax_id": "Client tax ID",
    "invoice_no": "Your invoice no.", "recibo_no": "AT Recibo no.", "recibo_date": "Recibo date",
    "currency": "Currency", "amount": "Amount (orig.)", "fx": "FX (per €)", "net_eur": "Net € (AT recibo)",
    "vat_rate": "IVA %", "vat_eur": "IVA €", "withheld": "IRS withheld €", "vat_case": "VAT case",
    "invoice_file": "Invoice file", "recibo_file": "Recibo file", "account": "Account",
}
TEXT_FIELDS = {"expenses": ("supplier_vat", "invoice_no"), "income": ("client_tax_id", "invoice_no", "recibo_no")}
# Fields that identify a row; a second row with the same value is refused. Own invoice numbers can repeat when a
# template is not updated, so sales are identified by the AT document number and the invoice file.
UNIQUE = {"expenses": ("invoice_no",), "income": ("recibo_no", "invoice_file")}
DATE_FIELDS = {"date", "invoice_date", "recibo_date"}
NUMBER_FIELDS = {"amount", "vat_included", "fx", "business_pct", "net_eur", "vat_rate", "vat_eur", "withheld"}


def fields(kind: str) -> dict[str, str]:
    return dict(EXPENSE_FIELDS if kind == "expenses" else INCOME_FIELDS)
