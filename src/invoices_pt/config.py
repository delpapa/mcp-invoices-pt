"""Private settings: paths, NIF, books, cards and personal supplier and client rules. They live outside the repo."""

from __future__ import annotations

import glob
import os
import re

import yaml

from .model import Document

DEFAULT_PATH = "~/.config/mcp-invoicesPT/config.yaml"
# File names for sales documents; both files of a sale are named after the invoice date so they sort together.
# {invoice_no} is your invoice number, or the AT document's number when there is no invoice of your own.
DEFAULT_INCOME_NAMES = {"invoice": "{date:%Y%m%d}_invoice_{invoice_no}", "recibo": "{date:%Y%m%d}_recibo_{invoice_no}"}
DEFAULT_PATHS = {
    "inbox": "~/Downloads",
    "year_root": "~/Taxes/{year}",
    "expenses_dir": "{year_root}/Expenses",
    "income_dir": "{year_root}/Income",
    "workbook": "{year_root}/Bookkeeping_{year}.xlsx",
    "cache": "~/.cache/mcp-invoicesPT",
    "ledger": "~/.local/share/mcp-invoicesPT/ledger.sqlite",
}


def _card(key) -> str:
    """Card endings as text. YAML reads an unquoted 0123 as the number 123, so restore the leading zeros."""
    return str(key).zfill(4) if isinstance(key, int) else str(key).strip()


class Config:
    def __init__(self, data: dict, path: str = ""):
        self.data = data
        self.path = path
        self.nif = str((data.get("taxpayer") or {}).get("nif", "")).strip()
        self.cards = {_card(k): v for k, v in (data.get("cards") or {}).items()}
        self.suppliers = data.get("suppliers") or []
        self.clients = data.get("clients") or []
        self.google = data.get("google") or {}
        self.income_names = {**DEFAULT_INCOME_NAMES, **(data.get("income_names") or {})}

    @classmethod
    def load(cls, path: str | None = None) -> Config:
        path = os.path.expanduser(path or os.environ.get("INVOICES_PT_CONFIG", DEFAULT_PATH))
        if not os.path.exists(path):
            raise FileNotFoundError(f"no config at {path}; copy config.example.yaml there and fill it in")
        with open(path) as f:
            cfg = cls(yaml.safe_load(f) or {}, path)
        if cfg.data.get("parsers_dir"):
            from .documents import parsers
            parsers.load_dir(cfg.data["parsers_dir"])
        return cfg

    def paths(self, year: int) -> dict[str, str]:
        """Every path for a tax year (defaults for anything not configured), with {year} and {year_root} filled in."""
        raw = {**DEFAULT_PATHS, **{k: v for k, v in (self.data.get("paths") or {}).items() if v}}
        root = os.path.expanduser(str(raw["year_root"]).format(year=year))
        return {k: os.path.expanduser(str(v).format(year=year, year_root=root)) for k, v in raw.items()}

    def expenses_dir(self, year: int) -> str:
        return self.paths(year)["expenses_dir"]

    def income_dir(self, year: int) -> str:
        """The income folder: `income_dir`, or an existing folder matching `income_glob` (for folder names that vary
        between years), or the default."""
        p = self.paths(year)
        configured = (self.data.get("paths") or {})
        if "income_glob" in p and not configured.get("income_dir"):
            found = sorted(glob.glob(p["income_glob"]))
            if found:
                return found[0]
        return p["income_dir"]

    @property
    def backend(self) -> str:
        """Where the books live: "xlsx" (a local workbook, the default) or "google" (a Google Sheet)."""
        return str(self.data.get("backend") or "xlsx").lower()

    def column_overrides(self, kind: str) -> dict:
        """Header renames for a table, from `columns` / `income_columns` (top level or under google)."""
        key = "columns" if kind == "expenses" else "income_columns"
        return {**(self.google.get(key) or {}), **(self.data.get(key) or {})}

    def workbook(self, year: int) -> str:
        return self.paths(year)["workbook"]

    def sheet_name(self, kind: str, year: int) -> str:
        """Tab name: from google.<kind>_tab for Google Sheets, from xlsx.<kind>_sheet for a workbook."""
        if self.backend == "google":
            return str(self.google[f"{kind}_tab"]).format(year=year)
        defaults = {"expenses": "Expenses", "income": "Income"}
        return str((self.data.get("xlsx") or {}).get(f"{kind}_sheet", defaults[kind])).format(year=year)

    def tab(self, kind: str, year: int) -> str:
        return str(self.google[f"{kind}_tab"]).format(year=year)

    def supplier_rule(self, doc: Document) -> dict:
        """First supplier rule whose `match` regex hits the supplier's name or VAT number. Never the document text:
        a word like "landlord" in an unrelated letter must not turn it into rent."""
        for rule in self.suppliers:
            rx = re.compile(rule["match"], re.I)
            if (doc.supplier and rx.search(doc.supplier)) or (doc.supplier_vat and rx.search(doc.supplier_vat)):
                return rule
        return {}

    def client_rule(self, *texts: str) -> dict:
        """First client rule whose `match` regex hits any text (name, tax id, or the tax id's digits)."""
        candidates = [t for t in texts if t] + [re.sub(r"\D", "", t) for t in texts if t and re.search(r"\d", t)]
        for rule in self.clients:
            rx = re.compile(rule["match"], re.I)
            if any(rx.search(t) for t in candidates):
                return rule
        return {}

    def income_name(self, kind: str, day, invoice_no: str, ext: str = ".pdf") -> str:
        safe = re.sub(r"[^\w.-]+", "-", invoice_no or "noid").strip("-")
        return self.income_names[kind].format(date=day, invoice_no=safe) + ext

    def account(self, doc: Document) -> str:
        if doc.card_last4 and doc.card_last4 in self.cards:
            return self.cards[doc.card_last4]
        return self.supplier_rule(doc).get("account", "")
