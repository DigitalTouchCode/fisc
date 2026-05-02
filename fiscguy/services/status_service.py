import requests
from django.utils import timezone
from loguru import logger

from fiscguy.exceptions import StatusError
from fiscguy.models import Device, FiscalDay
from fiscguy.zimra_base import ZIMRAClient


class StatusService:
    def __init__(self, device: Device):
        self.device = device

    def get_status(self) -> dict:
        try:
            with ZIMRAClient(self.device) as client:
                status = client.get_status()
                self.reconcile_fiscal_day(self.device, status)
                return status
        except requests.RequestException as exc:
            logger.exception(f"Failed to fetch FDMS status for device {self.device}")
            raise StatusError("Could not retrieve device status") from exc
        except Exception as exc:
            logger.exception(f"Unexpected error fetching status for device {self.device}")
            raise StatusError("Unexpected error retrieving device status") from exc

    @staticmethod
    def reconcile_fiscal_day(device: Device, status_payload: dict) -> FiscalDay | None:
        fiscal_day_no = status_payload.get("fiscalDayNo") or status_payload.get("lastFiscalDayNo")
        fiscal_day_status = status_payload.get("fiscalDayStatus")

        if fiscal_day_no is None or not fiscal_day_status:
            return None

        try:
            fiscal_day_no = int(fiscal_day_no)
        except (TypeError, ValueError):
            return None

        fiscal_day = (
            FiscalDay.objects.filter(device=device, day_no=fiscal_day_no).order_by("-id").first()
        )
        if not fiscal_day:
            fiscal_day = FiscalDay.objects.create(
                device=device,
                day_no=fiscal_day_no,
                is_open=fiscal_day_status
                in {
                    "FiscalDayOpen",
                    "FiscalDayOpened",
                    "FiscalDayCloseInitiated",
                    "FiscalDayCloseFailed",
                },
                close_state=FiscalDay.CloseState.OPEN,
            )

        now = timezone.now()
        fiscal_day.fdms_status = fiscal_day_status
        fiscal_day.last_status_sync_at = now

        if fiscal_day_status in {"FiscalDayClosed", "FiscalDayCloseExecuted"}:
            fiscal_day.is_open = False
            fiscal_day.close_state = FiscalDay.CloseState.CLOSED
            fiscal_day.close_confirmed_at = fiscal_day.close_confirmed_at or now
            fiscal_day.last_close_error_code = None
        elif fiscal_day_status == "FiscalDayCloseFailed":
            fiscal_day.is_open = True
            fiscal_day.close_state = FiscalDay.CloseState.CLOSE_FAILED
            fiscal_day.last_close_error_code = status_payload.get("fiscalDayClosingErrorCode")
        elif fiscal_day_status == "FiscalDayCloseInitiated":
            fiscal_day.is_open = True
            fiscal_day.close_state = FiscalDay.CloseState.CLOSE_PENDING
        elif fiscal_day_status in {"FiscalDayOpen", "FiscalDayOpened"}:
            fiscal_day.is_open = True
            fiscal_day.close_state = FiscalDay.CloseState.OPEN
            fiscal_day.last_close_error_code = None

        fiscal_day.save(
            update_fields=[
                "fdms_status",
                "last_status_sync_at",
                "is_open",
                "close_state",
                "close_confirmed_at",
                "last_close_error_code",
                "updated_at",
            ]
        )
        return fiscal_day
