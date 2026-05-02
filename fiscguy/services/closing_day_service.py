from collections import defaultdict
from time import sleep
from typing import Any, Dict, Iterable, List, Tuple

from django.utils import timezone
from loguru import logger

from fiscguy.exceptions import CloseDayError
from fiscguy.models import Device, FiscalCounter, FiscalDay
from fiscguy.services.status_service import StatusService
from fiscguy.zimra_base import ZIMRAClient
from fiscguy.zimra_receipt_handler import ZIMRAReceiptHandler

SALE_BY_TAX_ORDER: Tuple[str, ...] = ("exempt", "zero", "standard")
SALE_TAX_BY_TAX_ORDER: Tuple[str, ...] = ("zero", "standard")
CREDIT_BY_TAX_ORDER: Tuple[str, ...] = ("exempt", "zero", "standard")
CREDIT_TAX_BY_TAX_ORDER: Tuple[str, ...] = ("zero", "standard")
DEBIT_BY_TAX_ORDER: Tuple[str, ...] = ("exempt", "zero", "standard")
DEBIT_TAX_BY_TAX_ORDER: Tuple[str, ...] = ("zero", "standard")


class ClosingDayService:
    """Closing day service"""

    def __init__(
        self,
        device: Device,
        fiscal_day: FiscalDay,
        fiscal_counters: Iterable[FiscalCounter],
        tax_map: Dict[int, str],
    ) -> None:
        self.device = device
        self.fiscal_day = fiscal_day
        self.counters = list(fiscal_counters)
        self.tax_map = tax_map
        self.receipt_handler = ZIMRAReceiptHandler(self.device)
        self.client = ZIMRAClient(self.device)

        self.sale_by_tax_payload: List[Dict[str, Any]] = []
        self.sale_tax_by_tax_payload: List[Dict[str, Any]] = []
        self.credit_by_tax_payload: List[Dict[str, Any]] = []
        self.credit_tax_by_tax_payload: List[Dict[str, Any]] = []
        self.debit_by_tax_payload: List[Dict[str, Any]] = []
        self.debit_tax_by_tax_payload: List[Dict[str, Any]] = []
        self.balance_by_money_payload: List[Dict[str, Any]] = []

    def _money_value(self, value: float) -> int:
        """Convert a currency value to cents (integer), preserving sign."""
        return int(round(value * 100))

    def _fmt_tax_percent(self, tax_percent) -> str:
        """
        Format tax percent for the closing signature string per ZIMRA spec
        (section 13.3.1):
          - Always two decimal places: 15 → "15.00", 0 → "0.00", 14.5 → "14.50"
          - Exempt (None) → empty string ""
        """
        if tax_percent is None:
            return ""
        return f"{float(tax_percent):.2f}"

    def _sort_by_tax_id(self, counters: List[FiscalCounter]) -> List[FiscalCounter]:
        """
        Sort counters by (currency ascending, tax_id ascending) as required
        by ZIMRA spec section 13.3.1 for byTax counter types.
        """
        return sorted(
            counters,
            key=lambda c: (
                (c.fiscal_counter_currency or "").upper(),
                c.fiscal_counter_tax_id if c.fiscal_counter_tax_id is not None else 0,
            ),
        )

    def build_sale_by_tax(self) -> str:
        buckets: Dict[str, List[str]] = defaultdict(list)

        # Filter, then sort by currency + tax_id per spec
        relevant = self._sort_by_tax_id(
            [
                c
                for c in self.counters
                if c.fiscal_counter_type.lower() == "salebytax" and c.fiscal_counter_value != 0
            ]  # spec: zero-value counters must not be submitted
        )

        for c in relevant:
            tax_name: str = self.tax_map.get(c.fiscal_counter_tax_id, "").lower()

            if "standard" in tax_name:
                key = "standard"
            elif "zero" in tax_name:
                key = "zero"
            else:
                key = "exempt"

            base: str = c.fiscal_counter_type.lower() + c.fiscal_counter_currency.upper()
            tax_part: str = self._fmt_tax_percent(c.fiscal_counter_tax_percent)

            buckets[key].append(f"{base}{tax_part}{self._money_value(c.fiscal_counter_value)}")

            self.sale_by_tax_payload.append(
                {
                    "fiscalCounterType": c.fiscal_counter_type,
                    "fiscalCounterCurrency": c.fiscal_counter_currency,
                    "fiscalCounterTaxPercent": (
                        float(c.fiscal_counter_tax_percent)
                        if c.fiscal_counter_tax_percent is not None
                        else None
                    ),
                    "fiscalCounterTaxID": c.fiscal_counter_tax_id,
                    "fiscalCounterValue": float(round(c.fiscal_counter_value, 2)),
                }
            )

        return "".join("".join(buckets[k]) for k in SALE_BY_TAX_ORDER)

    def build_sale_tax_by_tax(self) -> str:
        buckets: Dict[str, List[str]] = defaultdict(list)

        relevant = self._sort_by_tax_id(
            [
                c
                for c in self.counters
                if c.fiscal_counter_type.lower() == "saletaxbytax" and c.fiscal_counter_value != 0
            ]  # spec: zero-value counters must not be submitted
        )

        for c in relevant:
            tax_name: str = self.tax_map.get(c.fiscal_counter_tax_id, "").lower()
            key: str = "zero" if "zero" in tax_name else "standard"

            base: str = c.fiscal_counter_type.lower() + c.fiscal_counter_currency.upper()
            tax_part: str = self._fmt_tax_percent(c.fiscal_counter_tax_percent)

            buckets[key].append(f"{base}{tax_part}{self._money_value(c.fiscal_counter_value)}")

            self.sale_tax_by_tax_payload.append(
                {
                    "fiscalCounterType": c.fiscal_counter_type,
                    "fiscalCounterCurrency": c.fiscal_counter_currency,
                    "fiscalCounterTaxPercent": (
                        float(c.fiscal_counter_tax_percent)
                        if c.fiscal_counter_tax_percent is not None
                        else None
                    ),
                    "fiscalCounterTaxID": c.fiscal_counter_tax_id,
                    "fiscalCounterValue": float(round(c.fiscal_counter_value, 2)),
                }
            )

        return "".join("".join(buckets[k]) for k in SALE_TAX_BY_TAX_ORDER)

    def build_credit_note_by_tax(self) -> str:
        buckets: Dict[str, List[str]] = defaultdict(list)

        # spec: zero-value counters must not be submitted
        relevant = self._sort_by_tax_id(
            [
                c
                for c in self.counters
                if c.fiscal_counter_type.lower() == "creditnotebytax"
                and c.fiscal_counter_value != 0
            ]
        )

        for c in relevant:
            tax_name: str = self.tax_map.get(c.fiscal_counter_tax_id, "").lower()

            if "standard" in tax_name:
                key = "standard"
            elif "zero" in tax_name:
                key = "zero"
            else:
                key = "exempt"

            base: str = c.fiscal_counter_type.lower() + c.fiscal_counter_currency.upper()
            tax_part: str = self._fmt_tax_percent(c.fiscal_counter_tax_percent)

            # Value is already negative (set correctly by _update_fiscal_counters_inner)
            buckets[key].append(f"{base}{tax_part}{self._money_value(c.fiscal_counter_value)}")

            self.credit_by_tax_payload.append(
                {
                    "fiscalCounterType": c.fiscal_counter_type,
                    "fiscalCounterCurrency": c.fiscal_counter_currency,
                    "fiscalCounterTaxPercent": (
                        float(c.fiscal_counter_tax_percent)
                        if c.fiscal_counter_tax_percent is not None
                        else None
                    ),
                    "fiscalCounterTaxID": c.fiscal_counter_tax_id,
                    "fiscalCounterValue": float(round(c.fiscal_counter_value, 2)),
                }
            )

        return "".join("".join(buckets[k]) for k in CREDIT_BY_TAX_ORDER)

    def build_credit_note_tax_by_tax(self) -> str:
        buckets: Dict[str, List[str]] = defaultdict(list)

        # spec: zero-value counters must not be submitted
        relevant = self._sort_by_tax_id(
            [
                c
                for c in self.counters
                if c.fiscal_counter_type.lower() == "creditnotetaxbytax"
                and c.fiscal_counter_value != 0
            ]
        )

        for c in relevant:
            tax_name: str = self.tax_map.get(c.fiscal_counter_tax_id, "").lower()
            key: str = "zero" if "zero" in tax_name else "standard"

            base: str = c.fiscal_counter_type.lower() + c.fiscal_counter_currency.upper()
            tax_part: str = self._fmt_tax_percent(c.fiscal_counter_tax_percent)

            # Value is already negative (set correctly by _update_fiscal_counters_inner)
            buckets[key].append(f"{base}{tax_part}{self._money_value(c.fiscal_counter_value)}")

            self.credit_tax_by_tax_payload.append(
                {
                    "fiscalCounterType": c.fiscal_counter_type,
                    "fiscalCounterCurrency": c.fiscal_counter_currency,
                    "fiscalCounterTaxPercent": (
                        float(c.fiscal_counter_tax_percent)
                        if c.fiscal_counter_tax_percent is not None
                        else None
                    ),
                    "fiscalCounterTaxID": c.fiscal_counter_tax_id,
                    "fiscalCounterValue": float(round(c.fiscal_counter_value, 2)),
                }
            )

        return "".join("".join(buckets[k]) for k in CREDIT_TAX_BY_TAX_ORDER)

    def build_balance_by_money_type(self) -> str:
        strings: List[str] = []

        counters = sorted(
            [
                c
                for c in self.counters
                if c.fiscal_counter_type.lower() == "balancebymoneytype"
                and c.fiscal_counter_value != 0
            ],
            key=lambda c: (
                (c.fiscal_counter_currency or "").upper(),
                (c.fiscal_counter_money_type or "").upper(),
            ),
        )

        for c in counters:
            base = c.fiscal_counter_type.lower() + c.fiscal_counter_currency.upper()

            strings.append(
                f"{base}{c.fiscal_counter_money_type}{self._money_value(c.fiscal_counter_value)}"
            )

            self.balance_by_money_payload.append(
                {
                    "fiscalCounterType": c.fiscal_counter_type,
                    "fiscalCounterCurrency": c.fiscal_counter_currency,
                    "fiscalCounterMoneyType": c.fiscal_counter_money_type or 0,
                    "fiscalCounterValue": float(round(c.fiscal_counter_value, 2)),
                }
            )

        return "".join(strings)

    def build_debit_note_by_tax(self) -> str:
        buckets: Dict[str, List[str]] = defaultdict(list)

        relevant = self._sort_by_tax_id(
            [
                c
                for c in self.counters
                if c.fiscal_counter_type.lower() == "debitnotebytax" and c.fiscal_counter_value != 0
            ]
        )

        for c in relevant:
            tax_name: str = self.tax_map.get(c.fiscal_counter_tax_id, "").lower()

            if "standard" in tax_name:
                key = "standard"
            elif "zero" in tax_name:
                key = "zero"
            else:
                key = "exempt"

            base: str = c.fiscal_counter_type.lower() + c.fiscal_counter_currency.upper()
            tax_part: str = self._fmt_tax_percent(c.fiscal_counter_tax_percent)

            buckets[key].append(f"{base}{tax_part}{self._money_value(c.fiscal_counter_value)}")

            self.debit_by_tax_payload.append(
                {
                    "fiscalCounterType": c.fiscal_counter_type,
                    "fiscalCounterCurrency": c.fiscal_counter_currency,
                    "fiscalCounterTaxPercent": (
                        float(c.fiscal_counter_tax_percent)
                        if c.fiscal_counter_tax_percent is not None
                        else None
                    ),
                    "fiscalCounterTaxID": c.fiscal_counter_tax_id,
                    "fiscalCounterValue": float(round(c.fiscal_counter_value, 2)),
                }
            )

        return "".join("".join(buckets[k]) for k in DEBIT_BY_TAX_ORDER)

    def build_debit_note_tax_by_tax(self) -> str:
        buckets: Dict[str, List[str]] = defaultdict(list)

        relevant = self._sort_by_tax_id(
            [
                c
                for c in self.counters
                if c.fiscal_counter_type.lower() == "debitnotetaxbytax"
                and c.fiscal_counter_value != 0
            ]
        )

        for c in relevant:
            tax_name: str = self.tax_map.get(c.fiscal_counter_tax_id, "").lower()
            key: str = "zero" if "zero" in tax_name else "standard"

            base: str = c.fiscal_counter_type.lower() + c.fiscal_counter_currency.upper()
            tax_part: str = self._fmt_tax_percent(c.fiscal_counter_tax_percent)

            buckets[key].append(f"{base}{tax_part}{self._money_value(c.fiscal_counter_value)}")

            self.debit_tax_by_tax_payload.append(
                {
                    "fiscalCounterType": c.fiscal_counter_type,
                    "fiscalCounterCurrency": c.fiscal_counter_currency,
                    "fiscalCounterTaxPercent": (
                        float(c.fiscal_counter_tax_percent)
                        if c.fiscal_counter_tax_percent is not None
                        else None
                    ),
                    "fiscalCounterTaxID": c.fiscal_counter_tax_id,
                    "fiscalCounterValue": float(round(c.fiscal_counter_value, 2)),
                }
            )

        return "".join("".join(buckets[k]) for k in DEBIT_TAX_BY_TAX_ORDER)

    def close_day(self) -> Dict[str, Any]:
        self._reconcile_with_fdms()

        if (
            not self.fiscal_day.is_open
            and self.fiscal_day.close_state == FiscalDay.CloseState.CLOSED
        ):
            return {
                "fiscalDayStatus": self.fiscal_day.fdms_status or "FiscalDayClosed",
                "message": "Fiscal day already closed in FDMS",
            }

        sale_by_tax: str = self.build_sale_by_tax()
        sale_tax_by_tax: str = self.build_sale_tax_by_tax()
        credit_by_tax: str = self.build_credit_note_by_tax()
        credit_tax_by_tax: str = self.build_credit_note_tax_by_tax()
        debit_by_tax: str = self.build_debit_note_by_tax()
        debit_tax_by_tax: str = self.build_debit_note_tax_by_tax()
        balance_by_money: str = self.build_balance_by_money_type()

        closing_string: str = (
            f"{self.device.device_id}"
            f"{self.fiscal_day.day_no}"
            f"{self.fiscal_day.created_at.strftime('%Y-%m-%d')}"
            f"{sale_by_tax}"
            f"{sale_tax_by_tax}"
            f"{credit_by_tax}"
            f"{credit_tax_by_tax}"
            f"{debit_by_tax}"
            f"{debit_tax_by_tax}"
            f"{balance_by_money}"
        ).upper()

        logger.info(f"Closing string: {closing_string}")

        signature = self.receipt_handler.crypto.generate_receipt_hash_and_signature(closing_string)

        payload_counters = (
            self.sale_by_tax_payload
            + self.sale_tax_by_tax_payload
            + self.credit_by_tax_payload
            + self.credit_tax_by_tax_payload
            + self.debit_by_tax_payload
            + self.debit_tax_by_tax_payload
            + self.balance_by_money_payload
        )

        payload: Dict[str, Any] = {
            "deviceID": self.device.device_id,
            "fiscalDayNo": self.fiscal_day.day_no,
            "fiscalDayDate": self.fiscal_day.created_at.strftime("%Y-%m-%d"),
            "fiscalDayCounters": payload_counters,
            "fiscalDayDeviceSignature": signature,
            "receiptCounter": self.fiscal_day.receipt_counter,
        }

        logger.info(payload)
        self.client.close_day(payload)
        self._mark_close_requested()

        sleep(10)

        status = self.client.get_status()
        StatusService.reconcile_fiscal_day(self.device, status)
        self.fiscal_day.refresh_from_db()

        if not status:
            raise CloseDayError("FDMS returned an empty response")

        fiscal_day_status = status.get("fiscalDayStatus", "")

        if fiscal_day_status in {"FiscalDayClosed", "FiscalDayCloseExecuted"}:
            return status

        if fiscal_day_status == "FiscalDayCloseFailed":
            error_code = status.get("fiscalDayClosingErrorCode", "unknown")
            raise CloseDayError(f"FDMS rejected the close day request (errorCode={error_code})")

        if fiscal_day_status == "FiscalDayCloseInitiated":
            return {
                **status,
                "message": "Close request accepted by FDMS and is still processing",
            }

        logger.warning(f"Unexpected fiscalDayStatus from FDMS: {status}")
        raise CloseDayError(f"Unexpected FDMS status: {fiscal_day_status!r}")

    def _mark_close_requested(self) -> None:
        self.fiscal_day.close_state = FiscalDay.CloseState.CLOSE_PENDING
        self.fiscal_day.close_requested_at = timezone.now()
        self.fiscal_day.last_close_error_code = None
        self.fiscal_day.save(
            update_fields=[
                "close_state",
                "close_requested_at",
                "last_close_error_code",
                "updated_at",
            ]
        )

    def _reconcile_with_fdms(self) -> None:
        status = self.client.get_status()
        StatusService.reconcile_fiscal_day(self.device, status)
        self.fiscal_day.refresh_from_db()
