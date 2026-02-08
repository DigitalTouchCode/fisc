from loguru import logger
from django.db import transaction
from fiscguy.models import Configuration, Taxes


def create_or_update_config(res: dict) -> None:
    try:
        with transaction.atomic():
            config = Configuration.objects.first()

            branch_addr = res.get("deviceBranchAddress") or {}
            addr_parts = []
            for k in ("houseNo", "street", "city", "province"):
                v = branch_addr.get(k)
                if v:
                    addr_parts.append(str(v))
            address_str = ", ".join(addr_parts) if addr_parts else ""

            contacts = res.get("deviceBranchContacts") or {}
            
            if not config:
                config = Configuration.objects.create(
                    tax_payer_name=res.get("taxPayerName", "DEFAULT TAXPAYER"),
                    tax_inclusive=True,
                    tin_number=res.get("taxPayerTIN", ""),
                    vat_number=res.get("vatNumber", ""),
                    address=address_str,
                    phone_number=contacts.get("phoneNo", ""),
                    email=contacts.get("email", ""),
                    url=res.get("qrUrl", None),
                )
            else:
                config.tax_payer_name = res.get("taxPayerName", config.tax_payer_name)
                config.tin_number = res.get("taxPayerTIN", config.tin_number)
                config.vat_number = res.get("vatNumber", config.vat_number)
                config.address = address_str or config.address
                config.phone_number = contacts.get("phoneNo", config.phone_number)
                config.email = contacts.get("email", config.email)
                config.url = res.get("qrUrl", config.url)
                config.save()

            Taxes.objects.all().delete()
            for tax in res.get("applicableTaxes", []):
                tax_id = tax.get("taxID") or 0
                percent = tax.get("taxPercent")
                if percent is None:
                    # e.g. 'Exempt' entries may have no percent
                    percent = 0.0
                try:
                    Taxes.objects.create(
                        code=str(tax_id)[:10],
                        name=tax.get("taxName", ""),
                        tax_id=int(tax_id),
                        percent=float(percent),
                    )
                except Exception:
                    logger.exception(f"Error creating tax record for: {tax}")
    except Exception:
        logger.exception("Failed to persist configuration and taxes")
        raise
