from decimal import Decimal

import pytest

from fiscguy.zimra_crypto import ZIMRACrypto


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("0.10", 10),
        ("0.30", 30),
        ("23.75", 2375),
        ("999.99", 99999),
    ],
)
def test_decimal_to_cents_uses_decimal_rounding(value, expected):
    assert ZIMRACrypto._decimal_to_cents(Decimal(value)) == expected


def test_generate_receipt_signature_string_uses_decimal_values():
    signature = ZIMRACrypto().generate_receipt_signature_string(
        device_id="41872",
        receipt_type="FiscalInvoice",
        receipt_currency="USD",
        receipt_global_no=17,
        receipt_date="2026-05-03T12:30:45",
        receipt_total=Decimal("23.75"),
        receipt_taxes=[
            {
                "taxID": 3,
                "taxPercent": Decimal("15.00"),
                "taxAmount": Decimal("3.10"),
                "salesAmountWithTax": Decimal("23.75"),
            }
        ],
        previous_receipt_hash="prevhash",
    )

    assert signature == "41872FISCALINVOICEUSD172026-05-03T12:30:45237515.003102375prevhash"
