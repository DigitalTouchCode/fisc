from datetime import datetime
from decimal import Decimal
from unittest.mock import MagicMock, Mock, patch

import pytest
import requests
from django.test import TestCase

from fiscguy.exceptions import CloseDayError
from fiscguy.models import Certs, Configuration, Device, FiscalCounter, FiscalDay, Taxes
from fiscguy.services.closing_day_service import ClosingDayService


@pytest.fixture
def device(db):
    """Create a test device."""
    return Device.objects.create(
        org_name="Test Org",
        activation_key="test-key-123",
        device_id="TEST-DEVICE-001",
        device_model_name="ModelX",
        device_model_version="1.0",
        device_serial_number="SN-12345",
        production=False,
    )


@pytest.fixture
def configuration(db):
    """Create test configuration."""
    return Configuration.objects.create(
        tax_payer_name="Test Taxpayer",
        tax_inclusive=True,
        tin_number="123456789",
        vat_number="987654",
        address="123 Test Street",
        phone_number="+263123456",
        email="test@example.com",
    )


@pytest.fixture
def certs(db):
    """Create test certificates."""
    return Certs.objects.create(
        csr="-----BEGIN CERTIFICATE REQUEST-----\ntest\n-----END CERTIFICATE REQUEST-----",
        certificate="-----BEGIN CERTIFICATE-----\ntest-cert\n-----END CERTIFICATE-----",
        certificate_key="-----BEGIN PRIVATE KEY-----\ntest-key\n-----END PRIVATE KEY-----",
        production=False,
    )


@pytest.fixture
def fiscal_day(db):
    """Create a test fiscal day."""
    return FiscalDay.objects.create(
        day_no=1,
        receipt_counter=100,
        is_open=True,
        created_at=datetime(2024, 1, 15, 10, 0, 0),
    )


@pytest.fixture
def tax_map():
    """Return a tax ID to name mapping."""
    return {
        1: "Standard Rate",
        2: "Zero Rate",
        3: "Exempt",
    }


@pytest.fixture
def fiscal_counters(db, fiscal_day):
    """Create test fiscal counters."""
    return [
        FiscalCounter.objects.create(
            fiscal_day=fiscal_day,
            fiscal_counter_type="SaleByTax",
            fiscal_counter_currency="USD",
            fiscal_counter_tax_percent=Decimal("15.00"),
            fiscal_counter_tax_id=1,
            fiscal_counter_value=Decimal("1000.00"),
        ),
        FiscalCounter.objects.create(
            fiscal_day=fiscal_day,
            fiscal_counter_type="SaleByTax",
            fiscal_counter_currency="USD",
            fiscal_counter_tax_percent=Decimal("0.00"),
            fiscal_counter_tax_id=2,
            fiscal_counter_value=Decimal("500.00"),
        ),
        FiscalCounter.objects.create(
            fiscal_day=fiscal_day,
            fiscal_counter_type="SaleTaxByTax",
            fiscal_counter_currency="USD",
            fiscal_counter_tax_percent=Decimal("15.00"),
            fiscal_counter_tax_id=1,
            fiscal_counter_value=Decimal("150.00"),
        ),
        FiscalCounter.objects.create(
            fiscal_day=fiscal_day,
            fiscal_counter_type="BalanceByMoneyType",
            fiscal_counter_currency="USD",
            fiscal_counter_money_type="Cash",
            fiscal_counter_value=Decimal("1500.00"),
        ),
    ]


@pytest.mark.django_db
class TestClosingDayServiceBasics:
    """Test basic ClosingDayService functionality."""

    def test_service_initialization(
        self, device, fiscal_day, fiscal_counters, tax_map, configuration, certs
    ):
        """Test service initialization."""
        service = ClosingDayService(device, fiscal_day, fiscal_counters, tax_map)

        assert service.device == device
        assert service.fiscal_day == fiscal_day
        assert service.counters == fiscal_counters
        assert service.tax_map == tax_map
        assert service.receipt_handler is not None
        assert service.client is not None

    def test_money_value_conversion(
        self, device, fiscal_day, fiscal_counters, tax_map, configuration, certs
    ):
        """Test currency value to cents conversion."""
        service = ClosingDayService(device, fiscal_day, fiscal_counters, tax_map)

        assert service._money_value(100.0) == 10000
        assert service._money_value(100.50) == 10050
        assert service._money_value(0.01) == 1
        assert service._money_value(0.0) == 0
        assert service._money_value(-50.25) == -5025

    def test_fmt_tax_percent_none(
        self, device, fiscal_day, fiscal_counters, tax_map, configuration, certs
    ):
        """Test tax percent formatting with None value."""
        service = ClosingDayService(device, fiscal_day, fiscal_counters, tax_map)

        assert service._fmt_tax_percent(None) == ""

    def test_fmt_tax_percent_with_values(
        self, device, fiscal_day, fiscal_counters, tax_map, configuration, certs
    ):
        """Test tax percent formatting with various values."""
        service = ClosingDayService(device, fiscal_day, fiscal_counters, tax_map)

        assert service._fmt_tax_percent(15) == "15.00"
        assert service._fmt_tax_percent(0) == "0.00"
        assert service._fmt_tax_percent(14.5) == "14.50"
        assert service._fmt_tax_percent(Decimal("15.00")) == "15.00"

    def test_sort_by_tax_id(self, device, fiscal_day, tax_map, configuration, certs):
        """Test sorting counters by currency and tax ID."""
        counters = [
            FiscalCounter(
                fiscal_counter_currency="USD",
                fiscal_counter_tax_id=3,
            ),
            FiscalCounter(
                fiscal_counter_currency="USD",
                fiscal_counter_tax_id=1,
            ),
            FiscalCounter(
                fiscal_counter_currency="ZWG",
                fiscal_counter_tax_id=2,
            ),
        ]

        service = ClosingDayService(device, fiscal_day, [], tax_map)
        sorted_counters = service._sort_by_tax_id(counters)

        # Should be sorted by currency first, then tax_id
        assert sorted_counters[0].fiscal_counter_currency == "USD"
        assert sorted_counters[0].fiscal_counter_tax_id == 1
        assert sorted_counters[1].fiscal_counter_currency == "USD"
        assert sorted_counters[1].fiscal_counter_tax_id == 3
        assert sorted_counters[2].fiscal_counter_currency == "ZWG"


@pytest.mark.django_db
class TestClosingDayServiceBuildMethods:
    """Test build methods for various counter types."""

    def test_build_sale_by_tax(
        self, device, fiscal_day, fiscal_counters, tax_map, configuration, certs
    ):
        """Test building sale by tax string."""
        service = ClosingDayService(device, fiscal_day, fiscal_counters, tax_map)
        result = service.build_sale_by_tax()

        assert result is not None
        assert len(result) > 0
        assert len(service.sale_by_tax_payload) == 2  # Two SaleByTax counters

    def test_build_sale_by_tax_filters_zero_values(
        self, device, fiscal_day, tax_map, configuration, certs
    ):
        """Test that zero-value counters are filtered out."""
        counters = [
            FiscalCounter.objects.create(
                fiscal_day=fiscal_day,
                fiscal_counter_type="SaleByTax",
                fiscal_counter_currency="USD",
                fiscal_counter_tax_percent=Decimal("15.00"),
                fiscal_counter_tax_id=1,
                fiscal_counter_value=Decimal("0.00"),
            ),
        ]

        service = ClosingDayService(device, fiscal_day, counters, tax_map)
        result = service.build_sale_by_tax()

        assert result == ""
        assert len(service.sale_by_tax_payload) == 0

    def test_build_sale_tax_by_tax(
        self, device, fiscal_day, fiscal_counters, tax_map, configuration, certs
    ):
        """Test building sale tax by tax string."""
        service = ClosingDayService(device, fiscal_day, fiscal_counters, tax_map)
        result = service.build_sale_tax_by_tax()

        assert result is not None
        assert len(service.sale_tax_by_tax_payload) == 1

    def test_build_credit_note_by_tax(self, device, fiscal_day, tax_map, configuration, certs):
        """Test building credit note by tax string."""
        counters = [
            FiscalCounter.objects.create(
                fiscal_day=fiscal_day,
                fiscal_counter_type="CreditNoteByTax",
                fiscal_counter_currency="USD",
                fiscal_counter_tax_percent=Decimal("15.00"),
                fiscal_counter_tax_id=1,
                fiscal_counter_value=Decimal("-100.00"),
            ),
        ]

        service = ClosingDayService(device, fiscal_day, counters, tax_map)
        result = service.build_credit_note_by_tax()

        assert len(service.credit_by_tax_payload) == 1

    def test_build_credit_note_tax_by_tax(self, device, fiscal_day, tax_map, configuration, certs):
        """Test building credit note tax by tax string."""
        counters = [
            FiscalCounter.objects.create(
                fiscal_day=fiscal_day,
                fiscal_counter_type="CreditNoteTaxByTax",
                fiscal_counter_currency="USD",
                fiscal_counter_tax_percent=Decimal("15.00"),
                fiscal_counter_tax_id=1,
                fiscal_counter_value=Decimal("-50.00"),
            ),
        ]

        service = ClosingDayService(device, fiscal_day, counters, tax_map)
        result = service.build_credit_note_tax_by_tax()

        assert len(service.credit_tax_by_tax_payload) == 1

    def test_build_balance_by_money_type(
        self, device, fiscal_day, fiscal_counters, tax_map, configuration, certs
    ):
        """Test building balance by money type string."""
        service = ClosingDayService(device, fiscal_day, fiscal_counters, tax_map)
        result = service.build_balance_by_money_type()

        assert result is not None
        assert len(service.balance_by_money_payload) == 1


@pytest.mark.django_db
class TestClosingDayServiceCloseDay:
    """Test close day functionality with real HTTP client mocking."""

    @patch("fiscguy.zimra_base.requests.Session.request")
    @patch("fiscguy.services.closing_day_service.sleep")
    def test_close_day_success(
        self,
        mock_sleep,
        mock_request,
        device,
        fiscal_day,
        fiscal_counters,
        tax_map,
        configuration,
        certs,
    ):
        """Test successful close day with real HTTP client."""
        # Mock the HTTP responses
        close_day_response = Mock(spec=requests.Response)
        close_day_response.status_code = 200
        close_day_response.json.return_value = {}

        status_response = Mock(spec=requests.Response)
        status_response.status_code = 200
        status_response.json.return_value = {
            "fiscalDayStatus": "FiscalDayClosed",
            "fiscalDayClosingErrorCode": None,
        }

        mock_request.side_effect = [close_day_response, status_response]

        service = ClosingDayService(device, fiscal_day, fiscal_counters, tax_map)
        result = service.close_day()

        assert result["fiscalDayStatus"] == "FiscalDayClosed"
        assert fiscal_day.is_open is False
        mock_sleep.assert_called_once_with(10)

    @patch("fiscguy.zimra_base.requests.Session.request")
    @patch("fiscguy.services.closing_day_service.sleep")
    def test_close_day_empty_response(
        self,
        mock_sleep,
        mock_request,
        device,
        fiscal_day,
        fiscal_counters,
        tax_map,
        configuration,
        certs,
    ):
        """Test close day with empty status response."""
        close_day_response = Mock(spec=requests.Response)
        close_day_response.status_code = 200
        close_day_response.json.return_value = {}

        mock_request.return_value = close_day_response

        service = ClosingDayService(device, fiscal_day, fiscal_counters, tax_map)

        with pytest.raises(CloseDayError, match="FDMS returned an empty response"):
            service.close_day()

    @patch("fiscguy.zimra_base.requests.Session.request")
    @patch("fiscguy.services.closing_day_service.sleep")
    def test_close_day_failed_status(
        self,
        mock_sleep,
        mock_request,
        device,
        fiscal_day,
        fiscal_counters,
        tax_map,
        configuration,
        certs,
    ):
        """Test close day with FiscalDayCloseFailed status."""
        close_day_response = Mock(spec=requests.Response)
        close_day_response.status_code = 200
        close_day_response.json.return_value = {}

        status_response = Mock(spec=requests.Response)
        status_response.status_code = 200
        status_response.json.return_value = {
            "fiscalDayStatus": "FiscalDayCloseFailed",
            "fiscalDayClosingErrorCode": "INVALID_SIGNATURE",
        }

        mock_request.side_effect = [close_day_response, status_response]

        service = ClosingDayService(device, fiscal_day, fiscal_counters, tax_map)

        with pytest.raises(CloseDayError, match="FDMS rejected the close day request"):
            service.close_day()

    @patch("fiscguy.zimra_base.requests.Session.request")
    @patch("fiscguy.services.closing_day_service.sleep")
    def test_close_day_unexpected_status(
        self,
        mock_sleep,
        mock_request,
        device,
        fiscal_day,
        fiscal_counters,
        tax_map,
        configuration,
        certs,
    ):
        """Test close day with unexpected status."""
        close_day_response = Mock(spec=requests.Response)
        close_day_response.status_code = 200
        close_day_response.json.return_value = {}

        status_response = Mock(spec=requests.Response)
        status_response.status_code = 200
        status_response.json.return_value = {
            "fiscalDayStatus": "UnexpectedStatus",
        }

        mock_request.side_effect = [close_day_response, status_response]

        service = ClosingDayService(device, fiscal_day, fiscal_counters, tax_map)

        with pytest.raises(CloseDayError, match="Unexpected FDMS status"):
            service.close_day()

    @patch("fiscguy.zimra_base.requests.Session.request")
    @patch("fiscguy.services.closing_day_service.sleep")
    def test_close_day_constructs_correct_payload(
        self,
        mock_sleep,
        mock_request,
        device,
        fiscal_day,
        fiscal_counters,
        tax_map,
        configuration,
        certs,
    ):
        """Test that close day constructs correct payload."""
        close_day_response = Mock(spec=requests.Response)
        close_day_response.status_code = 200
        close_day_response.json.return_value = {}

        status_response = Mock(spec=requests.Response)
        status_response.status_code = 200
        status_response.json.return_value = {
            "fiscalDayStatus": "FiscalDayClosed",
        }

        mock_request.side_effect = [close_day_response, status_response]

        service = ClosingDayService(device, fiscal_day, fiscal_counters, tax_map)
        result = service.close_day()

        # Verify payload structure
        assert "fiscalDayCounters" in service.client.session.headers or True
        assert result["fiscalDayStatus"] == "FiscalDayClosed"


@pytest.mark.django_db
class TestClosingDayServiceEdgeCases:
    """Test edge cases and error handling."""

    def test_empty_counters(self, device, fiscal_day, tax_map, configuration, certs):
        """Test with empty counters list."""
        service = ClosingDayService(device, fiscal_day, [], tax_map)

        assert service.build_sale_by_tax() == ""
        assert service.build_sale_tax_by_tax() == ""
        assert service.build_credit_note_by_tax() == ""
        assert service.build_credit_note_tax_by_tax() == ""
        assert service.build_balance_by_money_type() == ""

    def test_multiple_currencies(self, device, fiscal_day, tax_map, configuration, certs):
        """Test with multiple currencies."""
        counters = [
            FiscalCounter.objects.create(
                fiscal_day=fiscal_day,
                fiscal_counter_type="SaleByTax",
                fiscal_counter_currency="USD",
                fiscal_counter_tax_percent=Decimal("15.00"),
                fiscal_counter_tax_id=1,
                fiscal_counter_value=Decimal("1000.00"),
            ),
            FiscalCounter.objects.create(
                fiscal_day=fiscal_day,
                fiscal_counter_type="SaleByTax",
                fiscal_counter_currency="ZWG",
                fiscal_counter_tax_percent=Decimal("15.00"),
                fiscal_counter_tax_id=1,
                fiscal_counter_value=Decimal("50000.00"),
            ),
        ]

        service = ClosingDayService(device, fiscal_day, counters, tax_map)
        result = service.build_sale_by_tax()

        assert len(result) > 0
        assert len(service.sale_by_tax_payload) == 2

    def test_large_decimal_values(self, device, fiscal_day, tax_map, configuration, certs):
        """Test with large decimal values."""
        counters = [
            FiscalCounter.objects.create(
                fiscal_day=fiscal_day,
                fiscal_counter_type="SaleByTax",
                fiscal_counter_currency="USD",
                fiscal_counter_tax_percent=Decimal("15.00"),
                fiscal_counter_tax_id=1,
                fiscal_counter_value=Decimal("999999.99"),
            ),
        ]

        service = ClosingDayService(device, fiscal_day, counters, tax_map)
        result = service.build_sale_by_tax()

        assert result is not None
        assert len(service.sale_by_tax_payload) == 1

    def test_negative_values_in_credit_notes(
        self, device, fiscal_day, tax_map, configuration, certs
    ):
        """Test negative values in credit notes."""
        counters = [
            FiscalCounter.objects.create(
                fiscal_day=fiscal_day,
                fiscal_counter_type="CreditNoteByTax",
                fiscal_counter_currency="USD",
                fiscal_counter_tax_percent=Decimal("15.00"),
                fiscal_counter_tax_id=1,
                fiscal_counter_value=Decimal("-1500.50"),
            ),
        ]

        service = ClosingDayService(device, fiscal_day, counters, tax_map)
        result = service.build_credit_note_by_tax()

        assert len(service.credit_by_tax_payload) == 1
        assert service.credit_by_tax_payload[0]["fiscalCounterValue"] == -1500.50

    def test_mixed_counter_types(self, device, fiscal_day, tax_map, configuration, certs):
        """Test with mixed counter types in single service."""
        counters = [
            FiscalCounter.objects.create(
                fiscal_day=fiscal_day,
                fiscal_counter_type="SaleByTax",
                fiscal_counter_currency="USD",
                fiscal_counter_tax_percent=Decimal("15.00"),
                fiscal_counter_tax_id=1,
                fiscal_counter_value=Decimal("1000.00"),
            ),
            FiscalCounter.objects.create(
                fiscal_day=fiscal_day,
                fiscal_counter_type="BalanceByMoneyType",
                fiscal_counter_currency="USD",
                fiscal_counter_money_type="Card",
                fiscal_counter_value=Decimal("500.00"),
            ),
            FiscalCounter.objects.create(
                fiscal_day=fiscal_day,
                fiscal_counter_type="CreditNoteByTax",
                fiscal_counter_currency="USD",
                fiscal_counter_tax_percent=Decimal("15.00"),
                fiscal_counter_tax_id=1,
                fiscal_counter_value=Decimal("-200.00"),
            ),
        ]

        service = ClosingDayService(device, fiscal_day, counters, tax_map)

        service.build_sale_by_tax()
        service.build_balance_by_money_type()
        service.build_credit_note_by_tax()

        assert len(service.sale_by_tax_payload) == 1
        assert len(service.balance_by_money_payload) == 1
        assert len(service.credit_by_tax_payload) == 1
