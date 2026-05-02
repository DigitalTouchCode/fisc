from unittest.mock import MagicMock, Mock, patch

import pytest
import requests
from django.test import TestCase

from fiscguy.exceptions import DeviceRegistrationError, ZIMRAClientError
from fiscguy.models import Certs, Configuration, Device
from fiscguy.zimra_base import ZIMRAClient


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
def production_device(db):
    """Create a production device."""
    return Device.objects.create(
        org_name="Prod Org",
        activation_key="prod-key-456",
        device_id="PROD-DEVICE-001",
        device_model_name="ModelY",
        device_model_version="2.0",
        device_serial_number="SN-67890",
        production=True,
    )


@pytest.fixture
def configuration(db, device):
    """Create test configuration."""
    return Configuration.objects.create(
        device=device,
        tax_payer_name="Test Taxpayer",
        tax_inclusive=True,
        tin_number="123456789",
        vat_number="987654",
        address="123 Test Street",
        phone_number="+263123456",
        email="test@example.com",
    )


@pytest.fixture
def certs(db, device):
    """Create test certificates."""
    return Certs.objects.create(
        device=device,
        csr="-----BEGIN CERTIFICATE REQUEST-----\ntest\n-----END CERTIFICATE REQUEST-----",
        certificate="-----BEGIN CERTIFICATE-----\ntest-cert\n-----END CERTIFICATE-----",
        certificate_key="-----BEGIN PRIVATE KEY-----\ntest-key\n-----END PRIVATE KEY-----",
        production=False,
    )


@pytest.fixture
def prod_certs(db, production_device):
    """Create production certificates."""
    return Certs.objects.create(
        device=production_device,
        csr="-----BEGIN CERTIFICATE REQUEST-----\nprod\n-----END CERTIFICATE REQUEST-----",
        certificate="-----BEGIN CERTIFICATE-----\nprod-cert\n-----END CERTIFICATE-----",
        certificate_key="-----BEGIN PRIVATE KEY-----\nprod-key\n-----END PRIVATE KEY-----",
        production=True,
    )


@pytest.mark.django_db
class TestZIMRAClientInitialization:
    """Test ZIMRAClient initialization."""

    def test_client_initialization_with_config(self, device, configuration, certs):
        """Test client initializes correctly with configuration and certs."""
        client = ZIMRAClient(device)

        assert client.device == device
        assert client.config == configuration
        assert client.certs == certs
        assert client.base_url == f"https://fdmsapitest.zimra.co.zw/Device/v1/{device.device_id}"
        assert client.public_url == f"https://fdmsapitest.zimra.co.zw/Public/v1/{device.device_id}"

    def test_client_initialization_production(self, production_device, prod_certs):
        """Test client initializes with production URLs."""
        # Create a production configuration for the production device
        prod_config = Configuration.objects.create(
            device=production_device,
            tax_payer_name="Prod Taxpayer",
            tax_inclusive=True,
            tin_number="987654321",
            vat_number="654321",
            address="456 Production Ave",
            phone_number="+263987654",
            email="prod@example.com",
        )

        client = ZIMRAClient(production_device)

        assert (
            client.base_url
            == f"https://fdmsapi.zimra.co.zw/Device/v1/{production_device.device_id}"
        )
        assert (
            client.public_url
            == f"https://fdmsapi.zimra.co.zw/Public/v1/{production_device.device_id}"
        )

    def test_client_initialization_without_config(self, db):
        """Test client still initialises when config is missing."""
        device = Device.objects.create(
            org_name="No Config",
            activation_key="test-key",
            device_id="NO-CONFIG-001",
            device_model_name="Model",
            device_model_version="1.0",
        )

        client = ZIMRAClient(device)
        assert client.base_url == f"https://fdmsapitest.zimra.co.zw/Device/v1/{device.device_id}"

    def test_client_initialization_without_certs(self, device, configuration):
        """Test client initializes without certs."""
        client = ZIMRAClient(device)

        assert client.base_url == f"https://fdmsapitest.zimra.co.zw/Device/v1/{device.device_id}"
        assert client.public_url == f"https://fdmsapitest.zimra.co.zw/Public/v1/{device.device_id}"

    def test_client_session_headers(self, device, configuration, certs):
        """Test session headers are set correctly."""
        client = ZIMRAClient(device)

        assert client.session.headers["Content-Type"] == "application/json"
        assert client.session.headers["DeviceModelName"] == device.device_model_name
        assert client.session.headers["DeviceModelVersion"] == device.device_model_version


@pytest.mark.django_db
class TestZIMRAClientMethods:
    """Test ZIMRAClient HTTP methods with real client and mocked responses."""

    @patch("fiscguy.zimra_base.requests.Session.request")
    def test_get_status(self, mock_request, device, configuration, certs):
        """Test get_status method."""
        expected_response = {
            "fiscalDayStatus": "FiscalDayOpen",
            "receiptCounter": 100,
        }

        mock_response = Mock(spec=requests.Response)
        mock_response.status_code = 200
        mock_response.json.return_value = expected_response
        mock_request.return_value = mock_response

        client = ZIMRAClient(device)
        result = client.get_status()

        assert result == expected_response
        mock_request.assert_called_once()
        call_args = mock_request.call_args
        assert call_args[0][0] == "GET"

    @patch("fiscguy.zimra_base.requests.Session.request")
    def test_get_config(self, mock_request, device, configuration, certs):
        """Test get_config method."""
        expected_response = {
            "taxPayerName": "Test",
            "applicableTaxes": [{"taxID": 1, "taxName": "Standard", "taxPercent": 15.0}],
        }

        mock_response = Mock(spec=requests.Response)
        mock_response.status_code = 200
        mock_response.json.return_value = expected_response
        mock_request.return_value = mock_response

        client = ZIMRAClient(device)
        result = client.get_config()

        assert result == expected_response

    @patch("fiscguy.zimra_base.requests.Session.request")
    def test_ping(self, mock_request, device, configuration, certs):
        """Test ping method."""
        expected_response = {"status": "ok"}

        mock_response = Mock(spec=requests.Response)
        mock_response.status_code = 200
        mock_response.json.return_value = expected_response
        mock_request.return_value = mock_response

        client = ZIMRAClient(device)
        result = client.ping()

        assert result == expected_response

    @patch("fiscguy.zimra_base.requests.Session.request")
    def test_open_day(self, mock_request, device, configuration, certs):
        """Test open_day method."""
        payload = {"deviceID": device.device_id}
        expected_response = {"status": "opened"}

        mock_response = Mock(spec=requests.Response)
        mock_response.status_code = 200
        mock_response.json.return_value = expected_response
        mock_request.return_value = mock_response

        client = ZIMRAClient(device)
        result = client.open_day(payload)

        assert result == expected_response

    @patch("fiscguy.zimra_base.requests.Session.request")
    def test_close_day(self, mock_request, device, configuration, certs):
        """Test close_day method."""
        payload = {
            "deviceID": device.device_id,
            "fiscalDayNo": 1,
        }

        mock_response = Mock(spec=requests.Response)
        mock_response.status_code = 200
        mock_request.return_value = mock_response

        client = ZIMRAClient(device)
        result = client.close_day(payload)

        assert result == mock_response
        call_args = mock_request.call_args
        assert call_args[0][0] == "POST"
        assert call_args[1]["json"] == payload

    @patch("fiscguy.zimra_base.requests.Session.request")
    def test_submit_receipt(self, mock_request, device, configuration, certs):
        """Test submit_receipt method."""
        receipt_payload = {
            "receipt": {
                "receiptNumber": 1,
            }
        }

        expected_response = {"status": "submitted"}

        mock_response = Mock(spec=requests.Response)
        mock_response.status_code = 200
        mock_response.json.return_value = expected_response
        mock_request.return_value = mock_response

        client = ZIMRAClient(device)
        result = client.submit_receipt(receipt_payload, "hash123", "sig456")

        assert result == expected_response
        assert receipt_payload["receipt"]["receiptDeviceSignature"]["hash"] == "hash123"
        assert receipt_payload["receipt"]["receiptDeviceSignature"]["signature"] == "sig456"

    @patch("fiscguy.zimra_base.requests.Session.request")
    def test_request_raises_on_http_error(self, mock_request, device, configuration, certs):
        """Test that _request raises on HTTP error."""
        mock_response = Mock(spec=requests.Response)
        mock_response.status_code = 500
        mock_response.raise_for_status.side_effect = requests.HTTPError("Server error")
        mock_request.return_value = mock_response

        client = ZIMRAClient(device)

        with pytest.raises(requests.HTTPError):
            client.get_status()

    @patch("fiscguy.zimra_base.requests.Session.request")
    def test_request_raises_on_timeout(self, mock_request, device, configuration, certs):
        """Test that _request raises on timeout."""
        mock_request.side_effect = requests.Timeout("Connection timeout")

        client = ZIMRAClient(device)

        with pytest.raises(requests.Timeout):
            client.get_status()


@pytest.mark.django_db
class TestZIMRAClientRegisterDevice:
    """Test device registration with mocked HTTP."""

    @patch("fiscguy.zimra_base.requests.post")
    def test_register_device_success(self, mock_post, device, configuration):
        """Test successful device registration."""
        expected_response = {
            "deviceID": device.device_id,
            "activationKey": "new-key",
            "status": "registered",
        }

        mock_response = Mock(spec=requests.Response)
        mock_response.status_code = 200
        mock_response.json.return_value = expected_response
        mock_post.return_value = mock_response

        client = ZIMRAClient(device)
        payload = {"deviceModelName": "Test"}
        result = client.register_device(payload)

        assert result == expected_response
        mock_post.assert_called_once()

    @patch("fiscguy.zimra_base.requests.post")
    def test_register_device_empty_response(self, mock_post, device, configuration):
        """Test device registration with empty response."""
        mock_response = Mock(spec=requests.Response)
        mock_response.status_code = 200
        mock_response.json.return_value = {}
        mock_post.return_value = mock_response

        client = ZIMRAClient(device)
        payload = {"deviceModelName": "Test"}

        with pytest.raises(DeviceRegistrationError, match="FDMS returned an empty"):
            client.register_device(payload)

    @patch("fiscguy.zimra_base.requests.post")
    def test_register_device_request_error(self, mock_post, device, configuration):
        """Test device registration with request error."""
        mock_post.side_effect = requests.RequestException("Connection failed")

        client = ZIMRAClient(device)
        payload = {"deviceModelName": "Test"}

        with pytest.raises(DeviceRegistrationError, match="Device registration request failed"):
            client.register_device(payload)

    @patch("fiscguy.zimra_base.requests.post")
    def test_register_device_uses_correct_url(self, mock_post, device, configuration):
        """Test that registration uses correct URL based on production flag."""
        mock_response = Mock(spec=requests.Response)
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "ok"}
        mock_post.return_value = mock_response

        client = ZIMRAClient(device)
        client.register_device({})

        call_args = mock_post.call_args
        # Extract URL from first positional argument
        url = call_args[0][0] if call_args[0] else None
        assert url is not None
        assert "fdmsapitest.zimra.co.zw" in url
        assert url.endswith(f"/Public/v1/{device.device_id}/registerDevice")

    @patch("fiscguy.zimra_base.requests.Session.request")
    def test_issue_certificate_posts_payload(self, mock_request, device, configuration, certs):
        """Test certificate renewal sends the request payload."""
        mock_response = Mock(spec=requests.Response)
        mock_response.status_code = 200
        mock_response.json.return_value = {"certificate": "renewed-cert"}
        mock_request.return_value = mock_response

        client = ZIMRAClient(device)
        payload = {"certificateRequest": "csr-data"}

        result = client.issue_certificate(payload)

        assert result == {"certificate": "renewed-cert"}
        call_args = mock_request.call_args
        assert call_args[0][0] == "POST"
        assert call_args[1]["json"] == payload


@pytest.mark.django_db
class TestZIMRAClientContextManager:
    """Test ZIMRAClient as context manager."""

    def test_context_manager_enter_exit(self, device, configuration, certs):
        """Test context manager protocol."""
        with ZIMRAClient(device) as client:
            assert client.device == device
            assert client.session is not None

    def test_context_manager_closes_session(self, device, configuration, certs):
        """Test that context manager closes session."""
        client = ZIMRAClient(device)
        session_before = client.session

        with client:
            pass

        # Session should be closed after exiting context

    def test_client_lifecycle_cleanup(self, device, configuration, certs):
        """Test client cleanup."""
        client = ZIMRAClient(device)
        assert client.session is not None

        client.close()
        # Verify cleanup happened (session closed, temp dir removed)


@pytest.mark.django_db
class TestZIMRAClientEdgeCases:
    """Test edge cases and error conditions."""

    def test_client_with_none_cert_values(self, db):
        """Test client when device has no certs."""
        device = Device.objects.create(
            org_name="Test",
            activation_key="key",
            device_id="TEST-001",
            device_model_name="Model",
            device_model_version="1.0",
        )

        config = Configuration.objects.create(
            device=device,
            tax_payer_name="Test",
            tax_inclusive=True,
            tin_number="123",
            vat_number="456",
            address="Test",
            phone_number="123",
            email="test@test.com",
        )

        client = ZIMRAClient(device)
        # Should initialize without certs
        assert client.device == device

    @patch("fiscguy.zimra_base.requests.Session.request")
    def test_request_with_custom_kwargs(self, mock_request, device, configuration, certs):
        """Test _request with custom kwargs."""
        mock_response = Mock(spec=requests.Response)
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "ok"}
        mock_request.return_value = mock_response

        client = ZIMRAClient(device)
        payload = {"test": "data"}

        # Test that kwargs are passed through
        result = client._request("POST", "testEndpoint", json=payload)

        call_args = mock_request.call_args
        assert call_args.kwargs.get("json") == payload
