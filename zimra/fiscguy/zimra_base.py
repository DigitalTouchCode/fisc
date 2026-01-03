import json
import tempfile
import shutil
from pathlib import Path
from time import sleep
import threading

import requests
from loguru import logger

from django.utils import timezone
from zoneinfo import ZoneInfo

from .models import Device, Configuration, Certs, FiscalDay


class ZIMRAClient:
    """
    ZIMRA FDMS client.
    """

    TIMEOUT = 30

    def __init__(self, device: Device):
        self.device = device
        self.config = Configuration.objects.first()
        self.certs = Certs.objects.get(device=device)

        if not self.config:
            raise RuntimeError("ZIMRA configuration missing")

        # URLs
        self.base_url = f"https://{self.config.url}/Device/v1/{device.device_id}"
        self.public_url = f"https://{self.config.url}/Public/v1/{device.device_id}"

        # temp cert handling 
        self._lock = threading.Lock()
        self._temp_dir = Path(tempfile.mkdtemp(prefix="zimra_fdms_"))
        self._pem_path = self._temp_dir / "client.pem"
        self._pem_path.write_text(
            f"{self.certs.certificate}\n{self.certs.certificate_key}"
        )

        # session ----
        self.session = requests.Session()
        self.session.cert = str(self._pem_path)
        self.session.headers.update({
            "Content-Type": "application/json",
            "deviceModelName": self.config.device_model_name,
            "deviceModelVersion": self.config.device_model_verrsion,
        })

        logger.info(f"ZIMRA client initialised for device {device.device_id}")

    def _request(self, method: str, endpoint: str, **kwargs):
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        try:
            response = self.session.request(
                method,
                url,
                timeout=self.TIMEOUT,
                **kwargs
            )
            response.raise_for_status()
            return response
        except requests.RequestException as exc:
            logger.error(f"FDMS error [{method} {url}]: {exc}")
            raise

    @staticmethod
    def now_iso():
        return timezone.now().astimezone(
            ZoneInfo("Africa/Harare")
        ).replace(microsecond=0).isoformat()

    def get_status(self) -> dict:
        return self._request("GET", "getStatus").json()

    def get_config(self) -> dict:
        return self._request("GET", "getConfig").json()

    def open_day(self) -> dict:
        active_day = FiscalDay.objects.filter(is_open=True).first()
        if active_day:
            return {
                "success": True,
                "message": f"Fiscal day {active_day.day_no} already open"
            }

        last_day = FiscalDay.objects.order_by("-day_no").first()
        next_day_no = last_day.day_no + 1 if last_day else 1

        payload = {
            "fiscalDayOpened": self.now_iso(),
            "fiscalDayNo": next_day_no,
        }

        response = self._request("POST", "openDay", json=payload).json()

        FiscalDay.objects.create(
            day_no=next_day_no,
            is_open=True,
        )

        return response

    def submit_receipt(self, receipt_payload: dict, hash_value: str, signature: str) -> dict:
        receipt_payload["receipt"]["receiptDeviceSignature"] = {
            "hash": hash_value,
            "signature": signature,
        }

        return self._request(
            "POST",
            "SubmitReceipt",
            json=receipt_payload
        ).json()

    def close_day(self, hash_value: str, signature: str, counters: list) -> dict:
        active_day = FiscalDay.objects.filter(is_open=True).first()
        if not active_day:
            raise RuntimeError("No open fiscal day")

        payload = {
            "fiscalDayNo": active_day.day_no,
            "fiscaleDayDate": active_day.created_at.date().isoformat(),
            "receiptCounter": active_day.receipt_count,
            "fiscalDayCounters": counters,
            "fiscalDayDeviceSignature": {
                "hash": hash_value,
                "signature": signature,
            }
        }

        self._request(
            "POST",
            "CloseDay",
            data=json.dumps(payload)
        )

        active_day.is_open = False
        active_day.save()

        sleep(5)  # ZIMRA recommended delay
        return self.get_status()

    def close(self):
        with self._lock:
            try:
                self.session.close()
            finally:
                shutil.rmtree(self._temp_dir, ignore_errors=True)
                logger.info(
                    f"ZIMRA client closed for device {self.device.device_id}"
                )

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass
