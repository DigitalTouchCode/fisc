import requests
import json
import tempfile
import shutil
from pathlib import Path
import threading

from django.core.management.base import BaseCommand
from loguru import logger

from fiscguy.models import Certs, Configuration, Device
from fiscguy.zimra_crypto import ZIMRACrypto


crypto = ZIMRACrypto()


class Command(BaseCommand):
    help = "Interactive registration of a new ZIMRA device"

    cert = Certs.objects.first()

    def handle(self, *args, **options):

        print(
            "Welcome to device registration please input the following provided information as proveded by ZIMRA\n"
        )
        environment = input(
            "Enter yes if for production environment and no for test enviroment: "
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
                print("\n___Switching device to new environment___\n")
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

        # self.get_config(device_id, model_name, model_version, env)

        # return
        # cert_key, csr = crypto.generate_key_and_csr(device_sn, device_id, env)
      

        # # register the device and get signed certificate from ZIMRA
        # self.register_device(
        #     device_id, 
        #     activation_key,
        #     model_name, 
        #     model_version, 
        #     env, 
        #     csr, 
        #     device_sn
        # )


        # get zimra configurations for the provided device
        zimra_config = self.get_config(
            device_id, model_name, model_version, device.production
        )
        print(zimra_config)

    def get_config(self, device_id, model_name, model_version, env=True):
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

        # ---- create temporary cert and key files separately ----
        temp_dir = Path(tempfile.mkdtemp(prefix="zimra_fdms_"))
        cert_path = temp_dir / "client_cert.pem"
        key_path = temp_dir / "client_key.pem"

        from  fiscguy.models import Certs
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
            print(f"results: {response.json()}")
            return response.json()
        except requests.RequestException as e:
            logger.error(f"Error fetching config: {e}")
            return None
        finally:
            # clean up temp files
            cert_path.unlink(missing_ok=True)
            key_path.unlink(missing_ok=True)
            temp_dir.rmdir()

            return

            config = Configuration.objects.first()
            if not config:
                self.stdout.write(
                    "No configuration found. Creating default ZIMRA configuration..."
                )
                config = Configuration.objects.create(
                    tax_payer_name="DEFAULT TAXPAYER",
                    tax_inclusive=True,
                    device_model_name="POS-DEFAULT",
                    device_model_version="v1.0",
                    url="zimra.gov.zw",
                    activation_key="",
                )
            self.stdout.write(f"Using configuration for device {device_id}.")

            return response.json()
        

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

        headers = headers = {
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
                from  fiscguy.models import Certs
                cert = Certs.objects.first()
                cert.certificate = signed_certificate
                cert.save()

                logger.info(f"Device {device_id} registered successfully.")
                return signed_certificate
        except Exception as e:
            logger.error(f"Device registration failed: {e}")
            return
