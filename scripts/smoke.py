"""Run every reader over one tax year's folders and summarize what each layer handled.

Uses your private config; prints counts and the documents that still fall back to plain text.
Usage: python scripts/smoke.py 2026
"""

import collections
import os
import sys

from invoices_pt.config import Config
from invoices_pt.extract import proposal, read_document


def main(year: int) -> None:
    cfg = Config.load()
    folders = [cfg.expenses_dir(year), cfg.income_dir(year)]
    layers = collections.Counter()
    fallback = []
    for folder in folders:
        for name in sorted(os.listdir(folder)) if os.path.isdir(folder) else []:
            if not name.lower().endswith((".pdf", ".png", ".jpg", ".jpeg")):
                continue
            doc = read_document(os.path.join(folder, name))
            layers[doc.layer.split(":")[0] if doc.layer != "text" else "text"] += 1
            if doc.layer == "text":
                fallback.append((name, proposal(doc, cfg)["vat_code"], doc.card_last4, doc.markers))
    print(dict(layers))
    for row in fallback:
        print("  text:", *row)


if __name__ == "__main__":
    main(int(sys.argv[1]))
