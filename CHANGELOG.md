# Changelog

New document types are added as they come up. Each entry lists the layouts the release reads.

## 0.7.0

- `plan_inbox`: one deterministic plan for everything in the inbox. It gives expense rows ready to book, sales with
  your invoice paired with its AT document, documents to read, copies, non-invoices and e-Fatura exports.
- Files that do not read like an invoice or receipt are flagged, and their text is not passed on unless you ask.
- Supplier rules match only the supplier's name and VAT number, never the document's text.
- Sales documents go to their own income folder (`paths.income_dir`), created along with the year's books.
- Defaults for every path; card endings keep their leading zeros even when unquoted in the config.
- Clearer file names: the supplier's NIF when no rule names it, and the AT document number for sales without an
  invoice of your own.
- Requires Python 3.12+.

## 0.6.0

- Local Excel workbook (`.xlsx`) as the default place for the books; Google Sheets optional.
- The tools compute every box in Python, mirroring the workbook formulas with spreadsheet rounding. A test
  recalculates a workbook in LibreOffice and compares every box.

## 0.5.0

- `create_year_sheet` / `mcp-invoices-pt init-sheet YEAR`: creates a year's books, carrying the IVA credit over.
- Private parsers folder (`parsers_dir`); example parser for your own sales invoices.

## 0.4.0

- Sales: your invoice + the AT recibo verde / fatura / fatura-recibo, IRS and Segurança Social totals.

## 0.3.0

- Filing documents into the year's folders, missing-documents report, e-Fatura reconciliation, IVA return
  figures, locking a submitted quarter (checked against the return PDF).

## 0.2.0 — layouts

- **Stripe-hosted invoices and receipts** (the layout many software subscriptions are billed with)
- **GitHub** invoices and payment receipts
- **Google Cloud EMEA** invoices
- **Google Play** order receipts
- **Wise** transfer confirmations (fees, with Wise's rate)
- **Amazon EU marketplace** seller invoices (Spanish layout, Amazon.es)

## 0.1.0 — first release

- **AT QR code** on every certified Portuguese invoice, receipt and recibo verde (PDF or photo)
- **e-Fatura CSV export**
- Ledger of handled files, VAT coding, ECB exchange rates
