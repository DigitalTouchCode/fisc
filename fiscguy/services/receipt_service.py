from django.db import transaction
from loguru import logger

from fiscguy.exceptions import ReceiptSubmissionError
from fiscguy.models import Device, Receipt
from fiscguy.serializers import ReceiptCreateSerializer
from fiscguy.zimra_receipt_handler import ZIMRAReceiptHandler


class ReceiptService:
    """
    Validates and persists a receipt, then delegates processing and
    FDMS submission to ZIMRAReceiptHandler.
    """

    def __init__(self, device: Device):
        self.device = device
        self.receipt_handler = ZIMRAReceiptHandler(device)

    @transaction.atomic
    def create_and_submit_receipt(self, data: dict) -> tuple[Receipt, dict]:
        """
        Validate, persist, process, and submit a receipt to ZIMRA.

        If FDMS is offline the receipt is saved locally and queued for
        background sync. The submission result will contain
        ``{"submitted": False, "queued": True}`` in that case.

        Args:
            data: raw receipt payload from the request.

        Returns:
            Tuple of (Receipt instance, submission result dict).

        Raises:
            ValidationError: if the payload fails serializer validation.
            ReceiptSubmissionError: if processing or submission fails.
        """
        serializer = ReceiptCreateSerializer(data=data)
        serializer.is_valid(raise_exception=True)
        receipt = serializer.save()

        receipt = (
            Receipt.objects.select_related("buyer").prefetch_related("lines").get(id=receipt.id)
        )

        try:
            submission_result = self.receipt_handler.process_and_submit(receipt)
        except ReceiptSubmissionError:
            logger.exception(f"Receipt processing failed for receipt {receipt.id}")
            raise

        return receipt, submission_result
