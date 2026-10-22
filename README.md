# mcp-invoices-pt

**Invoice bookkeeping for freelancers in Portugal, done with an AI assistant.**

You keep downloading invoices and receipts as you do today. Then you ask your assistant *"organize my receipts"*,
and it:

- reads each document,
- files it in a folder per tax year, under a consistent name,
- books it in an Excel workbook (or a Google Sheet, if you prefer),
- works out what goes into each box of the quarterly IVA return (*Declaração Periódica*), including the credit
  carried over from the previous quarter,
- keeps the totals you need for IRS and the quarterly Segurança Social declaration,
- and tells you what is still missing.

Technically it is an [MCP](https://modelcontextprotocol.io) server: a set of tools that an AI assistant such as
Claude runs on your computer.

> **Not tax advice.** This is a bookkeeping aid. Check the figures before you submit anything, and ask a
> certified accountant (contabilista certificado) when in doubt.

> **Updated regularly.** New invoice and receipt layouts are added as they come up. See
> [Supported documents](#supported-documents) and the [CHANGELOG](CHANGELOG.md). If yours is not read yet, open an
> issue with a redacted sample, or [add it yourself](#adding-a-document-type).

---

## Contents

1. [Quick start](#quick-start)
2. [Who it is for](#who-it-is-for)
3. [Supported documents](#supported-documents)
4. [How it reads documents](#how-it-reads-documents)
5. [Your folders and books](#your-folders-and-books)
6. [Setup in detail](#setup-in-detail)
7. [Day-to-day use](#day-to-day-use)
8. [Tools reference](#tools-reference)
9. [Safety](#safety)
10. [Privacy: public code, private data](#privacy-public-code-private-data)
11. [Adding a document type](#adding-a-document-type)
12. [Tests](#tests)
13. [Limitations](#limitations)
14. [License](#license)

---

## Quick start

**You need:**
- **Claude Desktop** (macOS or Windows) or **Claude Code**, or another app that supports MCP servers;
- **Python 3.12 or newer**;
- **poppler**, a small free tool for reading PDFs.

It is tested on Linux and should work the same on macOS. Windows is untested.

1. **Install poppler and pipx**, then the tools:

   ```bash
   # macOS (with Homebrew):  brew install poppler pipx
   # Ubuntu / Debian:        sudo apt install poppler-utils pipx
   pipx install "git+https://github.com/delpapa/mcp-invoices-pt"
   ```

2. **Write your settings.** Download [`config.example.yaml`](config.example.yaml), save it as
   `~/.config/mcp-invoicesPT/config.yaml`, and put your **NIF** in it. Every other setting has a sensible default:
   - documents arrive in `~/Downloads`;
   - each tax year lives in `~/Taxes/<year>`;
   - the books are an Excel file inside that folder.

3. **Create this year's books:**

   ```bash
   mcp-invoices-pt init-sheet 2026
   ```

   This creates `~/Taxes/2026/` with `Expenses/`, `Income/` and `Bookkeeping_2026.xlsx`.

4. **Connect it to your assistant.**
   - **Claude Code:** `claude mcp add --scope user invoices-pt -- mcp-invoices-pt`
   - **Claude Desktop:** see [Connect to your assistant](#4-connect-to-your-assistant).

5. **Download a few invoices and ask:** *"organize my receipts"*.

---

## Who it is for

A **trabalhador independente** (freelancer issuing recibos verdes) who:

- is in the **normal VAT regime** (not the art. 53.º exemption) and files the **quarterly** Declaração Periódica;
- buys from Portuguese suppliers and from abroad (EU and non-EU software, cloud services, online shops);
- sells to clients in Portugal, the EU or outside it;
- uses **e-Fatura** and the **Portal das Finanças** (recibos verdes).

The usual cross-border cases are handled:
- reverse charge (autoliquidação) on EU and non-EU services;
- intra-EU purchases of goods;
- foreign suppliers who charged you Portuguese or foreign VAT (OSS);
- non-deductible IVA (meals, transport);
- partial business use, e.g. 30% of home rent;
- sales to clients in the EU (box 7) and outside it (box 8).

## Supported documents

**Portuguese documents, from any issuer** (read from the official AT QR code):
- Fatura (FT), fatura simplificada (FS), fatura-recibo (FR), nota de crédito (NC), nota de débito (ND), and
  recibo (RG/RC). That covers telecoms, utilities, landlords, shops and restaurants: anything issued by certified
  software.
- PDFs, or a photo of the paper receipt.
- The recibos verdes, faturas and faturas-recibo **you** issue on the Portal das Finanças.
- The **e-Fatura** CSV export, for invoices that only exist there.
- Your **submitted Declaração Periódica** PDF, used to check and lock a quarter you have filed.

**Foreign layouts** (one parser each):

| Parser | Covers | Notes |
|---|---|---|
| `stripe` | Invoices and receipts hosted by Stripe, the layout many software and AI subscriptions are billed with | Supplier, country, VAT numbers (yours and theirs), totals, VAT charged, card ending |
| `github` | GitHub invoices and payment receipts | |
| `google_cloud` | Google Cloud EMEA invoices | |
| `google_play` | Google Play order receipts (the e-mail saved as PDF) | |
| `wise` | Wise transfer confirmations | The expense is the fee, at Wise's own exchange rate |
| `amazon` | Amazon EU marketplace invoices issued by the seller (Spanish layout, Amazon.es) | Intra-EU goods: reverse charge |

**Your own sales invoices.** If you also issue invoices of your own besides the Portal document, there is an
example parser for a common template in [`examples/parsers/simple_invoice.py`](examples/parsers/simple_invoice.py).
Copy it into your private parsers folder and adapt it.

**Anything else** still works: the assistant reads the text itself. Once a layout is added as a parser, it no
longer needs to.

## How it reads documents

Each document goes through these layers in order, and the first one that works wins:

| Layer | What | AI needed? |
|---|---|---|
| 1. **AT QR code** | Every invoice from certified Portuguese software and every recibo verde has one (Portaria 195/2020). It holds the NIFs, date, number, ATCUD, and base and IVA per rate. | No |
| 2. **Layout parsers** | One small module per invoice layout (list above). | No |
| 3. **e-Fatura export** | The CSV from e-Fatura. | No |
| 4. **Plain text** | Anything else: the assistant reads the text and fills the fields. | Yes |

Every document is also checked for:
- the card ending printed on a receipt;
- reverse-charge wording (in English, Portuguese, German and Spanish);
- "art. 138" intra-EU supplies;
- Portuguese VAT charged by a foreign supplier.

From all that, the tools propose how to book the document:
- the VAT code, which decides the IVA boxes;
- the exchange rate: the official ECB rate for that day, or the rate printed on the document (e.g. Wise);
- the payment account;
- the business share;
- the file name.

Your rules in the private config, per supplier and per client, override any of these.

## Your folders and books

### Folders

```
~/Taxes/2026/
├── Bookkeeping_2026.xlsx           the books
├── Expenses/                       every purchase document, renamed
│   ├── accountant_01_FT-A1-123.pdf
│   ├── github_02_INV000000001.pdf
│   └── ...
├── Income/                         your sales: your invoice (if any) and the Portal document
│   ├── 20260215_recibo_RG-A1-1.pdf
│   └── ...
├── eFatura_2026_export_20260415.csv
└── IVA_2026_1TRI_....pdf           your submitted returns (save them here)
```

File names are `<supplier>_<month>_<document number>`. The supplier part comes from your rules, the supplier's
name, or its NIF.

### The books

`init-sheet YEAR` (or asking the assistant to create the year's books) makes **an Excel workbook**, which opens in
Excel, LibreOffice or Numbers. A **Google Sheet** is an option: set `backend: google` and see
[Google Sheets](#optional-google-sheets-instead-of-excel).

**Expenses sheet**
- **Declaração Periódica**, one column per quarter:
  - the boxes you type on the Portal: 3, 4, 7, 8, 12, 13, 16, 17, 20, 24, 61 and 98;
  - the boxes the Portal calculates, so you can check them: 90, 91, 92, 93, 94 and 96.
  - Box 61 (the credit carried in) is the previous quarter's box 96. Q1's comes from the previous year's Q4.
- **QUARTERS**: quarter sums under the table's columns.
- **The table**, one row per purchase.

**Income sheet**
- **IRS & SS**, per quarter:
  - gross income by invoice date, for IRS Anexo B;
  - income by recibo date, for the quarterly Segurança Social declaration;
  - business expenses.
- **The table**, one row per sale.

The cells are ordinary formulas, so you can read, check and change the books by hand.

### What the columns mean

| Column | Meaning |
|---|---|
| **Amount paid** | What the document says you paid, in its own currency, VAT included |
| **VAT included** | The VAT inside that amount, in the same currency (0 when none was charged) |
| **FX to EUR** | Units of the foreign currency per 1 € (e.g. 1.10 for dollars), as the ECB publishes it; 1 for euros |
| **Amount €**, **Net € (-VAT)** | The same in euros, with and without VAT |
| **NIF?** | Whether the invoice shows your NIF. Portuguese IVA is only deductible if it does |
| **VAT code** | How the purchase is treated for IVA (table below); decides the boxes |
| **Business %** | Share used for work: 100% normally, e.g. 30% for home rent |
| **Box N** | That purchase's contribution to box N of the Declaração Periódica |
| **Net VAT benefit €** | IVA you get back minus IVA you self-charge (0 for reverse charge) |
| **IRS deductible €** | The business cost for IRS: what you paid, times the business share, minus the IVA you recover |
| **Document** | What backs the row: QR-verified PDF, invoice, receipt, e-Fatura only, no invoice, MISSING |
| **Payment account** | Which card or account paid |
| **Q** | The quarter, from the date |

### VAT codes (purchases)

| Code | When | Boxes |
|---|---|---|
| `PT` | Portuguese IVA, deductible | 24 |
| `PT-ASSET` | Portuguese IVA on equipment you keep (e.g. a laptop) | 20 |
| `PT-NONDED-MEAL` | Meals: IVA not deductible (art. 21 CIVA) | – |
| `PT-NONDED-TRAVEL` | Transport of people: IVA not deductible | – |
| `NoVAT` | Exempt operation (e.g. rent) | – |
| `NONE` | Nothing to self-charge (bank and payment fees, no invoice) | – |
| `EU-RC` | Services from an EU supplier that charged no VAT (reverse charge) | 16 + 17, deducted in 24 |
| `EU-RC-GOODS` | Goods from an EU supplier that charged no VAT (reverse charge) | 12 + 13, deducted in 24 |
| `NON-EU-RC` | Services from outside the EU that charged no VAT (reverse charge) | 3 + 4 and 98, deducted in 24 |
| `OSS-PT-VAT-NONDED` | A foreign supplier charged you Portuguese IVA | not deductible |
| `FOREIGN-VAT-NONDED` | A foreign supplier charged another country's VAT | not deductible |

### Sales codes

| Code | When | Boxes |
|---|---|---|
| `PT / C3` | Portuguese client, IVA at 23% | 3 + 4 |
| `EU / C7` | Business client in another EU country, no IVA | 7, and the Declaração Recapitulativa |
| `NON-EU / C8` | Client outside the EU, no IVA | 8 |

Box numbers follow the Declaração Periódica in force for periods **before 1 July 2027**. Portaria 298/2026 changes
the return after that, and this project will follow.

## Setup in detail

### 1. Install

**With pipx** (simplest; pipx installs a command-line program in its own space):

```bash
pipx install "git+https://github.com/delpapa/mcp-invoices-pt"            # add [google] for Google Sheets
```

**From a clone** (if you want to change the code):

```bash
git clone https://github.com/delpapa/mcp-invoices-pt && cd mcp-invoices-pt
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"                 # add ,google for Google Sheets
```

Either way you also need **poppler**: `brew install poppler` on macOS, or `sudo apt install poppler-utils` on
Ubuntu / Debian.

### 2. Your private config

Save [`config.example.yaml`](config.example.yaml) as `~/.config/mcp-invoicesPT/config.yaml`. Every line in it is
commented. The settings that matter:

| Setting | What to put |
|---|---|
| `taxpayer.nif` | Your NIF (required) |
| `paths.inbox` | Where downloads arrive. `~/Downloads` works, but **a dedicated folder is better**: only what is in it gets looked at |
| `paths.year_root` | One folder per tax year, e.g. `~/Taxes/{year}` |
| `cards` | The last 4 digits of your cards, in quotes, mapped to the account names you use: `"1234": my-bank` |
| `suppliers` | Optional per-supplier rules: a display name for Portuguese suppliers (their QR code carries only the NIF), a file-name prefix, the account, a VAT code, the business share |
| `clients` | Optional per-client rules for sales: name, tax id, country, VAT case, account |

The config is YAML. Indentation matters, `#` starts a comment, and text values are safest in "quotes".

### 3. Create the year's books

```bash
mcp-invoices-pt init-sheet 2026                    # or: init-sheet 2026 <IVA credit carried in>
```

Without the credit, it is read from the previous year's Q4, if those books exist. You can also just ask the
assistant to *"create the 2026 books"*.

### 4. Connect to your assistant

**Claude Code:**

```bash
claude mcp add --scope user invoices-pt -- mcp-invoices-pt
```

**Claude Desktop:** open *Settings → Developer → Edit Config* (the file is
`~/Library/Application Support/Claude/claude_desktop_config.json` on macOS, and
`%APPDATA%\Claude\claude_desktop_config.json` on Windows), add this, and restart Claude Desktop:

```json
{
  "mcpServers": {
    "invoices-pt": {"command": "/full/path/to/mcp-invoices-pt"}
  }
}
```

`which mcp-invoices-pt` in a terminal shows the full path; with pipx it is usually `~/.local/bin/mcp-invoices-pt`.
If your config is somewhere else, add `"env": {"INVOICES_PT_CONFIG": "/path/to/config.yaml"}` next to `command`.

### 5. Already have invoices filed?

Ask the assistant to *"run index_year for 2026"*. Afterwards, a document you download again is recognised as a
copy.

### Optional: Google Sheets instead of Excel

1. Install with `[google]` and set `backend: google` in the config.
2. In a Google Cloud project, enable the **Google Sheets API** and create a **service account**.
3. Download its JSON key to the path in `google.service_account`, and keep it private.
4. Create a Google Sheet and share it with the service account's e-mail as **Editor**. Put the sheet's ID (from its
   URL) in `google.spreadsheet_id`.
5. `init-sheet YEAR` then adds the year's tabs to that sheet.

## Day-to-day use

### Collect

- **Purchases:**
  - download invoices and receipts from supplier portals (Stripe invoices, GitHub billing, cloud consoles, Amazon
    orders);
  - for paper receipts from Portuguese shops, photograph the QR code clearly.
- **Sales:** the Portal document you issued (recibo verde, fatura or fatura-recibo). If you also send clients an
  invoice of your own, save that too.
- **Every so often:** the **e-Fatura export**. On the Portal das Finanças: e-Fatura → Adquirente → Verificar
  faturas → export. It catches Portuguese invoices you never downloaded.

### Ask

**Close the workbook first** if it is open in Excel or LibreOffice; the tools will not write to an open workbook.

| You say | It does |
|---|---|
| "Organize my receipts." | Makes a plan of everything in the inbox and shows it to you. After you confirm, it files and books each document, books sales, checks the e-Fatura export, and reports what is missing. It asks about judgment calls, such as business or personal, or whether IVA is deductible |
| "What do I type for Q3?" | The Declaração Periódica boxes for the quarter, the credit carried over, and the result |
| "Q3 submitted." | Freezes that quarter's figures and locks its rows. If you saved the return PDF in the year folder, it compares the two; the submitted return is the source of truth |
| "What's missing for 2026?" | Rows marked MISSING, files that are gone, incomplete rows, unbooked files, receipts for payments already booked, gaps in monthly subscriptions, sales without a Portal document |
| "IRS and Segurança Social totals for 2026?" | Gross income, income by recibo date, business expenses, per quarter |
| "Create the 2027 books." | Next year's workbook, with the IVA credit carried over |

### Sales

- **The common case: only the Portal document.** If you issue a fatura-recibo (or recibo verde) on the Portal and
  nothing else, that document is the sale. Its QR code gives the date, amount, IVA, withholding and client tax id.
  Add a `clients` rule so it books with the client's name.
- **With an invoice of your own:** if you also send your own invoice (e.g. in dollars to a foreign client), the
  plan pairs it with its Portal document by date and amount. The row keeps both, and the exchange rate implied by
  the two.

### Type the return

On the Portal das Finanças, under IVA → Declaração Periódica, fill quadro 06 and 06-A with the boxes from
*"What do I type for Q3?"*. Box 61 is the credit carried in. After submitting, save the PDF in the year folder and
say *"Q3 submitted"*.

### Fixing a mistake

Edit the workbook directly: the tools read whatever is there, and the formulas recalculate. The exception is a
quarter you marked as submitted: its declaration figures are frozen, so later edits to its rows no longer change
them. To deliberately correct a filed quarter, ask the assistant. That is also when you would file a substitute
return.

### A new year

Ask for the new year's books, or run `init-sheet <year>`. The IVA credit carries over automatically.

## Tools reference

| Tool | Arguments | Does |
|---|---|---|
| `plan_inbox` | – | Reads everything in the inbox and returns the plan, writing nothing: expense rows, sales (paired), documents to read, copies, non-invoices, e-Fatura exports |
| `scan_inbox` | – | Lists the files in the inbox with their kind, whether they read like an invoice, and their status (new, read, filed) |
| `extract` | `path`, `read_anyway` | Reads one document and proposes how to book it. Text that does not read like an invoice is withheld unless `read_anyway` |
| `file_document` | `path`, `name`, `dry_run` | Moves a document into its year folder (expenses or income) under the proposed name. If it is a copy of a filed document, deletes the download instead |
| `add_expense` | `row`, `dry_run` | Adds a purchase; refuses duplicates and filed quarters |
| `propose_income` | `invoice_path`, `at_document_path` | Proposes one sale from your invoice and/or the Portal document |
| `add_income` | `row`, `dry_run` | Adds a sale |
| `read_efatura` / `reconcile_efatura` | `csv_path` (, `year`) | Reads an e-Fatura export / compares it with the books |
| `missing` | `year` | What is still missing, expenses and income |
| `vat_return` | `quarter`, `year` | The Declaração Periódica boxes for a quarter |
| `mark_filed` | `quarter`, `year`, `return_pdf`, `dry_run`, `apply_pdf_values` | Freezes and locks a submitted quarter, checked against the return PDF |
| `income_totals` | `year` | IRS and Segurança Social totals |
| `create_year_sheet` | `year`, `opening_credit`, `dry_run` | Creates a year's books and folders |
| `index_year` | `year` | Records the documents already filed, so copies are recognised |
| `vat_codes` | – | The VAT codes and the boxes each fills |

## Safety

- **Dry run first.** Every tool that changes something shows what it would do first, and only acts when told to.
- **Files.**
  - Documents are never overwritten.
  - Only files in the inbox are ever deleted, and only when they are copies of documents already filed.
  - Files that do not look like invoices are flagged and not read, unless you ask.
- **Books.**
  - No duplicate rows.
  - Rows are kept sorted by date. The table is rewritten when sorting, so colours or fonts you add to its cells
    by hand may be reset.
  - A filed quarter's figures are frozen, and the tools refuse to add rows to it.
- **The workbook.** Writes are atomic, so an interruption never leaves half a file. Nothing is written while the
  workbook is open elsewhere.
- **Numbers.** The tools compute the boxes in Python, mirroring the workbook's formulas with spreadsheet rounding.
  The test suite recalculates a workbook in LibreOffice and checks both agree to the cent.
- **Internet** is only used for ECB exchange rates. Without it, foreign-currency documents ask you for the rate.

## Privacy: public code, private data

Everything personal stays outside this repository, under `~/.config/mcp-invoicesPT/`:

| In the repository | In your private folder |
|---|---|
| Document readers, Portuguese VAT rules, the layout of the books, the tools | `config.yaml`: NIF, folders, cards → accounts, supplier and client rules |
| Tests with made-up documents only | `parsers/`: your own parsers (e.g. your personal invoice template) |
| An example parser to adapt | The Google service-account key (Google backend only) |
| | The ledger of files already handled (`~/.local/share/mcp-invoicesPT/`) |

**What the AI sees.** Documents are read on your computer. The assistant receives what the tools return:
- each document's fields;
- the text of documents in unknown layouts;
- never the text of files that do not look like invoices, unless you ask.

Your assistant's privacy terms apply to what it receives.

## Adding a document type

A parser is a Python module with three things:

```python
NAME = "acme"

def matches(text: str) -> bool:                    # is this document in my layout?
    return "ACME Cloud Ltd" in text and "Invoice number" in text

def parse(text: str, file: str = "") -> Document:  # read its fields
    ...
```

`parse` returns a `Document` with these fields: `layer`, `doc_type`, `date`, `supplier`, `supplier_vat`,
`country`, `invoice_no`, `currency`, `amount`, `vat_included`, `buyer_nif`, `markers` and `extra`. Helpers for
amounts in both number formats, dates in several languages, and country names are in
[`documents/parsers/_common.py`](src/invoices_pt/documents/parsers/_common.py).

- **A company's layout that others may use:** add it to `src/invoices_pt/documents/parsers/`, with a made-up sample
  in `tests/test_parsers.py` (never real data), and open a pull request. The registry picks it up automatically.
- **Something only you use** (e.g. your own invoice template): put it in a private folder and set `parsers_dir` in
  the config. It is loaded at start-up and tried before the public parsers.

## Tests

```bash
.venv/bin/pytest -q
```

The suite uses made-up documents only. It covers:
- every parser, QR codes and the e-Fatura import;
- VAT coding, filing and the inbox plan;
- the missing-documents report and sales;
- a complete workbook, with every box checked against hand-computed values (and recalculated in LibreOffice, if it
  is installed).

Opt-in checks against your own data:

```bash
INVOICES_PT_LIVE_SHEET=1 .venv/bin/pytest tests/test_live_layout.py -q
INVOICES_PT_PRIVATE=1 INVOICES_PT_YEAR=2026 .venv/bin/pytest tests/test_private_regression.py -q -s
```

- `test_live_layout.py` (Google backend) builds temporary tabs in your sheet, checks every box, and removes them.
- `test_private_regression.py` re-reads your filed documents and compares them with your booked rows.

## Limitations

- **Quarterly filers only.** The IVA you self-charge on reverse charge is at the mainland rate (23%). Monthly
  filing and the Azores and Madeira rates are not handled yet.
- **IRS:** the figures assume the *regime simplificado* (Anexo B). Organised accounting is out of scope.
- **The return model:** box numbers follow the Declaração Periódica valid until June 2027.
- **Photos:** reading a paper receipt depends on how sharp its QR code is in the photo.
- **Windows** is untested.

## License

This is a tool I have been writing for myself first. I keep the generic part here, separate from any personal
settings, so others can use it too.

[MIT](LICENSE). You can use, change and share this freely, including commercially, as long as you keep the
copyright notice. There is no warranty. Issues and pull requests are welcome.
