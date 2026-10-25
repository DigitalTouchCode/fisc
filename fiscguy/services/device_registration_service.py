from django.db import transaction
from loguru import logger

from fiscguy.exceptions import DeviceRegistrationError
from fiscguy.models import (
    Certs,
    Configuration,
    Device,
    FiscalCounter,
    FiscalDay,
    Receipt,
    ReceiptLine,
    Taxes,
)
from fiscguy.services.configuration_service import ConfigurationService
from fiscguy.zimra_base import ZIMRAClient
from fiscguy.zimra_crypto import ZIMRACrypto


class ResetConfirmationRequired(DeviceRegistrationError):
    """Switching test/production would delete the device's fiscal history and was not confirmed."""


def wipe_device_history(device: Device) -> None:
    ReceiptLine.objects.filter(receipt__device=device).delete()
    Receipt.objects.filter(device=device).delete()
    FiscalCounter.objects.filter(device=device).delete()
    FiscalDay.objects.filter(device=device).delete()
    Configuration.objects.filter(device=device).delete()
    Certs.objects.filter(device=device).delete()
    Taxes.objects.filter(device=device).delete()
    logger.warning(f"Wiped fiscal history for device {device.device_id} on environment switch")


def upsert_device(existing, *, org_name, device_id, activation_key, model_name, model_version,
                  device_sn, production) -> Device:
    fields = dict(
        org_name=org_name,
        activation_key=activation_key,
        device_id=device_id,
        device_model_name=model_name,
        device_serial_number=device_sn,
        device_model_version=model_version,
        production=production,
    )
    if existing:
        for key, value in fields.items():
            setattr(existing, key, value)
        existing.save()
        return existing
    return Device.objects.create(**fields)


def require_reset_confirmation(existing, production: bool, confirm_reset: bool) -> bool:
    """True when history must be wiped; raises unless the caller confirmed it."""
    if not existing or existing.production == production:
        return False
    if not confirm_reset:
        current = "production" if existing.production else "test"
        target = "production" if production else "test"
        raise ResetConfirmationRequired(
            f"Device {existing.device_id} is registered for {current}. Switching to {target} "
            "permanently deletes its fiscal history (days, counters, receipts, certificates, "
            "config). Confirm the reset to continue."
        )
    return True


class DeviceRegistrationService:
    """Registers a device with ZIMRA (CSR, registerDevice, config sync), the same flow as init_device."""

    @transaction.atomic
    def register(
        self,
        *,
        org_name: str,
        device_id: str,
        activation_key: str,
        model_name: str,
        model_version: str,
        device_sn: str,
        production: bool,
        confirm_reset: bool = False,
    ) -> Device:
        existing = Device.objects.filter(device_id=device_id).first()
        if require_reset_confirmation(existing, production, confirm_reset):
            wipe_device_history(existing)

        device = upsert_device(
            existing,
            org_name=org_name,
            device_id=device_id,
            activation_key=activation_key,
            model_name=model_name,
            model_version=model_version,
            device_sn=device_sn,
            production=production,
        )

        cert_key, csr = ZIMRACrypto.generate_key_and_csr(device_sn, device_id, production)

        try:
            response = ZIMRAClient(device).register_device(
                {"activationKey": activation_key, "certificateRequest": csr}
            )
        except Exception as exc:
            logger.error(f"ZIMRA registerDevice failed for {device_id}: {exc}")
            raise DeviceRegistrationError(f"ZIMRA rejected device registration: {exc}") from exc

        signed_cert = response.get("certificate")
        if not signed_cert:
            raise DeviceRegistrationError("ZIMRA returned no certificate for this device.")

        Certs.objects.update_or_create(
            device=device,
            defaults={
                "csr": csr,
                "certificate": signed_cert,
                "certificate_key": cert_key,
                "production": production,
            },
        )

        try:
            ConfigurationService(device).config()
        except Exception as exc:
            logger.exception(f"Device {device_id} registered but initial config fetch failed")
            raise DeviceRegistrationError(
                "Device registered with ZIMRA, but fetching its configuration and tax rates "
                f"failed: {exc}. The device is saved; retry with sync configuration."
            ) from exc

        return device
