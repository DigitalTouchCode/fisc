"""
REST API Views for ZIMRA Fiscal Device.

These views are thin wrappers around the public `fiscguy` library API.
The core logic resides in `fiscguy.api` and `fiscguy.services`.

For programmatic use, import directly from fiscguy:
    from fiscguy import open_day, close_day, submit_receipt, ...
"""

from loguru import logger
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView

# Import public library functions
from fiscguy.api import (
    open_day,
    close_day,
    get_status,
    submit_receipt,
    get_configuration,
    get_taxes,
)
from fiscguy.models import Receipt
from fiscguy.serializers import ReceiptSerializer


class ReceiptView(generics.GenericAPIView):
    """REST endpoint to list and submit receipts.

    GET: List all receipts
    POST: Create and submit a receipt to ZIMRA
    """

    serializer_class = ReceiptSerializer
    queryset = Receipt.objects.all()

    def get(self, request):
        """List receipts ordered by creation date."""
        data = self.queryset.order_by("created_at").select_related("buyer")
        return Response(ReceiptSerializer(data, many=True).data)

    def post(self, request):
        """Create and submit a receipt.

        Calls the library's submit_receipt function which handles
        serialization, creation, generation, and submission.
        """
        try:
            receipt = submit_receipt(request.data)
            return Response(ReceiptSerializer(receipt).data, status=201)
        except Exception as e:
            logger.exception("Receipt submission failed")
            return Response({"error": str(e)}, status=400)


class ReceiptDetailView(generics.RetrieveAPIView):
    """REST endpoint to retrieve a single receipt by ID."""

    queryset = Receipt.objects.all().select_related("receipt_lines", "buyer")
    serializer_class = ReceiptSerializer
    lookup_field = "id"


class ConfigurationView(APIView):
    """REST endpoint to get device configuration.

    GET: Fetch stored taxpayer configuration
    """

    def get(self, request):
        try:
            config = get_configuration()
            return Response(config, status=status.HTTP_200_OK)
        except Exception as e:
            logger.exception("Configuration fetch failed")
            return Response({"error": str(e)}, status=400)


class TaxView(APIView):
    """REST endpoint to list available taxes.

    GET: Fetch all configured tax types
    """

    def get(self, request):
        try:
            taxes = get_taxes()
            return Response(taxes, status=status.HTTP_200_OK)
        except Exception as e:
            logger.exception("Tax fetch failed")
            return Response({"error": str(e)}, status=400)


class GetStatusView(APIView):
    """REST endpoint to get device and fiscal day status.

    GET: Fetch status from ZIMRA FDMS
    """

    def get(self, request):
        try:
            status_payload = get_status()
            return Response(status_payload, status=status.HTTP_200_OK)
        except Exception as e:
            logger.exception("Status fetch failed")
            return Response({"error": str(e)}, status=400)
        

class OpenDayView(APIView):
    """REST endpoint to open a fiscal day.

    GET: Open a new fiscal day
    """

    def get(self, request):
        try:
            result = open_day()
            return Response(result, status=status.HTTP_200_OK)
        except Exception as e:
            logger.exception("Open day failed")
            return Response({"error": str(e)}, status=400)


class CloseDayView(APIView):
    """REST endpoint to close the fiscal day.

    GET: Close the open fiscal day (build counters, sign, submit)
    """

    def get(self, request):
        try:
            status_payload = close_day()
            return Response(status_payload, status=status.HTTP_200_OK)
        except Exception as e:
            logger.exception("Close day failed")
            return Response({"error": str(e)}, status=400)

