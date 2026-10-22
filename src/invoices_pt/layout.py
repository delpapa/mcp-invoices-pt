"""The sheet layout the tools expect, and a generator that creates a year's two tabs from scratch.

Expenses tab: the Declaração Periódica block (what to type per quarter, with the credit carried over), quarter
sums under the table columns, then one row per purchase. Income tab: IRS / Segurança Social totals, then one
row per sale. VAT maths are sheet formulas, so the sheet stays readable and editable by hand.
"""

from __future__ import annotations

from .vat import CODES, EU, SALES_CODES

EU_ARRAY = "{" + ",".join(f'"{c}"' for c in sorted(EU)) + "}"
DOCUMENT_LABELS = ["PDF ✓ QR-verified", "PDF invoice", "PDF receipt", "e-Fatura only", "No invoice",
                   "MISSING file", "MISSING (no data yet)"]

EXP_HEADER_ROW, EXP_FIRST_ROW = 30, 31
INC_HEADER_ROW, INC_FIRST_ROW = 7, 8
BLOCK_TITLE_ROW, SUMS_ROW = 3, 23
QUARTER_COLS = {"Q1": "E", "Q2": "F", "Q3": "G", "Q4": "H"}


def _q(col: str) -> str:
    return f'=IF({col}{{r}}="","","Q"&ROUNDUP(MONTH({col}{{r}})/3,0))'


def _region(col: str) -> str:
    eu = EU_ARRAY.replace("{", "{{").replace("}", "}}")     # the template is .format()-ed with {r} later
    return f'=IF({col}{{r}}="","",IF({col}{{r}}="PT","PT",IF(ISNUMBER(MATCH({col}{{r}},{eu},0)),"EU","OutEU")))'


# (header, formula template with {r} for the row, or None for an input column, number format)
EXPENSE_COLUMNS = [
    ("Date", None, "date"), ("Q", _q("A"), ""), ("Expense", None, ""), ("Supplier", None, ""),
    ("Country", None, ""), ("Region", _region("E"), ""), ("VAT", None, ""), ("Invoice no.", None, ""),
    ("Currency", None, ""), ("Amount paid", None, "num"), ("VAT included", None, "num"), ("FX to EUR", None, "fx"),
    ("Amount €", '=IF(J{r}="","",ROUND(J{r}/IF(L{r}="",1,L{r}),2))', "num"),
    ("Net € (-VAT)", '=IF(J{r}="","",ROUND((J{r}-N(K{r}))/IF(L{r}="",1,L{r}),2))', "num"),
    ("NIF?", None, ""), ("VAT code", None, ""), ("Business %", None, "pct"),
    ("Box 3", '=IF(P{r}="NON-EU-RC",N{r},0)', "num"),
    ("Box 4", '=IF(P{r}="NON-EU-RC",ROUND(N{r}*0.23,2),0)', "num"),
    ("Box 12", '=IF(P{r}="EU-RC-GOODS",N{r},0)', "num"),
    ("Box 13", '=IF(P{r}="EU-RC-GOODS",ROUND(N{r}*0.23,2),0)', "num"),
    ("Box 16", '=IF(P{r}="EU-RC",N{r},0)', "num"),
    ("Box 17", '=IF(P{r}="EU-RC",ROUND(N{r}*0.23,2),0)', "num"),
    ("Box 20", '=IF(P{r}="PT-ASSET",ROUND((M{r}-N{r})*Q{r},2),0)', "num"),
    ("Box 24", '=IF(P{r}="PT",ROUND((M{r}-N{r})*Q{r},2),0)+ROUND((S{r}+U{r}+W{r})*Q{r},2)', "num"),
    ("Box 98", "=R{r}", "num"),
    ("Net VAT benefit €", "=X{r}+Y{r}-S{r}-U{r}-W{r}", "num"),
    ("IRS deductible € (Anexo B)", '=IF(M{r}="","",ROUND(M{r}*Q{r}-AA{r},2))', "num"),
    ("Document", None, ""), ("File", None, ""), ("Payment account", None, ""),
]
INCOME_COLUMNS = [
    ("Invoice date", None, "date"), ("Q (IVA)", _q("A"), ""), ("Client", None, ""), ("Country", None, ""),
    ("Region", _region("D"), ""), ("Client tax ID", None, ""), ("Your invoice no.", None, ""),
    ("AT Recibo no.", None, ""), ("Recibo date", None, "date"), ("Q (SS)", _q("I"), ""), ("Currency", None, ""),
    ("Amount (orig.)", None, "num"), ("FX (per €)", None, "fx"), ("Net € (AT recibo)", None, "num"),
    ("IVA %", None, ""), ("IVA €", None, "num"), ("IRS withheld €", None, "num"),
    ("Total received €", '=IF(N{r}="","",N{r}+N(P{r})-N(Q{r}))', "num"), ("VAT case", None, ""),
    ("Box 3", '=IF(S{r}="PT / C3",N{r},0)', "num"), ("Box 4", '=IF(S{r}="PT / C3",N(P{r}),0)', "num"),
    ("Box 7", '=IF(S{r}="EU / C7",N{r},0)', "num"), ("Box 8", '=IF(S{r}="NON-EU / C8",N{r},0)', "num"),
    ("Invoice file", None, ""), ("Recibo file", None, ""), ("Account", None, ""),
]
FORMATS = {"date": {"type": "DATE", "pattern": "dd.mm.yyyy"}, "num": {"type": "NUMBER", "pattern": "#,##0.00"},
           "fx": {"type": "NUMBER", "pattern": "0.0000"}, "pct": {"type": "PERCENT", "pattern": "0%"}}


def col_letter(i: int) -> str:
    """0 -> A, 25 -> Z, 26 -> AA"""
    s, i = "", i + 1
    while i:
        i, r = divmod(i - 1, 26)
        s = chr(65 + r) + s
    return s


def row_formulas(kind: str, r: int) -> dict[str, str]:
    """Header -> formula for row `r` of a table in the default layout."""
    cols = EXPENSE_COLUMNS if kind == "expenses" else INCOME_COLUMNS
    return {h: f.format(r=r) for h, f, _ in cols if f}


def expense_letter(header: str) -> str:
    return col_letter([h for h, _, _ in EXPENSE_COLUMNS].index(header))


# Sum ranges start at the header row (never "Q1", and text is ignored in sums), not at the first data row:
# rows inserted right under the header then land inside the range instead of pushing it down.
def _end(end: int | None) -> str:
    return f"${end}" if end else ""


def _e(header: str, q: str, end: int | None = None) -> str:
    c = expense_letter(header)
    return f'SUMIFS(${c}${EXP_HEADER_ROW}:${c}{_end(end)},$B${EXP_HEADER_ROW}:$B{_end(end)},"{q}")'


def _i(income_tab: str, header: str, q: str, end: int | None = None) -> str:
    c = col_letter([h for h, _, _ in INCOME_COLUMNS].index(header))
    return (f"SUMIFS('{income_tab}'!${c}${INC_HEADER_ROW}:${c}{_end(end)},"
            f"'{income_tab}'!$B${INC_HEADER_ROW}:$B{_end(end)},\"{q}\")")


BLOCK = [  # box, label, formula builder (q, income_tab) -> formula, for the boxes you type
    ("3", "Base 23%: PT sales + non-EU purchases (self-charged)", lambda q, it, end: f"={_i(it, 'Box 3', q, end)}+{_e('Box 3', q, end)}"),
    ("4", "IVA 23% on box 3", lambda q, it, end: f"={_i(it, 'Box 4', q, end)}+{_e('Box 4', q, end)}"),
    ("7", "EU business clients, no IVA (+ Recapitulativa)", lambda q, it, end: f"={_i(it, 'Box 7', q, end)}"),
    ("8", "Non-EU clients, no IVA", lambda q, it, end: f"={_i(it, 'Box 8', q, end)}"),
    ("12", "EU goods bought (reverse charge): base", lambda q, it, end: f"={_e('Box 12', q, end)}"),
    ("13", "EU goods bought (reverse charge): IVA", lambda q, it, end: f"={_e('Box 13', q, end)}"),
    ("16", "EU services bought (reverse charge): base", lambda q, it, end: f"={_e('Box 16', q, end)}"),
    ("17", "EU services bought (reverse charge): IVA", lambda q, it, end: f"={_e('Box 17', q, end)}"),
    ("20", "Deductible IVA: fixed assets", lambda q, it, end: f"={_e('Box 20', q, end)}"),
    ("24", "Deductible IVA: other goods & services", lambda q, it, end: f"={_e('Box 24', q, end)}"),
    ("61", "Credit from previous quarter (= its box 96)", None),
    ("98", "Q 06-A: non-EU purchases self-charged (base)", lambda q, it, end: f"={_e('Box 98', q, end)}"),
]
RESULTS = [  # box, label, formula on the block's own rows ({c} = quarter column, {rN} = row of box N)
    ("90", "Total base (1+3+5+7+8+9+10+16+18)", "={c}{r3}+{c}{r7}+{c}{r8}+{c}{r12}+{c}{r16}"),
    ("91", "IVA in your favour (20+24+61)", "={c}{r20}+{c}{r24}+{c}{r61}"),
    ("92", "IVA in favour of the State (4+13+17)", "={c}{r4}+{c}{r13}+{c}{r17}"),
    ("93", "IVA to pay", "=MAX({c}{r92}-{c}{r91},0)"),
    ("94", "IVA to recover", "=MAX({c}{r91}-{c}{r92},0)"),
    ("96", "Credit to carry into next quarter's box 61", "={c}{r94}"),
]
SUM_HEADERS = ["Amount €", "Net € (-VAT)", "Box 3", "Box 4", "Box 12", "Box 13", "Box 16", "Box 17", "Box 20",
               "Box 24", "Box 98", "Net VAT benefit €", "IRS deductible € (Anexo B)"]


def expense_values(year: int, income_tab: str, opening_credit: float, end: int | None = None) -> list[list]:
    """All cell contents of a new expenses tab (rows 1..header), formulas included."""
    width = len(EXPENSE_COLUMNS)
    rows: list[list] = [[f"EXPENSES {year}"], [], ["Declaração Periódica", "", "", "", *QUARTER_COLS]]
    box_row = {}
    for k, (box, *_r) in enumerate(BLOCK + RESULTS):
        box_row[box] = BLOCK_TITLE_ROW + 1 + k
    refs = {f"r{b}": n for b, n in box_row.items()}
    for box, label, fb in BLOCK:
        line = [f"Box {box}", "", label, ""]
        for q, c in QUARTER_COLS.items():
            if box == "61":
                prev = {"Q1": None, "Q2": "E", "Q3": "F", "Q4": "G"}[q]
                line.append(opening_credit if prev is None else f"={prev}{box_row['96']}")
            else:
                line.append(fb(q, income_tab, end))
        rows.append(line)
    for box, label, tpl in RESULTS:
        rows.append([f"Box {box}", "", label, ""] + [tpl.format(c=c, **refs) for c in QUARTER_COLS.values()])
    while len(rows) < SUMS_ROW - 1:
        rows.append([])
    head = [""] * width
    head[0] = "QUARTERS"
    for h in SUM_HEADERS:
        head[[x for x, _, _ in EXPENSE_COLUMNS].index(h)] = h
    rows.append(head)
    for q in QUARTER_COLS:
        line = [""] * width
        line[0] = q
        for h in SUM_HEADERS:
            line[[x for x, _, _ in EXPENSE_COLUMNS].index(h)] = f"={_e(h, q, end)}"
        rows.append(line)
    total = [""] * width
    total[0] = str(year)
    for h in SUM_HEADERS:
        c = expense_letter(h)
        total[[x for x, _, _ in EXPENSE_COLUMNS].index(h)] = f"=SUM({c}{SUMS_ROW + 1}:{c}{SUMS_ROW + 4})"
    rows.append(total)
    while len(rows) < EXP_HEADER_ROW - 1:
        rows.append([])
    rows.append([h for h, _, _ in EXPENSE_COLUMNS])
    return rows


def income_values(year: int, expenses_tab: str, end: int | None = None) -> list[list]:
    irs, e = expense_letter("IRS deductible € (Anexo B)"), _end(end)
    exp_sum = lambda q: f"=SUMIFS('{expenses_tab}'!${irs}${EXP_HEADER_ROW}:${irs}{e},'{expenses_tab}'!$B${EXP_HEADER_ROW}:$B{e},\"{q}\")"
    inc_sum = lambda col, qcol, q: f'=SUMIFS(${col}${INC_HEADER_ROW}:${col}{e},${qcol}${INC_HEADER_ROW}:${qcol}{e},"{q}")'
    rows: list[list] = [[f"INCOME {year}"], ["IRS & SS", "", *QUARTER_COLS, str(year)]]
    for label, f in [("Gross income € (IRS Anexo B, by invoice date)", lambda q: inc_sum("N", "B", q)),
                     ("Income € by recibo date (Segurança Social quarterly declaration)", lambda q: inc_sum("N", "J", q)),
                     ("Business expenses € (IRS deductible, Anexo B quadro 17 if used)", exp_sum)]:
        n = len(rows) + 1
        rows.append([label, ""] + [f(q) for q in QUARTER_COLS] + [f"=SUM(C{n}:F{n})"])
    while len(rows) < INC_HEADER_ROW - 1:
        rows.append([])
    rows.append([h for h, _, _ in INCOME_COLUMNS])
    return rows


def _grid(sid: int, r0: int, r1: int, c0: int, c1: int) -> dict:
    return {"sheetId": sid, "startRowIndex": r0, "endRowIndex": r1, "startColumnIndex": c0, "endColumnIndex": c1}


def _formats(sid: int, columns: list, header_row: int, first_row: int, rows: int) -> list[dict]:
    reqs = [{"repeatCell": {"range": _grid(sid, header_row - 1, header_row, 0, len(columns)),
                            "cell": {"userEnteredFormat": {"textFormat": {"bold": True}, "wrapStrategy": "WRAP",
                                                           "verticalAlignment": "TOP",
                                                           "backgroundColor": {"red": .93, "green": .93, "blue": .93}}},
                            "fields": "userEnteredFormat"}}]
    for j, (h, _, fmt) in enumerate(columns):
        cell = {}
        if fmt:
            cell["numberFormat"] = FORMATS[fmt]
        if h.startswith("Box ") or h == "Net VAT benefit €":
            cell["backgroundColor"] = {"red": 1, "green": .985, "blue": .92}
        if h.startswith("IRS deductible"):
            cell["backgroundColor"] = {"red": .93, "green": .97, "blue": .93}
        if cell:
            reqs.append({"repeatCell": {"range": _grid(sid, first_row - 1, rows, j, j + 1), "cell": {"userEnteredFormat": cell},
                                        "fields": "userEnteredFormat(" + ",".join(cell) + ")"}})
    return reqs


def _validation(sid: int, col: int, first_row: int, rows: int, values: list[str]) -> dict:
    return {"setDataValidation": {"range": _grid(sid, first_row - 1, rows, col, col + 1), "rule": {
        "condition": {"type": "ONE_OF_LIST", "values": [{"userEnteredValue": v} for v in values]},
        "showCustomUi": True, "strict": False}}}


def create_year(sh: gspread.Spreadsheet, year: int, expenses_tab: str, income_tab: str,
                opening_credit: float = 0.0, rows: int = 1000) -> dict:
    """Add the expenses and income tabs for a year to a spreadsheet. Refuses if either tab exists."""
    existing = {w.title for w in sh.worksheets()}
    if expenses_tab in existing or income_tab in existing:
        raise ValueError(f"{expenses_tab} or {income_tab} already exists")
    exp = sh.add_worksheet(expenses_tab, rows=rows, cols=len(EXPENSE_COLUMNS))
    inc = sh.add_worksheet(income_tab, rows=rows, cols=len(INCOME_COLUMNS))
    exp.update(values=expense_values(year, income_tab, opening_credit), range_name="A1", value_input_option="USER_ENTERED")
    inc.update(values=income_values(year, expenses_tab), range_name="A1", value_input_option="USER_ENTERED")
    names = [h for h, _, _ in EXPENSE_COLUMNS]
    block_end = BLOCK_TITLE_ROW + len(BLOCK) + len(RESULTS)
    reqs = _formats(exp.id, EXPENSE_COLUMNS, EXP_HEADER_ROW, EXP_FIRST_ROW, rows)
    reqs += _formats(inc.id, INCOME_COLUMNS, INC_HEADER_ROW, INC_FIRST_ROW, rows)
    reqs += [
        {"repeatCell": {"range": _grid(exp.id, 0, 1, 0, 1), "cell": {"userEnteredFormat": {"textFormat": {"bold": True, "fontSize": 12}}},
                        "fields": "userEnteredFormat.textFormat"}},
        {"repeatCell": {"range": _grid(inc.id, 0, 1, 0, 1), "cell": {"userEnteredFormat": {"textFormat": {"bold": True, "fontSize": 12}}},
                        "fields": "userEnteredFormat.textFormat"}},
        {"repeatCell": {"range": _grid(exp.id, BLOCK_TITLE_ROW - 1, BLOCK_TITLE_ROW, 0, 8),
                        "cell": {"userEnteredFormat": {"textFormat": {"bold": True}, "backgroundColor": {"red": 1, "green": .95, "blue": .75}}},
                        "fields": "userEnteredFormat(textFormat,backgroundColor)"}},
        {"repeatCell": {"range": _grid(exp.id, BLOCK_TITLE_ROW, block_end, 4, 8), "cell": {"userEnteredFormat": {"numberFormat": FORMATS["num"]}},
                        "fields": "userEnteredFormat.numberFormat"}},
        {"repeatCell": {"range": _grid(exp.id, SUMS_ROW - 1, SUMS_ROW + 5, 0, len(names)),
                        "cell": {"userEnteredFormat": {"numberFormat": FORMATS["num"], "textFormat": {"bold": False}}},
                        "fields": "userEnteredFormat.numberFormat"}},
        {"repeatCell": {"range": _grid(exp.id, SUMS_ROW - 1, SUMS_ROW, 0, len(names)),
                        "cell": {"userEnteredFormat": {"textFormat": {"bold": True}, "wrapStrategy": "WRAP"}},
                        "fields": "userEnteredFormat(textFormat,wrapStrategy)"}},
        {"repeatCell": {"range": _grid(inc.id, 1, 2, 0, 7), "cell": {"userEnteredFormat": {"textFormat": {"bold": True}}},
                        "fields": "userEnteredFormat.textFormat"}},
        {"repeatCell": {"range": _grid(inc.id, 2, 5, 2, 7), "cell": {"userEnteredFormat": {"numberFormat": FORMATS["num"]}},
                        "fields": "userEnteredFormat.numberFormat"}},
        _validation(exp.id, names.index("VAT code"), EXP_FIRST_ROW, rows, list(CODES)),
        _validation(exp.id, names.index("Document"), EXP_FIRST_ROW, rows, DOCUMENT_LABELS),
        _validation(inc.id, [h for h, _, _ in INCOME_COLUMNS].index("VAT case"), INC_FIRST_ROW, rows, list(SALES_CODES)),
        {"addConditionalFormatRule": {"index": 0, "rule": {"ranges": [_grid(exp.id, EXP_FIRST_ROW - 1, rows, names.index("Document"), names.index("Document") + 1)],
                                                           "booleanRule": {"condition": {"type": "CUSTOM_FORMULA", "values": [
                                                               {"userEnteredValue": f'=REGEXMATCH({expense_letter("Document")}{EXP_FIRST_ROW},"MISSING")'}]},
                                                               "format": {"textFormat": {"bold": True, "foregroundColor": {"red": .8, "green": .1, "blue": .1}}}}}}},
        {"updateSheetProperties": {"properties": {"sheetId": exp.id, "gridProperties": {"frozenColumnCount": 3}},
                                   "fields": "gridProperties.frozenColumnCount"}},
    ]
    sh.batch_update({"requests": reqs})
    return {"expenses_tab": expenses_tab, "income_tab": income_tab, "opening_credit": opening_credit,
            "expense_table_row": EXP_HEADER_ROW, "income_table_row": INC_HEADER_ROW}
