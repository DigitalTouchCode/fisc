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

            #update receipt counters
            update_counter_res = receipt_handler._update_fiscal_counters(
                receipt, receipt_data["receipt_data"]
            )

            # # submiit receipt to zimra
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
    """
    View to close a day.
    Computes the closing day fdms string from the fiscal counters to a hash and signature.
    """

    def get(self, request):
        device = Device.objects.first()
        tax_map = {tax.tax_id: tax.name for tax in Taxes.objects.all()}
        fiscal_day = FiscalDay.objects.filter(is_open=True).first()
        fiscal_counters = fiscal_day.counters.all()

        salebytax = []
        saletaxbytax = []
        balancebymoneytype = []

        payload = None

        for counter in fiscal_counters:
            tax_percent = counter.fiscal_counter_tax_percent
            tax_id = counter.fiscal_counter_tax_id
            currency = counter.fiscal_counter_currency
            money_type = counter.fiscal_counter_money_type
            value = counter.fiscal_counter_value
            counter_name = counter.fiscal_counter_type.lower()

            intial_string = counter_name + currency

            if counter_name == "salebytax":
                if tax_map.get(tax_id).lower().__contains__("standard"):
                    salebytax.append(f"{intial_string}{tax_percent}{int(value*100)}")
                elif tax_map.get(tax_id).lower().__contains__("zero"):
                    salebytax.append(f"{intial_string}{tax_percent}{int(value*100)}")
                else:
                    salebytax.append(f"{intial_string}{int(value*100)}")

            elif counter_name == "saletaxbytax":
                saletaxbytax.append(f"{intial_string}{tax_percent}{int(value*100)}")

            elif counter_name == "balancebymoneytype":
                balancebymoneytype.append(
                    f"{intial_string}{money_type}{int(value*100)}"
                )
        # concatinate final string
        closing_string = (
            f"{device.device_id}{fiscal_day.day_no}{today()}" + \
            "".join(salebytax) + "".join(saletaxbytax) + "".join(balancebymoneytype)
        ).upper()
        
        # closing hash value and signature
        closing_hash_signature = receipt_handler.crypto.generate_receipt_hash_and_signature(closing_string)

        logger.info(f"Closing Fiscal Day string: {closing_string}")
        
        # zimra payload preparation
        regular_counters = []
        sale_tax_by_tax_counter = [] 
        balance_by_money_counter = [] 

        for counter in fiscal_counters:
            if counter.fiscal_counter_type == "Balancebymoneytype":
                fiscal_counter_data = {
                    "fiscalCounterType": counter.fiscal_counter_type,
                    "fiscalCounterCurrency": counter.fiscal_counter_currency,
                    "fiscalCounterMoneyType": counter.fiscal_counter_money_type or 0,
                    "fiscalCounterValue": float(round(counter.fiscal_counter_value, 2)),
                }
                
            # elif float(round(counter.fiscal_counter_value, 2))== 0.00:
            #     continue
            
            else:
                fiscal_counter_data = {
                    "fiscalCounterType": counter.fiscal_counter_type,
                    "fiscalCounterCurrency": counter.fiscal_counter_currency,
                    "fiscalCounterTaxPercent": float(counter.fiscal_counter_tax_percent),
                    "fiscalCounterTaxID": counter.fiscal_counter_tax_id,
                    "fiscalCounterValue": float(round(counter.fiscal_counter_value, 2)),
                }

            if counter.fiscal_counter_type == "SaleTaxByTax":
                sale_tax_by_tax_counter.append(fiscal_counter_data)  
            elif counter.fiscal_counter_type == "SaleByTax":
                regular_counters.append(fiscal_counter_data)
            elif counter.fiscal_counter_type == "BalanceByMoneyType":
                balance_by_money_counter.append(fiscal_counter_data) 
            else:
                logger.info(fiscal_counter_data)
                regular_counters.append(fiscal_counter_data)

        fiscal_day_counters = regular_counters + sale_tax_by_tax_counter + balance_by_money_counter
        
        logger.debug(fiscal_day_counters)
        
        payload = {
            "deviceID": device.device_id,
            "fiscalDayNo": fiscal_day.day_no,
            "fiscalDayDate": today(),
            "fiscalDayCounters": fiscal_day_counters,
            "fiscalDayDeviceSignature": {
                "hash": closing_hash_signature["hash"],
                "signature": closing_hash_signature["signature"],
            },
            "receiptCounter": fiscal_day.receipt_counter
        }

        logger.info(f"Closing Fiscal Day with payload: {payload}")

        # submit zimra
        submission_res = client.close_day(
            payload
        )
        
        return Response(submission_res)
