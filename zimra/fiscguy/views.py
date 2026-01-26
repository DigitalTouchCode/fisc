from django.shortcuts import render
from easy_pagination import NoPagination, StandardPagination
from loguru import logger
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import ModelViewSet

from fiscguy.models import Configuration, Device, FiscalDay, Receipt, Taxes
from fiscguy.serializers import (ConfigurationSerializer,
                                 ReceiptCreateSerializer, ReceiptSerializer,
                                 TaxSerializer)
from fiscguy.utils.datetime_now import date_today as today
from fiscguy.zimra_base import ZIMRAClient
from fiscguy.zimra_receipt_handler import ZIMRAReceiptHandler
from fiscguy.services.closing_day_service import ClosingDayService

client = ZIMRAClient(Device.objects.first())
receipt_handler = ZIMRAReceiptHandler()


class ReceiptView(generics.GenericAPIView):
    serializer_class = ReceiptSerializer
    # permission_classes = [
    #     IsAuthenticated,
    # ]
    queryset = Receipt.objects.all()

    def get(self, request):
        data = self.queryset.order_by("created_at").select_related("buyer")
        return Response(data)

    def post(self, request):

        serializer = ReceiptCreateSerializer(data=request.data)

        if serializer.is_valid():
            receipt = serializer.save()
            receipt = (
                Receipt.objects.select_related("buyer")
                .prefetch_related("lines")
                .get(id=receipt.id)
            )
            receipt_items = receipt.lines.all()

            # zimra formatted string and receipt data
            receipt_data = receipt_handler.generate_receipt_data(receipt, receipt_items)

            logger.info(receipt_data)

            # receipt hash and signature
            hash_sig_data = receipt_handler.crypto.generate_receipt_hash_and_signature(
                receipt_data["receipt_string"]
            )

            # assign hash and signature values to the receipt
            receipt.hash_value = hash_sig_data["hash"]
            receipt.signature = hash_sig_data["signature"]

            # assign qr_code to the receipt and 16 character md5 code
            receipt_handler._generate_qr_code(
                receipt, receipt_data["receipt_data"], hash_sig_data["signature"]
            )

            # assign receipt global number
            receipt.global_number = receipt_data["receipt_data"]["receiptGlobalNo"]

            # update receipt counters
            update_counter_res = receipt_handler._update_fiscal_counters(
                receipt, receipt_data["receipt_data"]
            )

            # submiit receipt to zimra
            submission_res = receipt_handler.submit_receipt(
                hash_sig_data["hash"],
                hash_sig_data["signature"],
                receipt_data["receipt_data"],
            )

            logger.info(f"Receipt submission response: {submission_res}")

            receipt.submitted = True

            # save receipt
            receipt.save()

            return Response(ReceiptSerializer(receipt).data, status=201)
        return Response(serializer.errors, status=400)


class ReceiptDetailView(generics.RetrieveAPIView):
    queryset = Receipt.objects.all().select_related("receipt_lines", "buyer")
    serializer_class = ReceiptSerializer
    lookup_field = "id"


class ConfigurationView(APIView):
    """
    ZIMRA FDMS Configuration View
    """

    serializer_class = ConfigurationSerializer

    def get(self, request):
        config = Configuration.objects.first()
        return Response(self.serializer_class(config).data, status=status.HTTP_200_OK)


class TaxView(APIView):
    """
    Return the list of taxes.
    """

    serializer_class = TaxSerializer

    def get(self, request):
        taxes = Taxes.objects.all()
        logger.info(taxes.values())
        return Response(
            self.serializer_class(taxes, many=True).data,
            status=status.HTTP_200_OK,
        )


class GetStatusView(APIView):
    """
    Shows the fiscal day status either open or closed(with errors or not)
    """

    def get(self, request):
        res = client.get_status()
        return Response(res, status=status.HTTP_200_OK)


class OpenDayView(APIView):
    """
    View to open a fiscal day
    """

    def get(self, request):
        res = client.open_day()
        return Response(res, status=status.HTTP_200_OK)


class CloseDayView(APIView):
    def get(self, request):
        device = Device.objects.first()
        fiscal_day = FiscalDay.objects.filter(is_open=True).first()
        fiscal_counters = fiscal_day.counters.all()
        tax_map = {t.tax_id: t.name for t in Taxes.objects.all()}

        service = ClosingDayService(
            device=device,
            fiscal_day=fiscal_day,
            fiscal_counters=fiscal_counters,
            tax_map=tax_map,
            receipt_handler=receipt_handler,
        )

        closing_string, payload = service.close_day()

        logger.info(f"Closing Fiscal Day string: {closing_string}")
        logger.info(f"Closing payload: {payload}")

        client.close_day(payload)

        return Response(client.get_status(), status=status.HTTP_200_OK)
