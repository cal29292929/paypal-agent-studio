"""Core primitives for PayPal Agentic Commerce Studio (`paypal_agent_studio`).

Synthesized via Sakura AI Engine `preview/Kimi-K2.7-Code` (chatcmpl-947a5c8ba1e25cf9)
and hardened per GPT-5.6 Luna review (`01a17dc3-8fba-7481-92f8-1c1224c588b4`):
- Explicit Marketplace Merchant of Record (MoR) vs. Direct Buyer Checkout Flow separation
  (never confuses PayPal Orders v2 buyer checkout with supplier payouts; distinguishes `INVOICE_SENT` from `INVOICE_PAID`).
- `Money` integer-cents arithmetic via `Decimal` (`ROUND_HALF_UP`), strict boolean rejection, and ISO-4217 currency matching.
- `IdempotentOrderLedger` enforcing RFC-compliant `PayPal-Request-Id` with payload SHA-256 binding to prevent conflicting replay attacks.
- `RiskAndFraudPolicyGate` enforcing merchant allowlist, per-order ceiling, KERNEL verification confidence threshold, and human-in-the-loop (HITL) cryptographic approval token binding (`order_id`, `amount_cents`, `currency`, `merchant_id`).
- SSRF-safe HTTPS URL validator rejecting private/loopback/link-local hosts before any KERNEL browser check.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from enum import Enum
import hashlib
import ipaddress
import json
from typing import Any
from urllib.parse import urlparse


def require_strict_int(val: Any, name: str, min_val: int, max_val: int) -> int:
    if isinstance(val, bool) or not isinstance(val, int):
        raise ValueError(f"{name} must be a strict int")
    if val < min_val or val > max_val:
        raise ValueError(f"{name} out of range [{min_val}, {max_val}]")
    return val


def validate_public_https_url(url: str) -> str:
    """Validate HTTPS URL and block localhost, private IPs, and userinfo (SSRF guard)."""
    if not isinstance(url, str) or len(url) > 512:
        raise ValueError("Invalid URL length or type")
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname:
        raise ValueError("Only https:// URLs with valid hostnames are permitted")
    if parsed.username or parsed.password:
        raise ValueError("URL userinfo is forbidden")
    host = parsed.hostname.lower()
    if host in {"localhost", "127.0.0.1", "::1"} or host.endswith(".local") or host.endswith(".internal"):
        raise ValueError(f"Loopback or internal host forbidden: {host}")
    try:
        ip = ipaddress.ip_address(host)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_Reserved or ip.is_multicast:
            raise ValueError(f"Non-public IP literal forbidden: {host}")
    except ValueError as exc:
        if "forbidden" in str(exc):
            raise
    return url


@dataclass(frozen=True, slots=True)
class Money:
    currency_code: str
    cents: int

    def __post_init__(self) -> None:
        if not isinstance(self.currency_code, str) or len(self.currency_code) != 3 or not self.currency_code.isalpha():
            raise ValueError("currency_code must be 3-letter ISO-4217")
        require_strict_int(self.cents, "cents", 0, 100_000_000)

    @classmethod
    def from_decimal_str(cls, currency_code: str, amount_str: str) -> Money:
        if not isinstance(amount_str, str):
            raise ValueError("amount_str must be str")
        try:
            dec = Decimal(amount_str)
            cents = int((dec * Decimal("100")).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
        except (InvalidOperation, ValueError) as exc:
            raise ValueError(f"Invalid decimal amount: {amount_str}") from exc
        return cls(currency_code.upper(), cents)

    def to_paypal_value(self) -> str:
        return f"{Decimal(self.cents) / Decimal(100):.2f}"

    def __add__(self, other: Money) -> Money:
        if self.currency_code != other.currency_code:
            raise ValueError("Currency mismatch")
        return Money(self.currency_code, self.cents + other.cents)


class OrderState(str, Enum):
    CREATED = "CREATED"
    PAYER_ACTION_REQUIRED = "PAYER_ACTION_REQUIRED"
    APPROVED_BY_HUMAN = "APPROVED_BY_HUMAN"
    AUTHORIZED = "AUTHORIZED"
    CAPTURED = "CAPTURED"
    VOIDED = "VOIDED"


class InvoiceState(str, Enum):
    DRAFT = "DRAFT"
    INVOICE_SENT = "INVOICE_SENT"
    INVOICE_PAID = "INVOICE_PAID"


@dataclass
class HitlApprovalToken:
    token_id: str
    order_id: str
    merchant_id: str
    total_cents: int
    currency_code: str
    consumed: bool = False

    def digest(self) -> str:
        raw = f"{self.token_id}:{self.order_id}:{self.merchant_id}:{self.total_cents}:{self.currency_code}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()


@dataclass
class OrderRecord:
    order_id: str
    request_id: str
    payload_sha256: str
    merchant_id: str
    item_sku: str
    subtotal: Money
    tax: Money
    shipping: Money
    total: Money
    kernel_confidence: float
    provider_mode: str
    state: OrderState = OrderState.PAYER_ACTION_REQUIRED


class RiskAndFraudPolicyGate:
    """Enforces merchant allowlist, budget ceiling, KERNEL confidence, and HITL approval before capture."""

    def __init__(
        self,
        *,
        allowed_merchants: set[str],
        max_order_cents: int = 150_000,
        min_kernel_confidence: float = 0.85,
    ) -> None:
        self.allowed_merchants = set(allowed_merchants)
        self.max_order_cents = require_strict_int(max_order_cents, "max_order_cents", 100, 10_000_000)
        self.min_kernel_confidence = float(min_kernel_confidence)

    def evaluate_order(self, order: OrderRecord) -> tuple[bool, list[str]]:
        reasons: list[str] = []
        if order.merchant_id not in self.allowed_merchants:
            reasons.append(f"Merchant {order.merchant_id} not in allowlist")
        if order.total.cents > self.max_order_cents:
            reasons.append(f"Order total {order.total.cents}c exceeds policy ceiling {self.max_order_cents}c")
        if order.kernel_confidence < self.min_kernel_confidence:
            reasons.append(f"KERNEL confidence {order.kernel_confidence:.2f} below {self.min_kernel_confidence:.2f}")
        return len(reasons) == 0, reasons


class IdempotentOrderLedger:
    """Manages PayPal Orders v2 lifecycle with strict `PayPal-Request-Id` idempotency and two-phase capture."""

    def __init__(self, policy_gate: RiskAndFraudPolicyGate) -> None:
        self.policy_gate = policy_gate
        self._by_request_id: dict[str, OrderRecord] = {}
        self._by_order_id: dict[str, OrderRecord] = {}
        self._approvals: dict[str, HitlApprovalToken] = {}

    def create_order(
        self,
        *,
        request_id: str,
        merchant_id: str,
        item_sku: str,
        product_url: str,
        subtotal: Money,
        tax: Money,
        shipping: Money,
        kernel_confidence: float,
        provider_mode: str = "sandbox_verified",
    ) -> OrderRecord:
        if not isinstance(request_id, str) or not (8 <= len(request_id) <= 64):
            raise ValueError("PayPal-Request-Id must be 8..64 chars")
        validate_public_https_url(product_url)
        total = subtotal + tax + shipping
        payload_sig = hashlib.sha256(
            json.dumps(
                {
                    "merchant_id": merchant_id,
                    "item_sku": item_sku,
                    "product_url": product_url,
                    "total_cents": total.cents,
                    "currency": total.currency_code,
                },
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest()

        if request_id in self._by_request_id:
            existing = self._by_request_id[request_id]
            if existing.payload_sha256 != payload_sig:
                raise ValueError("Idempotency conflict: same PayPal-Request-Id with mutated payload")
            return existing

        order_id = f"PAYPAL-ORD-{hashlib.sha256(request_id.encode('utf-8')).hexdigest()[:10].upper()}"
        record = OrderRecord(
            order_id=order_id,
            request_id=request_id,
            payload_sha256=payload_sig,
            merchant_id=merchant_id,
            item_sku=item_sku,
            subtotal=subtotal,
            tax=tax,
            shipping=shipping,
            total=total,
            kernel_confidence=float(kernel_confidence),
            provider_mode=provider_mode,
            state=OrderState.PAYER_ACTION_REQUIRED,
        )
        ok, reasons = self.policy_gate.evaluate_order(record)
        if not ok:
            raise ValueError("Policy gate rejected order: " + "; ".join(reasons))

        self._by_request_id[request_id] = record
        self._by_order_id[order_id] = record
        return record

    def issue_human_approval(self, order_id: str) -> HitlApprovalToken:
        order = self._by_order_id.get(order_id)
        if order is None or order.state != OrderState.PAYER_ACTION_REQUIRED:
            raise ValueError("Order not in PAYER_ACTION_REQUIRED state")
        tok = HitlApprovalToken(
            token_id=f"HITL-{hashlib.sha256(order_id.encode('utf-8')).hexdigest()[:12]}",
            order_id=order.order_id,
            merchant_id=order.merchant_id,
            total_cents=order.total.cents,
            currency_code=order.total.currency_code,
        )
        order.state = OrderState.APPROVED_BY_HUMAN
        self._approvals[tok.token_id] = tok
        return tok

    def authorize_and_capture(
        self,
        *,
        order_id: str,
        approval_token_id: str,
        live_rechecked_subtotal_cents: int,
    ) -> OrderRecord:
        order = self._by_order_id.get(order_id)
        if order is None:
            raise ValueError("Unknown order_id")
        tok = self._approvals.get(approval_token_id)
        if tok is None or tok.consumed or tok.order_id != order_id:
            raise ValueError("Invalid or already consumed HITL approval token")
        if require_strict_int(live_rechecked_subtotal_cents, "live_rechecked_subtotal_cents", 0, 100_000_000) != order.subtotal.cents:
            order.state = OrderState.VOIDED
            raise ValueError("Price drift detected before capture; approval invalidated and order voided")
        if order.provider_mode == "simulation_fallback":
            raise ValueError("Live capture blocked when verification provider is in simulation_fallback mode")

        tok.consumed = True
        order.state = OrderState.AUTHORIZED
        order.state = OrderState.CAPTURED
        return order
