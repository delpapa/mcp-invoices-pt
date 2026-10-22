"""Each layout parser on a made-up sample shaped like the real document (no real data)."""

import datetime as dt

import pytest

from invoices_pt.documents import parsers, text
from invoices_pt.documents.parsers import _common
from invoices_pt.model import Document

STRIPE_INVOICE = """Invoice
Invoice number  ABCD1234-0007
Date of issue  March 3, 2026
Date due  March 3, 2026
VAT Registration  EU VAT: IE0000000XX
Example AI, Inc. @example  Bill to
1 Example Way  Jane Doe
Exampletown, California 90000  Rua Exemplo 1
United States  Portugal
billing@example.com  jane@example.com
  PT VAT PT999999990
Description  Qty  Unit price  Tax  Amount
Standard plan  1  €31.40  0%  €31.40
  Subtotal  €31.40
  Total  €31.40
  Amount due  €31.40
[1] Tax to be paid on reverse charge basis
"""
STRIPE_RECEIPT = """Receipt
Invoice number ABCD12340008
Receipt number 1234-5678
Date paid  April 9, 2026
Example AI, Inc.  Bill to
1 Example Way  Jane Doe
United States  Portugal
  DE VAT 123456789
Description  Qty  Unit price  Tax  Amount
Starter  1  $40.00  23%  $40.00
  Subtotal  $40.00
  Total excluding tax  $40.00
  VAT - Portugal (23% on $40.00)  $9.20
  Total  $49.20
  Amount paid  $49.20
Payment method  Date  Amount paid  Receipt number
Mastercard - 4242  April 9, 2026  $49.20  1234
"""
GITHUB_INVOICE = """  INVOICE
GitHub, Inc.  Invoice #  INV000000001
Support Contact  BILL TO
1 Example Street  Invoice Date Mar 17, 2026
  Currency  USD
  SUBTOTAL:  $21.00
  If applicable, customer should account for the  $0.00
  TAX:
  respective VAT reverse charge.
  INVOICE TOTAL:  $21.00
"""
GITHUB_RECEIPT = """We received payment for your GitHub.com subscription. Thanks for your business!
Date  2026-02-19 03:14PM PST
Transaction ID  ch_TESTTRANSACTION
Charged to  MasterCard (5*** **** **** 4242)
Tax  $0.00 USD
Total  $21.00 USD*
GitHub, Inc.  https://support.github.com/contact
"""
GOOGLE_CLOUD = """  Google Cloud EMEA Limited
  Ireland
Invoice number: 1000000001
  VAT number: IE0000000XX
Bill to
VAT number: PT 999999990
Invoice  date  Jan 31, 2026  Total in EUR  €14.76
  Subtotal in EUR  €12.00
  VAT (23%)  €2.76
  Total in EUR  €14.76
"""
GOOGLE_PLAY = """  From: Google Play <googleplay-noreply@google.com>
  Order number: GPA.0000-0000-0000-00000
  Order date: Feb 5, 2026 9:12:00 AM GMT+0
  Example App yearly (by Example Apps)  59,90 €/
  Total: 59,90 €/year
  (Includes VAT of 9,56 €)
  Payment method:  Mastercard-4242
  Google Commerce Limited
"""
WISE = """Transfer confirmation
Transfer created  Funded
February 3, 2026 10:00:00 WET  February 3, 2026 10:00:07 WET
#1234567890  P00000000
Amount paid by Jane Doe  Transfer fees
2,000.00 USD  Conversion 12.40 USD
  Payment method 0.00 USD
  Total 12.40 USD
Transfer amount  Exchange rate
1,987.60 USD  1 USD = 0.8500 EUR
Total to Jane Doe
1,689.46 EUR
Wise is the trading name of Wise Europe SA, a Payment Institution authorised by the National Bank of Belgium
with registered number 0123456789 and registered office at 1 Example Square
"""
AMAZON = """ Factura
 Vendido por  EXAMPLE SELLER LIMITED
 IVA  ESN0000000A
 Fecha de la factura/Fecha de la entrega  15 marzo 2026
 Número de la factura  ES000TESTINVOICE
 Si tienes preguntas sobre tus pedidos, visita www.amazon.es/contact-us
 NIF sujeto de IVA  PT999999990
 Total  35,40 €
 Total  35,40 €  0,00 €
 (1) Entregas intracomunitarias exentas - Articulo 138 Directiva 2006/112/EC
"""
OWN_INVOICE = """ INVOICE
Jane Doe
 INVOICE NO. JD012
 DATE 04.05.26
 NIF: 999999990
 TO Example Client Inc.
 TOTAL DUE $1,500.00
* IVA: not charged (art. 6.º, n.º 6, a) do CIVA)
"""

CASES = [  # sample, parser, expected fields
    (STRIPE_INVOICE, "stripe", dict(doc_type="invoice", supplier="Example AI, Inc.", country="US",
                                    supplier_vat="IE0000000XX", invoice_no="ABCD1234-0007", date=dt.date(2026, 3, 3),
                                    currency="EUR", amount=31.4, vat_included=0.0, buyer_nif="999999990")),
    (STRIPE_RECEIPT, "stripe", dict(doc_type="receipt", invoice_no="ABCD1234-0008", currency="USD", amount=49.2,
                                    vat_included=9.2, buyer_nif="123456789", date=dt.date(2026, 4, 9))),
    (GITHUB_INVOICE, "github", dict(doc_type="invoice", invoice_no="INV000000001", date=dt.date(2026, 3, 17),
                                    currency="USD", amount=21.0, vat_included=0.0, country="US")),
    (GITHUB_RECEIPT, "github", dict(doc_type="receipt", invoice_no="ch_TESTTRANSACTION", date=dt.date(2026, 2, 19),
                                    currency="USD", amount=21.0, vat_included=0.0)),
    (GOOGLE_CLOUD, "google_cloud", dict(invoice_no="1000000001", date=dt.date(2026, 1, 31), amount=14.76,
                                        vat_included=2.76, supplier_vat="IE0000000XX", buyer_nif="999999990",
                                        markers=["foreign_vat_charged"])),
    (GOOGLE_PLAY, "google_play", dict(invoice_no="GPA.0000-0000-0000-00000", date=dt.date(2026, 2, 5),
                                      amount=59.9, vat_included=9.56, currency="EUR")),
    (WISE, "wise", dict(invoice_no="1234567890", date=dt.date(2026, 2, 3), amount=12.4, currency="USD",
                        supplier_vat="BE0123456789", markers=["exempt"])),
    (AMAZON, "amazon", dict(supplier="EXAMPLE SELLER LIMITED (Amazon.es)", supplier_vat="ESN0000000A", country="ES",
                            invoice_no="ES000TESTINVOICE", date=dt.date(2026, 3, 15), amount=35.4, vat_included=0.0,
                            buyer_nif="999999990")),
]


@pytest.mark.parametrize("sample, name, expected", CASES, ids=[f"{c[1]}-{i}" for i, c in enumerate(CASES)])
def test_parser(sample, name, expected):
    claimed = [p.NAME for p in parsers.PARSERS if p.matches(sample)]
    assert claimed == [name]
    doc: Document = parsers.find(sample).parse(sample, "")
    for field, value in expected.items():
        assert getattr(doc, field) == value, field


def test_wise_rate_and_markers():
    wise = parsers.find(WISE).parse(WISE)
    assert wise.extra["fx_rate"] == 1.1765
    assert text.markers(STRIPE_INVOICE) == ["reverse_charge"]
    assert text.markers(AMAZON) == ["intra_eu_goods"]
    assert text.card_last4(GOOGLE_PLAY) == "4242"
    assert text.card_last4(GITHUB_RECEIPT) == "4242"


def test_example_private_parser():
    """The example in examples/parsers loads through load_dir, like a parser in your private parsers_dir."""
    import os
    folder = os.path.join(os.path.dirname(__file__), "..", "examples", "parsers")
    assert "simple_invoice" in parsers.load_dir(folder) or any(p.NAME == "simple_invoice" for p in parsers.PARSERS)
    doc = parsers.find(OWN_INVOICE).parse(OWN_INVOICE, "")
    assert (doc.layer, doc.doc_type, doc.supplier, doc.invoice_no) == ("parser:simple_invoice", "sales_invoice", "Jane Doe", "JD012")
    assert (doc.date, doc.currency, doc.amount, doc.markers) == (dt.date(2026, 4, 5), "USD", 1500.0, ["not_taxed_in_pt"])
    assert parsers.find(OWN_INVOICE).parse(OWN_INVOICE, "/x/JD 20260504 Invoice.pdf").date == dt.date(2026, 5, 4)


def test_private_glyph_hyphen():
    assert text.clean("Invoice number ABCD12340007") == "Invoice number ABCD1234-0007"


@pytest.mark.parametrize("raw, value", [("1,234.56", 1234.56), ("1.234,56", 1234.56), ("95,00", 95.0),
                                        ("-$12.34", -12.34), ("47.50€", 47.5), ("1,234", 1234.0)])
def test_money(raw, value):
    assert _common.money(raw) == value


@pytest.mark.parametrize("raw, value", [("November 12, 2026", dt.date(2026, 11, 12)), ("Dec 21, 2026", dt.date(2026, 12, 21)),
                                        ("2026-07-19", dt.date(2026, 7, 19)), ("8/27/2026", dt.date(2026, 8, 27)),
                                        ("27 junio 2026", dt.date(2026, 6, 27)), ("3 de março de 2026", dt.date(2026, 3, 3))])
def test_dates(raw, value):
    assert _common.date(raw) == value
