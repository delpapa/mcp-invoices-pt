import os

from invoices_pt.filing import file_document, index_folder
from invoices_pt.ledger import Ledger

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
