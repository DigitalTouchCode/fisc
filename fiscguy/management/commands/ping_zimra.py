import time

from django.core.management.base import BaseCommand
from loguru import logger
from zimra_base import ZIMRAClient

from fiscguy.api import _get_client
from fiscguy.models import Device


class Command(BaseCommand):
    help = "Ping ZIMRA periodically"

    def handle(self, *arg, **optioons):
        logger.info("Ping for Initiatiated")
        while True:
            try:
                res = _get_client().ping()
                time.sleep(res["reportingFrequency"])
            except Exception as e:
                logger.error(f"Failed to ping zimra: {e}")
