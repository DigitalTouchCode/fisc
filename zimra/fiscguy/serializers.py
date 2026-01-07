from loguru import logger
from rest_framework import serializers

from fiscguy.models import Buyer, Configuration, Receipt, ReceiptLine, Taxes
from fiscguy.zimra_receipt_handler import ZIMRAReceiptHandler

receipt_handler = ZIMRAReceiptHandler()


class ConfigurationSerializer(serializers.ModelSerializer):
    """
    configurations for the taxpayer
    """

    class Meta:
        model = Configuration
        fields = [
            "id",
            "tax_payer_name",
            "tin_number",
            "vat_number",
            "address",
            "phone_number",
            "email",
        ]


class TaxSerializer(serializers.ModelSerializer):
    """
    Zimra official taxes
    """

    class Meta:
        model = Taxes
        fields = "__all__"


class ReceiptLineSerializer(serializers.ModelSerializer):
    """
    Receipt lines
    """

    class Meta:
        model = ReceiptLine
        fields = [
            "id",
            "product",
            "quantity",
            "unit_price",
            "line_total",
            "tax_amount",
        ]


class ReceiptLineCreateSerializer(serializers.ModelSerializer):
    """
    Writable serializer for receipt lines used when creating receipts.
    """

    tax_name = serializers.CharField(write_only=True, required=False)

    class Meta:
        model = ReceiptLine
        fields = [
            "product",
            "quantity",
            "unit_price",
            "line_total",
            "tax_amount",
            "tax_name",
        ]


class BuyerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Buyer
        fields = [
            "id",
            "name",
            "address",
            "tin_number",
            "vat_numberr",
        ]


class ReceiptSerializer(serializers.ModelSerializer):
    """
    Receipt Serialiazerr
    """

    lines = ReceiptLineSerializer(many=True, read_only=True)
    buyer = BuyerSerializer(read_only=True)

    class Meta:
        model = Receipt
        fields = "__all__"


class ReceiptCreateSerializer(serializers.ModelSerializer):
    lines = ReceiptLineCreateSerializer(many=True)

    class Meta:
        model = Receipt
        fields = [
            "receipt_type",
            "total_amount",
            "currency",
            "buyer",
            "lines",
            "payment_terms",
        ]

    def create(self, validated_data):
        lines_data = validated_data.pop("lines")

        receipt = Receipt.objects.create(**validated_data)
        for idx, line_data in enumerate(lines_data):
            tax_name = line_data.pop("tax_name", None)

            if tax_name:
                tax = Taxes.objects.filter(name__iexact=tax_name.strip()).first()
                if not tax:
                    tax = Taxes.objects.filter(name__icontains=tax_name.strip()).first()

                if not tax:
                    raise serializers.ValidationError(
                        {"lines": {idx: f"Tax with name '{tax_name}' not found"}}
                    )

                line_data["tax_type"] = tax

            ReceiptLine.objects.create(receipt=receipt, **line_data)

        return receipt
