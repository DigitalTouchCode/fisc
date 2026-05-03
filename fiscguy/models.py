from django.db import models

from fiscguy.fields import EncryptedTextField


class Device(models.Model):
    org_name = models.CharField(max_length=255)
    activation_key = models.CharField(max_length=255)
    device_id = models.CharField(max_length=100, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    device_model_name = models.CharField(max_length=255, null=True, blank=True)
    device_serial_number = models.CharField(max_length=255, null=True, blank=True)
    device_model_version = models.CharField(max_length=255, null=True, blank=True)
    production = models.BooleanField(default=False)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["device_id"]),
        ]

    def __str__(self):
        return f"{self.org_name} - {self.device_id}"


class Configuration(models.Model):
    """
    Zimra taxpayer configuration
    """

    device = models.OneToOneField(
        Device, on_delete=models.CASCADE, related_name="configuration", null=True, blank=True
    )
    tax_payer_name = models.CharField(max_length=255)
    tax_inclusive = models.BooleanField(default=True)
    tin_number = models.CharField(max_length=20)
    vat_number = models.CharField(max_length=20)
    address = models.CharField(max_length=255)
    phone_number = models.CharField(max_length=20)
    email = models.EmailField()
    device_operating_mode = models.CharField(max_length=20, blank=True)
    tax_payer_day_max_hrs = models.IntegerField(null=True, blank=True)
    tax_payer_day_end_notification_hrs = models.IntegerField(null=True, blank=True)
    certificate_valid_till = models.DateField(null=True, blank=True)
    url = models.URLField(
        null=True, blank=True
    )  # for zimra either testing or production (the url in config its old)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.tax_payer_name


class Certs(models.Model):
    """
    Zimra certificates for authentication,
    divided between production and testing certs
    """

    device = models.OneToOneField(
        Device, on_delete=models.CASCADE, related_name="certificate", null=True, blank=True
    )
    csr = models.TextField()
    certificate = models.TextField()
    certificate_key = EncryptedTextField()
    production = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        env = "Production" if self.production else "Testing"
        return f"{env} Certificate"


class Taxes(models.Model):
    """
    Zimra taxes automatically update on every day opening
    """

    device = models.ForeignKey(
        Device, on_delete=models.CASCADE, related_name="taxes", null=True, blank=True
    )
    code = models.CharField(max_length=10)
    name = models.CharField(max_length=100)
    tax_id = models.IntegerField()
    percent = models.DecimalField(max_digits=5, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["tax_id"]
        verbose_name_plural = "Taxes"
        indexes = [
            models.Index(fields=["device", "tax_id"]),
            models.Index(fields=["tax_id"]),
        ]

    def __str__(self):
        return f"{self.name}: {self.percent}"


class FiscalDay(models.Model):
    """
    Fiscal day model (increment with +1 every opening, keeps the receipt counter of the day)
    """

    class CloseState(models.TextChoices):
        OPEN = "open", "Open"
        CLOSE_PENDING = "close_pending", "Close Pending"
        CLOSE_FAILED = "close_failed", "Close Failed"
        CLOSED = "closed", "Closed"

    device = models.ForeignKey(
        Device, on_delete=models.CASCADE, related_name="fiscal_days", null=True, blank=True
    )
    day_no = models.IntegerField()
    receipt_counter = models.IntegerField(default=0)
    is_open = models.BooleanField(default=False)
    close_state = models.CharField(
        max_length=20, choices=CloseState.choices, default=CloseState.OPEN
    )
    fdms_status = models.CharField(max_length=64, null=True, blank=True)
    close_requested_at = models.DateTimeField(null=True, blank=True)
    close_confirmed_at = models.DateTimeField(null=True, blank=True)
    last_status_sync_at = models.DateTimeField(null=True, blank=True)
    last_close_error_code = models.CharField(max_length=128, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-day_no"]
        unique_together = ["device", "day_no"]
        indexes = [
            models.Index(fields=["device", "is_open"]),
        ]

    def __str__(self):
        return f"Day No: {self.day_no} | Open: {self.is_open}"


class FiscalCounter(models.Model):
    """
    Fiscal counter model
    """

    SALE_BY_TAX = "SaleByTax"
    SALE_TAX_BY_TAX = "SaleTaxByTax"

    CREDITNOTE_BY_TAX = "CreditNoteByTax"
    CREDITNOTE_TAX_BY_TAX = "CreditNoteTaxByTax"

    DEBITNOTE_BY_TAX = "DebitNoteByTax"
    DEBITNOTE_TAX_BY_TAX = "DebitNoteTaxByTax"

    BALANCE_BY_MONEY_TYPE = "BalanceByMoneyType"
    OTHER = "Other"

    COUNTER_TYPE_CHOICES = [
        (SALE_BY_TAX, "Sale_by_Tax"),
        (SALE_TAX_BY_TAX, "Sale Tax by Tax"),
        (CREDITNOTE_BY_TAX, "Credit Note by Tax"),
        (CREDITNOTE_TAX_BY_TAX, "Credit Note Tax by Tax"),
        (DEBITNOTE_BY_TAX, "Debit Note by Tax"),
        (DEBITNOTE_TAX_BY_TAX, "Debit Note Tax by Tax"),
        (BALANCE_BY_MONEY_TYPE, "Balance by Money Type"),
        (OTHER, "Other"),
    ]

    CASH = "Cash"
    CARD = "Card"
    BANK_TRANSFER = "BankTransfer"
    MOBILE_MONEY = "MobileWallet"
    COUPON = "Coupon"
    CREDIT = "Credit"
    OTHER_PAYMENT = "Other"

    MONEY_TYPE_CHOICES = [
        (CASH, "Cash"),
        (CARD, "Card"),
        (BANK_TRANSFER, "Bank Transfer"),
        (MOBILE_MONEY, "Mobile Wallet"),
        (COUPON, "Coupon"),
        (CREDIT, "Credit"),
        (OTHER_PAYMENT, "Other"),
    ]

    device = models.ForeignKey(
        Device, on_delete=models.CASCADE, related_name="fiscal_counters", null=True, blank=True
    )
    fiscal_day = models.ForeignKey(
        FiscalDay,
        on_delete=models.CASCADE,
        related_name="counters",
        null=True,
        blank=True,
    )
    fiscal_counter_type = models.CharField(
        max_length=30, choices=COUNTER_TYPE_CHOICES, default=SALE_BY_TAX
    )
    fiscal_counter_currency = models.CharField(
        max_length=10, choices=[("USD", "usd"), ("ZWG", "zwg")], default="USD"
    )
    fiscal_counter_tax_percent = models.DecimalField(
        max_digits=5, decimal_places=2, default=0.00, null=True, blank=True
    )
    fiscal_counter_tax_id = models.IntegerField(default=3, null=True, blank=True)
    fiscal_counter_money_type = models.CharField(
        max_length=20, choices=MONEY_TYPE_CHOICES, default=CASH, null=True
    )
    fiscal_counter_value = models.DecimalField(
        max_digits=10, decimal_places=2, default=0.00, null=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["device", "fiscal_day"]),
        ]

    def __str__(self):
        return f": ({self.fiscal_counter_type} - {self.fiscal_counter_currency} - {self.fiscal_counter_value})"


class Receipt(models.Model):
    """
    Receipt model
    """

    class PaymentMethod(models.TextChoices):
        CASH = "Cash", "Cash"
        CARD = "Card", "Card"
        MOBILE_WALLET = "MobileWallet", "Mobile Wallet"
        BANK_TRANSFER = "BankTransfer", "Bank Transfer"
        COUPON = "Coupon", "Coupon"
        CREDIT = "Credit", "Credit"
        OTHER = "Other", "Other"

    class ReceiptType(models.TextChoices):
        FISCAL_INVOICE = "fiscalinvoice", "Fiscal Invoice"
        CREDIT_NOTE = "creditnote", "Creditnote"
        DEBIT_NOTE = "debitnote", "Debitnote"

    device = models.ForeignKey(
        Device, on_delete=models.CASCADE, related_name="receipts", null=True, blank=True
    )
    receipt_number = models.CharField(unique=True, max_length=255, null=True, blank=True)
    receipt_type = models.CharField(
        choices=ReceiptType, default=ReceiptType.FISCAL_INVOICE, max_length=255
    )
    total_amount = models.DecimalField(max_digits=12, decimal_places=2)
    qr_code = models.ImageField(upload_to="Zimra_qr_codes", null=True, blank=True)
    code = models.CharField(max_length=20, null=True, blank=True)
    currency = models.CharField(
        max_length=255, choices=[("USD", "usd"), ("ZWG", "zwg")], default="USD"
    )

    global_number = models.IntegerField(null=True, blank=True)
    hash_value = models.CharField(max_length=255, null=True, blank=True)
    signature = models.TextField()

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    zimra_inv_id = models.CharField(max_length=255, null=True, blank=True)

    buyer = models.ForeignKey(
        "Buyer",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="receipts",
    )
    payment_terms = models.CharField(
        max_length=20,
        choices=PaymentMethod.choices,
        default=PaymentMethod.CASH,
    )

    submitted = models.BooleanField(default=False, null=True)
    is_credit_note = models.BooleanField(default=False, null=True)
    credit_note_reason = models.CharField(max_length=255, null=True, blank=True)
    credit_note_reference = models.CharField(max_length=255, null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["receipt_number"]),
            models.Index(fields=["device", "-created_at"]),
        ]

    def __str__(self):
        return f"Receipt No: {self.receipt_number} | Type: {self.receipt_type} | Total: {self.total_amount}"


class ReceiptLine(models.Model):
    """
    Receipt lines model, (product can vary with different taxes)
    """

    receipt = models.ForeignKey(Receipt, on_delete=models.CASCADE, related_name="lines")
    product = models.CharField(max_length=255)
    hs_code = models.CharField(max_length=8, blank=True, default="")
    quantity = models.DecimalField(max_digits=10, decimal_places=2)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    line_total = models.DecimalField(max_digits=12, decimal_places=2)
    tax_amount = models.DecimalField(max_digits=12, decimal_places=2)
    tax_type = models.ForeignKey(Taxes, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["receipt", "id"]
        indexes = [
            models.Index(fields=["receipt"]),
        ]

    def __str__(self):
        return f"{self.product} - {self.line_total}"


class Buyer(models.Model):
    """
    Buyer model (not mandatory on every transaction)
    """

    name = models.CharField(max_length=255)
    address = models.CharField(max_length=255, blank=True)
    phonenumber = models.CharField(max_length=20, blank=True)
    trade_name = models.CharField(max_length=100, blank=True)
    tin_number = models.CharField(max_length=255)
    email = models.EmailField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["tin_number"]),
        ]

    def __str__(self):
        return self.name
