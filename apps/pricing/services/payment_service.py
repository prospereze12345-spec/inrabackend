import hashlib
import hmac
import base64
import json
import logging
import time
from decimal import Decimal
from typing import Any, Dict

import requests
from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import ImproperlyConfigured
from django.db import transaction as db_transaction
from django.utils import timezone

from ..constants import FALLBACK_EXCHANGE_RATES, get_user_currency
from ..models import Plan, Transaction, UserPlan

logger = logging.getLogger(__name__)

HOSTED_CHECKOUT_URL = "https://api.flutterwave.com/v3/payments"
VERIFY_URL_TEMPLATE = "https://api.flutterwave.com/v3/transactions/{id}/verify"

# Flutterwave's v3 Standard (hosted) checkout already supports card, bank
# transfer, USSD, and mobile money in ONE flow -- it just needs to know
# which rails are valid for the transaction currency via `payment_options`.
# Add a currency here and every plan priced in it gets the right local
# payment methods automatically, with zero frontend changes.
CURRENCY_PAYMENT_OPTIONS = {
    "USD": "card",
    "NGN": "card,banktransfer,ussd",
    "GHS": "card,mobilemoneygh",
    "KES": "card,mpesa",
    "ZAR": "card",
    "EGP": "card",
}
DEFAULT_PAYMENT_OPTIONS = "card"


class PaymentService:
    """Handles all payment operations with idempotency and retry logic.

    Uses Flutterwave's v3 Standard (hosted) checkout exclusively. This one
    endpoint already covers card, bank transfer, USSD, and mobile money --
    Flutterwave decides which of those to show the customer based on
    `payment_options` + the transaction currency. There is no separate v4
    OAuth client and no custom channel-picker UI needed to support multiple
    countries/currencies.
    """

    def __init__(self):
        self.max_retries = 3
        self.retry_delay = 60

        self.secret_key = getattr(settings, "FLUTTERWAVE_SECRET_KEY", None)
        if not self.secret_key:
            raise ImproperlyConfigured(
                "FLUTTERWAVE_SECRET_KEY is not set in settings/.env — required for "
                "Flutterwave's v3 hosted checkout (/v3/payments). Get it from your "
                "Flutterwave dashboard under Settings > API > Test/Live API keys."
            )

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.secret_key}",
            "Content-Type": "application/json",
        }

    # ------------------------------------------------------------------
    # Currency / pricing
    # ------------------------------------------------------------------

    def _get_exchange_rate(self, currency: str) -> Decimal:
        if currency == "USD":
            return Decimal("1.0")

        cache_key = f"exchange_rate_{currency}"
        cached = cache.get(cache_key)
        if cached is not None:
            return Decimal(str(cached))

        rate = FALLBACK_EXCHANGE_RATES.get(currency, Decimal("1.0"))
        cache.set(cache_key, str(rate), timeout=3600)
        return Decimal(str(rate))

    def get_plan_prices(self, user, plan_type: str) -> Dict[str, Any]:
        try:
            plan = Plan.objects.get(plan_type=plan_type)
        except Plan.DoesNotExist:
            raise ValueError(f"Plan {plan_type} not found")

        currency = get_user_currency(user)

        price_field = {
            "USD": "price_usd",
            "NGN": "price_ngn",
            "KES": "price_kes",
            "GHS": "price_ghs",
            "ZAR": "price_zar",
            "EGP": "price_egp",
        }.get(currency, "price_usd")

        return {
            "price": getattr(plan, price_field),
            "currency": currency,
            "plan": plan,
        }

    # ------------------------------------------------------------------
    # Payment initiation
    # ------------------------------------------------------------------

    def initiate_payment(self, user, plan_type: str, idempotency_key: str) -> Dict[str, Any]:
        """Initiate a payment with idempotency check.

        Returns a Flutterwave hosted-checkout `redirect_url` — the frontend
        should send the browser there immediately, no intermediate UI needed.
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
                    flutterwave_ref=f"REF_{idempotency_key[:10]}_{int(timezone.now().timestamp())}",
                    idempotency_key=idempotency_key,
                    status="pending",
                )

        try:
            payment_data = self._create_hosted_checkout(user, transaction_obj)

            transaction_obj.metadata = {
    "redirect_url": payment_data["redirect_url"],
    "plan_name": plan_data["plan"].name,
}
            transaction_obj.save()

            return {
    "status": "pending",
    "transaction": transaction_obj,
    "transaction_id": str(transaction_obj.id),   # <-- ADD THIS
    "redirect_url": payment_data["redirect_url"],
    "reference": transaction_obj.flutterwave_ref,
}

        except Exception as e:
            logger.error(f"Error initiating payment: {e}")
            transaction_obj.status = "failed"
            transaction_obj.error_message = str(e)
            transaction_obj.save()
            raise

    def _create_hosted_checkout(self, user, transaction) -> Dict[str, Any]:
        """Card / bank-transfer / USSD / mobile-money via Flutterwave's v3
        Standard hosted checkout. `payment_options` tells Flutterwave which
        local rails are valid for this currency; Flutterwave decides which
        of those to actually present to the customer.
        """
        payload = {
            "tx_ref": transaction.flutterwave_ref,
            "amount": float(transaction.amount),
            "currency": transaction.currency,
            "payment_options": CURRENCY_PAYMENT_OPTIONS.get(
                transaction.currency, DEFAULT_PAYMENT_OPTIONS
            ),
            "redirect_url": getattr(settings, "FLUTTERWAVE_REDIRECT_URL", "http://localhost:3000/payment/verify"),
            
            "customer": {
                "email": user.email,
                "name": getattr(user, "full_name", getattr(user, "username", "Customer")),
            },
            "customizations": {"title": "Inra Studio Payment"},
        }

        try:
            response = requests.post(
                HOSTED_CHECKOUT_URL, json=payload, headers=self._headers(), timeout=15
            )
            response.raise_for_status()
            data = response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Flutterwave hosted checkout request failed: {e}")
            raise Exception(f"Could not reach Flutterwave: {e}")

        if data.get("status") == "success":
            return {
    "redirect_url": data["data"]["link"],
}

        raise Exception(data.get("message", "Checkout initialization failed"))

    # ------------------------------------------------------------------
    # Verification
    # ------------------------------------------------------------------

    def verify_payment(self,transaction_id,flutterwave_transaction_id,) -> Dict[str, Any]:
        """Verify a transaction via Flutterwave's v3 verify-by-id endpoint.

        Always re-checks amount and currency against what we stored, per
        Flutterwave's own recommendation, so a tampered redirect can't be
        used to fake a successful payment.
        """
        transaction_obj = Transaction.objects.get(id=transaction_id)

        if transaction_obj.status == "successful":
            return {"status": "success", "transaction": transaction_obj}

        
        url = VERIFY_URL_TEMPLATE.format(id=flutterwave_transaction_id)
        for attempt in range(self.max_retries):
            try:
                response = requests.get(url, headers=self._headers(), timeout=15)
                response.raise_for_status()
                body = response.json()

                if body.get("status") == "success":
                    data = body["data"]
                    payment_status = data.get("status", "pending")

                    amount_ok = Decimal(str(data.get("amount", 0))) >= Decimal(
                        str(transaction_obj.amount)
                    )
                    currency_ok = data.get("currency") == transaction_obj.currency

                    if payment_status == "successful" and amount_ok and currency_ok:
                        with db_transaction.atomic():
                            transaction_obj.status = "successful"
                            transaction_obj.completed_at = timezone.now()
                            transaction_obj.save()
                            self._activate_user_plan(transaction_obj.user, transaction_obj.plan)

                        logger.info(
                            f"Payment successful for user {transaction_obj.user.email}, "
                            f"transaction {transaction_obj.id}"
                        )
                        return {"status": "success", "transaction": transaction_obj}

                    if payment_status == "successful" and (not amount_ok or not currency_ok):
                        transaction_obj.status = "failed"
                        transaction_obj.error_message = (
                            "Amount/currency mismatch on verification — possible tampering"
                        )
                        transaction_obj.save()
                        return {"status": "failed", "message": transaction_obj.error_message}

                    if payment_status == "pending":
                        transaction_obj.status = "pending"
                        transaction_obj.save(update_fields=["status"])
                        return {"status": "pending", "message": "Payment is pending verification"}

                    transaction_obj.status = "failed"
                    transaction_obj.error_message = data.get("processor_response", "Payment failed")
                    transaction_obj.save()
                    return {"status": "failed", "message": transaction_obj.error_message}

                if attempt < self.max_retries - 1:
                    time.sleep(self.retry_delay)

            except requests.exceptions.RequestException as e:
                logger.error(f"Payment verification error (attempt {attempt + 1}): {e}")
                if attempt == self.max_retries - 1:
                    transaction_obj.status = "failed"
                    transaction_obj.error_message = (
                        f"Verification failed after {self.max_retries} attempts: {e}"
                    )
                    transaction_obj.save()
                    raise

        return {"status": "failed", "message": "Payment verification failed"}

    def _activate_user_plan(self, user, plan):
        user_plan, created = UserPlan.objects.get_or_create(
            user=user,
            defaults={
                "plan": plan,
                "is_active": True,
                "start_date": timezone.now(),
            },
        )

        if not created:
            if plan.plan_type == "pro":
                if user_plan.plan.plan_type == "pro" and user_plan.is_active:
                    user_plan.end_date = timezone.now() + timezone.timedelta(days=30)
                else:
                    user_plan.plan = plan
                    user_plan.is_active = True
                    user_plan.start_date = timezone.now()
                    user_plan.campaigns_used = 0
                    user_plan.daily_generation_count = 0
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

    def process_webhook(self, raw_body: bytes, signature: str) -> Dict[str, Any]:
        secret_hash = getattr(settings, "FLUTTERWAVE_WEBHOOK_SECRET_HASH", None)
        if not secret_hash:
            raise ImproperlyConfigured(
                "FLUTTERWAVE_WEBHOOK_SECRET_HASH is not set — this must match the "
                "'Secret Hash' configured in Flutterwave dashboard > Settings > Webhooks."
            )

        expected_signature = base64.b64encode(
            hmac.new(secret_hash.encode("utf-8"), raw_body, hashlib.sha256).digest()
        ).decode("utf-8")

        if not signature or not hmac.compare_digest(signature, expected_signature):
            logger.error("Invalid webhook signature")
            raise ValueError("Invalid webhook signature")

        payload = json.loads(raw_body)
        event = payload.get("event")
        data = payload.get("data", {})

        if event != "charge.completed":
            return {"status": "ignored"}

        transaction_ref = data.get("tx_ref") or data.get("reference")
        status = data.get("status")

        try:
            transaction_obj = Transaction.objects.get(flutterwave_ref=transaction_ref)
        except Transaction.DoesNotExist:
            logger.error(f"Transaction not found for ref: {transaction_ref}")
            raise

        if status == "successful" and transaction_obj.status != "successful":
            with db_transaction.atomic():
                transaction_obj.status = "successful"
                transaction_obj.completed_at = timezone.now()
                transaction_obj.save()
                self._activate_user_plan(transaction_obj.user, transaction_obj.plan)
            return {"status": "success", "transaction": transaction_obj}

        if status == "failed":
            transaction_obj.status = "failed"
            transaction_obj.error_message = data.get("message", "Payment failed")
            transaction_obj.save()
            return {"status": "failed", "transaction": transaction_obj}

        return {"status": "ignored"}