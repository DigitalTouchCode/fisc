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

from fiscguy.utils.datetime_now import datetime_now_isoformat as timestamp

from .models import FiscalCounter, FiscalDay, Receipt
from .zimra_base import ZIMRA
from .zimra_crypto import ZIMRACrypto


class ZIMRAReceiptHandler(ZIMRA):
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
        self.crypto = ZIMRACrypto()
        logger.info("ZIMRAReceiptHandler initialized")

    def _get_receipt_global_number(self):
        """
        Fetch the last receiptGlobalNo from Receipts.

        Returns:
            int: new global receipt number, or 0 if no receipts exist
        """
        last_receipt = Receipt.objects.order_by("-id").first()
        last_global_no = last_receipt.global_no if last_receipt else 0
        new_global_no = int(last_global_no) + 1

        return new_global_no

    def generate_receipt_data(self, receipt, receipt_items, request):
        """
        Transform invoice data to ZIMRA receipt format.

        Args:
            invoice: Receipt object
            invoice_items: QuerySet of ReceiptLine objects
            request: Django request object

        Returns:
            tuple: (signature_string, receipt_data) or (error_message, None)
        """
        try:

            # Get fiscal day
            fiscal_day = FiscalDay.objects.filter(is_open=True).first()

            # check if fiscal day is open
            if not fiscal_day:
                return {"message: no fiscal day open"}

            # Build receipt lines and calculate taxes
            receipt_lines = []
            tax_group_totals = defaultdict(
                lambda: {"taxAmount": 0.00, "salesAmountWithTax": 0.00}
            )

            for index, item in enumerate(receipt_items, start=1):
                line_total = float(item.unit_price) * item.quantity

                # Determine tax details
                tax_id = item.tax_type.tax_id
                tax_percent = float(item.item.tax_type.tax_percent)
                tax_code = item.item.tax_type.code
                tax_name = item.item.tax_type.name.lower()

                logger.info(
                    f"Tax ID: {tax_id}, Tax Percent: {tax_percent}, Tax Code: {tax_code}"
                )

                # Calculate tax amount
                if tax_name == "exempt" or tax_name == "zero-rated":
                    tax_amount = 0.00

                elif item.tax_type.name.lower() == "standard 15%":
                    tax_amount = line_total * (tax_percent / (100 + tax_percent))

                # Accumulate tax group totals
                key = (tax_id, tax_percent, tax_code, tax_name)
                tax_group_totals[key]["taxAmount"] += tax_amount
                tax_group_totals[key]["salesAmountWithTax"] += line_total

                logger.info(f"Tax Group Totals: {tax_group_totals}")

                # Build receipt line
                line_data = {
                    "receiptLineType": "Sale",
                    "receiptLineNo": index,
                    "receiptLineHSCode": "01010101",
                    "receiptLineName": item.item.name,
                    "receiptLinePrice": float(item.unit_price),
                    "receiptLineQuantity": item.quantity,
                    "receiptLineTotal": line_total,
                    "taxID": tax_id,
                    "taxCode": tax_code,
                }

                if tax_percent is not None:
                    line_data["taxPercent"] = float(tax_percent)

                receipt_lines.append(line_data)

            # Construct receiptTaxes from actual usage
            receipt_taxes = []
            for (
                tax_id,
                tax_percent,
                tax_code,
                tax_name,
            ), totals in tax_group_totals.items():
                tax_obj = {
                    "taxID": tax_id,
                    "taxCode": tax_code,
                    "taxAmount": round(totals["taxAmount"], 2),
                    "salesAmountWithTax": round(totals["salesAmountWithTax"], 2),
                }

                if tax_name != "exempt":
                    tax_obj["taxPercent"] = float(tax_percent)

                receipt_taxes.append(tax_obj)

            logger.info(f"Receipt taxes: {receipt_taxes}")

            # Build complete receipt data
            receipt_data = {
                "receiptType": receipt.receipt_type,
                "receiptCurrency": receipt.currency.name.upper(),
                "receiptCounter": fiscal_day.receipt_count + 1,
                "receiptGlobalNo": self._get_receipt_global_number(),
                "invoiceNo": f"{receipt.receipt_number}",
                "receiptNotes": "Thank you for shopping with us!",
                "receiptDate": timestamp(),
                "receiptLinesTaxInclusive": True,
                "receiptLines": receipt_lines,
                "receiptTaxes": receipt_taxes,
                "receiptPayments": [
                    {
                        "moneyTypeCode": receipt.payment_terms,
                        "paymentAmount": float(receipt.amount),
                    }
                ],
                "receiptTotal": float(receipt.amount),
                "receiptPrintForm": "Receipt48",
                "previousReceiptHash": (
                    "" if fiscal_day.receipt_count == 0 else receipt.hash_value
                ),
            }

            logger.info(f"Receipt data: {receipt_data}")

            # Generate signature string
            signature_string = self.crypto.generate_receipt_signature_string(
                device_id=os.getenv("DEVICE_ID"),
                receipt_type=receipt_data["receiptType"],
                receipt_currency=receipt_data["receiptCurrency"],
                receipt_global_no=receipt_data["receiptGlobalNo"],
                receipt_date=receipt_data["receiptDate"],
                receipt_total=Decimal(str(receipt_data["receiptTotal"])),
                receipt_taxes=receipt_data["receiptTaxes"],
                previous_receipt_hash=receipt_data["previousReceiptHash"],
            )

            logger.info(f"Signature string: {signature_string}")

            return signature_string, receipt_data

        except Exception as e:
            logger.error(f"Error generating receipt data: {e}")
            return f"Error generating receipt: {e}", None

    def submit_receipt(self, request, receipt_data, hash_value, signature):
        """
        Submit receipt to ZIMRA and handle offline storage, QR code generation, and fiscal counters.

        Args:
            request: Django request object
            receipt_data (dict): Receipt data
            hash_value (str): Receipt hash
            signature (str): Receipt signature
            invoice_id (int): Invoice ID

        Returns:
            dict: Response from ZIMRA
        """
        try:
            # Submit to ZIMRA
            response = self.submit_receipt(
                {"receipt": receipt_data},
                hash_value,
                signature,
            )

            logger.info(f"Receipt submission response: {response.json()}")

            if response:
                response = response.json()
                receipt_id = response.get("receiptID")

                # Get receipt
                receipt = (
                    Receipt.objects.filter(branch=request.user.branch)
                    .order_by("-id")
                    .first()
                )

                # Update invoice with signature and hash
                receipt.signature = signature
                receipt.hash_value = hash_value

                # create receipt record
                fiscal_day = FiscalDay.objects.filter(is_open=True).first()

                # Generate QR code
                self._generate_qr_code(receipt, receipt_data, signature)

                # Update fiscal day
                if fiscal_day:
                    fiscal_day.receipt_count += 1
                    fiscal_day.save()

                    logger.info("Fiscal day updated.")

                    # Update invoice with fiscal day info
                    receipt.fiscal_day = fiscal_day.day_no
                    receipt.invoice_number = (
                        f"{receipt.branch.name[:3]}-{receipt_data['receiptGlobalNo']}"
                    )

                    if receipt_id:
                        receipt.zimra_inv_id = receipt_id

                    receipt.save()
                    logger.info(f"Invoice saved: {receipt}")

                    # Update fiscal counters
                    self._update_fiscal_counters(receipt_data, receipt, fiscal_day)

            return response

        except Exception as e:
            logger.error(f"Error in submit_receipt_with_storage: {e}")
            return {"error": str(e)}

    def _generate_qr_code(self, invoice, receipt, receipt_data, signature):
        """
        Generate and save QR code for invoice.

        Args:
            receipt: Receipt object
            receipt_data (dict): Receipt data
            signature (str): Receipt signature
        """
        try:

            base_url = ZIMRA.config.url
            device_id = f"00000{ZIMRA.device_id}"
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
                f"qr_{invoice.receipt_number}.png",
                ContentFile(qr_io.getvalue()),
                save=False,
            )

            # save qr code to receipt | more to the customized system
            receipt.qr_code.save(
                f"qr_{invoice.receipt_number}.png",
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

    def _update_fiscal_counters(self, receipt_data, receipt, fiscal_day):
        """
        Update fiscal counters based on receipt data.

        Args:
            receipt_data (dict): Receipt data
            invoice: Invoice object
            fiscal_day: FiscalDay object
        """
        try:
            for tax in receipt_data.get("receiptTaxes", []):
                tax_id = tax["taxID"]
                tax_percent = tax.get("taxPercent")
                tax_amount = tax["taxAmount"]
                sales_amount_with_tax = tax["salesAmountWithTax"]

                logger.info(f"Updating counters - Tax percent: {tax_percent}")

                # SaleByTax counter
                sale_by_tax_counter, created_sbt = FiscalCounter.objects.get_or_create(
                    fiscal_counter_type="SaleByTax",
                    created_at__date=datetime.today(),
                    fiscal_counter_currency=receipt.currency.name.lower(),
                    fiscal_counter_tax_id=tax_id,
                    fiscal_counter_tax_percent=tax_percent,
                    fiscal_counter_money_type=receipt_data["receiptPayments"][0][
                        "moneyTypeCode"
                    ],
                    fiscal_day=fiscal_day,
                    defaults={
                        "fiscal_counter_value": sales_amount_with_tax,
                    },
                )

                if not created_sbt:
                    sale_by_tax_counter.fiscal_counter_value += Decimal(
                        sales_amount_with_tax
                    )
                    sale_by_tax_counter.save()

                # SaleTaxByTax counter (only if tax percent is not 0)
                if tax_percent and tax_percent != 0.00:
                    sale_tax_by_tax_counter, created_stbt = (
                        FiscalCounter.objects.get_or_create(
                            fiscal_counter_type="SaleTaxByTax",
                            created_at__date=datetime.today(),
                            fiscal_counter_currency=receipt.currency.name.lower(),
                            fiscal_counter_tax_id=tax_id,
                            fiscal_counter_tax_percent=tax_percent,
                            fiscal_counter_money_type=None,
                            fiscal_day=fiscal_day,
                            defaults={
                                "fiscal_counter_value": tax_amount,
                            },
                        )
                    )

                    if not created_stbt:
                        sale_tax_by_tax_counter.fiscal_counter_value += Decimal(
                            tax_amount
                        )
                        sale_tax_by_tax_counter.save()

            # Balance By Money Type counter
            fiscal_counter_bal_obj, created_bal = FiscalCounter.objects.get_or_create(
                fiscal_counter_type="Balancebymoneytype",
                created_at__date=datetime.today(),
                fiscal_counter_currency=receipt.currency.name.lower(),
                fiscal_day=fiscal_day,
                defaults={
                    "fiscal_counter_tax_percent": None,
                    "fiscal_counter_tax_id": tax_id,
                    "fiscal_counter_money_type": receipt.payment_terms,
                    "fiscal_counter_value": receipt.amount,
                },
            )

            if not created_bal:
                fiscal_counter_bal_obj.fiscal_counter_value += receipt.amount
                fiscal_counter_bal_obj.save()

        except Exception as e:
            logger.error(f"Error updating fiscal counters: {e}")
            raise
