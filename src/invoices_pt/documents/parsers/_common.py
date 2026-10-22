"""Helpers shared by the layout parsers: amounts, dates, currencies and country names."""

from __future__ import annotations

import datetime as dt
import re

SYMBOLS = {"€": "EUR", "$": "USD", "£": "GBP"}
COUNTRIES = {
    "united states": "US", "usa": "US", "ireland": "IE", "germany": "DE", "deutschland": "DE", "france": "FR",
    "spain": "ES", "españa": "ES", "netherlands": "NL", "belgium": "BE", "luxembourg": "LU", "italy": "IT",
    "portugal": "PT", "united kingdom": "GB", "switzerland": "CH", "hong kong": "HK", "canada": "CA",
}
MONTHS_ES = {"enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6, "julio": 7, "agosto": 8,
             "septiembre": 9, "setiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12}
MONTHS_PT = {"janeiro": 1, "fevereiro": 2, "março": 3, "abril": 4, "maio": 5, "junho": 6, "julho": 7, "agosto": 8,
             "setembro": 9, "outubro": 10, "novembro": 11, "dezembro": 12}


def money(s: str) -> float:
    """'1,234.56', '1.234,56', '108,00', '-$12.34' -> float"""
    s = re.sub(r"[^\d,.\-]", "", s)
    if "," in s and "." in s:
        s = s.replace(",", "") if s.rfind(".") > s.rfind(",") else s.replace(".", "").replace(",", ".")
    elif "," in s:
        s = s.replace(",", ".") if len(s.split(",")[-1]) == 2 else s.replace(",", "")
    return float(s)


def date(s: str, order: str = "mdy") -> dt.date:
    """English month names, ISO, numeric (in `order`), and Spanish or Portuguese month names."""
    s = " ".join(s.replace(",", ", ").split()).strip()
    for fmt in ("%B %d, %Y", "%b %d, %Y", "%Y-%m-%d"):
        try:
            return dt.datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    m = re.fullmatch(r"(\d{1,2})\s+(?:de\s+)?([a-zç]+)\s+(?:de\s+)?(\d{4})", s.lower())
    if m and (month := MONTHS_ES.get(m.group(2)) or MONTHS_PT.get(m.group(2))):
        return dt.date(int(m.group(3)), month, int(m.group(1)))
    m = re.fullmatch(r"(\d{1,2})[/.-](\d{1,2})[/.-](\d{2}|\d{4})", s)
    if m:
        a, b, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        y += 2000 if y < 100 else 0
        month, day = (a, b) if order == "mdy" else (b, a)
        return dt.date(y, month, day)
    raise ValueError(f"unrecognized date: {s!r}")


def find(pattern: str, text: str, flags: int = re.I | re.M, group: int = 1) -> str:
    m = re.search(pattern, text, flags)
    return m.group(group).strip() if m else ""


def country(name: str) -> str:
    return COUNTRIES.get(name.strip().lower(), "")


def left_column(line: str) -> str:
    """First column of a two-column pdftotext -layout line."""
    return re.split(r"\s{2,}", line.strip())[0] if line.strip() else ""
