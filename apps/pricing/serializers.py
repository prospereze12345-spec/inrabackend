
from decimal import Decimal

from django.contrib.auth import get_user_model
from rest_framework import serializers

from .constants import (
    CURRENCY_SYMBOLS,
    DEFAULT_CURRENCY,
    get_user_currency,
)
from .models import Plan, UserPlan, Transaction


User = get_user_model()


class PlanSerializer(serializers.ModelSerializer):
    price = serializers.SerializerMethodField()
    currency = serializers.SerializerMethodField()
    currency_symbol = serializers.SerializerMethodField()
    price_display = serializers.SerializerMethodField()
    old_price_display = serializers.SerializerMethodField()

    class Meta:
        model = Plan
        fields = (
            "id",
            "name",
            "plan_type",
            "price",
            "currency",
            "currency_symbol",
            "price_display",
            "old_price_display",
            "campaigns_per_month",
            "has_watermark",
            "priority_queue",
            "premium_templates",
            "is_active",
        )

    def _currency(self):
        request = self.context.get("request")

        if request and getattr(request, "user", None) and request.user.is_authenticated:
            return get_user_currency(request.user)

        user = self.context.get("user")
        if user:
            return get_user_currency(user)

        return DEFAULT_CURRENCY

    def _price(self, obj):
        """
        Delegates to Plan.get_price(), the single source of truth for
        which currencies the model actually supports.
        """
        return obj.get_price(self._currency())

    def get_price(self, obj):
        return self._price(obj)

    def get_currency(self, obj):
        return self._currency()

    def get_currency_symbol(self, obj):
        return CURRENCY_SYMBOLS.get(
            self._currency(),
            CURRENCY_SYMBOLS[DEFAULT_CURRENCY],
        )

    def get_price_display(self, obj):
        symbol = CURRENCY_SYMBOLS.get(
            self._currency(),
            CURRENCY_SYMBOLS[DEFAULT_CURRENCY],
        )
        return f"{symbol}{self._price(obj)}"

    def get_old_price_display(self, obj):
        """
        Original crossed-out price, per currency.

        Only currencies present in Plan.CURRENCY_FIELDS are actually billed
        in that currency. Unsupported currencies fall back to USD pricing.
        """
        if obj.plan_type == Plan.FREE:
            return None

        currency = self._currency()

        if currency not in Plan.CURRENCY_FIELDS:
            currency = DEFAULT_CURRENCY

        if obj.plan_type == Plan.PAYG:
            original = {
                "USD": Decimal("2.99"),
                "NGN": Decimal("2500"),
                "KES": Decimal("390"),
                "GHS": Decimal("32"),
            }
        else:
            original = {
                "USD": Decimal("9.99"),
                "NGN": Decimal("10000"),
                "KES": Decimal("780"),
                "GHS": Decimal("65"),
            }

        symbol = CURRENCY_SYMBOLS.get(
            currency,
            CURRENCY_SYMBOLS[DEFAULT_CURRENCY],
        )
        amount = original.get(currency, original["USD"])

        return f"{symbol}{amount}"


class TransactionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Transaction
        fields = (
            "id",
            "amount",
            "currency",
            "status",
            "created_at",
            "completed_at",
        )


class UserPlanSerializer(serializers.ModelSerializer):
    plan = PlanSerializer(read_only=True)

    campaigns_remaining = serializers.SerializerMethodField()
    payg_credits = serializers.IntegerField(read_only=True)
    last_payment_at = serializers.SerializerMethodField()

    class Meta:
        model = UserPlan
        fields = (
            "id",
            "plan",
            "is_active",
            "campaigns_used",
            "campaigns_generated",
            "campaigns_remaining",
            "payg_credits",
            "start_date",
            "end_date",
            "last_payment_at",
        )

    def get_campaigns_remaining(self, obj):
        """
        The meaning of campaigns_remaining depends on the plan.

        Free:
            Number of free trial campaigns still available.

        PAYG:
            Actual prepaid PAYG credits.

        Pro:
            Pro is not represented as a fixed campaign balance here.
            The dashboard displays total assets generated instead.
        """
        if obj.plan.plan_type == Plan.PRO:
            return "Unlimited"

        if obj.plan.plan_type == Plan.PAYG:
            return max(0, obj.payg_credits)

        return max(
            0,
            (obj.plan.campaigns_per_month or 0) - obj.campaigns_used,
        )

    def get_last_payment_at(self, obj):
        """
        Return the most recent successful payment for this customer.

        We deliberately use Transaction.completed_at instead of
        UserPlan.start_date because start_date represents the current
        plan period and is not a reliable record of the latest payment,
        especially for Pro renewals and repeated PAYG purchases.
        """
        transaction = (
            Transaction.objects
            .filter(
                user=obj.user,
                status="successful",
                completed_at__isnull=False,
            )
            .order_by("-completed_at")
            .first()
        )

        if transaction:
            return transaction.completed_at

        return None


class InitiatePaymentSerializer(serializers.Serializer):
    """
    All the frontend sends now is which plan to buy and an idempotency key.

    Channel selection is handled by PaymentService and the provider
    checkout flow.
    """

    plan_type = serializers.ChoiceField(
        choices=Plan.PLAN_TYPES
    )

    idempotency_key = serializers.CharField(
        max_length=255
    )


class VerifyPaymentSerializer(serializers.Serializer):
    """
    Only transaction_id is required.

    The provider transaction reference is handled server-side.
    """

    transaction_id = serializers.UUIDField()

    status = serializers.CharField(required=False)
