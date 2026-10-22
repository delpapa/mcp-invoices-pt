"""Submitted Declaração Periódica (the PDF the Portal das Finanças gives you after submitting): read its boxes."""

from __future__ import annotations

import os
import re

from .documents.text import pdf_text

# Boxes of quadro 06 / 06-A and the result fields
KNOWN = {1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 40, 41,
         61, 90, 91, 92, 93, 94, 95, 96, 97, 98, 106}
PAIR = re.compile(r"(?<![\d.,])(\d{1,3})\s+(-?\d{1,3}(?:\.\d{3})*,\d{2})(?![\d,])")


def _pt_number(s: str) -> float:
    return float(s.replace(".", "").replace(",", "."))


def parse_return_text(text: str) -> dict[int, float]:
    """Box -> value from the text of a submitted return. Box 61 (credit carried in) is printed apart from its
    label, so it is derived from box 91 = 20 + 21 + 22 + 23 + 24 + 40 + 61."""
    boxes: dict[int, float] = {}
    for m in PAIR.finditer(text):
        box = int(m.group(1))
        if box in KNOWN and box not in boxes:
            boxes[box] = _pt_number(m.group(2))
    if 61 not in boxes and 91 in boxes:
        boxes[61] = round(boxes[91] - sum(boxes.get(b, 0.0) for b in (20, 21, 22, 23, 24, 40)), 2)
    return boxes


def parse_return_pdf(path: str) -> dict[int, float]:
    return parse_return_text(pdf_text(path))


def find_return_pdf(folder: str, quarter: str, year: int) -> str | None:
    """Most likely submitted return for a quarter in a folder: a substitution wins over the original,
    then the newest file. Matches names with IVA and the quarter, e.g. IVA_2026_1TRI_....pdf or IVA_2026_Q1_....pdf."""
    n = quarter[1]
    rx = re.compile(rf"IVA.*(?:\b|_)({n}\s*TRI|Q{n}\b|Q{n}_|{n}Tri)", re.I)
    if not os.path.isdir(folder):
        return None
    hits = [os.path.join(folder, f) for f in os.listdir(folder) if f.lower().endswith(".pdf") and rx.search(f)]
    if not hits:
        return None
    hits.sort(key=lambda p: ("SUBSTIT" in os.path.basename(p).upper(), os.path.getmtime(p)), reverse=True)
    return hits[0]
