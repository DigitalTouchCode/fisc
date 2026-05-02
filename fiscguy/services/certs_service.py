from typing import Tuple

from django.db import transaction
from loguru import logger

from fiscguy.exceptions import CryptoError, PersistenceError, RegistrationError
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
        Generate a key-pair + CSR, renew the device certificate with ZIMRA,
        and persist the signed certificate.

        Returns:
            (private_key_pem, signed_certificate_pem)

        Raises:
            CryptoError: Key/CSR generation failed.
            RegistrationError: ZIMRA rejected the registration request.
            PersistenceError: The signed certificate could not be saved.
        """
        private_key, csr = self._generate_key_and_csr()
        signed_cert = self._issue_certificate(csr)
        self._persist_certificate(private_key, csr, signed_cert)
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

    def _issue_certificate(self, csr: str) -> str:
        """Submit the CSR to ZIMRA's issueCertificate endpoint and return the certificate PEM."""
        payload = {"certificateRequest": csr}
        try:
            response = self.client.issue_certificate(payload)
        except Exception as exc:
            logger.error(
                "Certificate renewal failed for serial={} — {}",
                self.device.device_serial_number,
                exc,
            )
            raise RegistrationError("ZIMRA certificate renewal failed.") from exc

        certificate = response.get("certificate")
        if not certificate:
            raise RegistrationError("ZIMRA did not return a renewed certificate.")

        return certificate

    def _persist_certificate(self, private_key: str, csr: str, signed_cert: str) -> None:
        """Write the signed certificate to the database inside a transaction."""
        try:
            with transaction.atomic():
                tenant_cert, _ = Certs.objects.update_or_create(
                    device=self.device,
                    defaults={
                        "csr": csr,
                        "certificate": signed_cert,
                        "certificate_key": private_key,
                        "production": self.device.production,
                    },
                )
        except Exception as exc:
            logger.error(f"Failed to persist certificate for device={self.device} — {exc}")
            raise PersistenceError("Could not save the signed certificate.") from exc
