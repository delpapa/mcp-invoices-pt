"""Submitted Declaração Periódica (the PDF the Portal das Finanças gives you after submitting): read its boxes."""

from __future__ import annotations

import os
import re

from .documents.text import pdf_text

# Boxes of quadro 06 / 06-A and the result fields
KNOWN = {1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 40, 41,
         61, 65, 66, 67, 68, 90, 91, 92, 93, 94, 95, 96, 97, 98, 106}
PAIR = re.compile(r"(?<![\d.,])(\d{1,3})\s+(-?(?:\d{1,3}(?:\.\d{3})+|\d+),\d{2})(?![\d,])")


def _pt_number(s: str) -> float:
    return float(s.replace(".", "").replace(",", "."))


def parse_return_text(text: str) -> dict[int, float]:
    """Box -> value from the text of a submitted return. Box 61 (credit carried in) is printed apart from its
    label, so it is derived from box 91 = 20 + 21 + 22 + 23 + 24 + 40 + 61 + 65 + 67."""
    boxes: dict[int, float] = {}
    for m in PAIR.finditer(text):
        box = int(m.group(1))
        if box in KNOWN and box not in boxes:
            boxes[box] = _pt_number(m.group(2))
    if 61 not in boxes and 91 in boxes:
        boxes[61] = round(boxes[91] - sum(boxes.get(b, 0.0) for b in (20, 21, 22, 23, 24, 40, 65, 67)), 2)
    return boxes


def parse_return_pdf(path: str) -> dict[int, float]:
    return parse_return_text(pdf_text(path))


def find_return_pdf(folder: str, quarter: str, year: int) -> str | None:
    """Prefer a return labelled with the requested year, then a substitution, then the newest file.
    Older names with just IVA and a quarter are supported in the year's own folder."""
    if not re.fullmatch(r"Q[1-4]", quarter, re.I) or not os.path.isdir(folder):
        return None
    n = quarter[1]
    period = re.compile(rf"IVA.*?(?<![a-z0-9])(?:{n}\s*TRI(?:MESTRE)?|Q{n})(?![a-z0-9])", re.I)
    hits = []
    with os.scandir(folder) as entries:
        for entry in entries:
            if not entry.name.lower().endswith(".pdf") or not period.search(entry.name) or not entry.is_file():
                continue
            labelled = re.search(r"(?<!\d)((?:19|20)\d{2})(?!\d)", entry.name)
            if labelled and int(labelled[1]) != year:
                continue
            hits.append((bool(labelled), "SUBSTIT" in entry.name.upper(), entry.stat().st_mtime, entry.path))
    return max(hits)[-1] if hits else None
