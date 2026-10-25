from dataclasses import dataclass

from django.db import transaction
from loguru import logger

from fiscguy.exceptions import DeviceRegistrationError
from fiscguy.models import Certs, Device
from fiscguy.services.cert_bundle import CertBundle, CertBundleError, parse_certificate_bundle
from fiscguy.services.device_registration_service import (
    require_reset_confirmation,
    upsert_device,
    wipe_device_history,
)


@dataclass
class ManualRegistrationResult:
    device: Device
    bundle: CertBundle
    created: bool
    wiped: bool


class ManualDeviceRegistrationService:
    """Registers a device from a certificate and key supplied by hand. Makes no call to ZIMRA."""

    @transaction.atomic
    def register(
        self,
        *,
        org_name: str,
        device_id: str,
        production: bool,
        certificate_text: str,
        private_key_text: str | None = None,
        csr_text: str | None = None,
        activation_key: str = "",
        model_name: str,
        model_version: str,
        device_sn: str = "",
        confirm_reset: bool = False,
    ) -> ManualRegistrationResult:
        device_id = str(device_id).strip()
        if not device_id.isdigit():
            raise DeviceRegistrationError("Device ID must be the numeric ZIMRA device ID.")

        try:
            bundle = parse_certificate_bundle(
                certificate_text, private_key_text, csr_text, device_id=device_id
            )
        except CertBundleError as exc:
            raise DeviceRegistrationError(str(exc)) from exc

        existing = Device.objects.filter(device_id=device_id).first()
        wiped = require_reset_confirmation(existing, production, confirm_reset)
        if wiped:
            wipe_device_history(existing)

        device = upsert_device(
            existing,
            org_name=org_name.strip(),
            device_id=device_id,
            activation_key=(activation_key or "").strip(),
            model_name=model_name.strip(),
            model_version=model_version.strip(),
            device_sn=(device_sn or "").strip(),
            production=production,
        )

        Certs.objects.update_or_create(
            device=device,
            defaults={
                "csr": bundle.csr_pem,
                "certificate": bundle.certificate_pem,
                "certificate_key": bundle.private_key_pem,
                "production": production,
            },
        )

        logger.info(
            f"Manual registration: device {device.device_id} "
            f"({'production' if production else 'test'}), created={existing is None}, "
            f"history_wiped={wiped}, cert expires {bundle.not_after:%Y-%m-%d}"
        )
        return ManualRegistrationResult(
            device=device, bundle=bundle, created=existing is None, wiped=wiped
        )
