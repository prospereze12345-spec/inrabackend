from decimal import Decimal

from rest_framework import serializers
from django.contrib.auth import get_user_model

from .models import Plan, UserPlan, Transaction
from .constants import CURRENCY_SYMBOLS, DEFAULT_CURRENCY, get_user_currency

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
        which currencies the model actually supports. Never hardcode a
        currency->field mapping here again -- if the model doesn't have
        a column for a currency, get_price() already falls back to USD.
        """
        return obj.get_price(self._currency())

    def get_price(self, obj):
        return self._price(obj)

    def get_currency(self, obj):
        return self._currency()

    def get_currency_symbol(self, obj):
        return CURRENCY_SYMBOLS.get(self._currency(), CURRENCY_SYMBOLS[DEFAULT_CURRENCY])

    def get_price_display(self, obj):
        symbol = CURRENCY_SYMBOLS.get(self._currency(), CURRENCY_SYMBOLS[DEFAULT_CURRENCY])
        return f"{symbol}{self._price(obj)}"

    def get_old_price_display(self, obj):
        """
        Original crossed-out price, per currency.

        IMPORTANT: only currencies present in Plan.CURRENCY_FIELDS are
        actually billed in that currency -- everything else silently
        falls back to USD pricing via get_price(). To avoid showing an
        "old price" in a currency the real price isn't shown in, we key
        off the same set of supported currencies as the model.
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

        symbol = CURRENCY_SYMBOLS.get(currency, CURRENCY_SYMBOLS[DEFAULT_CURRENCY])
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

    class Meta:
        model = UserPlan
        fields = (
            "id",
            "plan",
            "is_active",
            "campaigns_used",
            "campaigns_generated",
            "campaigns_remaining",
            "start_date",
            "end_date",
        )

    def get_campaigns_remaining(self, obj):

        if obj.plan.plan_type == Plan.PRO:
            return "Unlimited"

        if obj.plan.plan_type == Plan.PAYG:
            return max(0, 1 - obj.campaigns_used)

        return max(
            0,
            (obj.plan.campaigns_per_month or 0)
            - obj.campaigns_used,
        )


class InitiatePaymentSerializer(serializers.Serializer):
    """
    All the frontend sends now is which plan to buy and an idempotency key.

    Channel selection (card / bank transfer / USSD / mobile money) is no
    longer a client decision -- PaymentService picks Flutterwave's v3
    hosted checkout and passes `payment_options` based on the user's
    currency, and Flutterwave's own checkout page presents whichever of
    those the customer can actually use. There is no cardholder data or
    channel-specific payload to validate here anymore.
    """

    plan_type = serializers.ChoiceField(
        choices=Plan.PLAN_TYPES
    )

    idempotency_key = serializers.CharField(
        max_length=255
    )


class VerifyPaymentSerializer(serializers.Serializer):
    """
    Not currently wired into PricingViewSet.verify_payment (that action reads
    request.data directly) -- kept here in case another call site uses it.
    Only transaction_id is required; Flutterwave's own transaction id is
    looked up server-side from the stored transaction, not supplied by the
    client, so there's no flutterwave_ref for the client to send.
    """

    transaction_id = serializers.UUIDField()

    status = serializers.CharField(required=False)
