"""
Base ZIMRA Class
Handles core ZIMRA FDMS API operations including device management,
status checks, and day operations.
"""

import datetime
import json
import os
from time import sleep

import requests
from celery import shared_task
from django.conf import settings
from dotenv import load_dotenv
from loguru import logger

from .models import Certs, Configuration, FiscalDay

load_dotenv()

today = datetime.datetime.today()
logger.add("fiscal.log", rotation="1 MB", level="INFO")


class ZIMRA:
    """
    Base ZIMRA class for interacting with Zimbabwe Revenue Authority (ZIMRA)
    Fiscal Device Management System (FDMS) API.

    This class handles:
    - Device registration and certificate management
    - Device status and configuration
    - API communication with FDMS
    """

    # global
    device_id = int(os.getenv("DEVICE_ID"))
    all_certificates = Certs.objects.first()
    config = Configuration.objects.first()

    def __init__(self, certs, config):
        """Initialize ZIMRA instance with configuration from environment variables"""
        self.activation_key = config.activation_key
        self.device_model_name = config.device_model_name
        self.device_model_version = config.device_model_verrsion
        self.certificate = certs.certificate
        self.certificate_key = certs.certificate_key
        self.registration_url = f"https://{config.url}/Public/v1/{self.device_id}"
        self.base_url = f"https://{config.url}/Device/v1/{self.device_id}"

        logger.info(f"ZIMRA instance initialized for device {self.device_id}")

    def _get_headers(self):
        """Get standard headers for ZIMRA API requests"""
        return {
            "Content-Type": "application/json",
            "deviceModelName": self.device_model_name,
            "deviceModelVersion": self.device_model_version,
        }

    def register_device(self):
        """
        Register device with ZIMRA FDMS.

        Returns:
            str: Signed certificate if successful, None otherwise
        """
        payload = {
            "activationKey": self.activation_key,
            "certificateRequest": self.load_certificate(),
        }

        headers = self._get_headers()

        logger.info(f"Registering device with payload: {payload}")

        try:
            response = requests.post(
                f"{self.registration_url}/RegisterDevice", json=payload, headers=headers
            )
            response.raise_for_status()

            signed_certificate = response.json().get("certificate")
            if signed_certificate:
                self.save_certificate(signed_certificate)
                logger.info("Device registered successfully.")
                return signed_certificate
        except Exception as e:
            logger.error(f"Device registration failed: {e}")
            return None

    def load_certificate(self):
        """
        Read the existing certificate request file.

        Returns:
            str: Certificate content or error message
        """
        try:
            with open(self.certificate_path, "r") as cert_file:
                return cert_file.read()
        except FileNotFoundError:
            logger.error(
                f"Certificate request file not found at {self.certificate_path}"
            )
            return "CERTIFICATE REQUEST NOT FOUND"

    def save_certificate(self, signed_certificate):
        """
        Save the signed certificate to file.

        Args:
            signed_certificate (str): The signed certificate to save
        """
        try:
            with open(self.certificate_path, "w") as cert_file:
                cert_file.write(signed_certificate)
            logger.info(f"Signed certificate saved at {self.certificate_path}")
        except Exception as e:
            logger.error(f"Failed to save signed certificate: {e}")

    def issue_certificate(self):
        """
        Issue a new certificate from ZIMRA.

        Returns:
            dict: Response data from ZIMRA or None if failed
        """
        url = f"https://{self.base_url}/IssueCertificate"

        headers = self._get_headers()

        payload = {"certificateRequest": self.load_certificate()}

        try:
            response = requests.post(
                url,
                headers=headers,
                json=payload,
                cert=(self.certificate_path, self.certificate_key),
            )
            response.raise_for_status()
            data = response.json()

            logger.info("Issue Certificate Response:", data)

            if "certificate" in data:
                with open("cert.pem", "w") as cert_file:
                    cert_file.write(data["certificate"])
                logger.info("Certificate saved to cert.pem")

            return data
        except requests.exceptions.RequestException as e:
            logger.error(f"Error issuing certificate: {e}")
            return None

    def get_status(self):
        """
        Get current device status from ZIMRA.

        Returns:
            dict: Status information or None if failed
        """
        headers = self._get_headers()

        try:
            response = requests.get(
                f"{self.base_url}/getStatus",
                headers=headers,
                cert=(self.certificate_path, self.certificate_key),
            )
            response.raise_for_status()
            logger.success(f"GetStatus Response: {response.json()}")
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Error getting status: {e}")
            return None

    def get_config(self):
        """
        Get device configuration from ZIMRA.

        Returns:
            dict: Configuration data or None if failed
        """
        headers = self._get_headers()

        try:
            response = requests.get(
                f"{self.base_url}/getConfig",
                headers=headers,
                cert=(self.certificate_path, self.certificate_key),
            )
            response.raise_for_status()
            logger.info(f"GetConfig Response: {response.json()}")
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Error getting config: {e}")
            return None

    def submit_receipt(self, receipt_data, credit_note_data, hash_value, signature):
        """
        Submit a receipt to ZIMRA FDMS.

        Args:
            receipt_data (dict): Receipt data with 'receipt' key
            hash_value (str): Receipt hash
            signature (str): Receipt signature

        Returns:
            dict: Response from ZIMRA or error
        """
        headers = self._get_headers()

        try:
            logger.info(f"Receipt data: {receipt_data}")

            receipt_data["receipt"]["receiptDeviceSignature"] = {
                "hash": hash_value,
                "signature": signature,
            }

            request = requests.post(
                f"{self.base_url}/SubmitReceipt/",
                json=receipt_data,
                headers=headers,
                cert=(self.certificate_path, self.certificate_key),
            )

            request.raise_for_status()
            logger.info(f"Receipt response: {request.json()}")
            return request

        except Exception as e:
            logger.error(f"Error submitting receipt: {e}")
            return {"error": str(e)}

    def open_day(self, payload):
        """
        Open a fiscal day via ZIMRA API.

        Args:
            payload (dict): Fiscal day opening data

        Returns:
            dict: Response from ZIMRA or error
        """
        headers = self._get_headers()

        try:
            response = requests.post(
                f"{self.base_url}/openDay",
                json=payload,
                headers=headers,
                cert=(self.certificate_path, self.certificate_key),
            )
            response.raise_for_status()
            logger.info(f"Open day response: {response.json()}")
            return response.json()
        except Exception as e:
            logger.error(f"Error opening fiscal day: {e}")
            return {"error": str(e)}

    def close_day(self, hash, signature, counters):
        """
        Closes the active fiscal day and submits the necessary data to ZIMRA FDMS.
        """
        active_day = FiscalDay.objects.filter(is_open=True).first()

        if not active_day:
            logger.info("No active fiscal day to close.")
            return

        logger.info(f"signature: {signature}")
        logger.info(f"signature: {hash}")
        logger.info(f"signature: {counters}")

        sale_by_tax_counter = []
        sale_tax_by_tax_counter = []
        balance_by_money_counter = []

        for counter in counters:
            if counter.fiscal_counter_type == "Balancebymoneytype":
                fiscal_counter_data = {
                    "fiscalCounterType": counter.fiscal_counter_type,
                    "fiscalCounterCurrency": counter.fiscal_counter_currency,
                    "fiscalCounterMoneyType": counter.fiscal_counter_money_type or 0,
                    "fiscalCounterValue": float(round(counter.fiscal_counter_value, 2)),
                }

            elif float(round(counter.fiscal_counter_value, 2)) == 0.00:
                continue

            else:
                fiscal_counter_data = {
                    "fiscalCounterType": counter.fiscal_counter_type,
                    "fiscalCounterCurrency": counter.fiscal_counter_currency,
                    "fiscalCounterTaxPercent": float(
                        counter.fiscal_counter_tax_percent
                    ),
                    "fiscalCounterTaxID": counter.fiscal_counter_tax_id,
                    "fiscalCounterValue": float(round(counter.fiscal_counter_value, 2)),
                }

            if counter.fiscale_counter_type == "SaleByTax":
                sale_by_tax_counter.append(counter)
            elif counter.fiscal_counter_type == "SaleTaxByTax":
                sale_tax_by_tax_counter.append(fiscal_counter_data)
            elif counter.fiscal_counter_type == "BalanceByMoneyType":
                balance_by_money_counter.append(fiscal_counter_data)

        fiscal_day_counters = (
            sale_by_tax_counter + sale_tax_by_tax_counter + balance_by_money_counter
        )

        payload = {
            "fiscalDayNo": active_day.day_no,
            "fiscaleDayDate": active_day.created_at.date().isoformat(),
            "fiscalDayCounters": fiscal_day_counters,
            "fiscalDayDeviceSignature": {"hash": hash, "signature": signature},
            "receiptCounter": active_day.receipt_count,
        }

        logger.info(f"Fiscal day counters: {fiscal_day_counters}")
        logger.info(f"Closing Fiscal Day with payload: {payload}")

        headers = self._get_headers()

        try:
            json_payload = json.dumps(payload)

            logger.info(f"JSON payload: {json_payload}")

            response = requests.post(
                f"{self.base_url}/CloseDay",
                data=json_payload,
                headers=headers,
                cert=(self.certificate_path, self.certificate_key),
            )

            response.raise_for_status()

            active_day.is_open = False
            active_day.save()

            sleep(10)

            status = self.get_status()

            logger.info(f"Fiscal Day {active_day.day_no} closed successfully.")

            return status.json()
        except requests.RequestException as e:
            logger.error(f"Error closing fiscal day: {e}")
            return f"Error closing fiscal day: {e}"

    def ping(self):
        """
        Ping ZIMRA FDMS to maintain connection and get reporting frequency.
        This is a Celery task that reschedules itself based on the response.

        Returns:
            dict: Response from ZIMRA or error
        """
        headers = self._get_headers()

        try:
            response = requests.post(
                f"{self.base_url}{self.device_id}/Ping",
                headers=headers,
                cert=(self.certificate_path, self.certificate_key),
            )

            logger.info(f"Ping response: {response}")
            response.raise_for_status()

            data = response.json()
            reporting_frequency = int(data.get("reportingFrequency", 300))

            settings.REPORTING_FREQUENCY = reporting_frequency * 60

            logger.info(
                f"FDMS online. Next ping in {reporting_frequency * 60} seconds."
            )

            # Reschedule the task
            self.apply_async(countdown=reporting_frequency * 60)

            return response.json()

        except requests.RequestException as e:
            logger.error(f"Ping error: {e}")
            return {"error": str(e)}
