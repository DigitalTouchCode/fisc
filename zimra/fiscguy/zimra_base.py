import json
import shutil
import tempfile
import threading
from pathlib import Path
from time import sleep
from zoneinfo import ZoneInfo

import requests
from django.utils import timezone
from loguru import logger

from fiscguy.utils.datetime_now import date_today as today
from fiscguy.utils.datetime_now import datetime_now as timestamp

from .models import Certs, Configuration, Device, FiscalDay


class ZIMRAClient:
    """
    ZIMRA FDMS client.
    """

    TIMEOUT = 30

    def __init__(self, device: Device):
        self.device = device
        self.config = Configuration.objects.first()
        self.certs = Certs.objects.first()

        if not self.config:
            raise RuntimeError("ZIMRA configuration missing")

        # URLs
        if self.certs.production:
            self.base_url = f"https://fdmsapi.zimra.co.zw/Device/v1/{device.device_id}"
            self.public_url = (
                f"https://fdmsapi.zimra.co.zw/Public/v1/{device.device_id}"
            )
        else:
            self.base_url = (
                f"https://fdmsapitest.zimra.co.zw/Device/v1/{device.device_id}"
            )
            self.public_url = (
                f"https://fdmsapitest.zimra.co,.zw/Public/v1/{device.device_id}"
            )

        # temp cert handling
        self._lock = threading.Lock()
        self._temp_dir = Path(tempfile.mkdtemp(prefix="zimra_fdms_"))
        self._pem_path = self._temp_dir / "client.pem"
        self._pem_path.write_text(
            f"{self.certs.certificate}\n{self.certs.certificate_key}"
        )

        # session
        self.session = requests.Session()
        self.session.cert = str(self._pem_path)
        self.session.headers.update(
            {
                "Content-Type": "application/json",
                "deviceModelName": self.device.device_model_name,
                "deviceModelVersion": self.device.device_model_version,
            }
        )

        logger.info(f"ZIMRA client initialised for device {device.device_id}")

    def _request(self, method: str, endpoint: str, **kwargs):
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        try:
            response = self.session.request(method, url, timeout=self.TIMEOUT, **kwargs)
            response.raise_for_status()
            return response
        except requests.RequestException as exc:
            logger.error(f"FDMS error [{method} {url}]: {exc}")
            raise

    @staticmethod
    def now_iso():
        return (
            timezone.now()
            .astimezone(ZoneInfo("Africa/Harare"))
            .replace(microsecond=0)
            .isoformat()
        )

    def get_status(self) -> dict:
        return self._request("GET", "getStatus").json()

    def get_config(self) -> dict:
        return self._request("GET", "getConfig").json()

    def open_day(self) -> dict:
        active_day = FiscalDay.objects.filter(is_open=True).first()
        if active_day:
            return {
                "success": True,
                "message": f"Fiscal day {active_day.day_no} already open",
            }

        last_day = FiscalDay.objects.order_by("-id").first()
        next_day_no = last_day.day_no + 1 if last_day else 1

        payload = {
            "fiscalDayOpened": timestamp(),
            "fiscalDayNo": next_day_no,
        }

        response = self._request("POST", "openDay", json=payload).json()

        FiscalDay.objects.create(day_no=next_day_no, is_open=True, receipt_counter=0)

        return response

    def close_day(self, payload: dict) -> dict:

        active_day = FiscalDay.objects.filter(is_open=True).first()
        if not active_day:
            raise RuntimeError("No open fiscal day")

        self._request("POST", "CloseDay", data=json.dumps(payload))

        active_day.is_open = False
        active_day.save()

        sleep(10)

        return self.get_status()

    def submit_receipt(
        self, receipt_payload: dict, hash_value: str, signature: str
    ) -> dict:
        receipt_payload["receipt"]["receiptDeviceSignature"] = {
            "hash": hash_value,
            "signature": signature,
        }

        logger.info(f"Submitting receipt: {receipt_payload}")
        
        return self._request("POST", "SubmitReceipt", json=receipt_payload).json()

    def close(self):
        with self._lock:
            try:
                self.session.close()
            finally:
                shutil.rmtree(self._temp_dir, ignore_errors=True)
                logger.info(f"ZIMRA client closed for device {self.device.device_id}")

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass
