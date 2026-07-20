import uuid
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import models

User = get_user_model()


class Plan(models.Model):
    """Subscription plans."""

    FREE = "free"
    PAYG = "payg"
    PRO = "pro"

    PLAN_TYPES = (
        (FREE, "Free Trial"),
        (PAYG, "Pay-as-you-go"),
        (PRO, "Pro Plan"),
    )

    CURRENCY_FIELDS = {
        "USD": "price_usd",
        "NGN": "price_ngn",
        "KES": "price_kes",
        "GHS": "price_ghs",
        "ZAR": "price_zar",
    }

    CURRENCY_SYMBOLS = {
        "USD": "$",
        "NGN": "₦",
        "KES": "KSh",
        "GHS": "GH₵",
        "ZAR": "R",
    }

    name = models.CharField(max_length=50)

    plan_type = models.CharField(
        max_length=10,
        choices=PLAN_TYPES,
        unique=True,
    )

    # Stored prices
    price_usd = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    price_ngn = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    price_kes = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    price_ghs = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    price_zar = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    price_egp = models.DecimalField(max_digits=10, decimal_places=2, default=0)  


    campaigns_per_month = models.PositiveIntegerField(default=0)

    has_watermark = models.BooleanField(default=True)
    priority_queue = models.BooleanField(default=False)
    premium_templates = models.BooleanField(default=False)

    daily_limit = models.PositiveIntegerField(
        null=True,
        blank=True,
    )

    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["price_usd"]

    def __str__(self):
        return self.name

    # -----------------------
    # Currency Helpers
    # -----------------------

    def get_price(self, currency="USD") -> Decimal:
        """
        Returns the numeric price for the requested currency.
        Falls back to USD.
        """
        field = self.CURRENCY_FIELDS.get(currency, "price_usd")
        return getattr(self, field)

    def get_symbol(self, currency="USD") -> str:
        return self.CURRENCY_SYMBOLS.get(currency, "$")

    def get_display_price(self, currency="USD") -> str:
        return f"{self.get_symbol(currency)}{self.get_price(currency)}"


class UserPlan(models.Model):
    """Current active subscription."""

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="user_plan",
    )

    plan = models.ForeignKey(
        Plan,
        on_delete=models.PROTECT,
    )

    start_date = models.DateTimeField(auto_now_add=True)

    end_date = models.DateTimeField(
        null=True,
        blank=True,
    )

    is_active = models.BooleanField(default=True)

    campaigns_used = models.PositiveIntegerField(default=0)
    campaigns_generated = models.PositiveIntegerField(default=0)

    daily_generation_count = models.PositiveIntegerField(default=0)

    last_generation_date = models.DateField(
        null=True,
        blank=True,
    )

    def __str__(self):
        return f"{self.user.email} - {self.plan.name}"


class Transaction(models.Model):
    """Payment transaction."""

    PENDING = "pending"
    SUCCESSFUL = "successful"
    FAILED = "failed"
    REFUNDED = "refunded"
    PARTIAL_REFUND = "partial_refund"

    STATUS_CHOICES = (
        (PENDING, "Pending"),
        (SUCCESSFUL, "Successful"),
        (FAILED, "Failed"),
        (REFUNDED, "Refunded"),
        (PARTIAL_REFUND, "Partial Refund"),
    )

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="transactions",
    )

    plan = models.ForeignKey(
        Plan,
        on_delete=models.PROTECT,
    )

    amount = models.DecimalField(max_digits=10, decimal_places=2)


    currency = models.CharField(max_length=10)

    flutterwave_ref = models.CharField(
        max_length=100,
        unique=True,
        db_index=True,
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=PENDING,
    )

    idempotency_key = models.CharField(
        max_length=255,
        unique=True,
        db_index=True,
    )

    metadata = models.JSONField(default=dict)

    error_message = models.TextField(
        blank=True,
        null=True,
    )

    refund_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        blank=True,
        null=True,
    )

    refund_reference = models.CharField(
        max_length=100,
        blank=True,
        null=True,
    )

    retry_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    updated_at = models.DateTimeField(auto_now=True)

    completed_at = models.DateTimeField(
        blank=True,
        null=True,
    )

    class Meta:
        ordering = ["-created_at"]

        indexes = [
            models.Index(fields=["user", "status"]),
            models.Index(fields=["flutterwave_ref"]),
            models.Index(fields=["idempotency_key"]),
        ]

    def __str__(self):
        return f"{self.flutterwave_ref} ({self.status})"


class UsageLog(models.Model):
    """Campaign usage history."""

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="usage_logs",
    )

    transaction = models.ForeignKey(
        Transaction,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )

    campaign_id = models.CharField(max_length=100)

    action = models.CharField(max_length=50)

    metadata = models.JSONField(default=dict)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user.email} - {self.action}"