"""Move documents from the inbox into the tax-year folders, and remove copies that are already filed.

Safety rules: never overwrite, and only ever delete files that sit in the inbox.
"""

from __future__ import annotations

import datetime as dt
import os
import shutil

from .config import Config
from .documents import efatura
from .extract import proposal, read_document
from .ledger import Ledger, sha256
from .model import Document

DOC_EXT = (".pdf", ".png", ".jpg", ".jpeg", ".webp")


def target_dir(cfg: Config, doc: Document, year: int) -> str:
    """Your own sales documents (and AT documents issued under your NIF) go to the income folder, the rest to
    expenses."""
    own = doc.doc_type == "sales_invoice" or (cfg.nif and doc.supplier_vat == "PT" + cfg.nif)
    return cfg.income_dir(year) if own else cfg.expenses_dir(year)


def index_folder(folder: str, ledger: Ledger) -> dict:
    """Read every document in a folder into the ledger (status "filed") so copies are recognised later."""
    counts = {"indexed": 0, "known": 0, "failed": []}
    for name in sorted(os.listdir(folder)):
        path = os.path.join(folder, name)
        if not name.lower().endswith(DOC_EXT) or not os.path.isfile(path):
            continue
        digest = sha256(path)
        known = ledger.get(digest)
        if known and known["path"] == path and known["status"] == "filed":
            counts["known"] += 1
            continue
        try:
            doc = read_document(path)
        except Exception as e:
            counts["failed"].append(f"{name}: {e}")
            continue
        ledger.record(digest, path, doc.key if doc.invoice_no else "", doc.layer, "filed")
        counts["indexed"] += 1
    return counts


def _filed_copy(ledger: Ledger, digest: str, key: str) -> str | None:
    """Path of a filed file with the same content, or the same invoice, that still exists."""
    same = ledger.get(digest)
    if same and same["status"] == "filed" and os.path.exists(same["path"]):
        return same["path"]
    if key and not key.endswith("|"):
        for r in ledger.by_key(key):
            if r["status"] == "filed" and r["sha256"] != digest and os.path.exists(r["path"]):
                return r["path"]
    return None


def file_document(cfg: Config, ledger: Ledger, path: str, name: str = "", dry_run: bool = True,
                  delete_duplicate: bool = True) -> dict:
    inbox = os.path.realpath(cfg.paths(dt.date.today().year)["inbox"])
    in_inbox = os.path.dirname(os.path.realpath(path)) == inbox
    digest = sha256(path)

    if path.lower().endswith(".csv") and efatura.is_export(path):
        docs = efatura.parse_csv(path)
        year = max(d.date for d in docs).year if docs else dt.date.today().year
        dest = os.path.join(cfg.paths(year)["year_root"], name or f"eFatura_{year}_export_{dt.date.today():%Y%m%d}.csv")
        key = ""
    else:
        doc = read_document(path)
        if not doc.date:
            return {"error": "no date read from the document; pass the fields to add_expense and a name to file_document"}
        year = doc.date.year
        key = doc.key if doc.invoice_no else ""
        dest = os.path.join(target_dir(cfg, doc, year), name or proposal(doc, cfg)["file_name"])

    copy = _filed_copy(ledger, digest, key)
    if copy and os.path.realpath(copy) == os.path.realpath(path):
        return {"status": "already_filed", "path": copy}
    if copy:
        result = {"status": "duplicate", "existing": copy, "deleted": False}
        if delete_duplicate and in_inbox:
            result["deleted"] = not dry_run
            if not dry_run:
                os.remove(path)
        return {"dry_run": dry_run, **result}
    if os.path.exists(dest):
        return {"error": f"{dest} already exists and is a different document; pass another name"}
    if dry_run:
        return {"dry_run": True, "status": "would_move", "to": dest}
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    shutil.move(path, dest)
    ledger.record(digest, dest, key, "csv" if dest.endswith(".csv") else "document", "filed")
    return {"status": "moved", "to": dest}
