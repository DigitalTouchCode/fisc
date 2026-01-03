import requests
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

        cert_key = crypto._create_private_key(env)
        csr = crypto._create_csr(cert_key, device_sn, device_id)

        # register the device and get signed certificate from ZIMRA
        self.register_device(
            device_id, activation_key, model_name, model_version, env, csr, device_sn
        )

        # get zimra configurations for the provided device
        zimra_config = self.get_config(
            device_id, model_name, model_version, device.production
        )
        print(zimra_config)

    def get_config(self, device_id, model_name, model_version, env):
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

        try:
            response = requests.get(
                f"{url}/getConfig",
                headers=headers,
                cert=(self.cert.certificate, self.cert.certificate_key),
            )
            response.raise_for_status()
            logger.info(f"response: {response}")
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
        except requests.exceptions.RequestException as e:
            logger.error(f"Error getting config: {e}")
            return None

    def register_device(
        self, device_id, activation_key, model_name, model_version, env, csr, device_sn
    ):
        logger.info(f"Registering device: {device_id}")
        url = (
            f"https://fdmsapi.zimra.co.zw/Public/v1/{device_id}"
            if env
            else f"https://fdmsapitest.zimra.co.zw/Public/v1/{device_id}"
        )

        csr = csr.replace("\n", "")

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

            signed_certificate = response.json().get("certificate")

            if signed_certificate:

                self.cert.certificate = signed_certificate
                self.cert.save()

                logger.info(f"Device {device_id} registered successfully.")
                return signed_certificate
        except Exception as e:
            logger.error(f"Device registration failed: {e}")
            return
