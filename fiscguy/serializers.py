from django.db import transaction
from rest_framework import serializers

from fiscguy.models import Buyer, Configuration, Receipt, ReceiptLine, Taxes


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
        fields = ["id", "name", "address", "tin_number", "trade_name", "email", "phonenumber"]


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
    buyer = BuyerSerializer(required=False, allow_null=True)

    credit_note_reference = serializers.CharField(required=False, allow_blank=True)
    credit_note_reason = serializers.CharField(required=False, allow_blank=True)
    payment_terms = serializers.ChoiceField(choices=Receipt.PaymentMethod.choices)

    class Meta:
        model = Receipt
        fields = [
            "receipt_type",
            "total_amount",
            "currency",
            "buyer",
            "lines",
            "payment_terms",
            "credit_note_reference",
            "credit_note_reason",
        ]

    def validate(self, attrs):
        receipt_type = attrs.get("receipt_type", "").lower()
        total_amount = attrs.get("total_amount", 0)

        if receipt_type == "creditnote":

            if not attrs.get("credit_note_reference"):
                raise serializers.ValidationError(
                    {"credit_note_reference": "This field is required for credit notes"}
                )

            if not Receipt.objects.filter(receipt_number=attrs["credit_note_reference"]).exists():
                raise serializers.ValidationError(
                    {"credit_note_reference": "Referenced receipt does not exist"}
                )

            # Amount must be negative
            if total_amount > 0:
                raise serializers.ValidationError(
                    {"total_amount": "Credit note total must be negative"}
                )

        return attrs

    def create(self, validated_data):

        buyer_data = validated_data.pop("buyer", None)
        lines_data = validated_data.pop("lines")
        receipt_type = validated_data.get("receipt_type", "").lower()

        with transaction.atomic():

            buyer = None

            if buyer_data:
                # validate tin number
                if len(buyer_data["tin_number"]) != 10:
                    raise serializers.ValidationError(
                        {"buyer": "Tin number is incorrect, must be ten digit."}
                    )

                buyer, _ = Buyer.objects.get_or_create(
                    tin_number=buyer_data["tin_number"].strip(),
                    defaults={
                        "name": buyer_data["name"].strip(),  # business registered name
                        "email": buyer_data["email"].strip(),
                        "trade_name": buyer_data[
                            "trade_name"
                        ].strip(),  # trade name e.g branch name
                        "phonenumber": buyer_data["phonenumber"].strip(),
                        "address": buyer_data["address"].strip(),
                    },
                )

            receipt = Receipt.objects.create(**validated_data)

            if buyer:
                receipt.buyer = buyer
                receipt.save()

            for idx, line_data in enumerate(lines_data):

                tax_name = line_data.pop("tax_name", None)

                if tax_name:
                    tax = (
                        Taxes.objects.filter(name__iexact=tax_name.strip()).first()
                        or Taxes.objects.filter(name__icontains=tax_name.strip()).first()
                    )

                    if not tax:
                        raise serializers.ValidationError(
                            {"lines": {idx: f"Tax with name '{tax_name}' not found"}}
                        )

                    line_data["tax_type"] = tax

                if receipt_type == "creditnote":
                    if line_data.get("unit_price", 0) > 0:
                        line_data["unit_price"] *= -1

                    if line_data.get("line_total", 0) > 0:
                        line_data["line_total"] *= -1

                ReceiptLine.objects.create(receipt=receipt, **line_data)

            return receipt
