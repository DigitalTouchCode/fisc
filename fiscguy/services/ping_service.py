import requests
from loguru import logger

from fiscguy.exceptions import DevicePingError
from fiscguy.models import Device
from fiscguy.zimra_base import ZIMRAClient


class PingService:
    PING_TIMEOUT = 8

    def __init__(self, device: Device):
        self.device = device

    def ping(self) -> dict:
        try:
            with ZIMRAClient(self.device) as client:
                client.TIMEOUT = self.PING_TIMEOUT
                return client.ping()
        except requests.RequestException as exc:
            logger.exception(f"Failed to ping device {self.device}")
            raise DevicePingError("Device ping failed") from exc
        except Exception as exc:
            logger.exception(f"Unexpected error pinging device {self.device}")
            raise DevicePingError("Unexpected error during device ping") from exc
