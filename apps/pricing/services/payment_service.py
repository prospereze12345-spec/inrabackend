import logging
import time
from datetime import timedelta
from decimal import Decimal
from typing import Any, Dict, Optional

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.db import transaction as db_transaction
from django.utils import timezone

from ..constants import get_user_currency
from ..models import Plan, Transaction, UserPlan
from ..providers.base import PaymentProviderError
from ..providers.flutterwave import FlutterwaveProvider
from ..providers.paystack import PaystackProvider
from .entitlement import is_pro_live

logger = logging.getLogger(__name__)

PROVIDERS = {
    "paystack": PaystackProvider,
    "flutterwave": FlutterwaveProvider,
}

PRO_PERIOD = timedelta(days=30)


class PaymentService:
    """
    Provider-agnostic payment orchestration: idempotency, retry bookkeeping,
    plan activation, webhook dispatch. All gateway-specific HTTP calls and
    signature schemes live behind PaymentProvider (services/providers/*.py)
    -- this class never imports `requests` or knows a gateway's field
    names.

    Active gateway is controlled by settings.PAYMENT_PROVIDER (defaults to
    "paystack"). To bring Flutterwave back: set
    PAYMENT_PROVIDER = "flutterwave" -- nothing else here changes. When
    multiple gateways are live simultaneously (e.g. Paystack for NG,
    Flutterwave for everywhere else), swap __init__'s single lookup for a
    per-currency/per-country one; PROVIDERS already gives you the registry
    to do that from.

    NG-only for now: SUPPORTED_CURRENCIES gates this so a user with a
    non-NG country code doesn't silently get a transaction created in a
    currency Paystack can't actually charge on this account.
    """

    SUPPORTED_CURRENCIES = {"NGN"}

    def __init__(self):
        self.max_retries = 3
        self.retry_delay = 60

        provider_name = getattr(settings, "PAYMENT_PROVIDER", "paystack")
        provider_cls = PROVIDERS.get(provider_name)
        if not provider_cls:
            raise ImproperlyConfigured(
                f"Unknown PAYMENT_PROVIDER '{provider_name}'. Valid options: "
                f"{list(PROVIDERS)}"
            )
        self.provider_name = provider_name
        self.provider = provider_cls()

    # ------------------------------------------------------------------
    # Pricing
    # ------------------------------------------------------------------

    def get_plan_prices(self, user, plan_type: str) -> Dict[str, Any]:
        try:
            plan = Plan.objects.get(plan_type=plan_type)
        except Plan.DoesNotExist:
            raise ValueError(f"Plan {plan_type} not found")

        currency = get_user_currency(user)

        if currency not in self.SUPPORTED_CURRENCIES:
            # NG-only for now: everyone else falls back to NGN pricing
            # rather than erroring, so checkout still works while only one
            # country/gateway is live. Revisit this fallback once a second
            # currency (and Flutterwave) is wired back in.
            logger.info(
                "Currency %s not supported by %s yet -- defaulting user %s to NGN pricing",
                currency, self.provider_name, getattr(user, "id", None),
            )
            currency = "NGN"

        price_field = Plan.CURRENCY_FIELDS.get(currency, "price_ngn")

        return {
            "price": getattr(plan, price_field),
            "currency": currency,
            "plan": plan,
        }

    # ------------------------------------------------------------------
    # Initiation
    # ------------------------------------------------------------------

    def initiate_payment(self, user, plan_type: str, idempotency_key: str) -> Dict[str, Any]:
        """Initiate a payment with idempotency check.

        Returns a hosted-checkout `redirect_url` -- the frontend should
        send the browser there immediately.
        """
        existing_transaction = Transaction.objects.filter(
            idempotency_key=idempotency_key
        ).first()

        plan_data = self.get_plan_prices(user, plan_type)

        if existing_transaction:
            if existing_transaction.status == "successful":
                return {
                    "status": "success",
                    "transaction": existing_transaction,
                    "message": "Payment already processed",
                }
            if existing_transaction.status == "pending":
                return {
                    "status": "pending",
                    "transaction": existing_transaction,
                    "redirect_url": (existing_transaction.metadata or {}).get("redirect_url"),
                    "message": "Payment is still being processed",
                }

            if existing_transaction.retry_count >= self.max_retries:
                raise ValueError("Maximum retry attempts exceeded")
            existing_transaction.retry_count += 1
            existing_transaction.save(update_fields=["retry_count"])
            transaction_obj = existing_transaction
        else:
            with db_transaction.atomic():
                transaction_obj = Transaction.objects.create(
                    user=user,
                    plan=plan_data["plan"],
                    amount=plan_data["price"],
                    currency=plan_data["currency"],
                    provider_reference=f"REF_{idempotency_key[:10]}_{int(timezone.now().timestamp())}",
                    idempotency_key=idempotency_key,
                    status="pending",
                )

        try:
            result = self.provider.initialize_transaction(user=user, transaction=transaction_obj)

            transaction_obj.metadata = {
                "redirect_url": result["redirect_url"],
                "plan_name": plan_data["plan"].name,
                "provider": self.provider_name,
            }
            transaction_obj.save()

            return {
                "status": "pending",
                "transaction": transaction_obj,
                "transaction_id": str(transaction_obj.id),
                "redirect_url": result["redirect_url"],
                "reference": transaction_obj.provider_reference,
            }

        except PaymentProviderError as e:
            logger.error(f"Error initiating payment: {e}")
            transaction_obj.status = "failed"
            transaction_obj.error_message = str(e)
            transaction_obj.save()
            raise

    # ------------------------------------------------------------------
    # Verification
    # ------------------------------------------------------------------

    def verify_payment(
        self, transaction_id, flutterwave_transaction_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        `flutterwave_transaction_id` kept as the parameter name for
        call-site backward-compatibility (PricingViewSet.verify_payment
        already passes this kwarg) -- it's really "provider_transaction_id".
        Paystack doesn't use it (it verifies by our own reference), but
        Flutterwave needs its own transaction id to verify, so the plumbing
        stays in place for when that's re-enabled.
        """
        transaction_obj = Transaction.objects.get(id=transaction_id)

        if transaction_obj.status == "successful":
            return {"status": "success", "transaction": transaction_obj}

        for attempt in range(self.max_retries):
            try:
                result = self.provider.verify_transaction(
                    transaction=transaction_obj,
                    provider_transaction_id=flutterwave_transaction_id,
                )
            except PaymentProviderError as e:
                logger.error(f"Payment verification error (attempt {attempt + 1}): {e}")
                if attempt == self.max_retries - 1:
                    transaction_obj.status = "failed"
                    transaction_obj.error_message = (
                        f"Verification failed after {self.max_retries} attempts: {e}"
                    )
                    transaction_obj.save()
                    raise
                time.sleep(self.retry_delay)
                continue

            amount_ok = result["amount"] >= Decimal(str(transaction_obj.amount))
            currency_ok = result["currency"] == transaction_obj.currency

            if result["status"] == "successful" and amount_ok and currency_ok:
                with db_transaction.atomic():
                    # Lock the row and re-check: the webhook may have activated
                    # this same payment while we were talking to the provider.
                    transaction_obj = Transaction.objects.select_for_update().get(
                        pk=transaction_obj.pk
                    )
                    if transaction_obj.status == "successful":
                        return {"status": "success", "transaction": transaction_obj}
                    transaction_obj.status = "successful"
                    transaction_obj.completed_at = timezone.now()
                    transaction_obj.save()
                    self._activate_user_plan(transaction_obj.user, transaction_obj.plan)

                logger.info(
                    f"Payment successful for user {transaction_obj.user.email}, "
                    f"transaction {transaction_obj.id}"
                )
                return {"status": "success", "transaction": transaction_obj}

            if result["status"] == "successful" and (not amount_ok or not currency_ok):
                transaction_obj.status = "failed"
                transaction_obj.error_message = (
                    "Amount/currency mismatch on verification — possible tampering"
                )
                transaction_obj.save()
                return {"status": "failed", "message": transaction_obj.error_message}

            if result["status"] == "pending":
                transaction_obj.status = "pending"
                transaction_obj.save(update_fields=["status"])
                return {"status": "pending", "message": "Payment is pending verification"}

            transaction_obj.status = "failed"
            transaction_obj.error_message = "Payment failed"
            transaction_obj.save()
            return {"status": "failed", "message": transaction_obj.error_message}

        return {"status": "failed", "message": "Payment verification failed"}

    def _activate_user_plan(self, user, plan):
        """
        Must be called inside db_transaction.atomic() (both callers do), so
        the select_for_update() row lock below is valid.

        Pro:
          - first purchase           -> end_date = now + 30d
          - renewal while still live -> end_date += 30d (remaining time kept)
          - expired / other plan     -> fresh period, end_date = now + 30d
        PAYG:
          - every successful payment -> +1 credit (credits persist until used)
          - a live Pro plan is NOT downgraded by a PAYG purchase
        Free: unchanged.
        """
        now = timezone.now()
        is_pro = plan.plan_type == "pro"
        is_payg = plan.plan_type == "payg"

        defaults = {
            "plan": plan,
            "is_active": True,
            "start_date": now,
        }
        if is_pro:
            defaults["end_date"] = now + PRO_PERIOD
        if is_payg:
            defaults["payg_credits"] = 1

        user_plan, created = UserPlan.objects.get_or_create(user=user, defaults=defaults)

        if not created:
            # Serialise concurrent activations for the same user. No
            # select_related: that would also lock the shared Plan row.
            user_plan = UserPlan.objects.select_for_update().get(pk=user_plan.pk)

            if is_pro:
                still_active_pro = (
                    user_plan.plan.plan_type == "pro"
                    and user_plan.is_active
                    and user_plan.end_date is not None
                    and user_plan.end_date > now
                )
                if still_active_pro:
                    user_plan.end_date = user_plan.end_date + PRO_PERIOD
                else:
                    user_plan.plan = plan
                    user_plan.is_active = True
                    user_plan.start_date = now
                    user_plan.end_date = now + PRO_PERIOD
                    user_plan.campaigns_used = 0
                    user_plan.daily_generation_count = 0
            elif is_payg:
                user_plan.payg_credits += 1
                if not is_pro_live(user_plan, now):
                    user_plan.plan = plan
                    user_plan.is_active = True
            else:
                user_plan.plan = plan
                user_plan.is_active = True
                if plan.plan_type == "free":
                    user_plan.campaigns_used = 0
                    user_plan.daily_generation_count = 0

        user_plan.save()

    # ------------------------------------------------------------------
    # Webhook
    # ------------------------------------------------------------------

    def process_webhook(self, raw_body: bytes, signature: Optional[str]) -> Dict[str, Any]:
        if not self.provider.verify_webhook_signature(raw_body, signature):
            logger.error("Invalid webhook signature")
            raise ValueError("Invalid webhook signature")

        event = self.provider.parse_webhook_event(raw_body)
        if event["event"] == "ignored":
            return {"status": "ignored"}

        try:
            transaction_obj = Transaction.objects.get(provider_reference=event["reference"])
        except Transaction.DoesNotExist:
            logger.error(f"Transaction not found for ref: {event['reference']}")
            raise

        if event["status"] == "successful" and transaction_obj.status != "successful":
            with db_transaction.atomic():
                # Lock + re-check so verify_payment() and this webhook can't
                # both activate the same payment.
                transaction_obj = Transaction.objects.select_for_update().get(
                    pk=transaction_obj.pk
                )
                if transaction_obj.status == "successful":
                    return {"status": "ignored"}
                transaction_obj.status = "successful"
                transaction_obj.completed_at = timezone.now()
                transaction_obj.save()
                self._activate_user_plan(transaction_obj.user, transaction_obj.plan)
            return {"status": "success", "transaction": transaction_obj}

        # A late/duplicate "failed" event must never overwrite a paid transaction.
        if event["status"] == "failed" and transaction_obj.status != "successful":
            transaction_obj.status = "failed"
            transaction_obj.error_message = "Payment failed"
            transaction_obj.save()
            return {"status": "failed", "transaction": transaction_obj}

        return {"status": "ignored"}