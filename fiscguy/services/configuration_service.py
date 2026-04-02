from typing import Dict

from django.db import DatabaseError, transaction
from loguru import logger

from fiscguy.exceptions import ConfigurationError
from fiscguy.models import Configuration, Device, Taxes
from fiscguy.zimra_base import ZIMRAClient


class ConfigurationService:
    def __init__(self, device: Device):
        self.device = device
        self.client = ZIMRAClient(self.device)

    def config(self) -> Configuration:
        config_data = self.get_configuration()
        config = self.create_or_update_config(config_data)
        return config_data

    def get_configuration(self) -> Dict[str, any]:
        try:
            return self.client.get_config()
        except ConfigurationError as exc:
            logger.error(f"Failed to fetch configuration for device {self.device}: {exc}")
            raise ConfigurationError(
                f"Failed to process configuration update for device: {self.device}"
            ) from exc

    def create_or_update_config(self, res: dict) -> Configuration:
        try:
            with transaction.atomic():
                config = self._persist_configuration(res)
                self._persist_taxes(res)
                return config
        except ConfigurationError:
            raise
        except DatabaseError as exc:
            logger.exception("Database error while persisting configuration and taxes")
            raise ConfigurationError("Configuration update failed due to a database error") from exc
        except Exception as exc:
            logger.exception("Unexpected error while persisting configuration and taxes")
            raise ConfigurationError("Configuration update failed unexpectedly") from exc

    def _persist_configuration(self, res: dict) -> Configuration:
        address = self._format_address(res.get("deviceBranchAddress") or {})
        contacts = res.get("deviceBranchContacts") or {}

        config, created = Configuration.objects.get_or_create(
            device=self.device,
            defaults={
                "tax_payer_name": res.get("taxPayerName", "DEFAULT TAXPAYER"),
                "tax_inclusive": res.get("taxInclusive", True),
                "tin_number": res.get("taxPayerTIN", ""),
                "vat_number": res.get("vatNumber", ""),
                "address": address,
                "phone_number": contacts.get("phoneNo", ""),
                "email": contacts.get("email", ""),
                "url": res.get("qrUrl"),
            },
        )

        if not created:
            # Update existing config
            config.tax_payer_name = res.get("taxPayerName", config.tax_payer_name)
            config.tax_inclusive = res.get("taxInclusive", config.tax_inclusive)
            config.tin_number = res.get("taxPayerTIN", config.tin_number)
            config.vat_number = res.get("vatNumber", config.vat_number)
            config.address = address or config.address
            config.phone_number = contacts.get("phoneNo", config.phone_number)
            config.email = contacts.get("email", config.email)
            config.url = res.get("qrUrl", config.url)

            config.save()
            logger.info(f"Updated configuration for device {self.device}")
        else:
            logger.info(f"Created configuration for device {self.device}")

        return config

    def _persist_taxes(self, res: dict) -> None:
        raw_taxes = res.get("applicableTaxes") or []

        tax_objects = [
            Taxes(
                code=str(tax.get("taxID") or 0)[:10],
                name=tax.get("taxName", ""),
                tax_id=int(tax.get("taxID") or 0),
                percent=float(tax.get("taxPercent") or 0.0),
            )
            for tax in raw_taxes
        ]

        Taxes.objects.all().delete()

        try:
            Taxes.objects.bulk_create(tax_objects)
            logger.info(f"Persisted {len(tax_objects)} tax record(s)")
        except DatabaseError as exc:
            logger.exception(
                f"Failed to bulk create {len(tax_objects)} tax record(s) due to database error"
            )
            raise ConfigurationError("Failed to persist tax records") from exc

    @staticmethod
    def _format_address(branch_addr: dict) -> str:
        parts = [
            str(v)
            for key in ("houseNo", "street", "city", "province")
            if (v := branch_addr.get(key))
        ]
        return ", ".join(parts)
