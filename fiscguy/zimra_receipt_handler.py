from collections import defaultdict
from datetime import datetime, timedelta
from decimal import Decimal
from io import BytesIO
from zoneinfo import ZoneInfo

import qrcode
from django.core.files.base import ContentFile
from django.db import DatabaseError
from django.db.models import F
from django.utils import timezone
from loguru import logger

from fiscguy.exceptions import ReceiptSubmissionError
from fiscguy.models import Device
from fiscguy.utils.datetime_now import datetime_now as timestamp

from .models import FiscalCounter, FiscalDay, Receipt, Taxes
from .zimra_base import ZIMRAClient
from .zimra_crypto import ZIMRACrypto


class ZIMRAReceiptHandler:
    """
    Handles receipt generation, signing, QR code creation, fiscal counter
    updates, and submission to ZIMRA FDMS.
    """

    def __init__(self, device: Device):
        self._device = device
        self._client: ZIMRAClient | None = None
        self.crypto = ZIMRACrypto()

    @property
    def client(self) -> ZIMRAClient | None:
        """
        Return a cached ZIMRA client for the device.
        """
        if self._client is None:
            self._client = ZIMRAClient(self._device)
        return self._client

    @property
    def is_online(self) -> bool:
        return self.client is not None

    def process_and_submit(self, receipt: Receipt) -> dict:
        """
        Full pipeline: generate → hash/sign → QR code → counters → submit.

        This implementation targets the online FDMS `submitReceipt` flow.

        Args:
            receipt: a fully hydrated Receipt instance (select_related buyer,
                     prefetch_related lines already applied by the caller).

        Returns:
            dict `.
            On successful FDMS submission also contains ``"receiptID"``.

        Raises:
            ReceiptSubmissionError: for any unrecoverable processing error.
        """
        fiscal_day = self._ensure_fiscal_day_open()

        receipt_items = receipt.lines.all()

        receipt_data = self._build_receipt_data(receipt, receipt_items, fiscal_day)

        hash_sig = self.crypto.generate_receipt_hash_and_signature(receipt_data["receipt_string"])

        receipt.hash_value = hash_sig["hash"]
        receipt.signature = hash_sig["signature"]
        receipt.global_number = receipt_data["receipt_data"]["receiptGlobalNo"]
        receipt.receipt_number = f"R-{receipt.global_number:08d}"

        self._generate_qr_code(receipt, receipt_data["receipt_data"], hash_sig["signature"])
        self._update_fiscal_counters(receipt, receipt_data["receipt_data"])

        submission_res = self._submit_to_fdms(
            hash_sig["hash"], hash_sig["signature"], receipt_data["receipt_data"]
        )

        receipt.submitted = True
        receipt.zimra_inv_id = submission_res.get("receiptID", "")
        receipt.save()

        return {"submitted": True, "queued": False, **submission_res}

    def _ensure_fiscal_day_open(self) -> FiscalDay:
        """
        Return the currently open fiscal day, auto-opening one if needed.

        Raises:
            ReceiptSubmissionError: if no day can be opened.
        """
        fiscal_day = FiscalDay.objects.filter(device=self._device, is_open=True).first()

        if fiscal_day:
            if fiscal_day.close_state == FiscalDay.CloseState.CLOSE_PENDING:
                raise ReceiptSubmissionError(
                    "Fiscal day close is pending FDMS confirmation; new receipts are blocked"
                )
            return fiscal_day

        logger.info(f"No open fiscal day for device {self._device} — attempting auto-open")

        if not self.is_online:
            raise ReceiptSubmissionError(
                "No open fiscal day and FDMS is unreachable — cannot auto-open"
            )

        from fiscguy.services.open_day_service import OpenDayService

        try:
            OpenDayService(self._device).open_day()
        except Exception as exc:
            raise ReceiptSubmissionError("Failed to auto-open fiscal day") from exc

        fiscal_day = FiscalDay.objects.filter(device=self._device, is_open=True).first()

        if not fiscal_day:
            raise ReceiptSubmissionError("Fiscal day still not open after auto-open attempt")

        return fiscal_day

    def _get_next_global_number(self, receipt: Receipt) -> int:
        """
        Return the next receipt global number.

        Online:  query FDMS for lastReceiptGlobalNo and return +1.
                 Logs a warning if local DB differs.
        Raises:
            ReceiptSubmissionError: on malformed FDMS response or DB error.
        """
        return self._next_global_number_from_fdms(receipt)

    def _next_global_number_from_fdms(self, receipt: Receipt) -> int:
        try:
            res = self.client.get_status()
        except Exception as exc:
            logger.exception(f"Failed to fetch FDMS status for device {self._device}")
            raise ReceiptSubmissionError("Could not retrieve FDMS status") from exc

        raw = res.get("lastReceiptGlobalNo")
        if raw is None:
            raise ReceiptSubmissionError(
                f"FDMS status response missing 'lastReceiptGlobalNo' for device {self._device}"
            )

        try:
            fdms_last = int(raw)
        except (TypeError, ValueError) as exc:
            raise ReceiptSubmissionError(
                f"Invalid 'lastReceiptGlobalNo' from FDMS: {raw!r}"
            ) from exc

        local_last = self._local_last_global_number(receipt)

        if local_last != fdms_last:
            logger.warning(
                f"receiptGlobalNo mismatch for device {self._device}: "
                f"local={local_last}, fdms={fdms_last}. Deferring to FDMS."
            )

        return fdms_last + 1

    def _local_last_global_number(self, receipt: Receipt) -> int:
        try:
            last = (
                Receipt.objects.filter(device=self._device)
                .exclude(id=receipt.id)
                .order_by("-created_at")
                .first()
            )
        except DatabaseError as exc:
            logger.exception(f"Failed to query receipts for device {self._device}")
            raise ReceiptSubmissionError("Failed to get last receipt global number") from exc

        return last.global_number if (last and last.global_number) else 0

    def _build_receipt_data(self, receipt: Receipt, receipt_items, fiscal_day: FiscalDay) -> dict:
        """
        Transform a Receipt into the ZIMRA receipt payload.

        Returns:
            {"receipt_string": str, "receipt_data": dict}

        Raises:
            ReceiptSubmissionError: on any processing failure.
        """
        try:
            return self._build_receipt_data_inner(receipt, receipt_items, fiscal_day)
        except ReceiptSubmissionError:
            raise
        except Exception as exc:
            logger.exception("Unexpected error building receipt data")
            raise ReceiptSubmissionError("Failed to build receipt data") from exc

    def _build_receipt_data_inner(
        self, receipt: Receipt, receipt_items, fiscal_day: FiscalDay
    ) -> dict:
        is_credit_note = receipt.receipt_type.lower() == "creditnote"
        is_debit_note = receipt.receipt_type.lower() == "debitnote"
        fdms_receipt_type = self._fdms_receipt_type(receipt.receipt_type)
        original_receipt = (
            self._get_original_receipt(receipt) if (is_credit_note or is_debit_note) else None
        )

        last_receipt = (
            Receipt.objects.filter(device=self._device)
            .exclude(id=receipt.id)
            .exclude(hash_value__isnull=True)
            .order_by("-created_at")
            .first()
        )

        receipt_lines = []
        tax_group_totals: dict = defaultdict(
            lambda: {"taxAmount": Decimal("0"), "salesAmountWithTax": Decimal("0")}
        )

        for index, item in enumerate(receipt_items, start=1):
            unit_price = Decimal(str(item.unit_price))
            quantity = Decimal(str(item.quantity))
            line_total = unit_price * quantity

            tax_id = item.tax_type.tax_id
            tax_percent = Decimal(str(item.tax_type.percent))
            tax_name = item.tax_type.name.lower()

            if tax_name in ("exempt", "zero rated 0%"):
                tax_amount = Decimal("0")
            else:
                tax_amount = line_total * (tax_percent / (Decimal("100") + tax_percent))

            key = (tax_id, tax_percent, tax_name)
            tax_group_totals[key]["taxAmount"] += tax_amount
            tax_group_totals[key]["salesAmountWithTax"] += line_total

            line_data = {
                "receiptLineType": "Sale",
                "receiptLineNo": index,
                "receiptLineHSCode": self._resolve_receipt_line_hs_code(
                    item=item,
                    tax_name=tax_name,
                    is_credit_note=is_credit_note,
                    is_debit_note=is_debit_note,
                    original_receipt=original_receipt,
                ),
                "receiptLineName": item.product,
                "receiptLinePrice": float(unit_price),
                "receiptLineQuantity": float(quantity),
                "receiptLineTotal": float(round(line_total, 2)),
                "taxID": tax_id,
            }
            if tax_name != "exempt":
                line_data["taxPercent"] = float(tax_percent)

            receipt_lines.append(line_data)

        receipt_taxes = []
        signature_taxes = []
        for (tax_id, tax_percent, tax_name), totals in tax_group_totals.items():
            rounded_tax_amount = round(totals["taxAmount"], 2)
            rounded_sales_amount = round(totals["salesAmountWithTax"], 2)
            tax_obj = {
                "taxID": tax_id,
                "taxAmount": float(rounded_tax_amount),
                "salesAmountWithTax": float(rounded_sales_amount),
            }
            signature_tax_obj = {
                "taxID": tax_id,
                "taxAmount": rounded_tax_amount,
                "salesAmountWithTax": rounded_sales_amount,
            }
            if tax_name != "exempt":
                tax_obj["taxPercent"] = float(tax_percent)
                signature_tax_obj["taxPercent"] = tax_percent
            receipt_taxes.append(tax_obj)
            signature_taxes.append(signature_tax_obj)

        # Resolve global number once and reuse
        global_no = self._get_next_global_number(receipt)

        receipt_data = {
            "receiptType": fdms_receipt_type,
            "receiptCurrency": receipt.currency.upper(),
            "receiptCounter": fiscal_day.receipt_counter + 1,
            "receiptGlobalNo": global_no,
            "invoiceNo": f"R-{global_no:08d}",
            "receiptNotes": (
                receipt.credit_note_reason
                if (is_credit_note or is_debit_note)
                else "Thank you for shopping with us!"
            ),
            "receiptDate": self._build_receipt_timestamp(fiscal_day, last_receipt),
            "receiptLinesTaxInclusive": True,
            "receiptLines": receipt_lines,
            "receiptTaxes": receipt_taxes,
            "receiptPayments": [
                {
                    "moneyTypeCode": receipt.payment_terms,
                    "paymentAmount": float(receipt.total_amount),
                }
            ],
            "receiptTotal": float(receipt.total_amount),
            "receiptPrintForm": "Receipt48",
            "previousReceiptHash": (
                ""
                if fiscal_day.receipt_counter == 0 or not last_receipt
                else last_receipt.hash_value
            ),
        }

        if original_receipt:
            receipt_data["creditDebitNote"] = {"receiptID": original_receipt.zimra_inv_id}

        if receipt.buyer:
            receipt_data["buyerData"] = {
                "buyerRegisterName": receipt.buyer.name,
                "buyerTIN": receipt.buyer.tin_number,
            }

        signature_string = self.crypto.generate_receipt_signature_string(
            device_id=self._device.device_id,
            receipt_type=receipt_data["receiptType"],
            receipt_currency=receipt_data["receiptCurrency"],
            receipt_global_no=receipt_data["receiptGlobalNo"],
            receipt_date=receipt_data["receiptDate"],
            receipt_total=receipt.total_amount,
            receipt_taxes=signature_taxes,
            previous_receipt_hash=receipt_data["previousReceiptHash"],
        )

        return {"receipt_string": signature_string, "receipt_data": receipt_data}

    def _get_original_receipt(self, receipt: Receipt) -> Receipt:
        try:
            return Receipt.objects.get(receipt_number=receipt.credit_note_reference)
        except Receipt.DoesNotExist as exc:
            note_kind = "Credit" if receipt.receipt_type.lower() == "creditnote" else "Debit"
            raise ReceiptSubmissionError(
                f"{note_kind} note references unknown receipt: {receipt.credit_note_reference}"
            ) from exc

    def _resolve_receipt_line_hs_code(
        self,
        item,
        tax_name: str,
        is_credit_note: bool,
        is_debit_note: bool,
        original_receipt: Receipt | None,
    ) -> str:
        if item.hs_code:
            return item.hs_code

        if (is_credit_note or is_debit_note) and original_receipt:
            inherited_hs_code = self._inherit_original_hs_code(original_receipt, item.product)
            if inherited_hs_code:
                return inherited_hs_code
            if is_debit_note:
                return self._service_hs_code_for_tax_name(tax_name)

        return "01010101"

    @staticmethod
    def _inherit_original_hs_code(original_receipt: Receipt, product_name: str) -> str:
        original_line = (
            original_receipt.lines.filter(product__iexact=product_name.strip())
            .exclude(hs_code="")
            .first()
        )
        return original_line.hs_code if original_line else ""

    @staticmethod
    def _service_hs_code_for_tax_name(tax_name: str) -> str:
        if "exempt" in tax_name:
            return "99003000"
        if "zero" in tax_name:
            return "99002000"
        return "99001000"

    def _submit_to_fdms(self, hash_value: str, signature: str, receipt_data: dict) -> dict:
        """
        Submit a receipt to ZIMRA FDMS and increment the fiscal day counter.

        Raises:
            ReceiptSubmissionError: if the request fails.
        """
        try:
            response = self.client.submit_receipt({"receipt": receipt_data}, hash_value, signature)
        except Exception as exc:
            logger.exception(f"FDMS submission failed for device {self._device}")
            raise ReceiptSubmissionError("FDMS receipt submission failed") from exc

        logger.info(f"FDMS submission response for device {self._device}: {response}")

        try:
            fiscal_day = FiscalDay.objects.filter(device=self._device, is_open=True).first()
            if fiscal_day:
                fiscal_day.receipt_counter += 1
                fiscal_day.save()
        except DatabaseError:
            # Counter mismatch is recoverable — log and continue
            logger.exception(f"Failed to increment receipt counter for device {self._device}")

        return response

    def _build_receipt_timestamp(self, fiscal_day: FiscalDay, last_receipt: Receipt | None) -> str:
        """
        Build a receipt timestamp that is strictly later than:
        - the fiscal day open time for the first receipt
        - the previous receipt timestamp for subsequent receipts
        """
        receipt_dt = self._current_harare_datetime()

        fiscal_day_dt = self._to_harare_datetime(fiscal_day.created_at) + timedelta(seconds=1)
        if receipt_dt < fiscal_day_dt:
            receipt_dt = fiscal_day_dt

        if last_receipt:
            previous_receipt_dt = self._to_harare_datetime(last_receipt.created_at) + timedelta(
                seconds=1
            )
            if receipt_dt < previous_receipt_dt:
                receipt_dt = previous_receipt_dt

        return receipt_dt.strftime("%Y-%m-%dT%H:%M:%S")

    def _generate_qr_code(self, receipt: Receipt, receipt_data: dict, signature: str) -> None:
        """
        Generate and save the QR code and verification code to the receipt.

        Raises:
            ReceiptSubmissionError: if QR generation fails.
        """
        try:
            config = self.client.config
            base = (config.url or "").rstrip("/") if config and config.url else ""
            if not base:
                base = (
                    f"https://fdmsapi.zimra.co.zw/Device/v1/{self._device.device_id}"
                    if self._device.production
                    else f"https://fdmsapitest.zimra.co.zw/Device/v1/{self._device.device_id}"
                )

            device_id = f"00000{self._device.device_id}"
            receipt_date = datetime.strptime(
                receipt_data["receiptDate"], "%Y-%m-%dT%H:%M:%S"
            ).strftime("%d%m%Y")
            receipt_global_no = str(receipt_data["receiptGlobalNo"]).zfill(10)
            verification_code = self.crypto.generate_verification_code(signature)
            qr_data = verification_code.replace("-", "")

            full_url = f"{base}/{device_id}{receipt_date}{receipt_global_no}{qr_data}"

            qr = qrcode.make(full_url)
            qr_io = BytesIO()
            qr.save(qr_io, format="PNG")
            qr_io.seek(0)

            receipt.qr_code.save(
                f"qr_{receipt.receipt_number}.png",
                ContentFile(qr_io.getvalue()),
                save=False,
            )
            receipt.code = verification_code
            receipt.save()

            logger.info(
                f"QR code saved for receipt {receipt.receipt_number} " f"(device {self._device})"
            )

        except Exception as exc:
            logger.exception(f"QR code generation failed for receipt {receipt.receipt_number}")
            raise ReceiptSubmissionError("Failed to generate QR code") from exc

    def _update_fiscal_counters(self, receipt: Receipt, receipt_data: dict) -> None:
        """
        Update FiscalCounter rows for SaleByTax, SaleTaxByTax,
        CreditNoteByTax, CreditNoteTaxByTax, and BalanceByMoneyType.

        Raises:
            ReceiptSubmissionError: if any DB operation fails.
        """
        try:
            self._update_fiscal_counters_inner(receipt, receipt_data)
        except ReceiptSubmissionError:
            raise
        except Exception as exc:
            logger.exception(f"Unexpected error updating fiscal counters for device {self._device}")
            raise ReceiptSubmissionError("Failed to update fiscal counters") from exc

    def _update_fiscal_counters_inner(self, receipt: Receipt, receipt_data: dict) -> None:
        fiscal_day = FiscalDay.objects.filter(device=self._device, is_open=True).first()

        receipt_type = receipt_data["receiptType"].lower()
        receipt_taxes = receipt_data.get("receiptTaxes", [])

        for tax in receipt_taxes:
            tax_id = tax["taxID"]
            tax_amount = Decimal(str(tax["taxAmount"]))
            sales_amount_with_tax = Decimal(str(tax["salesAmountWithTax"]))  # per-group amount

            tax_obj = Taxes.objects.filter(device=self._device, tax_id=tax_id).first()
            tax_name = tax_obj.name.lower() if tax_obj else ""
            tax_percent = Decimal(str(tax["taxPercent"])) if tax_name not in ("exempt",) else None

            if receipt_type == "fiscalinvoice":
                self._upsert_counter(
                    counter_type="SaleByTax",
                    currency=receipt.currency.upper(),
                    tax_id=tax_id,
                    tax_percent=tax_percent,
                    fiscal_day=fiscal_day,
                    amount=sales_amount_with_tax,
                )

                if tax_percent and tax_name not in ("exempt", "zero rated 0%"):
                    self._upsert_counter(
                        counter_type="SaleTaxByTax",
                        currency=receipt.currency.upper(),
                        tax_id=tax_id,
                        tax_percent=tax_percent,
                        fiscal_day=fiscal_day,
                        amount=tax_amount,
                    )

            elif receipt_type == "creditnote":
                self._upsert_counter(
                    counter_type="CreditNoteByTax",
                    currency=receipt.currency.upper(),
                    tax_id=tax_id,
                    tax_percent=tax_percent,
                    fiscal_day=fiscal_day,
                    amount=sales_amount_with_tax,
                )

                if tax_percent and tax_name not in ("exempt", "zero rated 0%"):
                    self._upsert_counter(
                        counter_type="CreditNoteTaxByTax",
                        currency=receipt.currency.upper(),
                        tax_id=tax_id,
                        tax_percent=tax_percent,
                        fiscal_day=fiscal_day,
                        amount=tax_amount,
                    )

            elif receipt_type == "debitnote":
                self._upsert_counter(
                    counter_type="DebitNoteByTax",
                    currency=receipt.currency.upper(),
                    tax_id=tax_id,
                    tax_percent=tax_percent,
                    fiscal_day=fiscal_day,
                    amount=sales_amount_with_tax,
                )

                if tax_percent and tax_name not in ("exempt", "zero rated 0%"):
                    self._upsert_counter(
                        counter_type="DebitNoteTaxByTax",
                        currency=receipt.currency.upper(),
                        tax_id=tax_id,
                        tax_percent=tax_percent,
                        fiscal_day=fiscal_day,
                        amount=tax_amount,
                    )

        # BalanceByMoneyType
        balance_amount = (
            Decimal(str(receipt.total_amount))
            if receipt_type == "creditnote"
            else Decimal(str(receipt.total_amount))
        )
        self._upsert_counter(
            counter_type="BalanceByMoneyType",
            currency=receipt.currency.upper(),
            tax_id=None,
            tax_percent=None,
            fiscal_day=fiscal_day,
            amount=balance_amount,
            money_type=receipt.payment_terms,
        )

    def _upsert_counter(
        self,
        counter_type: str,
        currency: str,
        tax_id,
        tax_percent,
        fiscal_day: FiscalDay,
        amount: Decimal,
        money_type: str | None = None,
    ) -> None:
        """
        Get-or-create a FiscalCounter and increment its value.

        Raises:
            ReceiptSubmissionError: on DB failure.
        """
        try:
            counter, created = FiscalCounter.objects.get_or_create(
                device=self._device,
                fiscal_counter_type=counter_type,
                fiscal_counter_currency=currency,
                fiscal_counter_tax_id=tax_id,
                fiscal_counter_tax_percent=tax_percent,
                fiscal_counter_money_type=money_type,
                fiscal_day=fiscal_day,
                defaults={"fiscal_counter_value": amount},
            )
            if not created:
                FiscalCounter.objects.filter(pk=counter.pk).update(
                    fiscal_counter_value=F("fiscal_counter_value") + amount
                )
        except DatabaseError as exc:
            logger.exception(f"Failed to upsert {counter_type} counter for device {self._device}")
            raise ReceiptSubmissionError(f"Failed to update {counter_type} fiscal counter") from exc

    @staticmethod
    def _fdms_receipt_type(receipt_type: str) -> str:
        mapping = {
            "fiscalinvoice": "FiscalInvoice",
            "creditnote": "CreditNote",
            "debitnote": "DebitNote",
        }
        return mapping.get(receipt_type.lower(), receipt_type)

    @staticmethod
    def _current_harare_datetime() -> datetime:
        return datetime.now(ZoneInfo("Africa/Harare")).replace(microsecond=0)

    @staticmethod
    def _to_harare_datetime(value: datetime) -> datetime:
        if timezone.is_aware(value):
            return timezone.localtime(value, ZoneInfo("Africa/Harare")).replace(microsecond=0)
        return value.replace(microsecond=0)
