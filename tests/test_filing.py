import os

import pytest
from PIL import Image

from invoices_pt import inbox
from invoices_pt.filing import file_document, index_folder
from invoices_pt.ledger import Ledger, sha256

from conftest import AT_PAYLOAD
from test_efatura import CSV


def _setup(cfg):
    p = cfg.paths(2026)
    os.makedirs(p["inbox"], exist_ok=True)
    os.makedirs(p["expenses_dir"], exist_ok=True)
    return p, Ledger(p["ledger"])


def test_moves_then_deletes_inbox_copy(qr_png, cfg, tmp_path):
    p, ledger = _setup(cfg)
    src = qr_png(folder=tmp_path / "inbox")
    plan = file_document(cfg, ledger, src)
    assert plan["status"] == "would_move" and os.path.exists(src)
    assert plan["to"] == os.path.join(p["expenses_dir"], "500000000_01_FT-A1-42.png")
    done = file_document(cfg, ledger, src, dry_run=False)
    assert done["status"] == "moved" and os.path.exists(done["to"]) and not os.path.exists(src)
    again = qr_png(folder=tmp_path / "inbox", name="copy.png")       # same invoice downloaded again
    dup = file_document(cfg, ledger, again, dry_run=False)
    assert dup["status"] == "duplicate" and dup["deleted"] and not os.path.exists(again)


def test_never_deletes_outside_inbox(qr_png, cfg, tmp_path):
    p, ledger = _setup(cfg)
    file_document(cfg, ledger, qr_png(folder=tmp_path / "inbox"), dry_run=False)
    elsewhere = qr_png(folder=tmp_path / "other")
    dup = file_document(cfg, ledger, elsewhere, dry_run=False)
    assert dup["status"] == "duplicate" and not dup["deleted"] and os.path.exists(elsewhere)


def test_refuses_to_overwrite(qr_png, cfg, tmp_path):
    p, ledger = _setup(cfg)
    taken = os.path.join(p["expenses_dir"], "taken.png")
    open(taken, "wb").write(b"another document")
    src = qr_png(folder=tmp_path / "inbox")
    assert "already exists" in file_document(cfg, ledger, src, name="taken.png")["error"]
    assert open(taken, "rb").read() == b"another document"


def test_index_folder_recognises_existing(qr_png, cfg, tmp_path):
    p, ledger = _setup(cfg)
    qr_png(folder=tmp_path / "2026" / "Purchases", name="filed.png")
    assert index_folder(p["expenses_dir"], ledger)["indexed"] == 1
    dup = file_document(cfg, ledger, qr_png(folder=tmp_path / "inbox"))
    assert dup["status"] == "duplicate"


def test_efatura_export_goes_to_year_root(cfg, tmp_path):
    p, ledger = _setup(cfg)
    src = tmp_path / "inbox" / "e-fatura.csv"
    src.write_text(CSV, encoding="utf-8")
    done = file_document(cfg, ledger, str(src), dry_run=False)
    assert os.path.dirname(done["to"]) == p["year_root"] and os.path.basename(done["to"]).startswith("eFatura_2026_export_")


@pytest.mark.parametrize("legacy", [False, True], ids=["current-ledger", "legacy-ledger"])
def test_credit_note_with_same_supplier_and_number(qr_png, cfg, tmp_path, legacy):
    _, ledger = _setup(cfg)
    folder = tmp_path / "inbox"
    payload = AT_PAYLOAD.replace("G:FT A1/42", "G:A1/42")
    invoice = qr_png(payload, folder=folder)
    filed = file_document(cfg, ledger, invoice, dry_run=False)["to"]
    if legacy:
        ledger.record(sha256(filed), filed, "PT500000000|A1/42", "document", "filed")
    credit_payload = payload.replace("D:FT", "D:NC").replace("H:ABCD1234-42", "H:EFGH5678-42")
    credit = qr_png(credit_payload, folder=folder, name="credit.png")

    result = file_document(cfg, ledger, credit, dry_run=False)
    assert os.path.isfile(credit), result
    assert "already exists" in result["error"]  # same default filename, different document
    plan = inbox.plan(cfg, ledger)
    assert not plan["copies"] and [e["path"] for e in plan["expenses"]] == [credit]
    moved = file_document(cfg, ledger, credit, name="credit-note.png", dry_run=False)
    assert moved["status"] == "moved"
    assert os.path.isfile(filed) and os.path.isfile(moved["to"])

    # A differently encoded image of the invoice still matches the filed invoice.
    download = str(folder / "download.png")
    with Image.open(filed) as image:
        image.save(download, compress_level=0)
    assert sha256(download) != sha256(filed)
    duplicate = file_document(cfg, ledger, download, dry_run=False)
    assert duplicate["existing"] == filed and duplicate["deleted"]


def test_replaced_archive_file_does_not_make_inbox_download_a_duplicate(qr_png, cfg, tmp_path):
    _, ledger = _setup(cfg)
    folder = tmp_path / "inbox"
    original = qr_png(folder=folder)
    filed = file_document(cfg, ledger, original, dry_run=False)["to"]
    with open(filed, "wb") as archive:
        archive.write(b"unrelated file now occupies archived path")
    download = qr_png(folder=folder)
    assert not inbox.plan(cfg, ledger)["copies"]
    result = file_document(cfg, ledger, download, dry_run=False)
    assert os.path.isfile(download) and "already exists" in result["error"]


def test_racing_file_publication_keeps_both_documents(qr_png, cfg, tmp_path, monkeypatch):
    from pathlib import Path
    from invoices_pt import filing

    paths, ledger = _setup(cfg)
    src = qr_png(folder=tmp_path / "inbox")
    dest = Path(paths["expenses_dir"]) / "same-name.png"
    mkdir = os.makedirs

    def competitor_finishes_first(folder, **kwargs):
        mkdir(folder, **kwargs)
        if os.fspath(folder) == str(dest.parent):
            dest.write_bytes(b"independently filed document")

    monkeypatch.setattr(filing.os, "makedirs", competitor_finishes_first)
    result = file_document(cfg, ledger, src, dest.name, dry_run=False)
    assert "already exists" in result["error"]
    assert os.path.isfile(src)
    assert dest.read_bytes() == b"independently filed document"


def test_filing_can_retry_after_a_ledger_failure(qr_png, cfg, tmp_path, monkeypatch):
    _, ledger = _setup(cfg)
    src = qr_png(folder=tmp_path / "inbox")
    planned = file_document(cfg, ledger, src)["to"]
    digest = sha256(src)

    def full(*args):
        raise OSError("ledger disk full")

    with monkeypatch.context() as patch:
        patch.setattr(ledger, "record", full)
        with pytest.raises(OSError, match="ledger disk full"):
            file_document(cfg, ledger, src, dry_run=False)
    assert os.path.isfile(src)
    file_document(cfg, ledger, src, dry_run=False)
    assert ledger.get(digest)["path"] == planned
    assert sha256(planned) == digest and not os.path.exists(src)


@pytest.mark.skipif(os.name == "nt", reason="Windows uses exclusive rename")
def test_archive_on_a_drive_without_hard_links(qr_png, cfg, tmp_path, monkeypatch):
    import errno
    from invoices_pt import filing

    _, ledger = _setup(cfg)
    src = qr_png(folder=tmp_path / "inbox")
    dest = file_document(cfg, ledger, src)["to"]

    def unsupported(*args):
        raise OSError(errno.ENOTSUP, "links unsupported")

    monkeypatch.setattr(filing.os, "link", unsupported)
    with monkeypatch.context() as fail:
        def full(*args):
            raise OSError("drive full")
        fail.setattr(filing.os, "replace", full)
        with pytest.raises(OSError, match="drive full"):
            file_document(cfg, ledger, src, dry_run=False)
    assert os.path.isfile(src) and not os.path.exists(dest)
    assert file_document(cfg, ledger, src, dry_run=False) == {"status": "moved", "to": dest}


def test_identical_unindexed_archive_is_recorded_only_on_commit(qr_png, cfg, tmp_path):
    import shutil

    _, ledger = _setup(cfg)
    src = qr_png(folder=tmp_path / "inbox")
    dest = file_document(cfg, ledger, src)["to"]
    shutil.copyfile(src, dest)
    digest = sha256(src)
    preview = file_document(cfg, ledger, src)
    assert preview["existing"] == dest and not preview["deleted"]
    assert os.path.isfile(src) and ledger.get(digest) is None
    result = file_document(cfg, ledger, src, dry_run=False)
    assert result["existing"] == dest and result["deleted"]
    assert ledger.get(digest)["path"] == dest and sha256(dest) == digest


@pytest.mark.parametrize("update", [("*E:N*", "*E:A*"), ("*O:123.00*", "*O:125.00*"),
                                     ("ABCD1234-42", "OTHER123-42")])
def test_revised_document_is_preserved_with_original(qr_png, cfg, tmp_path, update):
    _, ledger = _setup(cfg)
    folder = tmp_path / "inbox"
    first = file_document(cfg, ledger, qr_png(folder=folder), dry_run=False)["to"]
    revised = qr_png(AT_PAYLOAD.replace(*update), folder=folder, name="revision.png")
    result = file_document(cfg, ledger, revised, name="revised.png", dry_run=False)
    assert result["status"] == "moved"
    assert os.path.isfile(first) and sha256(first) != sha256(result["to"])
