import json
from types import SimpleNamespace

from django.test import SimpleTestCase

from fiscguy.services.closing_day_service import ClosingDayService

TAX_MAP = {1: "Exempt", 2: "Zero rated 0%", 517: "Standard rated 15.5%"}


def counter(type_, tax_id, percent, value):
    return SimpleNamespace(
        fiscal_counter_type=type_,
        fiscal_counter_currency="USD",
        fiscal_counter_tax_id=tax_id,
        fiscal_counter_tax_percent=percent,
        fiscal_counter_value=value,
        fiscal_counter_money_type=None,
    )


def make_service(counters):
    # Bypass __init__: it builds a ZIMRA client / crypto handler, which needs
    # certificates and has nothing to do with how the payload is shaped.
    svc = ClosingDayService.__new__(ClosingDayService)
    svc.counters = counters
    svc.tax_map = TAX_MAP
    for name in (
        "sale_by_tax", "sale_tax_by_tax", "credit_by_tax", "credit_tax_by_tax",
        "debit_by_tax", "debit_tax_by_tax", "balance_by_money",
    ):
        setattr(svc, f"{name}_payload", [])
    return svc


def by_tax_id(payload):
    return {p["fiscalCounterTaxID"]: p for p in payload}


class ByTaxCounterPayloadTests(SimpleTestCase):
    CASES = [
        # (counter type, builder, payload attribute)
        ("SaleByTax", "build_sale_by_tax", "sale_by_tax_payload"),
        ("CreditNoteByTax", "build_credit_note_by_tax", "credit_by_tax_payload"),
        ("DebitNoteByTax", "build_debit_note_by_tax", "debit_by_tax_payload"),
    ]

    def _run(self, type_, builder):
        svc = make_service([
            counter(type_, 1, None, 20.0),       # exempt
            counter(type_, 2, 0.0, 9.0),         # zero-rated
            counter(type_, 517, 15.5, 1562.37),  # standard
        ])
        closing = getattr(svc, builder)()
        return svc, closing

    def test_exempt_counter_sends_explicit_null_tax_percent(self):
        # Regression guard: omitting the key made the FDMS test server close the
        # day with BadCertificateSignature. Exempt must go out as null.
        for type_, builder, attr in self.CASES:
            with self.subTest(type_):
                svc, _ = self._run(type_, builder)
                exempt = by_tax_id(getattr(svc, attr))[1]
                self.assertIn("fiscalCounterTaxPercent", exempt)
                self.assertIsNone(exempt["fiscalCounterTaxPercent"])
                self.assertEqual(exempt["fiscalCounterValue"], 20.0)

    def test_exempt_counter_json_has_null_percent(self):
        for type_, builder, attr in self.CASES:
            with self.subTest(type_):
                svc, _ = self._run(type_, builder)
                exempt = by_tax_id(getattr(svc, attr))[1]
                self.assertIn('"fiscalCounterTaxPercent": null', json.dumps(exempt))

    def test_zero_rated_is_still_sent_as_zero(self):
        for type_, builder, attr in self.CASES:
            with self.subTest(type_):
                svc, _ = self._run(type_, builder)
                zero = by_tax_id(getattr(svc, attr))[2]
                self.assertIn("fiscalCounterTaxPercent", zero)
                self.assertEqual(zero["fiscalCounterTaxPercent"], 0.0)

    def test_standard_rate_is_sent(self):
        for type_, builder, attr in self.CASES:
            with self.subTest(type_):
                svc, _ = self._run(type_, builder)
                self.assertEqual(by_tax_id(getattr(svc, attr))[517]["fiscalCounterTaxPercent"], 15.5)

    def test_all_counters_still_present_and_in_order(self):
        for type_, builder, attr in self.CASES:
            with self.subTest(type_):
                svc, _ = self._run(type_, builder)
                self.assertEqual([p["fiscalCounterTaxID"] for p in getattr(svc, attr)], [1, 2, 517])

    def test_signed_closing_string_is_unchanged(self):
        # exempt has no rate segment, zero is "0.00", standard "15.50"; amounts in cents.
        svc, closing = self._run("SaleByTax", "build_sale_by_tax")
        self.assertEqual(closing, "salebytaxUSD2000" "salebytaxUSD0.00900" "salebytaxUSD15.50156237")

    def test_tax_by_tax_counters_keep_their_rate(self):
        svc = make_service([counter("SaleTaxByTax", 517, 15.5, 209.67)])
        svc.build_sale_tax_by_tax()
        self.assertEqual(svc.sale_tax_by_tax_payload[0]["fiscalCounterTaxPercent"], 15.5)
