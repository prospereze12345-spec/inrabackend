import hashlib
import hmac
import json
import logging
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Dict, Optional

import requests
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from .base import PaymentProvider, PaymentProviderError

logger = logging.getLogger(__name__)

INITIALIZE_URL = "https://api.paystack.co/transaction/initialize"
VERIFY_URL_TEMPLATE = "https://api.paystack.co/transaction/verify/{reference}"

# Paystack event we actually act on. There are others (transfer.success,
# subscription.*, etc) -- we don't sell subscriptions through Paystack's own
# subscription API, we just charge once per plan purchase, so everything
# else is explicitly ignored in parse_webhook_event rather than silently
# mis-handled.
HANDLED_EVENT = "charge.success"


class PaystackProvider(PaymentProvider):
    """
    Paystack Standard (hosted) checkout. NGN only -- enforced one level up
    in PaymentService.SUPPORTED_CURRENCIES, not here, so this class doesn't
    need to know about the business rule, only about the Paystack API.
    """

    signature_header_name = "x-paystack-signature"

    def __init__(self):
        self.secret_key = getattr(settings, "PAYSTACK_SECRET_KEY", None)
        if not self.secret_key:
            raise ImproperlyConfigured(
                "PAYSTACK_SECRET_KEY is not set in settings/.env -- required for "
                "Paystack's hosted checkout. Get it from the Paystack dashboard "
                "under Settings > API Keys & Webhooks."
            )

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.secret_key}",
            "Content-Type": "application/json",
        }

    @staticmethod
    def _to_kobo(amount: Decimal) -> int:
        return int((amount * 100).to_integral_value(rounding=ROUND_HALF_UP))

    @staticmethod
    def _from_kobo(amount: Any) -> Decimal:
        return Decimal(str(amount)) / Decimal("100")

    def initialize_transaction(self, *, user, transaction) -> Dict[str, Any]:
        payload = {
            "email": user.email,
            "amount": self._to_kobo(transaction.amount),
            "currency": transaction.currency,
            # We generate the reference ourselves at Transaction-creation
            # time (see PaymentService.initiate_payment) so it's stable
            # across retries -- Paystack accepts a client-supplied
            # reference instead of only returning its own.
            "reference": transaction.provider_reference,
            "callback_url": getattr(
                settings,
                "PAYSTACK_CALLBACK_URL",
                "https://inrastudio.vercel.app/payment/verify",
            ),
            "metadata": {
                # str() matters here: `requests` serializes `json=` with
                # plain stdlib json.dumps, which (unlike DRF's response
                # encoder) doesn't know how to handle a UUID -- and many
                # Supabase-backed User models use UUID primary keys, not
                # ints. Without this, initialize_transaction blows up with
                # "Object of type UUID is not JSON serializable" before
                # the request ever reaches Paystack.
                "user_id": str(user.id),
                "plan_type": transaction.plan.plan_type,
            },
        }

        try:
            response = requests.post(
                INITIALIZE_URL, json=payload, headers=self._headers(), timeout=15
            )
            response.raise_for_status()
            data = response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Paystack initialize request failed: {e}")
            raise PaymentProviderError(f"Could not reach Paystack: {e}")

        if not data.get("status"):
            raise PaymentProviderError(data.get("message", "Paystack initialization failed"))

        return {
            "redirect_url": data["data"]["authorization_url"],
            "provider_reference": data["data"]["reference"],
        }

    def verify_transaction(
        self, *, transaction, provider_transaction_id: Optional[str] = None
    ) -> Dict[str, Any]:
        # Paystack verifies by the reference *we* generated at init time --
        # provider_transaction_id is accepted only so this method's
        # signature matches the shared interface (Flutterwave verifies by
        # its own transaction id and needs that argument); Paystack ignores
        # it.
        url = VERIFY_URL_TEMPLATE.format(reference=transaction.provider_reference)

        try:
            response = requests.get(url, headers=self._headers(), timeout=15)
            response.raise_for_status()
            body = response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Paystack verify request failed: {e}")
            raise PaymentProviderError(f"Could not reach Paystack: {e}")

        if not body.get("status"):
            raise PaymentProviderError(body.get("message", "Paystack verification failed"))

        data = body["data"]
        # Paystack statuses: success | failed | abandoned | reversed | ...
        status_map = {
            "success": "successful",
            "abandoned": "pending",
        }

        return {
            "status": status_map.get(data.get("status"), "failed"),
            "amount": self._from_kobo(data.get("amount", 0)),
            "currency": data.get("currency"),
            "raw": data,
        }

    def verify_webhook_signature(self, raw_body: bytes, signature: Optional[str]) -> bool:
        if not signature:
            return False
        expected = hmac.new(
            self.secret_key.encode("utf-8"), raw_body, hashlib.sha512
        ).hexdigest()
        return hmac.compare_digest(expected, signature)

    def parse_webhook_event(self, raw_body: bytes) -> Dict[str, Any]:
        payload = json.loads(raw_body)
        event = payload.get("event")

        if event != HANDLED_EVENT:
            return {"event": "ignored"}

        data = payload.get("data", {})
        return {
            "event": event,
            "reference": data.get("reference"),
            "status": "successful" if data.get("status") == "success" else "failed",
            "amount": self._from_kobo(data.get("amount", 0)),
            "currency": data.get("currency"),
        }