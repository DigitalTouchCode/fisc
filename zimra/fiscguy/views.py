from django.shortcuts import render
from easy_pagination import NoPagination, StandardPagination
from loguru import logger
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import ModelViewSet

from fiscguy.models import Configuration, Device, Receipt, Taxes
from fiscguy.serializers import (ConfigurationSerializer,
                                 ReceiptLineSerializer, ReceiptSerializer,
                                 TaxSerializer, ReceiptCreateSerializer)
from fiscguy.zimra_base import ZIMRAClient
from fiscguy.zimra_receipt_handler import ZIMRAReceiptHandler

client = ZIMRAClient(Device.objects.first())
receipt_handler = ZIMRAReceiptHandler()


class ReceiptView(generics.GenericAPIView):
    serializer_class = ReceiptSerializer
    # pagination_class = StandardPagination
    # permission_classes = [
    #     IsAuthenticated,
    # ]
    queryset = Receipt.objects.all()

    def get(self, request):
        data = self.queryset.order_by("created_at").select_related("buyer")
        return Response(data)

    def post(self, request):
        serializer = ReceiptCreateSerializer(data=request.data)
        logger.info(serializer)
        if serializer.is_valid():
            receipt = serializer.save()
            receipt = Receipt.objects.select_related('buyer').prefetch_related('lines').get(id=receipt.id)
            receipt_items = receipt.lines.all()
            
            # zimra formatted string and receipt data
            data = receipt_handler.generate_receipt_data(
                receipt,
                receipt_items
            )

            logger.info(f'data: {data}')

            # receipt hash and signature
            hash_sig_data = receipt_handler.crypto.generate_receipt_hash_and_signature(data["receipt_string"])

            # assign qr_code to the receipt and md5 code
            receipt_handler._generate_qr_code(
                receipt, 
                data["receipt_data"], 
                hash_sig_data["signature"]
            )
            
            logger.info(data)
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
    def get(self, request):
        res = client.get_status()
        return Response(res, status=status.HTTP_200_OK)


class OpenDayView(APIView):
    def get(self, request):
        res = client.open_day()
        return Response(res, status=status.HTTP_200_OK)


class CloseDayView(APIView):
    pass
