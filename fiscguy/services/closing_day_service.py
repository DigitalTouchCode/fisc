from collections import defaultdict
from typing import Any, Dict, Iterable, List, Tuple
from django.utils.timezone import now
from fiscguy.models import Device, FiscalCounter, FiscalDay
from fiscguy.utils.datetime_now import date_today as today

from loguru import logger

SALE_BY_TAX_ORDER: Tuple[str, ...] = ("exempt", "zero", "standard")
SALE_TAX_BY_TAX_ORDER: Tuple[str, ...] = ("zero", "standard")
CREDIT_BY_TAX_ORDER: Tuple[str, ...] = ("exempt", "zero", "standard")
CREDIT_TAX_BY_TAX_ORDER: Tuple[str, ...] = ("zero", "standard")


class ClosingDayService:
    """Closing day service"""

    def __init__(
        self,
        device: Device,
        fiscal_day: FiscalDay,
        fiscal_counters: Iterable[FiscalCounter],
        tax_map: Dict[int, str],
        receipt_handler: Any,
    ) -> None:
        self.device = device
        self.fiscal_day = fiscal_day
        self.counters = fiscal_counters
        self.tax_map = tax_map
        self.receipt_handler = receipt_handler

        self.sale_by_tax_payload: List[Dict[str, Any]] = []
        self.sale_tax_by_tax_payload: List[Dict[str, Any]] = []
        self.credit_by_tax_payload: List[Dict[str, Any]] = []
        self.credit_tax_by_tax_payload: List[Dict[str, Any]] = []
        self.balance_by_money_payload: List[Dict[str, Any]] = []

    def _today(self) -> str:
        return today()

    def _money_value(self, value: float) -> int:
        return int(value * 100)

    def build_sale_by_tax(self) -> str:
        buckets: Dict[str, List[str]] = defaultdict(list)

        for c in self.counters:
            if c.fiscal_counter_type.lower() != "salebytax":
                continue

            tax_name: str = self.tax_map.get(c.fiscal_counter_tax_id, "").lower()

            if "standard" in tax_name:
                key = "standard"
            elif "zero" in tax_name:
                key = "zero"
            else:
                key = "exempt"

            base: str = c.fiscal_counter_type.lower() + c.fiscal_counter_currency

            tax_part: str = (
                str(c.fiscal_counter_tax_percent)
                if c.fiscal_counter_tax_percent is not None
                else ""
            )

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

        for c in self.counters:

            if c.fiscal_counter_type.lower() != "saletaxbytax":
                continue

            if c.fiscal_counter_type.lower() == "saletaxbytax" and c.fiscal_counter_value == 0:
                continue

            tax_name: str = self.tax_map.get(c.fiscal_counter_tax_id, "").lower()
            key: str = "zero" if "zero" in tax_name else "standard"

            base: str = c.fiscal_counter_type.lower() + c.fiscal_counter_currency

            tax_part: str = (
                str(c.fiscal_counter_tax_percent)
                if c.fiscal_counter_tax_percent is not None
                else ""
            )

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

        for c in self.counters:
            if c.fiscal_counter_type.lower() != "creditnotebytax":
                continue

            tax_name: str = self.tax_map.get(c.fiscal_counter_tax_id, "").lower()

            if "standard" in tax_name:
                key = "standard"
            elif "zero" in tax_name:
                key = "zero"
            else:
                key = "exempt"

            base: str = c.fiscal_counter_type.lower() + c.fiscal_counter_currency

            tax_part: str = (
                str(c.fiscal_counter_tax_percent)
                if c.fiscal_counter_tax_percent is not None
                else ""
            )

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

        for c in self.counters:
            if c.fiscal_counter_type.lower() != "creditnotetaxbytax":
                continue

            if (
                c.fiscal_counter_type.lower() == "creditnotetaxbytax"
                and c.fiscal_counter_value == 0
            ):
                continue

            tax_name: str = self.tax_map.get(c.fiscal_counter_tax_id, "").lower()
            key: str = "zero" if "zero" in tax_name else "standard"

            base: str = c.fiscal_counter_type.lower() + c.fiscal_counter_currency

            tax_part: str = (
                str(c.fiscal_counter_tax_percent)
                if c.fiscal_counter_tax_percent is not None
                else ""
            )

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

        for c in self.counters:

            if c.fiscal_counter_type.lower() != "balancebymoneytype":
                continue

            if (
                c.fiscal_counter_type.lower() == "balancebymoneytype"
                and c.fiscal_counter_value == 0
            ):
                continue

            base: str = c.fiscal_counter_type.lower() + c.fiscal_counter_currency

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

    def close_day(self) -> Tuple[str, Dict[str, Any]]:
        sale_by_tax: str = self.build_sale_by_tax()
        sale_tax_by_tax: str = self.build_sale_tax_by_tax()
        credit_by_tax: str = self.build_credit_note_by_tax()
        credit_tax_by_tax: str = self.build_credit_note_tax_by_tax()
        balance_by_money: str = self.build_balance_by_money_type()

        closing_string: str = (
            f"{self.device.device_id}"
            f"{self.fiscal_day.day_no}"
            f"{self._today()}"
            f"{sale_by_tax}"
            f"{sale_tax_by_tax}"
            f"{credit_by_tax}"
            f"{credit_tax_by_tax}"
            f"{balance_by_money}"
        ).upper()

        signature = self.receipt_handler.crypto.generate_receipt_hash_and_signature(closing_string)

        payload_counters = (
            self.sale_by_tax_payload
            + self.sale_tax_by_tax_payload
            + self.credit_by_tax_payload
            + self.credit_tax_by_tax_payload
            + self.balance_by_money_payload
        )

        payload: Dict[str, Any] = {
            "deviceID": self.device.device_id,
            "fiscalDayNo": self.fiscal_day.day_no,
            "fiscalDayDate": self._today(),
            "fiscalDayCounters": payload_counters,
            "fiscalDayDeviceSignature": signature,
            "receiptCounter": self.fiscal_day.receipt_counter,
        }

        return closing_string, payload
