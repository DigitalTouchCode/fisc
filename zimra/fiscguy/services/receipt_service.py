from typing import Tuple, Dict, Any
from django.db import transaction
from loguru import logger

class ReceiptService:
    """
    Service to handle creation and submission of receipts.
    """

    def __init__(self, receipt_handler: Any):
        self.receipt_handler = receipt_handler

    @transaction.atomic
    def create_and_submit_receipt(self, validated_data: Dict[str, Any]) -> Tuple[Any, Dict[str, Any]]:
        from fiscguy.models import Receipt
        from fiscguy.serializers import ReceiptCreateSerializer

        serializer = ReceiptCreateSerializer(data=validated_data)
        serializer.is_valid(raise_exception=True)
        receipt = serializer.save()

        receipt = Receipt.objects.select_related("buyer").prefetch_related("lines").get(id=receipt.id)
        receipt_items = receipt.lines.all()

        try:
            # Receipt formatting
            receipt_data = self.receipt_handler.generate_receipt_data(receipt, receipt_items)

            # Hash & signature
            hash_sig_data = self.receipt_handler.crypto.generate_receipt_hash_and_signature(
                receipt_data["receipt_string"]
            )
            receipt.hash_value = hash_sig_data["hash"]
            receipt.signature = hash_sig_data["signature"]

            # QR code generation
            self.receipt_handler._generate_qr_code(
                receipt,
                receipt_data["receipt_data"],
                hash_sig_data["signature"]
            )

            # Assign global number
            receipt.global_number = receipt_data["receipt_data"]["receiptGlobalNo"]

            # Update counters
            self.receipt_handler._update_fiscal_counters(receipt, receipt_data["receipt_data"])

            # Submit receipt to ZIMRA
            submission_res = self.receipt_handler.submit_receipt(
                hash_sig_data["hash"],
                hash_sig_data["signature"],
                receipt_data["receipt_data"]
            )
            receipt.submitted = True
            receipt.zimra_inv_id = submission_res.get("receiptID", "")
            receipt.save()

        except Exception as e:
            logger.exception(f"Receipt processing failed for {receipt.id}")
            raise  

        return receipt, submission_res
