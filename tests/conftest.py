"""Synthetic fixtures only: no real invoices or personal data in the repo."""

import pytest
import zxingcpp
from PIL import Image

from invoices_pt.config import Config

# A made-up Portuguese invoice: 100.00 + 23% IVA, supplier and buyer NIFs are fake
AT_PAYLOAD = ("A:500000000*B:999999990*C:PT*D:FT*E:N*F:20260115*G:FT A1/42*H:ABCD1234-42*I1:PT*"
              "I7:100.00*I8:23.00*N:23.00*O:123.00*Q:abcd*R:0000")


@pytest.fixture
def qr_png(tmp_path):
    def make(payload: str = AT_PAYLOAD, folder=None, name: str = "invoice.png") -> str:
        img = zxingcpp.create_barcode(payload, zxingcpp.BarcodeFormat.QRCode).to_image(scale=6)
        mv = memoryview(img)
        folder = folder or tmp_path
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / name
        Image.frombytes("L", (mv.shape[1], mv.shape[0]), mv.tobytes()).save(path)
        return str(path)
    return make


@pytest.fixture
def cfg(tmp_path):
    return Config({
        "taxpayer": {"nif": "999999990"},
        "paths": {"inbox": str(tmp_path / "inbox"), "year_root": str(tmp_path / "{year}"),
                  "expenses_dir": "{year_root}/Purchases", "income_glob": "{year_root}/Sales*",
                  "cache": str(tmp_path / "cache"), "ledger": str(tmp_path / "ledger.sqlite")},
        "cards": {"4242": "card-a"},
        "suppliers": [{"match": "ACME", "slug": "acme", "account": "card-b", "business_pct": 0.3},
                      {"match": "Wise Europe", "code": "NONE"}],
    })


def text_pdf(path, lines: list[str]) -> str:
    """A minimal one-page PDF with real text, so pdftotext can read it (no PDF library needed)."""
    body = "BT /F1 11 Tf 50 780 Td 14 TL " + " ".join(
        "(" + ln.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)") + ") '" for ln in lines) + " ET"
    objs = ["<< /Type /Catalog /Pages 2 0 R >>", "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
            f"<< /Length {len(body)} >>\nstream\n{body}\nendstream",
            "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    out, offsets = b"%PDF-1.4\n", []
    for i, o in enumerate(objs, 1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n{o}\nendobj\n".encode("latin-1")
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode() + b"".join(f"{o:010d} 00000 n \n".encode() for o in offsets)
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    with open(path, "wb") as f:
        f.write(out)
    return str(path)
