"""Move documents from the inbox into the tax-year folders, and remove copies that are already filed.

Safety rules: never overwrite, and only ever delete files that sit in the inbox.
"""

from __future__ import annotations

import datetime as dt
import errno
import os
import shutil
import tempfile

from .config import Config
from .documents import efatura
from .extract import matching_documents, proposal, read_document
from .ledger import Ledger, sha256, verified_filed_copy
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
        ledger.record(digest, path, doc.key, doc.layer, "filed")
        counts["indexed"] += 1
    return counts


def _filed_copy(ledger: Ledger, digest: str, doc: Document | None) -> str | None:
    """Path of a filed file with the same content, or the same invoice, that still exists."""
    same = ledger.get(digest)
    if verified_filed_copy(same):
        return same["path"]
    if doc is not None:
        for r in matching_documents(doc, ledger):
            if r["sha256"] != digest and verified_filed_copy(r):
                return r["path"]
    return None


def _publish_copy(source: str, dest: str, digest: str) -> None:
    """Stage complete bytes on the archive filesystem and claim the destination exclusively."""
    with tempfile.TemporaryDirectory(dir=os.path.dirname(dest)) as staging:
        staged = os.path.join(staging, "document")
        shutil.copy2(source, staged)
        if sha256(staged) != digest:
            raise OSError("the source document changed while filing; retry with the current file")
        if os.name == "nt":
            os.rename(staged, dest)  # Windows rename refuses existing files
            return
        try:
            os.link(staged, dest)
        except OSError as exc:
            if exc.errno not in (errno.EPERM, errno.ENOTSUP, errno.ENOSYS):
                raise
            # Some mounted drives do not support links. Reserve the final name first.
            with open(dest, "xb"):
                pass
            try:
                os.replace(staged, dest)
            except BaseException:
                os.unlink(dest)
                raise


def file_document(cfg: Config, ledger: Ledger, path: str, name: str = "", dry_run: bool = True,
                  delete_duplicate: bool = True) -> dict:
    inbox = os.path.realpath(cfg.paths(dt.date.today().year)["inbox"])
    in_inbox = os.path.dirname(os.path.realpath(path)) == inbox
    digest = sha256(path)

    if path.lower().endswith(".csv") and efatura.is_export(path):
        docs = efatura.parse_csv(path)
        year = max(d.date for d in docs).year if docs else dt.date.today().year
        dest = os.path.join(cfg.paths(year)["year_root"], name or f"eFatura_{year}_export_{dt.date.today():%Y%m%d}.csv")
        doc = None
    else:
        doc = read_document(path)
        if not doc.date:
            return {"error": "no date read from the document; pass the fields to add_expense and a name to file_document"}
        year = doc.date.year
        dest = os.path.join(target_dir(cfg, doc, year), name or proposal(doc, cfg)["file_name"])

    key, layer = (doc.key, "document") if doc else ("", "csv")
    copy = _filed_copy(ledger, digest, doc)
    if not copy and os.path.isfile(dest) and sha256(dest) == digest:
        # A prior attempt may have published the bytes before its ledger write failed.
        copy = dest
        if not dry_run:
            ledger.record(digest, dest, key, layer, "filed")
    if copy and os.path.realpath(copy) == os.path.realpath(path):
        return {"status": "already_filed", "path": copy}
    if copy:
        result = {"status": "duplicate", "existing": copy, "deleted": False}
        if delete_duplicate and in_inbox and not dry_run:
            if sha256(path) != digest:
                return {"error": "the inbox file changed while checking the duplicate; retry with the current file"}
            os.remove(path)
            result["deleted"] = True
        return {"dry_run": dry_run, **result}
    collision = {"error": f"{dest} already exists; pass another name"}
    if os.path.lexists(dest):
        return collision
    if dry_run:
        return {"dry_run": True, "status": "would_move", "to": dest}
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    try:
        _publish_copy(path, dest, digest)
    except FileExistsError:
        return collision
    ledger.record(digest, dest, key, layer, "filed")
    if sha256(path) != digest:
        return {"error": "the source changed after its original contents were filed", "to": dest}
    os.remove(path)
    return {"status": "moved", "to": dest}
