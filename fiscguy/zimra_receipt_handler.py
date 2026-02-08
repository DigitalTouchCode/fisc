"""
ZIMRA Receipt Handler
Handles receipt generation, signing, and submission to ZIMRA FDMS.
Inherits from base ZIMRA class.
"""

import os
from collections import defaultdict
from datetime import datetime
from decimal import Decimal
from io import BytesIO

import qrcode
from django.core.files.base import ContentFile
from loguru import logger

from fiscguy.models import Certs, Device
from fiscguy.utils.datetime_now import datetime_now as timestamp

from .models import FiscalCounter, FiscalDay, Receipt, Taxes
from .zimra_base import ZIMRAClient
from .zimra_crypto import ZIMRACrypto
from time import sleep


class ZIMRAReceiptHandler:
    """
    Extended ZIMRA class that handles receipt generation, signing, and submission.

    This class inherits from the base ZIMRA class and adds functionality for:
    - Generating receipt data from invoices
    - Signing receipts with device signature
    - Submitting receipts to ZIMRA FDMS
    - Managing offline receipt storage
    - Generating QR codes for receipts
    - Managing fiscal counters
    """

    def __init__(self):
        """Initialize receipt handler with crypto utilities"""
        super().__init__()
        self._device = None
        self._certs = None
        self._client = None
        self.crypto = ZIMRACrypto()
        logger.info("ZIMRAReceiptHandler initialized")

    @property
    def device(self):
        if self._device is None:
            self._device = Device.objects.first()
        return self._device

    @property
    def certs(self):
        if self._certs is None:
            self._certs = Certs.objects.first()
        return self._certs

    @property
    def client(self):
        if self._client is None:
            try:
                self._client = ZIMRAClient(self.device)
            except Exception:
                self._client = None
        return self._client

    def _get_receipt_global_number(self, receipt):
        """
        Fetch the last receiptGlobalNo from Receipts.

        Returns:
            int: new global receipt number, or 0 if no receipts exist
        """
        last_receipt = (
            Receipt.objects.exclude(id=receipt.id).order_by("-created_at").first()
        )
        last_global_no = last_receipt.global_number if last_receipt else 0
        new_global_no = int(last_global_no) + 1
        return new_global_no

    def generate_receipt_data(self, receipt: Receipt, receipt_items: list):
        """
        Transform receipt data to ZIMRA receipt format.
        Supports FiscalInvoice and CreditNote.

        Args:
            receipt: Receipt object
            receipt_items: QuerySet of ReceiptLine objects

        Returns:
            receipt_string, receipt_data or (error_message, None)
        """
        try:
            is_credit_note = receipt.receipt_type.lower() == "creditnote"

            # Get last receipt (for previousReceiptHash)
            last_receipt = (
                Receipt.objects.exclude(id=receipt.id)
                .exclude(hash_value__isnull=True)
                .order_by("-created_at")
                .first()
            )

            # Fiscal day - auto-open if straight sell
            fiscal_day = FiscalDay.objects.filter(is_open=True).first()
            if not fiscal_day:
                logger.info("No fiscal day open, auto-opening a new fiscal day")
                try:
                    open_day_result = self.client.open_day() if self.client else None
                    if not open_day_result or open_day_result.get("error"):
                        return {"error": "Failed to auto-open fiscal day"}
                    fiscal_day = FiscalDay.objects.filter(is_open=True).first()
                    if not fiscal_day:
                        return {"error": "No fiscal day open"}
                except Exception as e:
                    logger.error(f"Error auto-opening fiscal day: {e}")
                    return {"error": f"Failed to auto-open fiscal day: {str(e)}"}
                
            sleep(5) 

            # Containers
            receipt_lines = []
            tax_group_totals = defaultdict(
                lambda: {
                    "taxAmount": float("0.00"),
                    "salesAmountWithTax": float("0.00"),
                }
            )

            # Build receipt lines
            for index, item in enumerate(receipt_items, start=1):

                unit_price = item.unit_price

                quantity = item.quantity
                line_total = unit_price * quantity

                tax_id = item.tax_type.tax_id
                tax_percent = item.tax_type.percent
                tax_name = item.tax_type.name.lower()

                # Tax calculation
                if tax_name in ["exempt", "zero rated 0%"]:
                    tax_amount = float("0.00")
                else:
                    tax_amount = line_total * (
                        tax_percent / (float("100.00") + tax_percent)
                    )

                logger.info(
                    f"Line {index} | Price: {unit_price} | Total: {line_total} | Tax: {tax_amount}"
                )

                # Accumulate tax totals
                key = (tax_id, tax_percent, tax_name)
                tax_group_totals[key]["taxAmount"] += tax_amount
                tax_group_totals[key]["salesAmountWithTax"] += line_total

                # Receipt line
                line_data = {
                    "receiptLineType": "Sale",
                    "receiptLineNo": index,
                    "receiptLineHSCode": "01010101",
                    "receiptLineName": item.product,
                    "receiptLinePrice": float(unit_price),
                    "receiptLineQuantity": float(quantity),
                    "receiptLineTotal": float(line_total),
                    "taxID": tax_id,
                }

                if tax_name != "exempt":
                    line_data["taxPercent"] = float(tax_percent)

                receipt_lines.append(line_data)

            # Build receiptTaxes
            receipt_taxes = []
            for (tax_id, tax_percent, tax_name), totals in tax_group_totals.items():
                tax_obj = {
                    "taxID": tax_id,
                    "taxAmount": round(totals["taxAmount"], 2),
                    "salesAmountWithTax": round(totals["salesAmountWithTax"], 2),
                }

                if tax_name != "exempt":
                    tax_obj["taxPercent"] = float(tax_percent)

                receipt_taxes.append(tax_obj)

            # Receipt totals
            receipt_total = receipt.total_amount

            # Base receipt payload
            receipt_data = {
                "receiptType": receipt.receipt_type,
                "receiptCurrency": receipt.currency.upper(),
                "receiptCounter": fiscal_day.receipt_counter + 1,
                "receiptGlobalNo": self._get_receipt_global_number(receipt),
                "invoiceNo": receipt.receipt_number,
                "receiptNotes": (
                    receipt.credit_note_reason
                    if is_credit_note
                    else "Thank you for shopping with us!"
                ),
                "receiptDate": timestamp(),
                "receiptLinesTaxInclusive": True,
                "receiptLines": receipt_lines,
                "receiptTaxes": receipt_taxes,
                "receiptPayments": [
                    {
                        "moneyTypeCode": receipt.payment_terms,
                        "paymentAmount": float(receipt_total),
                    }
                ],
                "receiptTotal": float(receipt_total),
                "receiptPrintForm": "Receipt48",
                "previousReceiptHash": (
                    "" if fiscal_day.receipt_counter == 0 else last_receipt.hash_value
                ),
            }

            # Credit Note
            if is_credit_note:
                original_receipt = Receipt.objects.get(
                    receipt_number=receipt.credit_note_reference
                )

                receipt_data["creditDebitNote"] = {
                    "receiptID": original_receipt.zimra_inv_id
                }

            logger.info(f"Final receipt payload: {receipt_data}")

            # Generate signature string
            signature_string = self.crypto.generate_receipt_signature_string(
                device_id=self.device.device_id,
                receipt_type=receipt_data["receiptType"],
                receipt_currency=receipt_data["receiptCurrency"],
                receipt_global_no=receipt_data["receiptGlobalNo"],
                receipt_date=receipt_data["receiptDate"],
                receipt_total=receipt_data["receiptTotal"],
                receipt_taxes=receipt_data["receiptTaxes"],
                previous_receipt_hash=receipt_data["previousReceiptHash"],
            )

            return {
                "receipt_string": signature_string,
                "receipt_data": receipt_data,
            }

        except Exception as e:
            logger.exception("Error generating receipt data")
            return {"error": str(e)}

    def submit_receipt(self, hash_value, signature, receipt_data):
        """
        Submit receipt to ZIMRA and handle offline storage, QR code generation, and fiscal counters.

        Args:
            hash_value (str): Receipt hash
            signature (str): Receipt signature
            receipt_data (dict): Receipt data

        Returns:
            dict: Response from ZIMRA
        """
        try:
            # Submit to ZIMRA using the ZIMRA client instance.
            if not self.client:
                raise RuntimeError("ZIMRA client not initialised")

            response = self.client.submit_receipt(
                {"receipt": receipt_data}, hash_value, signature
            )

            logger.info(f"Receipt submission response: {response}")

            fiscal_day = FiscalDay.objects.filter(is_open=True).first()
            if fiscal_day:
                fiscal_day.receipt_counter += 1
                fiscal_day.save()

            return response

        except Exception as e:
            logger.error(f"Error in submit_receipt_with_storage: {e}")
            return {"error": str(e)}

    def _generate_qr_code(self, receipt, receipt_data, signature):
        """
        Generate and save QR code for invoice.

        Args:
            receipt: Receipt object
            receipt_data (dict): Receipt data
            signature (str): Receipt signature
        """
        try:

            base_url = (
                f"https://fdmsapi.zimra.co.zw/Device/v1/{self.device.device_id}"
                if self.certs.production
                else f"https://fdmsapitest.zimra.co.zw/Device/v1/{self.device.device_id}"
            )

            device_id = f"00000{self.device.device_id}"
            receipt_date = datetime.strptime(
                receipt_data["receiptDate"], "%Y-%m-%dT%H:%M:%S"
            ).strftime("%d%m%Y")
            receipt_global_no = str(receipt_data["receiptGlobalNo"]).zfill(10)
            receipt_qr_data = self.crypto.generate_verification_code(signature).replace(
                "-", ""
            )

            logger.info(
                f"QR Data: {device_id}, {receipt_date}, {receipt_global_no}, {receipt_qr_data}"
            )

            full_url = f"{base_url}/{device_id}{receipt_date}{receipt_global_no}{receipt_qr_data}"

            # Generate QR code
            qr = qrcode.make(full_url)
            qr_io = BytesIO()
            qr.save(qr_io, format="PNG")
            qr_io.seek(0)

            # Save QR code to invoice
            receipt.qr_code.save(
                f"qr_{receipt.receipt_number}.png",
                ContentFile(qr_io.getvalue()),
                save=False,
            )

            # Generate and save verification code
            code = self.crypto.generate_verification_code(signature)
            receipt.code = code
            receipt.save()

            logger.info(
                f"QR code and verification code saved for invoice {receipt.receipt_number}"
            )

        except Exception as e:
            logger.error(f"Error generating QR code: {e}")
            raise

    def _update_fiscal_counters(self, receipt, receipt_data):
        """
        Update fiscal counters based on receipt data.

        Args:
            receipt: receipt object
            receipt_data (dict): Receipt data
        """
        try:
            fiscal_day = FiscalDay.objects.filter(is_open=True).first()
            tax_id = None
            for tax in receipt_data.get("receiptTaxes", []):
                tax_id = tax["taxID"]
                tax_amount = tax["taxAmount"]
                sales_amount_with_tax = tax["salesAmountWithTax"]

                logger.info(f"Receipt tyepe: {receipt_data['receiptType']}")

                tax_name = Taxes.objects.filter(tax_id=tax_id).first().name.lower()

                # dont assign for no exempt
                tax_percent = (
                    tax.get("taxPercent") if not tax_name == "exempt" else None
                )

                logger.info(f"Updating counters - Tax percent: {tax_percent}")

                if receipt_data["receiptType"].lower() == "fiscalinvoice":
                    # SaleByTax counter
                    sale_by_tax_counter, created_sbt = (
                        FiscalCounter.objects.get_or_create(
                            fiscal_counter_type="SaleByTax",
                            fiscal_counter_currency=receipt.currency.lower(),
                            fiscal_counter_tax_id=tax_id,
                            fiscal_counter_tax_percent=tax_percent,
                            fiscal_counter_money_type=receipt_data["receiptPayments"][
                                0
                            ]["moneyTypeCode"],
                            fiscal_day=fiscal_day,
                            defaults={
                                "fiscal_counter_value": sales_amount_with_tax,
                            },
                        )
                    )

                    if not created_sbt:
                        sale_by_tax_counter.fiscal_counter_value += Decimal(
                            sales_amount_with_tax
                        )
                        sale_by_tax_counter.save()

                    # SaleTaxByTax counter
                    if (
                        tax_percent
                        and tax_name != "exempt"
                        and tax_name != "zero rated 0%"
                    ):
                        sale_tax_by_tax_counter, created_stbt = (
                            FiscalCounter.objects.get_or_create(
                                fiscal_counter_type="SaleTaxByTax",
                                fiscal_counter_currency=receipt.currency.lower(),
                                fiscal_counter_tax_id=tax_id,
                                fiscal_counter_tax_percent=tax_percent,
                                fiscal_counter_money_type=None,
                                fiscal_day=fiscal_day,
                                defaults={
                                    "fiscal_counter_value": tax_amount,
                                },
                            )
                        )

                        if tax_name != "exempt" and tax_name != "zero rated 0%":
                            if not created_stbt:
                                sale_tax_by_tax_counter.fiscal_counter_value += Decimal(
                                    tax_amount
                                )
                                sale_tax_by_tax_counter.save()

                elif receipt_data["receiptType"].lower() == "creditnote":
                    # CreditNoteByTax
                    fiscal_sale_counter_obj, _sbt = FiscalCounter.objects.get_or_create(
                        fiscal_counter_type="CreditNoteByTax",
                        created_at__date=datetime.today(),
                        fiscal_counter_currency=receipt.currency.lower(),
                        fiscal_day=fiscal_day,
                        defaults={
                            "fiscal_counter_tax_percent": tax_percent,
                            "fiscal_counter_tax_id": tax_id,
                            "fiscal_counter_money_type": receipt.payment_terms,
                            "fiscal_counter_value": receipt_data["receiptTotal"],
                        },
                    )

                    if not _sbt:
                        fiscal_sale_counter_obj.fiscal_counter_value += Decimal(
                            receipt_data["receiptTotal"]
                        )
                        fiscal_sale_counter_obj.save()

                    logger.info(
                        f"taxes: {receipt_data['receiptTaxes'][0]['taxAmount']}"
                    )

                    # CreditNoteTaxByTax
                    if (
                        tax_percent
                        and tax_name != "exempt"
                        and tax_name != "zero rated 0%"
                    ):
                        fiscal_counter_obj, _stbt = FiscalCounter.objects.get_or_create(
                            fiscal_counter_type="CreditNoteTaxByTax",
                            created_at__date=datetime.today(),
                            fiscal_counter_currency=receipt.currency.lower(),
                            fiscal_day=fiscal_day,
                            defaults={
                                "fiscal_counter_tax_percent": tax_percent,
                                "fiscal_counter_tax_id": tax_id,
                                "fiscal_counter_money_type": None,
                                "fiscal_counter_value": receipt_data["receiptTaxes"][0][
                                    "taxAmount"
                                ],
                            },
                        )

                        if not _stbt:
                            fiscal_counter_obj.fiscal_counter_value += Decimal(
                                receipt_data["receiptTaxes"][0]["taxAmount"]
                            )
                            fiscal_counter_obj.save()

            # Balance By Money Type counter
            fiscal_counter_bal_obj, created_bal = FiscalCounter.objects.get_or_create(
                fiscal_counter_type="Balancebymoneytype",
                fiscal_counter_currency=receipt.currency.lower(),
                fiscal_day=fiscal_day,
                defaults={
                    "fiscal_counter_tax_percent": None,
                    "fiscal_counter_tax_id": tax_id,
                    "fiscal_counter_money_type": receipt.payment_terms,
                    "fiscal_counter_value": receipt.total_amount,
                },
            )

            if not created_bal:
                fiscal_counter_bal_obj.fiscal_counter_value += Decimal(
                    receipt.total_amount
                )
                fiscal_counter_bal_obj.save()

        except Exception as e:
            logger.error(f"Error updating fiscal counters: {e}")
            raise
