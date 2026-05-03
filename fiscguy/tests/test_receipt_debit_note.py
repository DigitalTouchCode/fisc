from datetime import datetime
from decimal import Decimal
from unittest.mock import patch

import pytest

from fiscguy.exceptions import ReceiptSubmissionError
from fiscguy.models import Certs, Configuration, Device, FiscalCounter, FiscalDay, Receipt, Taxes
from fiscguy.serializers import ReceiptCreateSerializer
from fiscguy.zimra_receipt_handler import ZIMRAReceiptHandler


@pytest.fixture
def device(db):
    return Device.objects.create(
        org_name="Test Org",
        activation_key="test-key-123",
        device_id="1001",
        device_model_name="ModelX",
        device_model_version="1.0",
        device_serial_number="SN-12345",
        production=False,
    )


@pytest.fixture
def configuration(db, device):
    return Configuration.objects.create(
        device=device,
        tax_payer_name="Test Taxpayer",
        tax_inclusive=True,
        tin_number="123456789",
        vat_number="987654",
        address="123 Test Street",
        phone_number="+263123456",
        email="test@example.com",
        url="https://example.com/qr",
    )


@pytest.fixture
def certs(db, device):
    return Certs.objects.create(
        device=device,
        csr="-----BEGIN CERTIFICATE REQUEST-----\ntest\n-----END CERTIFICATE REQUEST-----",
        certificate="-----BEGIN CERTIFICATE-----\ntest-cert\n-----END CERTIFICATE-----",
        certificate_key="-----BEGIN PRIVATE KEY-----\ntest-key\n-----END PRIVATE KEY-----",
        production=False,
    )


@pytest.fixture
def tax(db, device):
    return Taxes.objects.create(
        device=device,
        code="3",
        name="Standard Rated 15%",
        tax_id=3,
        percent=Decimal("15.00"),
    )


@pytest.fixture
def original_receipt(db, device, tax):
    receipt = Receipt.objects.create(
        device=device,
        receipt_number="R-00000142",
        receipt_type="fiscalinvoice",
        total_amount=Decimal("100.00"),
        currency="USD",
        signature="orig-signature",
        global_number=142,
        hash_value="prev-hash",
        zimra_inv_id="fdms-receipt-142",
        submitted=True,
        payment_terms="Cash",
    )
    receipt.lines.create(
        product="Delivery fee",
        hs_code="22030000",
        quantity=Decimal("1.00"),
        unit_price=Decimal("100.00"),
        line_total=Decimal("100.00"),
        tax_amount=Decimal("13.04"),
        tax_type=tax,
    )
    return receipt


@pytest.mark.django_db
def test_debit_note_serializer_accepts_alias_fields(device, original_receipt):
    serializer = ReceiptCreateSerializer(
        data={
            "device": device.id,
            "receipt_type": "debitnote",
            "currency": "USD",
            "total_amount": "23.00",
            "payment_terms": "Card",
            "debit_note_reference": original_receipt.receipt_number,
            "debit_note_reason": "Additional delivery fee",
            "lines": [
                {
                    "product": "Fee",
                    "hs_code": "99001000",
                    "quantity": "1",
                    "unit_price": "23.00",
                    "line_total": "23.00",
                    "tax_amount": "3.00",
                    "tax_id": 3,
                }
            ],
        }
    )

    assert serializer.is_valid(), serializer.errors
    assert serializer.validated_data["credit_note_reference"] == original_receipt.receipt_number
    assert serializer.validated_data["credit_note_reason"] == "Additional delivery fee"


@pytest.mark.django_db
def test_debit_note_serializer_rejects_negative_total(device, original_receipt):
    serializer = ReceiptCreateSerializer(
        data={
            "device": device.id,
            "receipt_type": "debitnote",
            "currency": "USD",
            "total_amount": "-23.00",
            "payment_terms": "Card",
            "debit_note_reference": original_receipt.receipt_number,
            "debit_note_reason": "Additional delivery fee",
            "lines": [
                {
                    "product": "Fee",
                    "hs_code": "99001000",
                    "quantity": "1",
                    "unit_price": "23.00",
                    "line_total": "23.00",
                    "tax_amount": "3.00",
                    "tax_id": 3,
                }
            ],
        }
    )

    assert not serializer.is_valid()
    assert "total_amount" in serializer.errors


@pytest.mark.django_db
def test_fiscal_invoice_serializer_requires_hs_code(device):
    serializer = ReceiptCreateSerializer(
        data={
            "device": device.id,
            "receipt_type": "fiscalinvoice",
            "currency": "USD",
            "total_amount": "23.00",
            "payment_terms": "Cash",
            "lines": [
                {
                    "product": "Consulting",
                    "hs_code": "",
                    "quantity": "1",
                    "unit_price": "23.00",
                    "line_total": "23.00",
                    "tax_amount": "3.00",
                    "tax_id": 3,
                }
            ],
        }
    )

    assert not serializer.is_valid()
    assert "lines" in serializer.errors


@pytest.mark.django_db
def test_receipt_serializer_rejects_empty_lines(device):
    serializer = ReceiptCreateSerializer(
        data={
            "device": device.id,
            "receipt_type": "fiscalinvoice",
            "currency": "USD",
            "total_amount": "23.00",
            "payment_terms": "Cash",
            "lines": [],
        }
    )

    assert not serializer.is_valid()
    assert "lines" in serializer.errors


@pytest.mark.django_db
def test_receipt_serializer_rejects_total_mismatch(device):
    serializer = ReceiptCreateSerializer(
        data={
            "device": device.id,
            "receipt_type": "fiscalinvoice",
            "currency": "USD",
            "total_amount": "20.00",
            "payment_terms": "Cash",
            "lines": [
                {
                    "product": "Consulting",
                    "hs_code": "99001000",
                    "quantity": "1",
                    "unit_price": "23.00",
                    "line_total": "23.00",
                    "tax_amount": "3.00",
                    "tax_id": 3,
                }
            ],
        }
    )

    assert not serializer.is_valid()
    assert "total_amount" in serializer.errors


@pytest.mark.django_db
def test_receipt_serializer_rejects_unknown_tax_id(device):
    serializer = ReceiptCreateSerializer(
        data={
            "device": device.id,
            "receipt_type": "fiscalinvoice",
            "currency": "USD",
            "total_amount": "23.00",
            "payment_terms": "Cash",
            "lines": [
                {
                    "product": "Consulting",
                    "hs_code": "99001000",
                    "quantity": "1",
                    "unit_price": "23.00",
                    "line_total": "23.00",
                    "tax_amount": "3.00",
                    "tax_id": 999,
                }
            ],
        }
    )

    assert serializer.is_valid(), serializer.errors
    with pytest.raises(Exception):
        serializer.save()


@pytest.mark.django_db
def test_receipt_handler_maps_debit_note_payload_and_counters(
    device, configuration, certs, tax, original_receipt
):
    fiscal_day = FiscalDay.objects.create(device=device, day_no=1, receipt_counter=1, is_open=True)
    receipt = Receipt.objects.create(
        device=device,
        receipt_type="debitnote",
        total_amount=Decimal("23.00"),
        currency="USD",
        signature="",
        payment_terms="Card",
        credit_note_reason="Additional delivery fee",
        credit_note_reference=original_receipt.receipt_number,
    )
    receipt.lines.create(
        product="Delivery fee",
        hs_code="99001000",
        quantity=Decimal("1.00"),
        unit_price=Decimal("23.00"),
        line_total=Decimal("23.00"),
        tax_amount=Decimal("3.00"),
        tax_type=tax,
    )

    handler = ZIMRAReceiptHandler(device)

    with patch.object(handler, "_get_next_global_number", return_value=143):
        payload = handler._build_receipt_data_inner(receipt, receipt.lines.all(), fiscal_day)

    assert payload["receipt_data"]["receiptType"] == "DebitNote"
    assert payload["receipt_data"]["receiptLines"][0]["receiptLineHSCode"] == "99001000"
    assert payload["receipt_data"]["creditDebitNote"] == {
        "receiptID": original_receipt.zimra_inv_id
    }

    handler._update_fiscal_counters_inner(receipt, payload["receipt_data"])

    assert FiscalCounter.objects.filter(
        device=device,
        fiscal_day=fiscal_day,
        fiscal_counter_type="DebitNoteByTax",
    ).exists()
    assert FiscalCounter.objects.filter(
        device=device,
        fiscal_day=fiscal_day,
        fiscal_counter_type="DebitNoteTaxByTax",
    ).exists()


@pytest.mark.django_db
def test_debit_note_inherits_hs_code_from_original_receipt_line(
    device, configuration, certs, tax, original_receipt
):
    fiscal_day = FiscalDay.objects.create(device=device, day_no=1, receipt_counter=1, is_open=True)
    receipt = Receipt.objects.create(
        device=device,
        receipt_type="debitnote",
        total_amount=Decimal("23.00"),
        currency="USD",
        signature="",
        payment_terms="Card",
        credit_note_reason="Additional delivery fee",
        credit_note_reference=original_receipt.receipt_number,
    )
    receipt.lines.create(
        product="Delivery fee",
        hs_code="",
        quantity=Decimal("1.00"),
        unit_price=Decimal("23.00"),
        line_total=Decimal("23.00"),
        tax_amount=Decimal("3.00"),
        tax_type=tax,
    )

    handler = ZIMRAReceiptHandler(device)

    with patch.object(handler, "_get_next_global_number", return_value=143):
        payload = handler._build_receipt_data_inner(receipt, receipt.lines.all(), fiscal_day)

    assert payload["receipt_data"]["receiptLines"][0]["receiptLineHSCode"] == "22030000"


@pytest.mark.django_db
def test_receipt_handler_blocks_submission_while_close_pending(device):
    FiscalDay.objects.create(
        device=device,
        day_no=1,
        receipt_counter=1,
        is_open=True,
        close_state=FiscalDay.CloseState.CLOSE_PENDING,
    )

    handler = ZIMRAReceiptHandler(device)

    with pytest.raises(ReceiptSubmissionError, match="close is pending"):
        handler._ensure_fiscal_day_open()


@pytest.mark.django_db
def test_debit_note_falls_back_to_service_hs_code_when_no_original_match(
    device, configuration, certs, tax, original_receipt
):
    fiscal_day = FiscalDay.objects.create(device=device, day_no=1, receipt_counter=1, is_open=True)
    receipt = Receipt.objects.create(
        device=device,
        receipt_type="debitnote",
        total_amount=Decimal("23.00"),
        currency="USD",
        signature="",
        payment_terms="Card",
        credit_note_reason="Additional service fee",
        credit_note_reference=original_receipt.receipt_number,
    )
    receipt.lines.create(
        product="Support surcharge",
        hs_code="",
        quantity=Decimal("1.00"),
        unit_price=Decimal("23.00"),
        line_total=Decimal("23.00"),
        tax_amount=Decimal("3.00"),
        tax_type=tax,
    )

    handler = ZIMRAReceiptHandler(device)

    with patch.object(handler, "_get_next_global_number", return_value=143):
        payload = handler._build_receipt_data_inner(receipt, receipt.lines.all(), fiscal_day)

    assert payload["receipt_data"]["receiptLines"][0]["receiptLineHSCode"] == "99001000"


@pytest.mark.django_db
def test_credit_note_inherits_hs_code_from_original_receipt_line(
    device, configuration, certs, tax, original_receipt
):
    fiscal_day = FiscalDay.objects.create(device=device, day_no=1, receipt_counter=1, is_open=True)
    receipt = Receipt.objects.create(
        device=device,
        receipt_type="creditnote",
        total_amount=Decimal("-23.00"),
        currency="USD",
        signature="",
        payment_terms="Card",
        credit_note_reason="Returned delivery fee",
        credit_note_reference=original_receipt.receipt_number,
    )
    receipt.lines.create(
        product="Delivery fee",
        hs_code="",
        quantity=Decimal("1.00"),
        unit_price=Decimal("-23.00"),
        line_total=Decimal("-23.00"),
        tax_amount=Decimal("-3.00"),
        tax_type=tax,
    )

    handler = ZIMRAReceiptHandler(device)

    with patch.object(handler, "_get_next_global_number", return_value=143):
        payload = handler._build_receipt_data_inner(receipt, receipt.lines.all(), fiscal_day)

    assert payload["receipt_data"]["receiptLines"][0]["receiptLineHSCode"] == "22030000"


@pytest.mark.django_db
def test_first_receipt_date_is_after_fiscal_day_open_time(device, configuration, certs, tax):
    fiscal_day = FiscalDay.objects.create(device=device, day_no=1, receipt_counter=0, is_open=True)
    receipt = Receipt.objects.create(
        device=device,
        receipt_type="fiscalinvoice",
        total_amount=Decimal("23.00"),
        currency="USD",
        signature="",
        payment_terms="Cash",
    )
    receipt.lines.create(
        product="Item",
        hs_code="22030000",
        quantity=Decimal("1.00"),
        unit_price=Decimal("23.00"),
        line_total=Decimal("23.00"),
        tax_amount=Decimal("3.00"),
        tax_type=tax,
    )

    handler = ZIMRAReceiptHandler(device)
    fixed_now = handler._to_harare_datetime(fiscal_day.created_at)

    with (
        patch.object(handler, "_get_next_global_number", return_value=1),
        patch.object(handler, "_current_harare_datetime", return_value=fixed_now),
    ):
        payload = handler._build_receipt_data_inner(receipt, receipt.lines.all(), fiscal_day)

    assert payload["receipt_data"]["receiptDate"] > fixed_now.strftime("%Y-%m-%dT%H:%M:%S")


@pytest.mark.django_db
def test_receipt_date_is_after_previous_receipt_time(device, configuration, certs, tax):
    fiscal_day = FiscalDay.objects.create(device=device, day_no=1, receipt_counter=1, is_open=True)
    previous_receipt = Receipt.objects.create(
        device=device,
        receipt_number="R-00000001",
        receipt_type="fiscalinvoice",
        total_amount=Decimal("23.00"),
        currency="USD",
        signature="prev-signature",
        global_number=1,
        hash_value="prev-hash",
        submitted=True,
        payment_terms="Cash",
    )
    previous_receipt.created_at = fiscal_day.created_at
    previous_receipt.save(update_fields=["created_at"])

    receipt = Receipt.objects.create(
        device=device,
        receipt_type="fiscalinvoice",
        total_amount=Decimal("23.00"),
        currency="USD",
        signature="",
        payment_terms="Cash",
    )
    receipt.lines.create(
        product="Item",
        hs_code="22030000",
        quantity=Decimal("1.00"),
        unit_price=Decimal("23.00"),
        line_total=Decimal("23.00"),
        tax_amount=Decimal("3.00"),
        tax_type=tax,
    )

    handler = ZIMRAReceiptHandler(device)
    fixed_now = handler._to_harare_datetime(previous_receipt.created_at)

    with (
        patch.object(handler, "_get_next_global_number", return_value=2),
        patch.object(handler, "_current_harare_datetime", return_value=fixed_now),
    ):
        payload = handler._build_receipt_data_inner(receipt, receipt.lines.all(), fiscal_day)

    expected = (fixed_now.replace(microsecond=0)).strftime("%Y-%m-%dT%H:%M:%S")
    assert payload["receipt_data"]["receiptDate"] > expected
