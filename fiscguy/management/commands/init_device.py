import json
import shutil
import tempfile
import threading
from pathlib import Path

import requests
from django.core.management.base import BaseCommand
from django.db import transaction
from loguru import logger

from fiscguy.models import Certs, Configuration, Device, Taxes
from fiscguy.zimra_crypto import ZIMRACrypto
from fiscguy.services.configuration_service import create_or_update_config

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


crypto = ZIMRACrypto()


class Command(BaseCommand):
    """Django management command for device registration.

    Usage (interactive): run `python manage.py init_device` and follow
    the prompts. The command will:
    - create/update a `Device` record
    - generate a CSR and register the device to obtain a signed cert
    - fetch and persist configuration and taxes from ZIMRA's FDMS

    The class keeps operations small and logs failures rather than
    raising unhandled exceptions so it can be used in ad-hoc admin
    workflows.
    """

    help = "Interactive registration of a new ZIMRA device"

    def handle(self, *args, **options):
        print("\n" + "*" * 75)
        print("*" + " " * 73 + "*")
        print("*  ****  **  ****   ****   ****    **  **  **   **  ")
        print("*  **    **  **     **     **      **  **  **   **  ")
        print("*  ****  **  ****   **     ** **   **  **   *****   ")
        print("*  **    **    **   **     **  **  **  **     **    ")
        print("*  **    **  ****   ****   ****     ****      **    ")
        print("*" + " " * 73 + "*")
        print("*" * 75)
        print("\nDeveloped by Casper Moyo")
        print("Version 1.0.0\n")
        print(
            "Welcome to device registration please input the following provided information as proveded by ZIMRA\n"
        )

        environment = input(
            "Enter yes for production environment and no for test enviroment: "
        ).strip()
        org = input("Enter your organisation name: ").strip()
        device_id = input("Enter your device ID: ").strip()
        activation_key = input("Enter activation Key: ").strip()
        model_version = input("Enter device model version eg v1: ").strip()
        model_name = input("Enter device model name eg Server: ").strip()
        device_sn = input("Enter device serial number: ").strip()

        if not environment.lower() in ["yes", "no"]:
            self.stdout.write(
                self.style.ERROR("Please input environment between yes or no")
            )
            return

        if (
            not device_id
            or not model_version
            or not model_name
            or not environment
            or not device_sn
            or not org
            or not activation_key
        ):
            self.stdout.write(self.style.ERROR("All fields are required."))
            return

        device = Device.objects.first()
        env = True if environment.lower() == "yes" else False

        if not device:
            device = Device.objects.create(
                org_name=org,
                activation_key=activation_key,
                device_id=device_id,
                device_model_name=model_name,
                device_serial_number=device_sn,
                device_model_version=model_version,
                production=env,
            )
            print(
                f"Device {device.device_id} created for {'production' if env else 'test'} environment."
            )

        else:
            if device.production != env:
                print("\n" + "!" * 75)
                print("!" + " " * 73 + "!")
                print("!  WARNING: ENVIRONMENT SWITCH DETECTED" + " " * 33 + "!")
                print("!" + " " * 73 + "!")
                print("!" + " " * 73 + "!")
                print("!  Switching from", "PRODUCTION" if device.production else "TEST", "to", "PRODUCTION" if env else "TEST" + " " * (73 - 54) + "!")
                print("!" + " " * 73 + "!")
                print("!  ALL TEST DATA WILL BE PERMANENTLY DELETED:" + " " * 28 + "!")
                print("!    - Fiscal Days" + " " * 57 + "!")
                print("!    - Fiscal Counters" + " " * 52 + "!")
                print("!    - Receipts & Receipt Lines" + " " * 40 + "!")
                print("!    - Device Configuration" + " " * 47 + "!")
                print("!    - Certificates" + " " * 55 + "!")
                print("!    - Device Record" + " " * 54 + "!")
                print("!" + " " * 73 + "!")
                print("!" * 75)
                
                confirm = input(
                    "\nType 'YES' to confirm data deletion and switch environment, or press Enter to cancel: "
                ).strip()
                
                if confirm.upper() != "YES":
                    print("Environment switch cancelled. No data was deleted.")
                    return
                
                print("\nDeleting all test data...")
                self.delete_all_test_data()
                print("✓ All test data has been deleted.\n")
                
                device.org_name = org
                device.activation_key = activation_key
                device.device_id = device_id
                device.device_model_name = model_name
                device.device_serial_number = device_sn
                device.device_model_version = model_version
                device.production = env
                device.save()
                print(
                    f"Device {device.device_id} updated to {'production' if env else 'test'} environment."
                )
            else:
                device.org_name = org
                device.activation_key = activation_key
                device.device_id = device_id
                device.save()
                print(f"Device {device.device_id} updated for current environment.")

        cert_key, csr = crypto.generate_key_and_csr(device_sn, device_id, env)

        # register the device and get signed certificate from ZIMRA
        self.register_device(
            device_id, activation_key, model_name, model_version, env, csr, device_sn
        )

        # get zimra configurations for the provided device
        zimra_config = self.get_config(
            device_id, model_name, model_version, device.production
        )
        print(zimra_config)

    def delete_all_test_data(self) -> None:
        """
        Delete all test data when switching environments.
        
        Deletes in order of dependencies:
        - Fiscal Days
        - Fiscal Counters
        - Receipts & Receipt Lines
        - Configuration
        - Certificates
        - Device
        - Taxes
        
        """
        try:
            from fiscguy.models import (
                FiscalDay,
                FiscalCounter,
                Receipt,
                ReceiptLine,
                Configuration,
            )
            
            with transaction.atomic():
                # Delete in order of dependencies (child tables first)
                logger.info("Deleting receipt lines...")
                count = ReceiptLine.objects.all().delete()[0]
                self.stdout.write(self.style.SUCCESS(f"  Deleted {count} receipt lines"))
                
                logger.info("Deleting receipts...")
                count = Receipt.objects.all().delete()[0]
                self.stdout.write(self.style.SUCCESS(f"  Deleted {count} receipts"))
                
                logger.info("Deleting fiscal counters...")
                count = FiscalCounter.objects.all().delete()[0]
                self.stdout.write(self.style.SUCCESS(f"  Deleted {count} fiscal counters"))
                
                logger.info("Deleting fiscal days...")
                count = FiscalDay.objects.all().delete()[0]
                self.stdout.write(self.style.SUCCESS(f"  Deleted {count} fiscal days"))
                
                logger.info("Deleting configuration...")
                count = Configuration.objects.all().delete()[0]
                self.stdout.write(self.style.SUCCESS(f"  Deleted {count} configuration records"))
                
                logger.info("Deleting certificates...")
                count = Certs.objects.all().delete()[0]
                self.stdout.write(self.style.SUCCESS(f"  Deleted {count} certificates"))
                
                logger.info("Deleting taxes...")
                count = Taxes.objects.all().delete()[0]
                self.stdout.write(self.style.SUCCESS(f"  Deleted {count} tax records"))
                
                logger.info("Deleting device...")
                count = Device.objects.all().delete()[0]
                self.stdout.write(self.style.SUCCESS(f"  Deleted {count} devices"))
                
                logger.info("All test data successfully deleted")
        except Exception as e:
            logger.exception(f"Error deleting test data: {e}")
            self.stdout.write(self.style.ERROR(f"ERROR: Failed to delete test data: {e}"))
            raise

    def get_config(
        self, device_id: str, model_name: str, model_version: str, env: bool
    ) -> dict:
        """Fetch device configuration from ZIMRA and persist locally.

        Args:
            device_id (str): Device identifier supplied by ZIMRA.
            model_name (str): Device model name header required by FDMS.
            model_version (str): Device model version header.
            env (bool): True for production FDMS endpoint, False for test.

        Returns:
            dict | None: Parsed JSON response from FDMS on success, or
            None when the HTTP request fails.

        Side effects:
            - Creates/updates a single `Configuration` row.
            - Replaces all rows in `Taxes` with the `applicableTaxes`
              returned by the FDMS response.
        """

        logger.info(f"Fetching device: {device_id} configurations")

        url = (
            f"https://fdmsapi.zimra.co.zw/Device/v1/{device_id}"
            if env
            else f"https://fdmsapitest.zimra.co.zw/Device/v1/{device_id}"
        )

        headers = {
            "Content-Type": "application/json",
            "deviceModelName": model_name,
            "deviceModelVersion": model_version,
        }

        temp_dir = Path(tempfile.mkdtemp(prefix="zimra_fdms_"))
        cert_path = temp_dir / "client_cert.pem"
        key_path = temp_dir / "client_key.pem"

        from fiscguy.models import Certs

        cert = Certs.objects.first()
        cert_path.write_text(cert.certificate)
        key_path.write_text(cert.certificate_key)

        try:
            response = requests.get(
                f"{url}/getConfig",
                headers=headers,
                cert=(str(cert_path), str(key_path)),
                timeout=30,
            )
            response.raise_for_status()
            res = response.json()

            create_or_update_config(res)
            logger.info(f"Configuration for device {device_id} updated successfully.")
            return res
        except requests.RequestException as e:
            logger.error(f"Error fetching config: {e}")
            return None
        finally:
            cert_path.unlink(missing_ok=True)
            key_path.unlink(missing_ok=True)
            temp_dir.rmdir()

    def register_device(
        self, device_id, activation_key, model_name, model_version, env, csr, device_sn
    ):
        logger.info(f"Registering device: {device_id}")
        url = (
            f"https://fdmsapi.zimra.co.zw/Public/v1/{device_id}"
            if env
            else f"https://fdmsapitest.zimra.co.zw/Public/v1/{device_id}"
        )
        print(csr)
        csr = csr.replace("\n", "")
        print(csr)

        payload = {
            "activationKey": activation_key,
            "deviceSerial": device_sn,
            "certificateRequest": csr,
        }

        headers = {
            "Content-Type": "application/json",
            "deviceModelName": model_name,
            "deviceModelVersion": model_version,
        }

        try:
            response = requests.post(
                f"{url}/RegisterDevice", json=payload, headers=headers
            )
            response.raise_for_status()

            logger.info(response.json())

            signed_certificate = response.json().get("certificate")

            if signed_certificate:
                from fiscguy.models import Certs

                cert = Certs.objects.first()
                cert.certificate = signed_certificate
                cert.save()

                logger.info(f"Device {device_id} registered successfully.")
                return signed_certificate
        except Exception as e:
            logger.error(f"Device registration failed: {e}")
            return
