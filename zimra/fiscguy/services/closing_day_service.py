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
    """ Closing day service """

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

    def _collect_buckets(self) -> Dict[str, List[str]]:
        """
        Build string buckets and payloads per fiscal counter type.
        """
        buckets: Dict[str, List[str]] = {
            "salebytax": [],
            "saletaxbytax": [],
            "creditnotebytax": [],
            "creditnotetaxbytax": [],
            "balancebymoneytype": [],
        }

        logger.info(self.counters)

        for c in self.counters:
            c_type = c.fiscal_counter_type.lower()
            logger.info(c_type)
            if c_type not in buckets:
                continue

            # build string item
            if "tax" in c_type:
                tax_part = str(c.fiscal_counter_tax_percent or "")
                value_str = f"{c_type}{c.fiscal_counter_currency}{tax_part}{self._money_value(c.fiscal_counter_value)}"
            else:
                value_str = f"{c_type}{c.fiscal_counter_currency}{c.fiscal_counter_money_type}{self._money_value(c.fiscal_counter_value)}"

            buckets[c_type].append(value_str)

            

            if c_type == "salebytax":
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
            elif c_type == "saletaxbytax":
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
            elif c_type == "creditnotebytax":
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
            elif c_type == "creditnotetaxbytax":
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
            elif c_type == "balancebymoneytype":
                self.balance_by_money_payload.append(
                    {
                        "fiscalCounterType": c.fiscal_counter_type,
                        "fiscalCounterCurrency": c.fiscal_counter_currency,
                        "fiscalCounterMoneyType": c.fiscal_counter_money_type or 0,
                        "fiscalCounterValue": float(round(c.fiscal_counter_value, 2)),
                    }
                )

        return buckets

    def close_day(self) -> Tuple[str, Dict[str, Any]]:
        # collect all buckets
        buckets = self._collect_buckets()

        # build final string in the exact order
        closing_string = (
            f"{self.device.device_id}" +
            f"{self.fiscal_day.day_no}" f"{self._today()}" +
            "".join(buckets["salebytax"]) +
            "".join(buckets["saletaxbytax"]) +
            "".join(buckets["creditnotebytax"]) +
            "".join(buckets["creditnotetaxbytax"]) +
            "".join(buckets["balancebymoneytype"])
        ).upper()

        signature = self.receipt_handler.crypto.generate_receipt_hash_and_signature(closing_string)

        logger.info(self.sale_tax_by_tax_payload)

        payload_counters = (
            self.sale_by_tax_payload +
            self.sale_tax_by_tax_payload +
            self.credit_by_tax_payload +
            self.credit_tax_by_tax_payload +
            self.balance_by_money_payload
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
