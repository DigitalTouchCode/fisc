"""
ZIMRA Receipt Handler
Handles receipt generation, signing, and submission to ZIMRA FDMS.
Inherits from base ZIMRA class.
"""
import os
import qrcode
from io import BytesIO
from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime
from collections import defaultdict
from loguru import logger
from django.utils.timezone import now
from django.core.files.base import ContentFile

from .base import ZIMRA
from .crypto_utils import ZIMRACrypto
from apps.zimra.models import FiscalDay, FiscalCounter
from apps.finance.models import Invoice
from apps.settings.models import OfflineReceipt

from apps.zimra.models import Receipt

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
    
    def get_last_receipt_number(self):
        """
        Fetch the last receiptGlobalNo from offline receipts.
        
        Returns:
            int: Last global receipt number, or 0 if no receipts exist
        """
        last_receipt = OfflineReceipt.objects.order_by("-id").first()
        
        logger.info(f'Last receipt: {last_receipt}')

        last_global_no = last_receipt.receipt_data["receiptGlobalNo"] if last_receipt else 0

        logger.info(f'Last receiptGlobalNo: {last_global_no}')

        return last_global_no
    
    def generate_receipt_data(self, invoice, invoice_items, request):
        """
        Transform invoice data to ZIMRA receipt format.
        
        Args:
            invoice: Invoice object
            invoice_items: QuerySet of InvoiceItem objects
            request: Django request object
            
        Returns:
            tuple: (signature_string, receipt_data) or (error_message, None)
        """
        try:
            logger.info(f'Processing Invoice: {invoice.invoice_number}')
            
            # Get fiscal day
            fiscal_day = FiscalDay.objects.filter(is_open=True).first()
            if not fiscal_day:
                raise ValueError("No open fiscal day found")
            
            logger.info(f"Fiscal day {fiscal_day.day_no}")

            # Get previous zimra receipt for hash chaining
            previous_receipt = Receipt.objects.order_by('-id').first()
            
            # Get next receipt number
            last_global_no = previous_receipt.global_no if previous_receipt else 0
            new_receipt_global_no = int(last_global_no) + 1
            logger.info(f'Global number: {new_receipt_global_no}')

            # Build receipt lines and calculate taxes
            receipt_lines = []
            tax_group_totals = defaultdict(lambda: {"taxAmount": 0.00, "salesAmountWithTax": 0.00})
            
            logger.info(f'Previous invoice: {previous_receipt}')

            for index, item in enumerate(invoice_items, start=1):
                line_total = float(item.unit_price) * item.quantity
            
                # Determine tax details
                tax_id = item.item.tax_type.tax_id
                tax_percent = float(item.item.tax_type.tax_percent) if item.item.tax_type.tax_percent else None
                tax_code = item.item.tax_type.code

                logger.info(f'Tax ID: {tax_id}, Tax Percent: {tax_percent}, Tax Code: {tax_code}')

                # Calculate tax amount
                try:
                    if tax_percent:
                        tax_amount = (line_total * (tax_percent / (100 + tax_percent)))
                    else:
                        tax_amount = 0.00
                    logger.info(f'Tax Amount: {tax_amount}')
                except Exception as e:
                    logger.error(f'Error calculating tax amount: {e}')
                    raise

                # Accumulate tax group totals
                key = (tax_id, tax_percent, tax_code)
                tax_group_totals[key]["taxAmount"] += tax_amount
                tax_group_totals[key]["salesAmountWithTax"] += line_total

                logger.info(f'Tax Group Totals: {tax_group_totals}')
                
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
                    "taxCode": tax_code
                }
                
                if tax_percent is not None:
                    line_data["taxPercent"] = float(tax_percent)

                receipt_lines.append(line_data)

            # Construct receiptTaxes from actual usage
            receipt_taxes = []
            for (tax_id, tax_percent, tax_code), totals in tax_group_totals.items():
                tax_obj = {
                    "taxID": tax_id,
                    "taxCode": tax_code,
                    "taxAmount": round(totals["taxAmount"], 2),
                    "salesAmountWithTax": round(totals["salesAmountWithTax"], 2)
                }
                
                if tax_id != 1 and tax_percent is not None:
                    tax_obj["taxPercent"] = float(tax_percent)
                    
                receipt_taxes.append(tax_obj)
                
            logger.info(f"Receipt taxes: {receipt_taxes}")
            logger.info(f"Receipt counter: {fiscal_day.receipt_count + 1}")

            # Build complete receipt data
            receipt_data = {
                "receiptType": "FiscalInvoice",
                "receiptCurrency": invoice.currency.name.upper(),
                "receiptCounter": fiscal_day.receipt_count + 1,
                "receiptGlobalNo": new_receipt_global_no,
                "invoiceNo": f"{invoice.branch.name}{new_receipt_global_no}",
                "receiptNotes": "Thank you for shopping with us!",
                "receiptDate": datetime.now().replace(microsecond=0).isoformat(),
                "receiptLinesTaxInclusive": True,
                "receiptLines": receipt_lines,
                "receiptTaxes": receipt_taxes,
                "receiptPayments": [
                    {
                        "moneyTypeCode": invoice.payment_terms,
                        "paymentAmount": float(invoice.amount)
                    }
                ],
                "receiptTotal": float(invoice.amount),
                "receiptPrintForm": "Receipt48",
                "previousReceiptHash": "" if fiscal_day.receipt_count == 0 else previous_receipt.hash_value
            }

            logger.info(f'Receipt data: {receipt_data}')

            # Generate signature string
            signature_string = self.crypto.generate_receipt_signature_string(
                device_id=os.getenv('DEVICE_ID'),
                receipt_type=receipt_data['receiptType'],
                receipt_currency=receipt_data['receiptCurrency'],
                receipt_global_no=receipt_data['receiptGlobalNo'],
                receipt_date=receipt_data['receiptDate'],
                receipt_total=Decimal(str(receipt_data['receiptTotal'])),
                receipt_taxes=receipt_data['receiptTaxes'],
                previous_receipt_hash=receipt_data['previousReceiptHash']
            )
            
            logger.info(f'Signature string: {signature_string}')

            return signature_string, receipt_data
            
        except Exception as e:
            logger.error(f"Error generating receipt data: {e}")
            return f"Error generating receipt: {e}", None
    
    def submit_receipt_with_storage(self, request, receipt_data, credit_note, hash_value, signature, invoice_id):
        """
        Submit receipt to ZIMRA and handle offline storage, QR code generation, and fiscal counters.
        
        Args:
            request: Django request object
            receipt_data (dict): Receipt data
            credit_note (dict): Credit note data
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
                {"receipt": credit_note}, 
                hash_value, 
                signature
            )
            logger.info(f"Receipt submission response: {response.json()}")

            response = response.json()

            receipt_id = response.get('receiptID')
            logger.info(f'ZIMRA receipt ID: {receipt_id}')

            if response:
                # Get invoice
                invoice = Invoice.objects.filter(
                    branch=request.user.branch
                ).order_by('-id').first()

                if not invoice:
                    logger.error("Invoice not found")
                    return response

                # Update invoice with signature and hash
                invoice.receiptServerSignature = signature
                invoice.receipt_hash = hash_value

                # create receipt record
                fiscal_day = FiscalDay.objects.filter(is_open=True).first()
                receipt = self._create_receipt_record(
                    receipt_data, 
                    hash_value, 
                    signature, 
                    fiscal_day,
                    receipt_id
                )

                # Generate QR code
                self._generate_qr_code(invoice, receipt, receipt_data, signature)
                
                # Update fiscal day
                if fiscal_day:
                    fiscal_day.receipt_count += 1
                    fiscal_day.global_count += 1
                    fiscal_day.total_sales += invoice.amount
                    fiscal_day.save()
                    logger.info('Fiscal day updated.')
                    
                    # Update invoice with fiscal day info
                    invoice.fiscal_day = fiscal_day.day_no
                    invoice.invoice_number = f"{invoice.branch.name[:3]}-{receipt_data['receiptGlobalNo']}"
                    
                    if receipt_id:
                        invoice.zimra_inv_id = receipt_id
                    
                    invoice.save()
                    logger.info(f'Invoice saved: {invoice}')
                    
                    # Update fiscal counters
                    self._update_fiscal_counters(receipt_data, invoice, fiscal_day)

            return response
            
        except Exception as e:
            logger.error(f"Error in submit_receipt_with_storage: {e}")
            return {"error": str(e)}
    
    def _generate_qr_code(self, invoice, receipt, receipt_data, signature):
        """
        Generate and save QR code for invoice.
        
        Args:
            invoice: Invoice object
            receipt_data (dict): Receipt data
            signature (str): Receipt signature
        """
        try:
            base_url = "https://fdmstest.zimra.co.zw"
            
            device_id = f'00000{os.getenv("DEVICE_ID")}'
            receipt_date = datetime.strptime(
                receipt_data['receiptDate'], 
                "%Y-%m-%dT%H:%M:%S"
            ).strftime('%d%m%Y')
            receipt_global_no = str(receipt_data['receiptGlobalNo']).zfill(10)
            receipt_qr_data = self.crypto.generate_verification_code(signature).replace('-', '')
            
            logger.info(f'QR Data: {device_id}, {receipt_date}, {receipt_global_no}, {receipt_qr_data}')

            full_url = f"{base_url}/{device_id}{receipt_date}{receipt_global_no}{receipt_qr_data}"

            # Generate QR code
            qr = qrcode.make(full_url)
            qr_io = BytesIO()
            qr.save(qr_io, format='PNG')
            qr_io.seek(0)
            
            # Save QR code to invoice
            invoice.qr_code.save(
                f"qr_{invoice.invoice_number}.png", 
                ContentFile(qr_io.getvalue()), 
                save=False
            )

            # save qr code to receipt | more to the customized system
            receipt.qr_code.save(
                f"qr_{invoice.invoice_number}.png", 
                ContentFile(qr_io.getvalue()), 
                save=False
            )
            
            # Generate and save verification code
            code = self.crypto.generate_verification_code(signature)
            invoice.code = code
            receipt.code = code
            receipt.save()
            invoice.save()
            
            logger.info(f"QR code and verification code saved for invoice {invoice.invoice_number}")
            
        except Exception as e:
            logger.error(f"Error generating QR code: {e}")
            raise
    
    def _update_fiscal_counters(self, receipt_data, invoice, fiscal_day):
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

                logger.info(f'Updating counters - Tax percent: {tax_percent}')
                
                # SaleByTax counter
                sale_by_tax_counter, created_sbt = FiscalCounter.objects.get_or_create(
                    fiscal_counter_type='SaleByTax',
                    created_at__date=datetime.today(),
                    fiscal_counter_currency=invoice.currency.name.lower(),
                    fiscal_counter_tax_id=tax_id,
                    fiscal_counter_tax_percent=tax_percent,
                    fiscal_counter_money_type=receipt_data['receiptPayments'][0]['moneyTypeCode'],
                    fiscal_day=fiscal_day,
                    defaults={
                        "fiscal_counter_value": sales_amount_with_tax,
                    }
                )
                
                if not created_sbt:
                    sale_by_tax_counter.fiscal_counter_value += Decimal(sales_amount_with_tax)
                    sale_by_tax_counter.save()
                    logger.info(f'Updated SaleByTax counter: {sale_by_tax_counter}')

                # SaleTaxByTax counter (only if tax percent is not 0)
                if tax_percent and tax_percent != 0.00:
                    sale_tax_by_tax_counter, created_stbt = FiscalCounter.objects.get_or_create(
                        fiscal_counter_type='SaleTaxByTax',
                        created_at__date=datetime.today(),
                        fiscal_counter_currency=invoice.currency.name.lower(),
                        fiscal_counter_tax_id=tax_id,
                        fiscal_counter_tax_percent=tax_percent,
                        fiscal_counter_money_type=None,
                        fiscal_day=fiscal_day,
                        defaults={
                            "fiscal_counter_value": tax_amount,
                        }
                    )
                    
                    if not created_stbt:
                        sale_tax_by_tax_counter.fiscal_counter_value += Decimal(tax_amount)
                        sale_tax_by_tax_counter.save()
                        logger.info(f'Updated SaleTaxByTax counter: {sale_tax_by_tax_counter}')
            
            # Balance By Money Type counter
            fiscal_counter_bal_obj, created_bal = FiscalCounter.objects.get_or_create(
                fiscal_counter_type="Balancebymoneytype",
                created_at__date=datetime.today(),
                fiscal_counter_currency=invoice.currency.name.lower(),
                fiscal_day=fiscal_day,
                defaults={
                    "fiscal_counter_tax_percent": None,
                    "fiscal_counter_tax_id": 1,
                    "fiscal_counter_money_type": invoice.payment_terms,
                    "fiscal_counter_value": invoice.amount,
                }
            )

            if not created_bal:
                fiscal_counter_bal_obj.fiscal_counter_value += invoice.amount
                fiscal_counter_bal_obj.save()
                logger.info(f'Updated Balance counter: {fiscal_counter_bal_obj}')
                
        except Exception as e:
            logger.error(f"Error updating fiscal counters: {e}")
            raise

    def _create_receipt_record(self, receipt_data, hash_value, signature, fiscal_day, receipt_id):
        """
        Create and save Receipt record in the database.
        
        Args:
            receipt_data (dict): Receipt data
            hash_value (str): Receipt hash
            signature (str): Receipt signature
            fiscal_day: FiscalDay object
            
        Returns:
            Receipt: Created Receipt object
        """
        try:
            receipt = Receipt(
                receipt_type=receipt_data['receiptType'],
                receipt_currency=receipt_data['receiptCurrency'],
                receipt_date=datetime.fromisoformat(receipt_data['receiptDate']).date(),
                receipt_number=receipt_data['invoiceNo'],
                receipt_id=receipt_id, 
                code="",
                global_no=receipt_data['receiptGlobalNo'],
                hash_value=hash_value,
                signature_value=signature,
                fiscal_day=fiscal_day
            )
            receipt.save()
            logger.info(f'Receipt record created: {receipt}')
            return receipt
        except Exception as e:
            logger.error(f"Error creating receipt record: {e}")
            raise
