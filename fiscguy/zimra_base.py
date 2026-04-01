import json
import shutil
import tempfile
import threading
from pathlib import Path

import requests
from loguru import logger

from fiscguy.exceptions import DeviceRegistrationError
from fiscguy.models import Certs, Configuration, Device


class ZIMRAClient:
    """
    ZIMRA FDMS client.
    """

    TIMEOUT = 30

    def __init__(self, device: Device):
        self.device = device
        self._config = None
        self._certs = None
        self._validate_config()

    @property
    def config(self):
        if self._config is None:
            self._config = Configuration.objects.filter(device=self.device).first()
        return self._config

    @property
    def certs(self):
        if self._certs is None:
            self._certs = Certs.objects.filter(device=self.device).first()
        return self._certs

    def _validate_config(self):
        """Validate that configuration exists"""
        if not self.config:
            raise RuntimeError("ZIMRA configuration missing")

        if self.certs:
            if self.certs.production:
                self.base_url = f"https://fdmsapi.zimra.co.zw/Device/v1/{self.device.device_id}"
                self.public_url = f"https://fdmsapi.zimra.co.zw/Public/v1/{self.device.device_id}"
            else:
                self.base_url = f"https://fdmsapitest.zimra.co.zw/Device/v1/{self.device.device_id}"
                self.public_url = (
                    f"https://fdmsapitest.zimra.co.zw/Public/v1/{self.device.device_id}"
                )
        else:
            self.base_url = None
            self.public_url = None

        self._lock = threading.Lock()
        self._temp_dir = Path(tempfile.mkdtemp(prefix="zimra_fdms_"))
        self._pem_path = self._temp_dir / "client.pem"

        if self.certs:
            self._pem_path.write_text(f"{self.certs.certificate}\n{self.certs.certificate_key}")
        else:
            logger.warning(
                "No ZIMRA certs found — temporary PEM not created yet. "
                "Certs must be registered before submitting receipts."
            )

        # session
        self.session = requests.Session()
        if self.certs:
            self.session.cert = str(self._pem_path)
        self.session.headers.update(
            {
                "Content-Type": "application/json",
                "deviceModelName": self.device.device_model_name,
                "deviceModelVersion": self.device.device_model_version,
            }
        )

        logger.info(f"ZIMRA client initialised for device {self.device.device_id}")

    def _request(self, method: str, endpoint: str, **kwargs):
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        try:
            response = self.session.request(method, url, timeout=self.TIMEOUT, **kwargs)
            response.raise_for_status()
            return response
        except requests.RequestException as exc:
            logger.error(f"FDMS error [{method} {url}]: {exc}")
            raise

    def register_device(self, payload: dict) -> dict:
        """
        Register the device via the public FDMS endpoint.
        Does not require certs — uses a plain requests.post.

        Raises:
            DeviceRegistrationError: on request failure or empty response.
        """
        domain = "fdmsapi.zimra.co.zw" if self.device.production else "fdmsapitest.zimra.co.zw"
        url = f"https://{domain}/Public/v1/{self.device.device_id}/RegisterDevice"

        logger.info(
            f"Registering device {self.device.device_id}, " f"production={self.device.production}"
        )

        try:
            response = requests.post(
                url,
                timeout=self.TIMEOUT,
                json=payload,
                headers={
                    "Content-Type": "application/json",
                    "deviceModelName": self.device.device_model_name,
                    "deviceModelVersion": self.device.device_model_version,
                },
            )
            response.raise_for_status()
            data = response.json()
        except requests.RequestException as exc:
            logger.exception(f"FDMS registration request failed [{url}]: {exc}")
            raise DeviceRegistrationError("Device registration request failed") from exc

        if not data:
            raise DeviceRegistrationError("FDMS returned an empty registration response")

        return data

    def get_status(self) -> dict:
        return self._request("GET", "getStatus").json()

    def get_config(self) -> dict:
        return self._request("GET", "getConfig").json()

    def ping(self) -> dict:
        return self._request("POST", "ping", json={}).json()

    def open_day(self, payload: dict) -> dict:
        return self._request("POST", "openDay", json=payload).json()

    def close_day(self, payload: dict) -> requests.Response:
        """
        Submit the close-day payload to FDMS.

        Returns the raw Response so callers can inspect status/headers.
        DB updates and post-close logic belong in ClosingDayService.
        """
        return self._request("POST", "CloseDay", data=json.dumps(payload))

    def submit_receipt(self, receipt_payload: dict, hash_value: str, signature: str) -> dict:
        receipt_payload["receipt"]["receiptDeviceSignature"] = {
            "hash": hash_value,
            "signature": signature,
        }
        logger.info(f"Submitting receipt for device {self.device.device_id}")
        return self._request("POST", "SubmitReceipt", json=receipt_payload).json()

    # Lifecycle
    def close(self):
        with self._lock:
            try:
                if self.session:
                    self.session.close()
            finally:
                shutil.rmtree(self._temp_dir, ignore_errors=True)
                logger.info(f"ZIMRAClient closed — device={self.device.device_id}")

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass
