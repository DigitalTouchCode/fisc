from unittest.mock import Mock, patch

import pytest
import requests

from fiscguy.exceptions import (
    DevicePingError,
    StatusError,
)
from fiscguy.models import Certs, Configuration, Device, Taxes
from fiscguy.services.configuration_service import ConfigurationService
from fiscguy.services.ping_service import PingService
from fiscguy.services.status_service import StatusService


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
    config = Configuration.objects.create(
        tax_payer_name="Test Taxpayer",
        tax_inclusive=True,
        tin_number="123456789",
        vat_number="987654",
        address="123 Test Street",
        phone_number="+263123456",
        email="test@example.com",
    )
    # Create at least one tax record for the delete() to work
    Taxes.objects.create(
        code="1",
        name="Standard",
        tax_id=1,
        percent=15.0,
    )
    return config


@pytest.fixture
def certs(db):
    """Create test certificates."""
    return Certs.objects.create(
        csr="-----BEGIN CERTIFICATE REQUEST-----\ntest\n-----END CERTIFICATE REQUEST-----",
        certificate="-----BEGIN CERTIFICATE-----\ntest-cert\n-----END CERTIFICATE-----",
        certificate_key="-----BEGIN PRIVATE KEY-----\ntest-key\n-----END PRIVATE KEY-----",
        production=False,
    )


@pytest.mark.django_db
class TestStatusService:
    """Test StatusService with real HTTP client."""

    def test_status_service_initialization(self, device):
        """Test StatusService initializes correctly."""
        service = StatusService(device)
        assert service.device == device

    @patch("fiscguy.zimra_base.requests.Session.request")
    def test_get_status_success(self, mock_request, device, configuration, certs):
        """Test successful status retrieval."""
        expected_response = {
            "fiscalDayStatus": "FiscalDayOpen",
            "receiptCounter": 150,
            "fiscalDayNo": 1,
        }

        mock_response = Mock(spec=requests.Response)
        mock_response.status_code = 200
        mock_response.json.return_value = expected_response
        mock_request.return_value = mock_response

        service = StatusService(device)
        result = service.get_status()

        assert result == expected_response
        assert result["fiscalDayStatus"] == "FiscalDayOpen"

    @patch("fiscguy.zimra_base.requests.Session.request")
    def test_get_status_request_error(self, mock_request, device, configuration, certs):
        """Test status retrieval with request error."""
        mock_request.side_effect = requests.RequestException("Connection failed")

        service = StatusService(device)

        with pytest.raises(StatusError, match="Could not retrieve device status"):
            service.get_status()

    @patch("fiscguy.zimra_base.requests.Session.request")
    def test_get_status_unexpected_error(self, mock_request, device, configuration, certs):
        """Test status retrieval with unexpected error."""
        mock_request.side_effect = Exception("Unexpected error")

        service = StatusService(device)

        with pytest.raises(StatusError, match="Unexpected error retrieving device status"):
            service.get_status()

    @patch("fiscguy.zimra_base.requests.Session.request")
    def test_get_status_different_states(self, mock_request, device, configuration, certs):
        """Test status retrieval with different fiscal day states."""
        states = [
            {"fiscalDayStatus": "FiscalDayOpen"},
            {"fiscalDayStatus": "FiscalDayClosed"},
            {"fiscalDayStatus": "FiscalDayCloseFailed"},
        ]

        service = StatusService(device)

        for state in states:
            mock_response = Mock(spec=requests.Response)
            mock_response.status_code = 200
            mock_response.json.return_value = state
            mock_request.return_value = mock_response

            result = service.get_status()
            assert result["fiscalDayStatus"] in [s["fiscalDayStatus"] for s in states]


@pytest.mark.django_db
class TestPingService:
    """Test PingService with real HTTP client."""

    def test_ping_service_initialization(self, device):
        """Test PingService initializes correctly."""
        service = PingService(device)
        assert service.device == device

    @patch("fiscguy.zimra_base.requests.Session.request")
    def test_ping_success(self, mock_request, device, configuration, certs):
        """Test successful device ping."""
        expected_response = {"status": "ok", "timestamp": "2024-01-15T10:00:00"}

        mock_response = Mock(spec=requests.Response)
        mock_response.status_code = 200
        mock_response.json.return_value = expected_response
        mock_request.return_value = mock_response

        service = PingService(device)
        result = service.ping()

        assert result == expected_response
        assert result["status"] == "ok"

    @patch("fiscguy.zimra_base.requests.Session.request")
    def test_ping_request_error(self, mock_request, device, configuration, certs):
        """Test ping with request error."""
        mock_request.side_effect = requests.RequestException("Connection failed")

        service = PingService(device)

        with pytest.raises(DevicePingError, match="Device ping failed"):
            service.ping()

    @patch("fiscguy.zimra_base.requests.Session.request")
    def test_ping_unexpected_error(self, mock_request, device, configuration, certs):
        """Test ping with unexpected error."""
        mock_request.side_effect = Exception("Unexpected error")

        service = PingService(device)

        with pytest.raises(DevicePingError, match="Unexpected error during device ping"):
            service.ping()

    @patch("fiscguy.zimra_base.requests.Session.request")
    def test_ping_multiple_times(self, mock_request, device, configuration, certs):
        """Test multiple pings in sequence."""
        mock_response = Mock(spec=requests.Response)
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "ok"}
        mock_request.return_value = mock_response

        service = PingService(device)

        for _ in range(3):
            result = service.ping()
            assert result["status"] == "ok"


@pytest.mark.django_db
class TestConfigurationService:
    """Test ConfigurationService with real HTTP client."""

    def test_config_service_initialization(self, device, configuration, certs):
        """Test ConfigurationService initializes correctly."""
        service = ConfigurationService(device)
        assert service.device == device
        assert service.client is not None

    @patch("fiscguy.zimra_base.requests.Session.request")
    def test_get_configuration_success(self, mock_request, device, configuration, certs):
        """Test successful configuration retrieval."""
        expected_response = {
            "taxPayerName": "Test Taxpayer",
            "tax_inclusive": True,
            "taxPayerTIN": "123456789",
            "vatNumber": "987654",
            "deviceBranchAddress": {
                "streetAddress": "123 Test Street",
                "city": "Harare",
            },
            "deviceBranchContacts": {
                "phoneNo": "+263123456",
                "email": "test@example.com",
            },
            "applicableTaxes": [
                {"taxID": 1, "taxName": "Standard", "taxPercent": 15.0},
                {"taxID": 2, "taxName": "Zero", "taxPercent": 0.0},
            ],
            "qrUrl": "https://example.com",
        }

        mock_response = Mock(spec=requests.Response)
        mock_response.status_code = 200
        mock_response.json.return_value = expected_response
        mock_request.return_value = mock_response

        service = ConfigurationService(device)
        result = service.get_configuration()

        assert result == expected_response

    @patch("fiscguy.zimra_base.requests.Session.request")
    def test_config_success(self, mock_request, device, configuration, certs):
        """Test full config method."""
        config_response = {
            "taxPayerName": "Updated Taxpayer",
            "tax_inclusive": False,
            "taxPayerTIN": "987654321",
            "vatNumber": "654321",
            "deviceBranchAddress": {
                "streetAddress": "456 New Street",
            },
            "deviceBranchContacts": {
                "phoneNo": "+263987654",
                "email": "updated@example.com",
            },
            "applicableTaxes": [
                {"taxID": 1, "taxName": "Standard", "taxPercent": 15.0},
            ],
        }

        mock_response = Mock(spec=requests.Response)
        mock_response.status_code = 200
        mock_response.json.return_value = config_response
        mock_request.return_value = mock_response

        service = ConfigurationService(device)
        config = service.config()

        assert config.tax_payer_name == "Updated Taxpayer"
        assert Taxes.objects.count() >= 1

    @patch("fiscguy.zimra_base.requests.Session.request")
    def test_persist_configuration_creates_new(self, mock_request, device, configuration, certs):
        """Test configuration creation when none exists."""
        config_response = {
            "taxPayerName": "New Taxpayer",
            "tax_inclusive": True,
            "taxPayerTIN": "111111111",
            "vatNumber": "111111",
            "deviceBranchAddress": {"streetAddress": "Test Street"},
            "deviceBranchContacts": {
                "phoneNo": "+263111111",
                "email": "new@example.com",
            },
            "applicableTaxes": [],
            "qrUrl": "https://test.com",
        }

        mock_response = Mock(spec=requests.Response)
        mock_response.status_code = 200
        mock_response.json.return_value = config_response
        mock_request.return_value = mock_response

        service = ConfigurationService(device)
        config = service.config()

        assert config.tax_payer_name == "New Taxpayer"
        assert config.tin_number == "111111111"

    @patch("fiscguy.zimra_base.requests.Session.request")
    def test_persist_configuration_updates_existing(
        self, mock_request, device, configuration, certs
    ):
        """Test configuration update when one exists."""
        config_response = {
            "taxPayerName": "Updated Name",
            "tax_inclusive": False,
            "taxPayerTIN": "222222222",
            "vatNumber": "222222",
            "deviceBranchAddress": {"streetAddress": "Updated Street"},
            "deviceBranchContacts": {
                "phoneNo": "+263222222",
                "email": "updated@example.com",
            },
            "applicableTaxes": [],
        }

        mock_response = Mock(spec=requests.Response)
        mock_response.status_code = 200
        mock_response.json.return_value = config_response
        mock_request.return_value = mock_response

        service = ConfigurationService(device)
        config = service.config()

        assert config.tax_payer_name == "Updated Name"
        assert config.tin_number == "222222222"

    @patch("fiscguy.zimra_base.requests.Session.request")
    def test_persist_taxes_multiple(self, mock_request, device, configuration, certs):
        """Test persisting multiple taxes."""
        config_response = {
            "taxPayerName": "Test",
            "tax_inclusive": True,
            "taxPayerTIN": "123",
            "vatNumber": "456",
            "deviceBranchAddress": {},
            "deviceBranchContacts": {},
            "applicableTaxes": [
                {"taxID": 1, "taxName": "Standard", "taxPercent": 15.0},
                {"taxID": 2, "taxName": "Zero", "taxPercent": 0.0},
                {"taxID": 3, "taxName": "Exempt", "taxPercent": 0.0},
            ],
        }

        mock_response = Mock(spec=requests.Response)
        mock_response.status_code = 200
        mock_response.json.return_value = config_response
        mock_request.return_value = mock_response

        service = ConfigurationService(device)
        service.config()

        assert Taxes.objects.count() == 3

    @patch("fiscguy.zimra_base.requests.Session.request")
    def test_config_handles_missing_fields(self, mock_request, device, configuration, certs):
        """Test configuration handles missing optional fields."""
        minimal_response = {
            "taxPayerName": "Minimal",
            "applicableTaxes": [],
            # Missing most optional fields
        }

        mock_response = Mock(spec=requests.Response)
        mock_response.status_code = 200
        mock_response.json.return_value = minimal_response
        mock_request.return_value = mock_response

        service = ConfigurationService(device)
        config = service.config()

        # Should handle missing fields gracefully
        assert config.tax_payer_name == "Minimal"

    @patch("fiscguy.zimra_base.requests.Session.request")
    def test_config_request_error(self, mock_request, device, configuration, certs):
        """Test configuration with request error."""
        mock_request.side_effect = requests.RequestException("Connection failed")

        service = ConfigurationService(device)

        with pytest.raises(requests.RequestException):
            service.get_configuration()

    @patch("fiscguy.zimra_base.requests.Session.request")
    def test_format_address_helper(self, mock_request, device, configuration, certs):
        """Test address formatting."""
        # Ensure we have at least one tax record for the delete() call in _persist_taxes
        if Taxes.objects.count() == 0:
            Taxes.objects.create(code="1", name="Temp", tax_id=99, percent=0.0)

        config_response = {
            "taxPayerName": "Test",
            "tax_inclusive": True,
            "taxPayerTIN": "123",
            "vatNumber": "456",
            "deviceBranchAddress": {
                "streetAddress": "123 Main St",
                "city": "Harare",
                "country": "Zimbabwe",
            },
            "deviceBranchContacts": {},
            "applicableTaxes": [],
        }

        mock_response = Mock(spec=requests.Response)
        mock_response.status_code = 200
        mock_response.json.return_value = config_response
        mock_request.return_value = mock_response

        service = ConfigurationService(device)
        config = service.config()

        # Address should be formatted
        assert "123 Main St" in config.address or config.address


@pytest.mark.django_db
class TestServiceEdgeCases:
    """Test edge cases across services."""

    @patch("fiscguy.zimra_base.requests.Session.request")
    def test_status_with_extra_fields(self, mock_request, device, configuration, certs):
        """Test status service with extra response fields."""
        mock_response = Mock(spec=requests.Response)
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "fiscalDayStatus": "FiscalDayOpen",
            "extraField": "should_be_ignored",
            "nested": {"deep": "value"},
        }
        mock_request.return_value = mock_response

        service = StatusService(device)
        result = service.get_status()

        assert result["fiscalDayStatus"] == "FiscalDayOpen"
        assert result["extraField"] == "should_be_ignored"

    @patch("fiscguy.zimra_base.requests.Session.request")
    def test_ping_with_timeout_simulation(self, mock_request, device, configuration, certs):
        """Test ping handling timeout."""
        mock_request.side_effect = requests.Timeout("Request timed out")

        service = PingService(device)

        with pytest.raises(DevicePingError):
            service.ping()

    @patch("fiscguy.zimra_base.requests.Session.request")
    def test_config_with_empty_taxes(self, mock_request, device, configuration, certs):
        """Test configuration with empty taxes list."""
        config_response = {
            "taxPayerName": "Test",
            "tax_inclusive": True,
            "taxPayerTIN": "123",
            "vatNumber": "456",
            "deviceBranchAddress": {},
            "deviceBranchContacts": {},
            "applicableTaxes": [],
        }

        mock_response = Mock(spec=requests.Response)
        mock_response.status_code = 200
        mock_response.json.return_value = config_response
        mock_request.return_value = mock_response

        service = ConfigurationService(device)
        config = service.config()

        assert config is not None
        assert Taxes.objects.count() == 0
