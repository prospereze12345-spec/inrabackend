"""
Not active right now (PAYMENT_PROVIDER=paystack) -- kept behind the same
PaymentProvider interface so re-enabling Flutterwave later is a one-line
settings change (PAYMENT_PROVIDER="flutterwave"), not a rewrite. This is a
straight port of the logic that used to live directly inside
PaymentService before the Paystack switch.

Before actually flipping back to this: re-verify the webhook signature
scheme against Flutterwave's current docs. Flutterwave's dashboard
"Secret Hash" is historically compared to the `verif-hash` header
*directly* (not HMAC'd) -- the HMAC-SHA256 approach below mirrors what was
in the pre-refactor code, but double-check that against Flutterwave's
current documentation before trusting it in production.
"""
import hashlib
import hmac
import json
import logging
from decimal import Decimal
from typing import Any, Dict, Optional

import requests
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from .base import PaymentProvider, PaymentProviderError

logger = logging.getLogger(__name__)

HOSTED_CHECKOUT_URL = "https://api.flutterwave.com/v3/payments"
VERIFY_URL_TEMPLATE = "https://api.flutterwave.com/v3/transactions/{id}/verify"

# Flutterwave's v3 Standard (hosted) checkout supports card, bank transfer,
# USSD, and mobile money in ONE flow via `payment_options` -- add a
# currency here and every plan priced in it gets the right local payment
# methods automatically.
CURRENCY_PAYMENT_OPTIONS = {
    "USD": "card",
    "NGN": "card,banktransfer,ussd",
    "GHS": "card,mobilemoneygh",
    "KES": "card,mpesa",
    "ZAR": "card",
    "EGP": "card",
}
DEFAULT_PAYMENT_OPTIONS = "card"


class FlutterwaveProvider(PaymentProvider):
    signature_header_name = "verif-hash"

    def __init__(self):
        self.secret_key = getattr(settings, "FLUTTERWAVE_SECRET_KEY", None)
        if not self.secret_key:
            raise ImproperlyConfigured(
                "FLUTTERWAVE_SECRET_KEY is not set in settings/.env -- required "
                "for Flutterwave's v3 hosted checkout."
            )

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.secret_key}",
            "Content-Type": "application/json",
        }

    def initialize_transaction(self, *, user, transaction) -> Dict[str, Any]:
        payload = {
            "tx_ref": transaction.provider_reference,
            "amount": float(transaction.amount),
            "currency": transaction.currency,
            "payment_options": CURRENCY_PAYMENT_OPTIONS.get(
                transaction.currency, DEFAULT_PAYMENT_OPTIONS
            ),
            "redirect_url": getattr(
                settings,
                "FLUTTERWAVE_REDIRECT_URL",
                "https://inrastudio.vercel.app/payment/verify",
            ),
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
            raise PaymentProviderError(f"Could not reach Flutterwave: {e}")

        if data.get("status") == "success":
            return {
                "redirect_url": data["data"]["link"],
                "provider_reference": transaction.provider_reference,
            }
        raise PaymentProviderError(data.get("message", "Checkout initialization failed"))

    def verify_transaction(
        self, *, transaction, provider_transaction_id: Optional[str] = None
    ) -> Dict[str, Any]:
        if not provider_transaction_id:
            raise PaymentProviderError(
                "Flutterwave verification requires the provider's transaction id "
                "(the id Flutterwave appends to the redirect, distinct from our "
                "own tx_ref)."
            )

        url = VERIFY_URL_TEMPLATE.format(id=provider_transaction_id)

        try:
            response = requests.get(url, headers=self._headers(), timeout=15)
            response.raise_for_status()
            body = response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Flutterwave verify request failed: {e}")
            raise PaymentProviderError(f"Could not reach Flutterwave: {e}")

        if body.get("status") != "success":
            raise PaymentProviderError(body.get("message", "Verification failed"))

        data = body["data"]
        status_map = {"successful": "successful", "pending": "pending"}

        return {
            "status": status_map.get(data.get("status"), "failed"),
            "amount": Decimal(str(data.get("amount", 0))),
            "currency": data.get("currency"),
            "raw": data,
        }

    def verify_webhook_signature(self, raw_body: bytes, signature: Optional[str]) -> bool:
        secret_hash = getattr(settings, "FLUTTERWAVE_WEBHOOK_SECRET_HASH", None)
        if not secret_hash or not signature:
            return False
        expected = hmac.new(
            secret_hash.encode("utf-8"), raw_body, hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(expected, signature)

    def parse_webhook_event(self, raw_body: bytes) -> Dict[str, Any]:
        payload = json.loads(raw_body)
        if payload.get("event") != "charge.completed":
            return {"event": "ignored"}

        data = payload.get("data", {})
        return {
            "event": "charge.completed",
            "reference": data.get("tx_ref") or data.get("reference"),
            "status": "successful" if data.get("status") == "successful" else "failed",
            "amount": Decimal(str(data.get("amount", 0))),
            "currency": data.get("currency"),
        }