import json
import os
import stat
import tempfile
import threading
from pathlib import Path

import requests
from django.core.management.base import BaseCommand
from django.db import transaction
from loguru import logger

from fiscguy.models import Certs, Device, Taxes
from fiscguy.services.configuration_service import ConfigurationService
from fiscguy.zimra_crypto import ZIMRACrypto

"""
Management command to register a ZIMRA fiscal device and fetch its
configuration from the ZIMRA FDMS API.

Primary responsibilities:
- Interactively collect device registration details from the user.
- Generate CSR and register the device to obtain a signed certificate.
- Fetch device configuration using the signed certificate and persist
    the taxpayer configuration and applicable taxes into local models.

This command intentionally writes/updates a single `Configuration` row
and replaces the `Taxes` table contents with the `applicableTaxes`
returned from ZIMRA. Database writes are wrapped in a transaction to
avoid partial updates.

Note: network calls to ZIMRA use client certificates stored in the
`Certs` model. Temporary files are created for the requests library
and removed afterwards.
"""

BANNER = """
***************************************************************************
*                                                                         *
*  ****  **  ****   ****   ****    **  **  **   **                        *
*  **    **  **     **     **      **  **  **   **                        *
*  ****  **  ****   **     ** **   **  **   *****                         *
*  **    **    **   **     **  **  **  **     **                          *
*  **    **  ****   ****   ****     ****      **                          *
*                                                                         *
***************************************************************************

Developed by Casper Moyo — Version 0.1.6
"""

_FDMS_URLS = {
    True: "https://fdmsapi.zimra.co.zw",
    False: "https://fdmsapitest.zimra.co.zw",
}


class Command(BaseCommand):
    """
    Django management command for ZIMRA device registration.

    Usage (interactive):
        python manage.py init_device

    Steps performed:
        1. Collect and validate device details from stdin.
        2. Create or update the local Device record.
        3. Generate a CSR and register the device with ZIMRA to obtain
           a signed certificate.
        4. Fetch and persist configuration and taxes from ZIMRA's FDMS.
    """

    help = "Interactive registration of a new ZIMRA fiscal device"

    def handle(self, *args, **options):
        self.stdout.write(BANNER)
        self.stdout.write(
            "Welcome to device registration. Please enter the information " "provided by ZIMRA.\n"
        )

        inputs = self._collect_inputs()
        if inputs is None:
            return

        device = self._upsert_device(inputs)
        if device is None:
            return  # environment switch cancelled

        cert_key, csr = self._crypto.generate_key_and_csr(
            inputs["device_sn"],
            inputs["device_id"],
            inputs["env"],
        )

        signed_cert = self.register_device(
            device_id=inputs["device_id"],
            activation_key=inputs["activation_key"],
            model_name=inputs["model_name"],
            model_version=inputs["model_version"],
            env=inputs["env"],
            csr=csr,
            device_sn=inputs["device_sn"],
        )
        if not signed_cert:
            self.stdout.write(self.style.ERROR("Device registration failed. Aborting."))
            return

        zimra_config = self.get_config(
            device_id=inputs["device_id"],
            model_name=inputs["model_name"],
            model_version=inputs["model_version"],
            env=device.production,
        )

        if zimra_config:
            self.stdout.write(self.style.SUCCESS("Configuration fetched successfully."))
            self.stdout.write(json.dumps(zimra_config, indent=2))
        else:
            self.stdout.write(self.style.ERROR("Failed to fetch configuration."))

    def _collect_inputs(self) -> dict | None:
        """
        Prompt the user for all required device fields and validate them.

        Returns a dict of validated inputs, or None if validation fails.
        """
        environment = input("Enter 'yes' for production or 'no' for test: ").strip().lower()
        org = input("Enter your organisation name: ").strip()
        device_id = input("Enter your device ID: ").strip()
        activation_key = input("Enter your activation key: ").strip()
        model_version = input("Enter device model version (e.g. v1): ").strip()
        model_name = input("Enter device model name (e.g. Server): ").strip()
        device_sn = input("Enter device serial number: ").strip()

        if environment not in ("yes", "no"):
            self.stdout.write(self.style.ERROR("Environment must be 'yes' or 'no'."))
            return None

        missing = [
            name
            for name, val in {
                "organisation": org,
                "device ID": device_id,
                "activation key": activation_key,
                "model version": model_version,
                "model name": model_name,
                "serial number": device_sn,
            }.items()
            if not val
        ]
        if missing:
            self.stdout.write(self.style.ERROR(f"Missing required fields: {', '.join(missing)}"))
            return None

        return {
            "env": environment == "yes",
            "org": org,
            "device_id": device_id,
            "activation_key": activation_key,
            "model_version": model_version,
            "model_name": model_name,
            "device_sn": device_sn,
        }

    def _upsert_device(self, inputs: dict) -> Device | None:
        """
        Create a new Device record or update the existing one.

        If the environment is switching (test ↔ production), prompts for
        confirmation and deletes all existing data before proceeding.

        Returns the Device instance, or None if the user cancelled.
        """
        env = inputs["env"]
        device = Device.objects.first()

        if not device:
            device = Device.objects.create(
                org_name=inputs["org"],
                activation_key=inputs["activation_key"],
                device_id=inputs["device_id"],
                device_model_name=inputs["model_name"],
                device_serial_number=inputs["device_sn"],
                device_model_version=inputs["model_version"],
                production=env,
            )
            self.stdout.write(
                self.style.SUCCESS(
                    f"Device {device.device_id} created for "
                    f"{'production' if env else 'test'} environment."
                )
            )
            return device

        if device.production != env:
            current_label = "PRODUCTION" if device.production else "TEST"
            target_label = "PRODUCTION" if env else "TEST"
            warning_lines = [
                "",
                "!" * 75,
                f"!  WARNING: switching from {current_label} to {target_label}.",
                "!  ALL existing data will be permanently deleted:",
                "!    Fiscal Days, Counters, Receipts, Configuration,",
                "!    Certificates, Taxes, Device record.",
                "!" * 75,
                "",
            ]
            self.stdout.write("\n".join(warning_lines))

            confirm = input(
                "Type YES to confirm deletion and switch environment, " "or press Enter to cancel: "
            ).strip()

            if confirm.upper() != "YES":
                self.stdout.write("Environment switch cancelled. No data was deleted.")
                return None

            self.stdout.write("Deleting all existing data...")
            self._delete_all_data()
            self.stdout.write(self.style.SUCCESS("All data deleted.\n"))

        # Update the existing (or freshly cleared) device record
        Device.objects.filter(pk=device.pk).update(
            org_name=inputs["org"],
            activation_key=inputs["activation_key"],
            device_id=inputs["device_id"],
            device_model_name=inputs["model_name"],
            device_serial_number=inputs["device_sn"],
            device_model_version=inputs["model_version"],
            production=env,
        )
        device.refresh_from_db()
        self.stdout.write(
            self.style.SUCCESS(
                f"Device {device.device_id} updated for "
                f"{'production' if env else 'test'} environment."
            )
        )
        return device

    def _delete_all_data(self) -> None:
        """
        Delete all application data in dependency order (children first).
        Wrapped in a transaction so the DB is never left half-empty.
        """
        from fiscguy.models import (
            Configuration,
            FiscalCounter,
            FiscalDay,
            Receipt,
            ReceiptLine,
        )

        ordered_models = [
            ("receipt lines", ReceiptLine),
            ("receipts", Receipt),
            ("fiscal counters", FiscalCounter),
            ("fiscal days", FiscalDay),
            ("configuration", Configuration),
            ("certificates", Certs),
            ("taxes", Taxes),
            ("devices", Device),
        ]

        try:
            with transaction.atomic():
                for label, model in ordered_models:
                    count, _ = model.objects.all().delete()
                    self.stdout.write(self.style.SUCCESS(f"  Deleted {count} {label}"))
                logger.info("All data successfully deleted.")
        except Exception as exc:
            logger.exception("Error during data deletion: {}", exc)
            self.stdout.write(self.style.ERROR(f"Failed to delete data: {exc}"))
            raise

    def register_device(
        self,
        device_id: str,
        activation_key: str,
        model_name: str,
        model_version: str,
        env: bool,
        csr: str,
        device_sn: str,
    ) -> str | None:
        """
        POST to ZIMRA's RegisterDevice endpoint and persist the signed cert.

        Args:
            device_id:      ZIMRA-issued device identifier.
            activation_key: ZIMRA-issued activation key.
            model_name:     Device model name for the request header.
            model_version:  Device model version for the request header.
            env:            True = production, False = test.
            csr:            PEM-encoded certificate signing request.
            device_sn:      Device serial number.

        Returns:
            The signed certificate string on success, or None on failure.
        """
        base_url = _FDMS_URLS[env]
        url = f"{base_url}/Public/v1/{device_id}/RegisterDevice"

        # ZIMRA requires the CSR without line breaks
        clean_csr = csr.replace("\n", "")

        payload = {
            "activationKey": activation_key,
            "deviceSerial": device_sn,
            "certificateRequest": clean_csr,
        }
        headers = {
            "Content-Type": "application/json",
            "deviceModelName": model_name,
            "deviceModelVersion": model_version,
        }

        logger.info("Registering device {} at {}", device_id, url)

        try:
            response = requests.post(url, json=payload, headers=headers, timeout=(5, 30))
            response.raise_for_status()
            data = response.json()
            logger.success("RegisterDevice response: {}", data)

            signed_cert = data.get("certificate")
            if not signed_cert:
                logger.error("No certificate in RegisterDevice response: {}", data)
                self.stdout.write(self.style.ERROR("ZIMRA returned no certificate."))
                return None

            Certs.objects.filter().update(certificate=signed_cert)
            logger.info("Device {} registered successfully.", device_id)
            self.stdout.write(self.style.SUCCESS(f"Device {device_id} registered."))
            return signed_cert

        except requests.Timeout:
            logger.error("RegisterDevice timed out for device {}", device_id)
            self.stdout.write(self.style.ERROR("Registration request timed out."))
        except requests.HTTPError as exc:
            logger.error(
                "RegisterDevice HTTP {}: {}",
                exc.response.status_code,
                exc.response.text,
            )
            self.stdout.write(
                self.style.ERROR(f"Registration failed: HTTP {exc.response.status_code}")
            )
        except requests.RequestException as exc:
            logger.error("RegisterDevice network error: {}", exc)
            self.stdout.write(self.style.ERROR(f"Network error: {exc}"))

        return None

    def get_config(
        self,
        device_id: str,
        model_name: str,
        model_version: str,
        env: bool,
    ) -> dict | None:
        """
        GET device configuration from ZIMRA FDMS and persist locally.

        Uses the client certificate stored in the Certs model.
        Certificate and key are written to a private temporary directory,
        used for the request, and deleted in a finally block.

        Args:
            device_id:     ZIMRA-issued device identifier.
            model_name:    Device model name for the request header.
            model_version: Device model version for the request header.
            env:           True = production, False = test.

        Returns:
            Parsed JSON response dict on success, or None on failure.

        Side effects:
            Creates/updates a single Configuration row.
            Replaces all Taxes rows with applicableTaxes from the response.
        """
        base_url = _FDMS_URLS[env]
        url = f"{base_url}/Device/v1/{device_id}/getConfig"
        headers = {
            "Content-Type": "application/json",
            "deviceModelName": model_name,
            "deviceModelVersion": model_version,
        }

        logger.info("Fetching config for device {} from {}", device_id, url)

        cert = Certs.objects.first()
        if not cert:
            logger.error("No certificate found in DB — cannot fetch config.")
            self.stdout.write(self.style.ERROR("No certificate found. Register the device first."))
            return None

        tmp_dir = Path(tempfile.mkdtemp(prefix="zimra_fdms_"))
        cert_path = tmp_dir / "client_cert.pem"
        key_path = tmp_dir / "client_key.pem"

        try:
            cert_path.write_text(cert.certificate)
            key_path.write_text(cert.certificate_key)

            if os.name != "nt":
                cert_path.chmod(stat.S_IRUSR | stat.S_IWUSR)
                key_path.chmod(stat.S_IRUSR | stat.S_IWUSR)

            response = requests.get(
                url,
                headers=headers,
                cert=(str(cert_path), str(key_path)),
                timeout=(5, 30),
            )
            response.raise_for_status()

            device = Device.objects.get(device_id=device_id)
            data = ConfigurationService(device).config()

            logger.info("Configuration for device {} persisted.", device_id)
            return data

        except requests.Timeout:
            logger.error("getConfig timed out for device {}", device_id)
            self.stdout.write(self.style.ERROR("Config request timed out."))

        except requests.HTTPError as exc:
            logger.error(
                "getConfig HTTP {}: {}",
                exc.response.status_code,
                exc.response.text,
            )
            self.stdout.write(
                self.style.ERROR(f"Config fetch failed: HTTP {exc.response.status_code}")
            )

        except requests.RequestException as exc:
            logger.error("getConfig network error: {}", exc)
            self.stdout.write(self.style.ERROR(f"Network error: {exc}"))

        except Exception as exc:
            logger.exception("Unexpected error fetching config: {}", exc)
            self.stdout.write(self.style.ERROR(f"Unexpected error: {exc}"))

        finally:
            cert_path.unlink(missing_ok=True)
            key_path.unlink(missing_ok=True)
            try:
                tmp_dir.rmdir()
            except OSError:
                pass

        return None

    @property
    def _crypto(self) -> ZIMRACrypto:
        if not hasattr(self, "_crypto_instance"):
            self._crypto_instance = ZIMRACrypto()
        return self._crypto_instance
