"""
ZIMRA Fiscal Device Public API.

Provides high-level functions for fiscal operations:
- open_day: Open a new fiscal day
- close_day: Close the open fiscal day
- get_status: Get device and fiscal status
- submit_receipt: Create and submit a receipt to ZIMRA
- get_configuration: Fetch device configuration
- get_taxes: Fetch available tax types

This module encapsulates business logic previously in views,
providing a clean library interface for both API and programmatic use.
"""

from typing import Dict, Any
from loguru import logger

from fiscguy.models import Device, FiscalDay, Taxes
from fiscguy.services.closing_day_service import ClosingDayService
from fiscguy.services.receipt_service import ReceiptService
from fiscguy.zimra_base import ZIMRAClient
from fiscguy.zimra_receipt_handler import ZIMRAReceiptHandler


# Module-level instances
_device = None
_client = None
_receipt_handler = None


def _get_device() -> Device:
    """Get or cache the first device. Raises if none exists."""
    global _device
    if _device is None:
        _device = Device.objects.first()
        if not _device:
            raise RuntimeError("No Device found. Please run init_device management command.")
    return _device


def _get_client() -> ZIMRAClient:
    """Get or cache the ZIMRA client. Lazy initialization."""
    global _client
    if _client is None:
        device = _get_device()
        logger.info(f"Initializing ZIMRA client for device {device}")
        _client = ZIMRAClient(device)
    return _client


def _get_receipt_handler() -> ZIMRAReceiptHandler:
    """Get or cache the receipt handler. Lazy initialization."""
    global _receipt_handler
    if _receipt_handler is None:
        _receipt_handler = ZIMRAReceiptHandler()
    return _receipt_handler


def get_status() -> Dict[str, Any]:
    """
    Get the current device and fiscal day status.

    Returns:
        dict: Status response from ZIMRA FDMS.

    Raises:
        RuntimeError: If device not found or FDMS request fails.
    """
    logger.info("Fetching device status")
    client = _get_client()
    return client.get_status()


def open_day() -> Dict[str, Any]:
    """
    Open a new fiscal day.

    Creates a FiscalDay record and calls ZIMRA to open the day.
    Returns early if a day is already open.

    Returns:
        dict: Response from ZIMRA FDMS or local message if already open.

    Raises:
        RuntimeError: If device not found or FDMS request fails.
    """
    logger.info("Opening fiscal day")
    client = _get_client()
    return client.open_day()


def close_day() -> Dict[str, Any]:
    """
    Close the open fiscal day.

    Collects fiscal counters, builds closing string, signs it, and submits
    to ZIMRA. Updates the fiscal day status and returns the status payload.

    Returns:
        dict: Final device/fiscal status from ZIMRA FDMS.

    Raises:
        error: If no open fiscal day or device not found.
        Exception: If FDMS request fails.
    """
    logger.info("Closing fiscal day")
    device = _get_device()
    receipt_handler = _get_receipt_handler()
    client = _get_client()

    # Get open fiscal day
    fiscal_day = FiscalDay.objects.filter(is_open=True).first()
    if not fiscal_day:
        return {"error": "No open fiscal day to close"}

    # Collect counters and build closing payload
    fiscal_counters = fiscal_day.counters.all()
    tax_map = {t.tax_id: t.name for t in Taxes.objects.all()}

    logger.info(f"Fiscal counters for day {fiscal_day.day_no}: {list(fiscal_counters)}")

    service = ClosingDayService(
        device=device,
        fiscal_day=fiscal_day,
        fiscal_counters=fiscal_counters,
        tax_map=tax_map,
        receipt_handler=receipt_handler,
    )

    closing_string, payload = service.close_day()

    # Submit to ZIMRA and fetch final status
    client.close_day(payload)
    status_payload = client.get_status()

    return status_payload


def submit_receipt(receipt_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Create and submit a receipt to ZIMRA.

    Parses the receipt payload, creates Receipt and ReceiptLine records,
    generates receipt data (signature/hash), and submits to ZIMRA.

    Args:
        receipt_data (dict): Receipt payload with structure:
            {
                "receipt_type": str,
                "currency": str,
                "total_amount": float,
                "lines": [
                    {
                        "product": str,
                        "quantity": float,
                        "unit_price": float,
                        "line_total": float,
                        "tax_amount": float, # optional, can be calculated from tax percent if tax_name provided
                        "tax_name": str,  
                    },
                    ...
                ],
                ...
            }

    Returns:
        dict: Serialized receipt with all fields including ID and lines.

    Raises:
        ValidationError: If receipt_data is invalid (missing required fields, invalid tax).
        Exception: If FDMS submission fails.
    """
    receipt_handler = _get_receipt_handler()

    service = ReceiptService(receipt_handler=receipt_handler)
    receipt, submission_res = service.create_and_submit_receipt(receipt_data)

    logger.info(f"Receipt submitted to ZIMRA: {submission_res}")
    return receipt


def get_configuration() -> Dict[str, Any]:
    """
    Get the stored device configuration.

    Returns:
        dict: Configuration fields (tax_payer_name, tin_number, vat_number, etc.)
              or empty dict if no configuration exists.
    """
    from fiscguy.models import Configuration
    from fiscguy.serializers import ConfigurationSerializer

    logger.info("Fetching device configuration")
    config = Configuration.objects.first()
    if not config:
        logger.warning("No configuration found")
        return {}
    return ConfigurationSerializer(config).data


def get_taxes() -> list:
    """
    Get all available tax types.

    Returns:
        list: Array of tax objects with fields:
            {
                "id": int,
                "code": str,
                "name": str,
                "tax_id": int,
                "percent": float
            }
    """
    from fiscguy.serializers import TaxSerializer

    logger.info("Fetching taxes")
    taxes = Taxes.objects.all()
    return TaxSerializer(taxes, many=True).data


# module-level shortcuts
__all__ = [
    "open_day",
    "close_day",
    "get_status",
    "submit_receipt",
    "get_configuration",
    "get_taxes",
]
