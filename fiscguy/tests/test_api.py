"""
Unit tests for the fiscguy public API library.

Tests all public functions (open_day, close_day, submit_receipt, get_status,
get_configuration, get_taxes) with mocking to avoid hitting the real FDMS
endpoint or making external network calls.
"""

from decimal import Decimal
from unittest.mock import MagicMock, patch, PropertyMock
from django.test import TestCase
from django.utils import timezone

from fiscguy.models import (
    Device,
    FiscalDay,
    FiscalCounter,
    Receipt,
    Taxes,
    Configuration,
    Buyer,
    Certs,
)
from fiscguy import api


class APILibraryTestSetup(TestCase):
    """Base test class with common fixtures for all API tests."""

    def setUp(self):
        """Set up test fixtures: device, fiscal day, taxes, config, certs."""
        # Create certificates (required for ZIMRAClient)
        self.certs = Certs.objects.create(
            csr="test-csr",
            certificate="test-cert",
            certificate_key="test-key",
            production=False,
        )

        # Create device
        self.device = Device.objects.create(
            org_name="Test Org",
            device_id="TEST-DEVICE-001",
            device_serial_number="test-sn-001",
            device_model_name="TestServer",
            device_model_version="v1",
            production=False,
            activation_key="test-key",
        )

        # Create configuration
        self.config = Configuration.objects.create(
            tax_payer_name="Test Taxpayer",
            tax_inclusive=True,
            tin_number="1234567890",
            vat_number="VAT123456",
            address="123 Test Street",
            phone_number="0778587612",
            email="test@example.com",
        )

        # Create taxes
        self.tax_standard = Taxes.objects.create(
            code="517",
            name="Standard rated 15.5%",
            tax_id=517,
            percent=Decimal("15.5"),
        )
        self.tax_zero = Taxes.objects.create(
            code="2",
            name="Zero rated 0%",
            tax_id=2,
            percent=Decimal("0.0"),
        )
        self.tax_exempt = Taxes.objects.create(
            code="1",
            name="Exempt",
            tax_id=1,
            percent=Decimal("0.0"),
        )

        # Create buyer
        self.buyer = Buyer.objects.create(
            name="Test Buyer",
            tin_number="1234567890",
            vat_numberr="VAT-BUYER-001",
        )

        # Reset module-level caches to avoid pollution between tests
        api._device = None
        api._client = None
        api._receipt_handler = None

    def tearDown(self):
        """Clean up: reset module-level caches."""
        api._device = None
        api._client = None
        api._receipt_handler = None


class GetStatusTest(APILibraryTestSetup):
    """Test the get_status() function."""

    @patch("fiscguy.api.ZIMRAClient")
    def test_get_status_success(self, mock_client_class):
        """Test successful status fetch from ZIMRA."""
        # Mock the client and its get_status method
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        expected_status = {
            "fiscalDayNo": 1,
            "isOpen": True,
            "receiptCounter": 10,
        }
        mock_client.get_status.return_value = expected_status

        # Call the API
        result = api.get_status()

        # Assertions
        self.assertEqual(result, expected_status)
        mock_client.get_status.assert_called_once()

    def test_get_status_no_device_raises(self):
        """Test that get_status raises RuntimeError if no device exists."""
        # Delete all devices
        Device.objects.all().delete()

        with self.assertRaises(RuntimeError) as context:
            api.get_status()

        self.assertIn("No Device found", str(context.exception))


class OpenDayTest(APILibraryTestSetup):
    """Test the open_day() function."""

    @patch("fiscguy.api.ZIMRAClient")
    def test_open_day_success(self, mock_client_class):
        """Test successful opening of a fiscal day."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        expected_response = {
            "success": True,
            "message": "Fiscal day 1 opened",
        }
        mock_client.open_day.return_value = expected_response

        result = api.open_day()

        self.assertEqual(result, expected_response)
        mock_client.open_day.assert_called_once()

    @patch("fiscguy.api.ZIMRAClient")
    def test_open_day_returns_already_open_message(self, mock_client_class):
        """Test that open_day handles case where day is already open."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        already_open_response = {
            "success": True,
            "message": "Fiscal day 1 already open",
        }
        mock_client.open_day.return_value = already_open_response

        result = api.open_day()

        self.assertIn("already open", result["message"])


class CloseDayTest(APILibraryTestSetup):
    """Test the close_day() function."""

    def setUp(self):
        """Set up fiscal day and counters for closing tests."""
        super().setUp()

        # Create and open a fiscal day
        self.fiscal_day = FiscalDay.objects.create(
            day_no=1,
            is_open=True,
            receipt_counter=5,
        )

        # Create fiscal counters for various types
        FiscalCounter.objects.create(
            fiscal_day=self.fiscal_day,
            fiscal_counter_type="SaleByTax",
            fiscal_counter_currency="USD",
            fiscal_counter_tax_id=517,
            fiscal_counter_tax_percent=Decimal("15.5"),
            fiscal_counter_value=Decimal("100.00"),
        )
        FiscalCounter.objects.create(
            fiscal_day=self.fiscal_day,
            fiscal_counter_type="SaleTaxByTax",
            fiscal_counter_currency="USD",
            fiscal_counter_tax_id=517,
            fiscal_counter_tax_percent=Decimal("15.5"),
            fiscal_counter_value=Decimal("15.50"),
        )
        FiscalCounter.objects.create(
            fiscal_day=self.fiscal_day,
            fiscal_counter_type="Balancebymoneytype",
            fiscal_counter_currency="USD",
            fiscal_counter_money_type="cash",
            fiscal_counter_value=Decimal("115.50"),
        )

    @patch("fiscguy.api.ZIMRAClient")
    def test_close_day_success(self, mock_client_class):
        """Test successful closing of a fiscal day."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        expected_close_response = {"success": True}
        expected_status = {
            "fiscalDayNo": 1,
            "isOpen": False,
            "receiptCounter": 5,
        }
        mock_client.close_day.return_value = expected_close_response
        mock_client.get_status.return_value = expected_status

        result = api.close_day()

        # Assertions
        self.assertEqual(result, expected_status)
        mock_client.close_day.assert_called_once()
        mock_client.get_status.assert_called_once()

    def test_close_day_no_open_day_raises(self):
        """Test that close_day returns error dict if no open fiscal day."""
        # Close the fiscal day so no open day exists
        self.fiscal_day.is_open = False
        self.fiscal_day.save()

        result = api.close_day()

        self.assertIn("error", result)
        self.assertIn("No open fiscal day", result["error"])

    @patch("fiscguy.api.ZIMRAClient")
    def test_close_day_builds_payload_with_counters(self, mock_client_class):
        """Test that close_day builds and submits payload with counter data."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        mock_client.close_day.return_value = {"success": True}
        mock_client.get_status.return_value = {"isOpen": False}

        api.close_day()

        # Verify that close_day was called with a payload dict
        mock_client.close_day.assert_called_once()
        call_args = mock_client.close_day.call_args
        self.assertIsNotNone(call_args)


class SubmitReceiptTest(APILibraryTestSetup):
    """Test the submit_receipt() function."""

    def setUp(self):
        """Set up fiscal day for receipt tests."""
        super().setUp()
        self.fiscal_day = FiscalDay.objects.create(
            day_no=1,
            is_open=True,
            receipt_counter=0,
        )

    @patch("fiscguy.api.ZIMRAReceiptHandler")
    def test_submit_receipt_success(self, mock_handler_class):
        """Test successful receipt submission."""
        mock_handler = MagicMock()
        mock_handler_class.return_value = mock_handler
        
        # Mock generate_receipt_data to return the expected dict format
        mock_handler.generate_receipt_data.return_value = {
            "receipt_string": "FISCALINVOICEUSD1...",
            "receipt_data": {"receiptTotal": 45.0, "receiptGlobalNo": 1},
        }
        
        # Mock crypto methods
        mock_handler.crypto.generate_receipt_hash_and_signature.return_value = {
            "hash": "test-hash",
            "signature": "test-signature",
        }
        
        # Mock submit_receipt
        mock_handler.submit_receipt.return_value = {"receiptID": 123}

        receipt_payload = {
            "receipt_type": "fiscalinvoice",
            "currency": "USD",
            "total_amount": Decimal("45.00"),
            "payment_terms": "cash",
            "lines": [
                {
                    "product": "Test Product",
                    "quantity": Decimal("1"),
                    "unit_price": Decimal("45.00"),
                    "line_total": Decimal("45.00"),
                    "tax_amount": Decimal("0"),
                    "tax_name": "standard rated 15.5%",
                }
            ],
            "buyer": self.buyer.id,
        }

        result = api.submit_receipt(receipt_payload)

        # Assertions
        self.assertIsNotNone(result)
        # Verify receipt was created in DB
        self.assertTrue(Receipt.objects.filter(receipt_type="fiscalinvoice").exists())

    def test_submit_receipt_invalid_tax_name_raises(self):
        """Test that submit_receipt raises error for invalid tax name."""
        receipt_payload = {
            "receipt_type": "fiscalinvoice",
            "currency": "USD",
            "total_amount": Decimal("45.00"),
            "lines": [
                {
                    "product": "Test Product",
                    "quantity": Decimal("1"),
                    "unit_price": Decimal("45.00"),
                    "line_total": Decimal("45.00"),
                    "tax_amount": Decimal("0"),
                    "tax_name": "nonexistent tax type",
                }
            ],
            "buyer": self.buyer.id,
        }

        with self.assertRaises(Exception):
            # Should raise during tax resolution
            api.submit_receipt(receipt_payload)

    @patch("fiscguy.api.ZIMRAReceiptHandler")
    def test_submit_receipt_with_multiple_tax_types(self, mock_handler_class):
        """Test submitting receipt with multiple tax types."""
        mock_handler = MagicMock()
        mock_handler_class.return_value = mock_handler
        
        # Mock generate_receipt_data to return the expected dict format
        mock_handler.generate_receipt_data.return_value = {
            "receipt_string": "FISCALINVOICEUSD1...",
            "receipt_data": {"receiptTotal": 45.0, "receiptGlobalNo": 1},
        }
        
        # Mock crypto methods
        mock_handler.crypto.generate_receipt_hash_and_signature.return_value = {
            "hash": "test-hash",
            "signature": "test-signature",
        }
        
        # Mock submit_receipt
        mock_handler.submit_receipt.return_value = {"receiptID": 124}

        receipt_payload = {
            "receipt_type": "fiscalinvoice",
            "currency": "USD",
            "total_amount": Decimal("45.00"),
            "payment_terms": "cash",
            "lines": [
                {
                    "product": "Product 1",
                    "quantity": Decimal("1"),
                    "unit_price": Decimal("15.00"),
                    "line_total": Decimal("15.00"),
                    "tax_amount": Decimal("0"),
                    "tax_name": "standard rated 15.5%",
                },
                {
                    "product": "Product 2",
                    "quantity": Decimal("1"),
                    "unit_price": Decimal("15.00"),
                    "line_total": Decimal("15.00"),
                    "tax_amount": Decimal("0"),
                    "tax_name": "zero rated 0%",
                },
                {
                    "product": "Product 3",
                    "quantity": Decimal("1"),
                    "unit_price": Decimal("15.00"),
                    "line_total": Decimal("15.00"),
                    "tax_amount": Decimal("0"),
                    "tax_name": "exempt",
                },
            ],
            "buyer": self.buyer.id,
        }

        result = api.submit_receipt(receipt_payload)

        # Verify receipt and lines were created
        self.assertTrue(Receipt.objects.filter(receipt_type="fiscalinvoice").exists())
        receipt = Receipt.objects.get(receipt_type="fiscalinvoice")
        self.assertEqual(receipt.lines.count(), 3)


class GetConfigurationTest(APILibraryTestSetup):
    """Test the get_configuration() function."""

    def test_get_configuration_success(self):
        """Test successful configuration retrieval."""
        result = api.get_configuration()

        self.assertIsNotNone(result)
        self.assertEqual(result["tax_payer_name"], "Test Taxpayer")
        self.assertEqual(result["tin_number"], "1234567890")

    def test_get_configuration_no_config_returns_empty(self):
        """Test that get_configuration returns empty dict if no config exists."""
        Configuration.objects.all().delete()

        result = api.get_configuration()

        self.assertEqual(result, {})

    def test_get_configuration_includes_required_fields(self):
        """Test that configuration response includes all required fields."""
        result = api.get_configuration()

        required_fields = [
            "tax_payer_name",
            "tin_number",
            "vat_number",
            "address",
            "phone_number",
            "email",
        ]
        for field in required_fields:
            self.assertIn(field, result)


class GetTaxesTest(APILibraryTestSetup):
    """Test the get_taxes() function."""

    def test_get_taxes_success(self):
        """Test successful taxes retrieval."""
        result = api.get_taxes()

        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 3)  # Standard, Zero, Exempt

    def test_get_taxes_includes_all_tax_info(self):
        """Test that each tax includes required fields."""
        result = api.get_taxes()

        required_fields = ["id", "code", "name", "tax_id", "percent"]
        for tax in result:
            for field in required_fields:
                self.assertIn(field, tax)

    def test_get_taxes_correct_values(self):
        """Test that retrieved taxes have correct values."""
        result = api.get_taxes()

        tax_ids = {t["tax_id"] for t in result}
        self.assertEqual(tax_ids, {1, 2, 517})

    def test_get_taxes_empty_returns_empty_list(self):
        """Test that get_taxes returns empty list if no taxes exist."""
        Taxes.objects.all().delete()

        result = api.get_taxes()

        self.assertEqual(result, [])


class APIModuleLevelCachingTest(APILibraryTestSetup):
    """Test that module-level caching works correctly."""

    @patch("fiscguy.api.ZIMRAClient")
    def test_client_is_cached(self, mock_client_class):
        """Test that ZIMRAClient is instantiated only once."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        mock_client.get_status.return_value = {}

        # Call get_status twice
        api.get_status()
        api.get_status()

        # ZIMRAClient should only be instantiated once
        mock_client_class.assert_called_once()

    @patch("fiscguy.api.ZIMRAReceiptHandler")
    def test_receipt_handler_is_cached(self, mock_handler_class):
        """Test that ZIMRAReceiptHandler is instantiated only once."""
        mock_handler = MagicMock()
        mock_handler_class.return_value = mock_handler

        # Force handler initialization via a mock to track instantiation
        api._receipt_handler = None
        _ = api._get_receipt_handler()
        _ = api._get_receipt_handler()

        # Handler should only be instantiated once
        mock_handler_class.assert_called_once()

    def test_device_is_cached(self):
        """Test that Device is fetched only once."""
        api._device = None

        # Call _get_device twice
        device1 = api._get_device()
        device2 = api._get_device()

        # Should return the same cached instance
        self.assertIs(device1, device2)


class APIErrorHandlingTest(APILibraryTestSetup):
    """Test error handling in API functions."""

    def test_get_status_with_network_error(self):
        """Test that network errors propagate correctly."""
        with patch("fiscguy.api.ZIMRAClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client
            mock_client.get_status.side_effect = Exception("Network error")

            with self.assertRaises(Exception) as context:
                api.get_status()

            self.assertIn("Network error", str(context.exception))

    def test_close_day_with_invalid_counters(self):
        """Test close_day with missing fiscal counters."""
        # Create fiscal day with no counters
        fiscal_day = FiscalDay.objects.create(
            day_no=1,
            is_open=True,
            receipt_counter=0,
        )

        with patch("fiscguy.api.ZIMRAClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client
            mock_client.close_day.return_value = {}
            mock_client.get_status.return_value = {"isOpen": False}

            # Should not raise; close with empty counters
            result = api.close_day()
            self.assertIsNotNone(result)
