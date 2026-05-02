from unittest.mock import MagicMock, patch

from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from fiscguy.exceptions import (
    CertificateError,
    CloseDayError,
    ConfigurationError,
    DevicePingError,
    FiscalDayError,
    ReceiptSubmissionError,
    StatusError,
)
from fiscguy.models import Buyer, Configuration, Device, FiscalCounter, FiscalDay, Receipt, Taxes


def make_device(**kwargs) -> Device:
    defaults = dict(
        org_name="Test Org",
        activation_key="test-key",
        device_id="41872",
        device_model_name="Server",
        device_model_version="1.0",
        device_serial_number="SN-001",
        production=False,
    )
    defaults.update(kwargs)
    return Device.objects.create(**defaults)


def make_fiscal_day(device: Device, is_open: bool = True, **kwargs) -> FiscalDay:
    defaults = dict(device=device, day_no=1, is_open=is_open, receipt_counter=0)
    defaults.update(kwargs)
    return FiscalDay.objects.create(**defaults)


def make_tax(**kwargs) -> Taxes:
    defaults = dict(tax_id=1, name="Standard VAT 15%", percent=15)
    defaults.update(kwargs)
    return Taxes.objects.create(**defaults)


# ReceiptView
class ReceiptViewGetTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.url = "/receipts/"
        self.device = make_device()

    def test_get_returns_paginated_receipts(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("results", response.data)

    def test_get_empty_returns_empty_results(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 0)


class ReceiptViewPostTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.url = "/receipts/"
        self.device = make_device()
        self.payload = {
            "receipt_type": "fiscalInvoice",
            "currency": "ZWG",
            "total_amount": "100.00",
            "payment_terms": "Cash",
            "lines": [],
        }

    @patch("fiscguy.views.ReceiptService")
    def test_post_success_returns_201(self, MockService):
        mock_receipt = MagicMock(spec=Receipt)
        MockService.return_value.create_and_submit_receipt.return_value = (
            mock_receipt,
            {"submitted": True},
        )
        with patch("fiscguy.views.ReceiptSerializer") as MockSerializer:
            MockSerializer.return_value.data = {"id": 1}
            response = self.client.post(self.url, self.payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    @patch("fiscguy.views.ReceiptService")
    def test_post_receipt_submission_error_returns_422(self, MockService):
        MockService.return_value.create_and_submit_receipt.side_effect = ReceiptSubmissionError(
            "FDMS rejected"
        )
        response = self.client.post(self.url, self.payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_422_UNPROCESSABLE_ENTITY)
        self.assertIn("error", response.data)

    @patch("fiscguy.views.ReceiptService")
    def test_post_unexpected_error_returns_500(self, MockService):
        MockService.return_value.create_and_submit_receipt.side_effect = Exception("boom")
        response = self.client.post(self.url, self.payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)
        self.assertIn("error", response.data)

    def test_post_no_device_does_not_crash(self):
        Device.objects.all().delete()
        # Device.objects.first() returns None — service will receive None
        # behaviour depends on service, view should not raise unhandled exception
        with patch("fiscguy.views.ReceiptService") as MockService:
            MockService.return_value.create_and_submit_receipt.side_effect = ReceiptSubmissionError(
                "no device"
            )
            response = self.client.post(self.url, self.payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_422_UNPROCESSABLE_ENTITY)


# ReceiptDetailView
class ReceiptDetailViewTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.device = make_device()

    def test_get_nonexistent_receipt_returns_404(self):
        response = self.client.get("/receipts/9999/")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


# ConfigurationView
class ConfigurationViewTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.url = "/configuration/"

    def test_get_no_device_returns_empty(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, {})

    def test_get_device_no_config_returns_empty(self):
        make_device()
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, {})

    def test_get_device_with_config_returns_data(self):
        device = make_device()
        Configuration.objects.create(device=device, tax_payer_name="Test Co")
        with patch("fiscguy.views.ConfigurationSerializer") as MockSerializer:
            MockSerializer.return_value.data = {"taxPayerName": "Test Co"}
            response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_get_exception_returns_400(self):
        with patch("fiscguy.views.Device.objects") as MockManager:
            MockManager.first.side_effect = Exception("db error")
            response = self.client.get(self.url)
        self.assertEqual(response.status_code, 400)
        self.assertIn("error", response.data)


# TaxView
class TaxViewTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.url = "/taxes/"

    def test_get_returns_empty_list(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, [])

    def test_get_returns_taxes(self):
        make_tax(tax_id=1, name="Standard VAT 15%", percent=15)
        make_tax(tax_id=2, name="Zero Rated 0%", percent=0)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 2)

    def test_get_exception_propagates(self):
        with patch("fiscguy.views.Taxes.objects") as MockManager:
            MockManager.all.side_effect = Exception("db error")
            with self.assertRaises(Exception):
                self.client.get(self.url)


# GetStatusView
class GetStatusViewTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.url = "/get-status/"

    def test_get_no_device_returns_404(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertIn("error", response.data)

    @patch("fiscguy.views.StatusService")
    def test_get_success_returns_200(self, MockService):
        make_device()
        MockService.return_value.get_status.return_value = {"fiscalDayStatus": "FiscalDayOpened"}
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["fiscalDayStatus"], "FiscalDayOpened")

    @patch("fiscguy.views.StatusService")
    def test_get_status_error_returns_500(self, MockService):
        make_device()
        MockService.return_value.get_status.side_effect = StatusError("FDMS unreachable")
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)
        self.assertIn("error", response.data)

    @patch("fiscguy.views.StatusService")
    def test_get_unexpected_error_returns_400(self, MockService):
        make_device()
        MockService.return_value.get_status.side_effect = Exception("unexpected")
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 400)
        self.assertIn("error", response.data)


# DevicePing
class DevicePingTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.url = "/get-ping/"

    def test_post_no_device_returns_404(self):
        response = self.client.post(self.url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertIn("error", response.data)

    @patch("fiscguy.views.PingService")
    def test_post_success_returns_200(self, MockService):
        make_device()
        MockService.return_value.ping.return_value = {"status": "ok"}
        response = self.client.post(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], "ok")

    @patch("fiscguy.views.PingService")
    def test_post_ping_error_returns_500(self, MockService):
        make_device()
        MockService.return_value.ping.side_effect = DevicePingError("timeout")
        response = self.client.post(self.url)
        self.assertEqual(response.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)
        self.assertIn("error", response.data)

    @patch("fiscguy.views.PingService")
    def test_post_unexpected_error_returns_400(self, MockService):
        make_device()
        MockService.return_value.ping.side_effect = Exception("unexpected")
        response = self.client.post(self.url)
        self.assertEqual(response.status_code, 400)
        self.assertIn("error", response.data)

    def test_get_not_allowed(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)


# OpenDayView
class OpenDayViewTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.url = "/open-day/"

    def test_post_no_device_returns_404(self):
        response = self.client.post(self.url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertIn("error", response.data)

    @patch("fiscguy.views.ConfigurationService")
    @patch("fiscguy.views.OpenDayService")
    def test_post_success_returns_200(self, MockOpenDay, MockConfig):
        make_device()
        MockOpenDay.return_value.open_day.return_value = {"fiscalDayNo": 1}
        MockConfig.return_value.config.return_value = None
        response = self.client.post(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["fiscalDayNo"], 1)

    @patch("fiscguy.views.OpenDayService")
    def test_post_fiscal_day_error_returns_400(self, MockOpenDay):
        make_device()
        MockOpenDay.return_value.open_day.side_effect = FiscalDayError("already open")
        response = self.client.post(self.url)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("error", response.data)

    @patch("fiscguy.views.ConfigurationService")
    @patch("fiscguy.views.OpenDayService")
    def test_post_config_error_after_open_returns_500(self, MockOpenDay, MockConfig):
        make_device()
        MockOpenDay.return_value.open_day.return_value = {"fiscalDayNo": 1}
        MockConfig.return_value.config.side_effect = ConfigurationError("sync failed")
        response = self.client.post(self.url)
        self.assertEqual(response.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)
        self.assertIn("error", response.data)

    @patch("fiscguy.views.OpenDayService")
    def test_post_unexpected_error_returns_500(self, MockOpenDay):
        make_device()
        MockOpenDay.return_value.open_day.side_effect = Exception("unexpected")
        response = self.client.post(self.url)
        self.assertEqual(response.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)
        self.assertIn("error", response.data)

    def test_get_not_allowed(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)


# CloseDayView
class CloseDayViewTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.url = "/close-day/"

    def test_post_no_device_returns_404(self):
        response = self.client.post(self.url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertIn("error", response.data)

    def test_post_no_open_fiscal_day_returns_400(self):
        device = make_device()
        make_fiscal_day(device, is_open=False)
        response = self.client.post(self.url)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("error", response.data)

    @patch("fiscguy.views.ClosingDayService")
    def test_post_success_returns_200(self, MockService):
        device = make_device()
        make_fiscal_day(device, is_open=True)
        make_tax()
        MockService.return_value.close_day.return_value = {"fiscalDayStatus": "FiscalDayClosed"}
        response = self.client.post(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["fiscalDayStatus"], "FiscalDayClosed")

    @patch("fiscguy.views.ClosingDayService")
    def test_post_close_day_error_returns_422(self, MockService):
        device = make_device()
        make_fiscal_day(device, is_open=True)
        make_tax()
        MockService.return_value.close_day.side_effect = CloseDayError("CountersMismatch")
        response = self.client.post(self.url)
        self.assertEqual(response.status_code, status.HTTP_422_UNPROCESSABLE_ENTITY)
        self.assertIn("error", response.data)

    @patch("fiscguy.views.ClosingDayService")
    def test_post_unexpected_error_returns_500(self, MockService):
        device = make_device()
        make_fiscal_day(device, is_open=True)
        make_tax()
        MockService.return_value.close_day.side_effect = Exception("unexpected")
        response = self.client.post(self.url)
        self.assertEqual(response.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)
        self.assertIn("error", response.data)

    @patch("fiscguy.views.ClosingDayService")
    def test_post_passes_correct_tax_map_to_service(self, MockService):
        device = make_device()
        make_fiscal_day(device, is_open=True)
        make_tax(tax_id=1, name="Standard VAT 15%", percent=15)
        make_tax(tax_id=2, name="Zero Rated 0%", percent=0)
        MockService.return_value.close_day.return_value = {}
        self.client.post(self.url)
        call_kwargs = MockService.call_args.kwargs
        self.assertEqual(call_kwargs["tax_map"], {1: "Standard VAT 15%", 2: "Zero Rated 0%"})

    def test_get_not_allowed(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)


# SyncConfigurationView
class SyncConfigurationViewTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.url = "/sync-config/"

    def test_post_no_device_returns_404(self):
        response = self.client.post(self.url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertIn("error", response.data)

    @patch("fiscguy.views.ConfigurationService")
    def test_post_success_returns_200(self, MockService):
        make_device()
        MockService.return_value.config.return_value = None
        response = self.client.post(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["message"], "Configuration Synced")

    @patch("fiscguy.views.ConfigurationService")
    def test_post_configuration_error_returns_500(self, MockService):
        make_device()
        MockService.return_value.config.side_effect = ConfigurationError("sync failed")
        response = self.client.post(self.url)
        self.assertEqual(response.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)
        self.assertIn("error", response.data)

    @patch("fiscguy.views.ConfigurationService")
    def test_post_unexpected_error_returns_500(self, MockService):
        make_device()
        MockService.return_value.config.side_effect = Exception("unexpected")
        response = self.client.post(self.url)
        self.assertEqual(response.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)
        self.assertIn("error", response.data)

    def test_get_not_allowed(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)


# IssueCertificateView
class IssueCertificateViewTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.url = "/issue-certificate/"

    def test_post_no_device_returns_404(self):
        response = self.client.post(self.url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertIn("error", response.data)

    @patch("fiscguy.views.CertificateService")
    def test_post_success_returns_200(self, MockService):
        make_device()
        MockService.return_value.issue_certificate.return_value = None
        response = self.client.post(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["message"], "Certificate issued successfully")

    @patch("fiscguy.views.CertificateService")
    def test_post_certificate_error_returns_422(self, MockService):
        make_device()
        MockService.return_value.issue_certificate.side_effect = CertificateError("expired")
        response = self.client.post(self.url)
        self.assertEqual(response.status_code, status.HTTP_422_UNPROCESSABLE_ENTITY)
        self.assertIn("error", response.data)

    @patch("fiscguy.views.CertificateService")
    def test_post_unexpected_error_returns_500(self, MockService):
        make_device()
        MockService.return_value.issue_certificate.side_effect = Exception("unexpected")
        response = self.client.post(self.url)
        self.assertEqual(response.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)
        self.assertIn("error", response.data)

    def test_get_not_allowed(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
