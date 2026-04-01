from django.db import DatabaseError, transaction
from loguru import logger

from fiscguy.exceptions import FiscalDayError
from fiscguy.models import Device, FiscalDay
from fiscguy.utils.datetime_now import datetime_now as timestamp
from fiscguy.zimra_base import ZIMRAClient


class OpenDayService:

    def __init__(self, device: Device):
        self.device = device
        self.client = ZIMRAClient(device)

    def open_day(self) -> dict:
        """
        Open a new fiscal day for this device.

        Raises:
            FiscalDayError: if FDMS returns an unexpected response or a DB write fails.
        """
        try:
            with transaction.atomic():
                return self._open_day_atomic()
        except FiscalDayError:
            raise
        except DatabaseError as exc:
            logger.exception(f"Database error while opening fiscal day for device {self.device}")
            raise FiscalDayError("Failed to persist fiscal day due to a database error") from exc
        except Exception as exc:
            logger.exception(f"Unexpected error while opening fiscal day for device {self.device}")
            raise FiscalDayError("Failed to open fiscal day unexpectedly") from exc

    def _open_day_atomic(self) -> dict:
        active_day = (
            FiscalDay.objects.select_for_update().filter(device=self.device, is_open=True).first()
        )
        if active_day:
            logger.info(f"Fiscal day {active_day.day_no} already open for device {self.device}")
            return {
                "success": True,
                "fiscal_day_no": active_day.day_no,
                "message": f"Fiscal day {active_day.day_no} already open",
            }

        next_day_no = self._resolve_next_day_no()
        response = self._call_fdms_open_day(next_day_no)
        self._persist_fiscal_day(next_day_no)

        return {
            "success": True,
            "fiscal_day_no": next_day_no,
            "fdms_response": response,
        }

    def _resolve_next_day_no(self) -> int:
        fdms_last_day_no = self._fetch_fdms_last_day_no()
        last_local_day = FiscalDay.objects.filter(device=self.device).order_by("-id").first()

        if last_local_day is None or last_local_day.day_no != fdms_last_day_no:
            logger.warning(
                f"Local/FDMS day_no mismatch for device {self.device}: "
                f"local={getattr(last_local_day, 'day_no', None)}, fdms={fdms_last_day_no}. "
                f"Deferring to FDMS."
            )

        return fdms_last_day_no + 1

    def _fetch_fdms_last_day_no(self) -> int:
        try:
            res = self.client.get_status()
        except Exception as exc:
            logger.exception(f"Failed to fetch FDMS status for device {self.device}")
            raise FiscalDayError("Could not retrieve FDMS status") from exc

        raw = res.get("lastFiscalDayNo")
        if raw is None:
            raise FiscalDayError(
                f"FDMS status response missing 'lastFiscalDayNo' for device {self.device}"
            )

        try:
            return int(raw)
        except (TypeError, ValueError) as exc:
            raise FiscalDayError(f"Invalid 'lastFiscalDayNo' value from FDMS: {raw!r}") from exc

    def _call_fdms_open_day(self, day_no: int) -> dict:
        payload = {
            "fiscalDayOpened": timestamp(),
            "fiscalDayNo": day_no,
        }
        try:
            response = self.client.open_day(payload)
            data = response
        except Exception as exc:
            logger.exception(
                f"FDMS openDay request failed for device {self.device}, day_no={day_no}"
            )
            raise FiscalDayError(f"FDMS openDay call failed for day {day_no}") from exc

        logger.info(f"FDMS openDay response for device {self.device}, day_no={day_no}: {data}")
        return data

    def _persist_fiscal_day(self, day_no: int) -> FiscalDay:
        fiscal_day = FiscalDay.objects.create(
            device=self.device,
            day_no=day_no,
            is_open=True,
            receipt_counter=0,
        )
        logger.info(f"Fiscal day {day_no} persisted for device {self.device}")
        return fiscal_day
