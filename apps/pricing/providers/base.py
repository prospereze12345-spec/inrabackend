from abc import ABC, abstractmethod
from typing import Any, Dict, Optional


class PaymentProviderError(Exception):
    """Raised when a provider call fails: network error, non-2xx response,
    or a response body that doesn't indicate success. PaymentService only
    ever needs to catch this one exception type, regardless of which
    gateway is behind it."""


class PaymentProvider(ABC):
    """
    Contract every payment gateway (Paystack, Flutterwave, ...) must
    implement. PaymentService talks to *this* interface only -- it never
    imports `requests`, builds a gateway-specific payload, or knows a
    gateway's field names. That's what makes swapping/adding a provider
    a new file here instead of a rewrite of payment_service.py.
    """

    #: The HTTP header the gateway puts its webhook signature in.
    #: Read by the webhook view to know which header to pass through.
    signature_header_name: str

    @abstractmethod
    def initialize_transaction(self, *, user, transaction) -> Dict[str, Any]:
        """
        Kick off a hosted checkout for `transaction`.
        Must return: {"redirect_url": str, "provider_reference": str}
        Raises PaymentProviderError on failure.
        """
        raise NotImplementedError

    @abstractmethod
    def verify_transaction(
        self, *, transaction, provider_transaction_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Confirm payment status directly with the gateway (never trust the
        client's redirect alone). Must return:
        {"status": "successful" | "pending" | "failed",
         "amount": Decimal, "currency": str, "raw": dict}
        Raises PaymentProviderError on failure.
        """
        raise NotImplementedError

    @abstractmethod
    def verify_webhook_signature(self, raw_body: bytes, signature: Optional[str]) -> bool:
        """Return True only if `signature` proves this webhook came from
        the gateway and not from an attacker replaying a payload."""
        raise NotImplementedError

    @abstractmethod
    def parse_webhook_event(self, raw_body: bytes) -> Dict[str, Any]:
        """
        Must return either:
          {"event": "ignored"}   -- event type we don't act on
        or:
          {"event": str, "reference": str, "status": "successful"|"failed",
           "amount": Decimal, "currency": str}
        """
        raise NotImplementedError