"""MCP server: the tools Claude calls to organize the invoices of a Portuguese freelancer."""

from __future__ import annotations

import datetime as dt
import os

from mcp.server.mcpserver import MCPServer

from . import __version__, report, vat
from .config import Config
from .declaration import find_return_pdf, parse_return_pdf
from . import inbox
from .documents import efatura, text
from .extract import expense_row, proposal, read_document
from .filing import file_document as file_document_
from .filing import index_folder
from .income import propose as propose_income_
from .ledger import Ledger, sha256
from .books import create_year, open_books, where
from .books import opening_credit as opening_credit_

INSTRUCTIONS = """\
Organize a Portuguese freelancer's invoices for the quarterly IVA return and yearly IRS.

"Organize my receipts" routine:
1. plan_inbox. It reads everything in the inbox and returns, without writing anything: expense rows ready to book,
   sales (your invoice paired with the AT recibo verde / fatura issued on the Portal), documents you must read
   yourself (needs_reading), copies, files that are not invoices, and e-Fatura exports.
2. Summarise the plan for the user in a few lines and ask about anything in `checks` or any judgment call
   (business or personal, deductibility). Never read files listed as not_invoices unless the user asks.
3. For each expense: file_document(path, name=file_name, dry_run=false), then add_expense(row, dry_run=false).
   For each sale: file_document for each document under its file_names, then add_income(row, dry_run=false).
   For needs_reading: extract, read the text, fill the row yourself, then the same; suggest adding a parser.
   For copies: file_document deletes the download when it is a copy of a filed document.
4. e-Fatura export: reconcile_efatura; ask the user which invoices missing from the books are business; then
   file_document to keep the export in the year folder.
5. missing for the year, and report it.
When the user says a quarter was submitted: mark_filed (it checks the submitted return PDF if it is saved).
vat_return gives the boxes to type for a quarter; income_totals the IRS / Segurança Social figures.
All tools that change something default to dry_run=true. Personal rules come from the private config file."""

mcp = MCPServer("invoices-pt", instructions=INSTRUCTIONS, version=__version__)


def _cfg() -> Config:
    return Config.load()


def _ledger(cfg: Config) -> Ledger:
    return Ledger(cfg.paths(dt.date.today().year)["ledger"])


@mcp.tool()
def scan_inbox() -> list[dict]:
    """List the files in the inbox folder (PDFs, images, e-Fatura CSVs), newest first: kind (document,
    not_an_invoice, efatura_export), whether a PDF reads like an invoice, its status in the ledger (new, extracted,
    filed) and whether it is an exact copy of another inbox file."""
    cfg = _cfg()
    return inbox.scan(cfg, _ledger(cfg))


@mcp.tool()
def plan_inbox() -> dict:
    """Read everything in the inbox and return the plan, without writing anything: expense rows ready for
    add_expense (with the file name for file_document and any `checks` to resolve), sales ready for add_income
    (your invoice paired with its AT document), documents to read yourself, copies, non-invoices, e-Fatura exports."""
    cfg = _cfg()
    return inbox.plan(cfg, _ledger(cfg))


@mcp.tool()
def extract(path: str, read_anyway: bool = False) -> dict:
    """Read one invoice or receipt (PDF or photo). Returns the document fields, which layer read them
    (qr / parser:<name> / text), a booking proposal (VAT code, region, ECB rate, payment account, business share,
    document label, file name) and a ready expense row. If a PDF does not read like an invoice or receipt, its text
    is withheld unless read_anyway=true, so unrelated documents are not exposed."""
    cfg = _cfg()
    doc = read_document(path)
    ledger = _ledger(cfg)
    digest = sha256(path)
    others = [r for r in ledger.by_key(doc.key) if r["sha256"] != digest] if doc.invoice_no else []
    ledger.record(digest, path, doc.key, doc.layer, "extracted")
    out = {"document": doc.to_dict(), "proposal": proposal(doc, cfg), "same_invoice_elsewhere": others}
    if doc.layer == "text":
        looks = text.looks_like_invoice(doc.text)
        out["looks_like_invoice"] = looks
        if looks is False and not read_anyway:
            out["document"].pop("text", None)
            out["warning"] = "this does not read like an invoice or receipt; its text was withheld (read_anyway=true)"
    else:
        out["row"] = expense_row(doc, out["proposal"])
    return out


@mcp.tool()
def read_efatura(csv_path: str) -> list[dict]:
    """Parse an e-Fatura CSV export into documents, each with a booking proposal."""
    cfg = _cfg()
    return [{"document": d.to_dict(), "proposal": proposal(d, cfg)} for d in efatura.parse_csv(csv_path)]


@mcp.tool()
def add_expense(row: dict, dry_run: bool = True) -> dict:
    """Add one expense row to the year's expenses tab. `row` keys: date (YYYY-MM-DD), expense, supplier,
    country, supplier_vat, invoice_no, currency, amount, vat_included, fx, nif, code, business_pct, document,
    file, account. Refuses duplicates and quarters already filed. Call with dry_run=true first."""
    cfg = _cfg()
    year = dt.date.fromisoformat(str(row["date"])).year
    return open_books(cfg, year)[0].add(row, dry_run=dry_run)


@mcp.tool()
def index_year(year: int) -> dict:
    """Read every document already in the year's folders into the ledger, so later copies are recognised.
    Run it once per year (and again after moving files by hand)."""
    cfg = _cfg()
    ledger = _ledger(cfg)
    return {folder: index_folder(folder, ledger) for folder in (cfg.expenses_dir(year), cfg.income_dir(year))
            if os.path.isdir(folder)}


@mcp.tool()
def file_document(path: str, name: str = "", dry_run: bool = True) -> dict:
    """Move a document from the inbox into its tax-year folder under the proposed name (or `name`).
    If the same file or the same invoice is already filed, the inbox copy is deleted instead. Never overwrites
    and never deletes outside the inbox. e-Fatura CSV exports go to the year folder. Dry run first."""
    cfg = _cfg()
    return file_document_(cfg, _ledger(cfg), path, name=name, dry_run=dry_run)


@mcp.tool()
def missing(year: int) -> dict:
    """What is still missing for a year: rows flagged MISSING, rows whose file is not in the folder, rows without
    a date, amount or invoice number, files in the folder no row books (and receipts that duplicate a booked
    payment), and months missing in monthly subscriptions. For income: sales without an AT document yet,
    missing files and unbooked files."""
    cfg = _cfg()
    folder, income_folder = cfg.expenses_dir(year), cfg.income_dir(year)
    if not os.path.isdir(cfg.paths(year)["year_root"]):
        return {"error": f"{cfg.paths(year)['year_root']} does not exist: nothing set up for {year} yet "
                         "(create_year_sheet), or the drive it lives on is not mounted"}
    expenses, income = open_books(cfg, year)
    return {"expenses": report.missing(expenses.records(), folder, read=read_document),
            "income": report.missing_income(income.records(), income_folder)}
    return out


@mcp.tool()
def propose_income(invoice_path: str = "", at_document_path: str = "") -> dict:
    """Read one sale: your own invoice and/or the AT document issued on the Portal (recibo verde, fatura or
    fatura-recibo). Returns the income row (client, tax id, recibo no. and date, amount, rate, IVA, withholding,
    VAT case), the file names to file both under, and checks that the two documents belong together."""
    cfg = _cfg()
    invoice = read_document(invoice_path) if invoice_path else None
    at_doc = read_document(at_document_path) if at_document_path else None
    return propose_income_(cfg, invoice, at_doc)


@mcp.tool()
def add_income(row: dict, dry_run: bool = True) -> dict:
    """Add one sale to the year's income tab. `row` keys: invoice_date (YYYY-MM-DD), client, country,
    client_tax_id, invoice_no, recibo_no, recibo_date, currency, amount, fx, net_eur, vat_rate, vat_eur, withheld,
    vat_case, invoice_file, recibo_file, account. Refuses duplicates and filed quarters. Dry run first."""
    cfg = _cfg()
    year = dt.date.fromisoformat(str(row["invoice_date"])).year
    return open_books(cfg, year)[1].add(row, dry_run=dry_run)


@mcp.tool()
def income_totals(year: int) -> list[dict]:
    """The IRS and Segurança Social totals at the top of the income tab, per quarter and for the year:
    gross income by invoice date (IRS), income by recibo date (Segurança Social quarterly declaration), and
    business expenses."""
    return open_books(_cfg(), year)[1].summary()


@mcp.tool()
def reconcile_efatura(csv_path: str, year: int) -> dict:
    """Compare an e-Fatura CSV export with the expenses tab: invoices not in the sheet, rows whose amount,
    VAT or invoice number differ (or that lack fields e-Fatura has), and Portuguese rows e-Fatura lacks."""
    cfg = _cfg()
    docs = [d for d in efatura.parse_csv(csv_path) if d.date and d.date.year == year]
    return report.reconcile_efatura(docs, open_books(cfg, year)[0].records())


@mcp.tool()
def vat_return(quarter: str, year: int) -> dict:
    """The Declaração Periódica boxes for a quarter (Q1-Q4) as the sheet shows them, including the credit
    carried over (box 61) and the result boxes 90-96, and whether the quarter is already filed."""
    return open_books(_cfg(), year)[0].declaration(quarter.upper())


@mcp.tool()
def mark_filed(quarter: str, year: int, return_pdf: str = "", dry_run: bool = True,
               apply_pdf_values: bool = False) -> dict:
    """After the user submits a quarter: freeze its declaration values, grey them and lock (warning-only) the
    quarter's block column, expense rows and income rows. If the submitted return PDF is in the year folder
    (or given), its boxes are compared with the sheet; apply_pdf_values=true copies the PDF's values over the
    frozen ones, since the submitted return is the source of truth. Dry run first."""
    cfg = _cfg()
    q = quarter.upper()
    sheet = open_books(cfg, year)[0]
    shown = {b["box"]: b["value"] for b in sheet.declaration(q)["boxes"]}
    pdf = return_pdf or find_return_pdf(cfg.paths(year)["year_root"], q, year)
    diffs = []
    if pdf:
        submitted = parse_return_pdf(pdf)
        diffs = [{"box": b, "sheet": shown[b], "submitted": v} for b, v in sorted(submitted.items())
                 if b in shown and abs((shown[b] or 0) - v) > 0.005]
    result = {"freeze": sheet.freeze(q, dry_run=dry_run), "return_pdf": pdf or "not found", "differences": diffs}
    if diffs and apply_pdf_values and not dry_run:
        sheet.set_declaration(q, {d["box"]: d["submitted"] for d in diffs})
        result["applied_pdf_values"] = True
    return result


@mcp.tool()
def vat_codes() -> dict:
    """The purchase and sales VAT codes the sheet understands, and which return boxes each one fills."""
    return {"purchases": vat.CODES, "sales": vat.SALES_CODES}


@mcp.tool()
def create_year_sheet(year: int, opening_credit: float | None = None, dry_run: bool = True) -> dict:
    """Create a tax year's books: a local .xlsx workbook (default) or tabs in a Google Sheet, per the config.
    Expenses and income tables with the Declaração Periódica block (what to type each quarter, with the credit
    carried over), quarter sums, IRS / Segurança Social totals, formulas, dropdowns and formats. The opening credit
    (Q1 box 61) defaults to the previous year's Q4 box 96. Refuses to overwrite."""
    cfg = _cfg()
    credit = opening_credit_(cfg, year) if opening_credit is None else opening_credit
    if dry_run:
        return {"dry_run": True, "backend": cfg.backend, "where": where(cfg, year), "opening_credit": credit}
    return create_year(cfg, year, credit)


def main() -> None:
    """`mcp-invoices-pt` runs the MCP server (stdio). `mcp-invoices-pt init-sheet YEAR [OPENING_CREDIT]` creates
    a year's tabs instead."""
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "init-sheet":
        year = int(sys.argv[2])
        credit = float(sys.argv[3]) if len(sys.argv) > 3 else None
        print(create_year_sheet(year, credit, dry_run=False))
        return
    mcp.run()


if __name__ == "__main__":
    main()
