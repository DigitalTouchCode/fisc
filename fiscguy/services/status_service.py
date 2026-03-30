import requests
from loguru import logger

from fiscguy.exceptions import StatusError
from fiscguy.models import Device
from fiscguy.zimra_base import ZIMRAClient


class StatusService:
    def __init__(self, device: Device):
        self.device = device

    def get_status(self) -> dict:
        try:
            with ZIMRAClient(self.device) as client:
                return client.get_status()
        except requests.RequestException as exc:
            logger.exception(f"Failed to fetch FDMS status for device {self.device}")
            raise StatusError("Could not retrieve device status") from exc
        except Exception as exc:
            logger.exception(f"Unexpected error fetching status for device {self.device}")
            raise StatusError("Unexpected error retrieving device status") from exc
