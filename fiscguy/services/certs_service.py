from typing import Tuple

from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction
from loguru import logger

from fiscguy.exceptions import CertNotFoundError, CryptoError, PersistenceError, RegistrationError
from fiscguy.models import Certs, Device
from fiscguy.zimra_base import ZIMRAClient
from fiscguy.zimra_crypto import ZIMRACrypto


class CertificateService:
    """Handles the full certificate lifecycle for a single device."""

    def __init__(self, device: Device) -> None:
        self.device = device
        self.crypto = ZIMRACrypto()
        self.client = ZIMRAClient(device)

    def issue_certificate(self) -> Tuple[str, str]:
        """
        Generate a key-pair + CSR, register the device with ZIMRA,
        and persist the signed certificate.

        Returns:
            (private_key_pem, signed_certificate_pem)

        Raises:
            CryptoError: Key/CSR generation failed.
            RegistrationError: ZIMRA rejected the registration request.
            PersistenceError: The signed certificate could not be saved.
        """
        private_key, csr = self._generate_key_and_csr()
        signed_cert = self._sign_certificate(csr)
        self._persist_certificate(signed_cert)
        return private_key, signed_cert

    def _generate_key_and_csr(self) -> Tuple[str, str]:
        """Return (private_key_pem, csr_pem) for the device."""
        try:
            return self.crypto.generate_key_and_csr(
                self.device.device_serial_number,
                self.device.device_id,
                self.device.production,
            )
        except Exception as exc:
            logger.exception("Key/CSR generation failed for device {}", self.device.device_id)
            raise CryptoError("Failed to generate key and CSR.") from exc

    def _sign_certificate(self, csr: str) -> str:
        """Submit the CSR to ZIMRA and return the signed certificate PEM."""
        payload = {
            "activationKey": self.device.activation_key,
            "deviceSerial": self.device.device_serial_number,
            "certificateRequest": csr.replace("\n", ""),  # remove escape character,
        }
        try:
            return self.client.register_device(payload)
        except Exception as exc:
            logger.error(
                "Device registration failed for serial={} — {}",
                self.device.device_serial_number,
                exc,
            )
            raise RegistrationError("ZIMRA device registration failed.") from exc

    def _persist_certificate(self, signed_cert: str) -> None:
        """Write the signed certificate to the database inside a transaction."""
        try:
            tenant_cert = Certs.objects.filter(device=self.device).first()
        except ObjectDoesNotExist as exc:
            logger.error("No certificate record found for device={}", self.device)
            raise CertNotFoundError(
                f"Certificate record not found for device {self.device!r}."
            ) from exc

        try:
            with transaction.atomic():
                tenant_cert.certificate = signed_cert
                tenant_cert.save(update_fields=["certificate"])
        except Exception as exc:
            logger.error(f"Failed to persist certificate for device={self.device} — {exc}")
            raise PersistenceError("Could not save the signed certificate.") from exc
