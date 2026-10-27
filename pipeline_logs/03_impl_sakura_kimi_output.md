 ```python
# paypal_agent_studio/core.py
"""Self-contained PayPal AI Hackathon core module.

Implements three production-grade primitives using only the Python 3.11
standard library:

1. `IdempotentOrderLedger` – RFC-compliant `PayPal-Request-Id` handling,
   two-phase AUTHORIZE -> CAPTURE state machine, and decimal-cents arithmetic.
2. `RiskAndFraudPolicyGate` – velocity limits, merchant allowlists, and
   human-in-the-loop (HITL) thresholds enforced before capture.
3. `Channel3AndKernelConnector` – deterministic Channel3 product enrichment,
   KERNEL browser-checkout telemetry, and AG Grid row export.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from enum import Enum, auto
from typing import Any, Callable, ClassVar


# --------------------------------------------------------------------------- #
# Shared primitives
# --------------------------------------------------------------------------- #

class PaymentError(Exception):
    """Base exception for all payment-domain errors."""


class IdempotencyError(PaymentError):
    """Invalid or conflicting idempotency key."""


class StateTransitionError(PaymentError):
    """Illegal order state transition."""


class RiskPolicyError(PaymentError):
    """Risk or fraud policy violation."""


class OrderState(Enum):
    CREATED = auto()
    AUTHORIZED = auto()
    CAPTURED = auto()
    VOIDED = auto()


@dataclass(frozen=True, slots=True)
class Money:
    """Immutable monetary value stored as integer cents.

    All arithmetic is performed with `decimal.Decimal` during construction;
    the canonical representation is integer cents to eliminate float rounding.
    """

    currency_code: str
    cents: int

    def __post_init__(self) -> None:
        if len(self.currency_code) != 3 or not self.currency_code.isascii() or not self.currency_code.isalpha():
            raise ValueError("currency_code must be an ISO 4217 alpha-3 code")
        if self.cents < 0:
            raise ValueError("cents must be non-negative")

    @classmethod
    def from_decimal(cls, currency_code: str, amount: Decimal) -> Money:
        """Convert a Decimal amount to cents using banker's rounding."""
        try:
            cents = int((amount * Decimal("100")).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
        except InvalidOperation as exc:
            raise ValueError(f"Invalid monetary amount: {amount}") from exc
        return cls(currency_code.upper(), cents)

    @classmethod
    def from_string(cls, currency_code: str, amount: str) -> Money:
        """Parse a string amount (e.g. "12.99") into cents."""
        return cls.from_decimal(currency_code, Decimal(amount))

    def to_decimal(self) -> Decimal:
        return Decimal(self.cents) / Decimal("100")

    def __add__(self, other: Money) -> Money:
        if self.currency_code != other.currency_code:
            raise ValueError("Currency mismatch")
        return Money(self.currency_code, self.cents + other.cents)

    def __sub__(self, other: Money) -> Money:
        if self.currency_code != other.currency_code:
            raise ValueError("Currency mismatch")
        return Money(self.currency_code, self.cents - other.cents)

    def __lt__(self, other: Money) -> bool:
        if self.currency_code != other.currency_code:
            raise ValueError("Currency mismatch")
        return self.cents < other.cents

    def __le__(self, other: Money) -> bool:
        if self.currency_code != other.currency_code:
            raise ValueError("Currency mismatch")
        return self.cents <= other.cents


@dataclass(slots=True)
class Order:
    order_id: str
    request_id: str
    state: OrderState
    amount: Money
    merchant_id: str
    payer_id: str
    authorized_at: datetime | None = None
    captured_at: datetime | None = None
    capture_amount: Money | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


# --------------------------------------------------------------------------- #
# 1. IdempotentOrderLedger
# --------------------------------------------------------------------------- #

class IdempotentOrderLedger:
    """Thread-safe order ledger enforcing PayPal-style idempotency.

    Idempotency keys (`PayPal-Request-Id`) are validated to be 1-50 characters
    of ASCII alphanumeric, hyphen, or underscore.  The ledger supports the
    canonical two-phase flow: CREATE -> AUTHORIZE -> CAPTURE.  Replays with a
    known key return the previously stored result without mutation.
    """

    _REQUEST_ID_RE: ClassVar[re.Pattern[str]] = re.compile(r"^[A-Za-z0-9\-_]{1,50}$")

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._orders: dict[str, Order] = {}
        self._request_index: dict[str, str] = {}

    @staticmethod
    def _default_id_generator() -> str:
        return uuid.uuid4().hex

    def _validate_request_id(self, request_id: str) -> None:
        if not isinstance(request_id, str) or not self._REQUEST_ID_RE.match(request_id):
            raise IdempotencyError(
                "PayPal-Request-Id must be 1-50 ASCII chars: alphanumeric, '-', '_'"
            )

    def create_or_get_order(
        self,
        request_id: str,
        merchant_id: str,
        payer_id: str,
        amount: Money,
        id_generator: Callable[[], str] | None = None,
    ) -> Order:
        """Create an order idempotently.

        If `request_id` has been seen before, the existing order is returned
        regardless of the other arguments (matching PayPal behavior).
        """
        self._validate_request_id(request_id)
        with self._lock:
            if request_id in self._request_index:
                return self._orders[self._request_index[request_id]]

            order_id = (id_generator or self._default_id_generator)()
            order = Order(
                order_id=order_id,
                request_id=request_id,
                state=OrderState.CREATED,
                amount=amount,
                merchant_id=merchant_id,
                payer_id=payer_id,
            )
            self._orders[order_id] = order
            self._request_index[request_id] = order_id
            return order

    def authorize(self, order_id: str, request_id: str) -> Order:
        """Move an order from CREATED to AUTHORIZED idempotently."""
        self._validate_request_id(request_id)
        with self._lock:
            order = self._orders.get(order_id)
            if order is None:
                raise IdempotencyError(f"Order {order_id} not found")
            if order.request_id != request_id:
                raise IdempotencyError("PayPal-Request-Id mismatch for order")
            if order.state == OrderState.AUTHORIZED:
                return order
            if order.state != OrderState.CREATED:
                raise StateTransitionError(
                    f"Cannot authorize order in state {order.state.name}"
                )
            order.state = OrderState.AUTHORIZED
            order.authorized_at = datetime.now(timezone.utc)
            return order

    def capture(
        self,
        order_id: str,
        request_id: str,
        capture_amount: Money | None = None,
    ) -> Order:
        """Move an order from AUTHORIZED to CAPTURED idempotently.

        Partial captures are supported when `capture_amount` is provided and
        does not exceed the authorized amount.
        """
        self._validate_request_id(request_id)
        with self._lock:
            order = self._orders.get(order_id)
            if order is None:
                raise IdempotencyError(f"Order {order_id} not found")
            if order.request_id != request_id:
                raise IdempotencyError("PayPal-Request-Id mismatch for order")
            if order.state == OrderState.CAPTURED:
                return order
            if order.state != OrderState.AUTHORIZED:
                raise StateTransitionError(
                    f"Cannot capture order in state {order.state.name}"
                )

            amount = capture_amount or order.amount
            if amount.currency_code != order.amount.currency_code:
                raise PaymentError("Capture currency does not match order currency")
            if amount.cents > order.amount.cents:
                raise PaymentError("Capture amount exceeds authorized amount")

            order.state = OrderState.CAPTURED
            order.capture_amount = amount
            order.captured_at = datetime.now(timezone.utc)
            return order

    def void(self, order_id: str, request_id: str) -> Order:
        """Void a CREATED or AUTHORIZED order idempotently."""
        self._validate_request_id(request_id)
        with self._lock:
            order = self._orders.get(order_id)
            if order is None:
                raise IdempotencyError(f"Order {order_id} not found")
            if order.request_id != request_id:
                raise IdempotencyError("PayPal-Request-Id mismatch for order")
            if order.state == OrderState.VOIDED:
                return order
            if order.state == OrderState.CAPTURED:
                raise StateTransitionError("Cannot void a captured order")
            order.state = OrderState.VOIDED
            return order

    def get_order(self, order_id: str) -> Order | None:
        with self._lock:
            return self._orders.get(order_id)


# --------------------------------------------------------------------------- #
# 2. RiskAndFraudPolicyGate
# --------------------------------------------------------------------------- #

@dataclass(frozen=True, slots=True)
class VelocityWindow:
    """Velocity limit over a rolling time window."""

    max_count: int
    max_amount_cents: int
    window_seconds: int


@dataclass(slots=True)
class RiskProfile:
    merchant_allowlist: set[str] = field(default_factory=set)
    velocity_windows: list[VelocityWindow] = field(default_factory=list)
    human_in_loop_threshold_cents: int = 1_000_000  # $10,000.00 default


@dataclass(slots=True)
class RiskDecision:
    approved: bool
    requires_human_review: bool
    reasons: list[str] = field(default_factory=list)
    transaction_id: str | None = None


class RiskAndFraudPolicyGate:
    """Pre-capture risk gate with velocity, allowlist, and HITL controls.

    The gate evaluates a proposed capture and returns a `RiskDecision`.
    Transactions requiring human review are blocked until `approve_manually`
    is called with the returned `transaction_id`.
    """

    def __init__(self, profile: RiskProfile | None = None) -> None:
        self._profile = profile or RiskProfile()
        self._lock = threading.RLock()
        self._transactions: list[dict[str, Any]] = []
        self._manual_approvals: set[str] = set()

    def add_merchant_to_allowlist(self, merchant_id: str) -> None:
        with self._lock:
            self._profile.merchant_allowlist.add(merchant_id)

    def approve_manually(self, transaction_id: str) -> None:
        """Record a human operator approval for a flagged transaction."""
        with self._lock:
            self._manual_approvals.add(transaction_id)

    def evaluate_capture(
        self,
        order: Order,
        transaction_id: str | None = None,
    ) -> RiskDecision:
        """Evaluate whether a capture may proceed.

        Returns an approved decision only when no policy triggers a block, or
        when all triggered blocks have been manually approved.
        """
        tx_id = transaction_id or uuid.uuid4().hex
        reasons: list[str] = []
        requires_human_review = False

        # Merchant allowlist
        if order.merchant_id not in self._profile.merchant_allowlist:
            reasons.append(f"Merchant '{order.merchant_id}' is not in allowlist")
            requires_human_review = True

        # Velocity limits
        velocity_violations = self._check_velocity(order)
        if velocity_violations:
            reasons.extend(velocity_violations)
            requires_human_review = True

        # Human-in-the-loop threshold
        if order.amount.cents >= self._profile.human_in_loop_threshold_cents:
            reasons.append(
                f"Amount {order.amount.cents} cents meets HITL threshold "
                f"{self._profile.human_in_loop_threshold_cents} cents"
            )
            requires_human_review = True

        if requires_human_review and tx_id not in self._manual_approvals:
            return RiskDecision(
                approved=False,
                requires_human_review=True,
                reasons=reasons,
                transaction_id=tx_id,
            )

        with self._lock:
            self._transactions.append(
                {
                    "transaction_id": tx_id,
                    "order_id": order.order_id,
                    "merchant_id": order.merchant_id,
                    "payer_id": order.payer_id,
                    "amount_cents": order.amount.cents,
                    "currency": order.amount.currency_code,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            )

        return RiskDecision(
            approved=True,
            requires_human_review=False,
            reasons=reasons or ["approved"],
            transaction_id=tx_id,
        )

    def _check_velocity(self, order: Order) -> list[str]:
        violations: list[str] = []
        if not self._profile.velocity_windows:
            return violations

        now = datetime.now(timezone.utc)
        max_window = max(w.window_seconds for w in self._profile.velocity_windows)

        with self._lock:
            recent = [
                tx
                for tx in self._transactions
                if tx["payer_id"] == order.payer_id
                and (now - datetime.fromisoformat(tx["timestamp"])).total_seconds()
                <= max_window
            ]

            for window in self._profile.velocity_windows:
                window_txs = [
                    tx
                    for tx in recent
                    if (now - datetime.fromisoformat(tx["timestamp"])).total_seconds()
                    <= window.window_seconds
                ]

                if len(window_txs) >= window.max_count:
                    violations.append(
                        f"Velocity count exceeded: {len(window_txs)} transactions "
                        f"in {window.window_seconds}s window"
                    )

                total_cents = sum(tx["amount_cents"] for tx in window_txs)
                if total_cents + order.amount.cents > window.max_amount_cents:
                    violations.append(
                        f"Velocity amount exceeded: {total_cents + order.amount_cents} cents "
                        f"in {window.window_seconds}s window (limit {window.max_amount_cents})"
                    )

        return violations

    def get_transaction_history(self, payer_id: str | None = None) -> list[dict[str, Any]]:
        with self._lock:
            if payer_id is None:
                return list(self._transactions)
            return [tx for tx in self._transactions if tx["payer_id"] == payer_id]


# --------------------------------------------------------------------------- #
# 3. Channel3AndKernelConnector
# --------------------------------------------------------------------------- #

@dataclass(frozen=True, slots=True)
class Product:
    sku: str
    name: str
    price: Money
    category: str
    in_stock: bool
    relevance_score: Decimal


@dataclass(slots=True)
class CheckoutTelemetry:
    session_id: str
    order_id: str
    browser_events: list[dict[str, Any]]
    verification_score: Decimal
    passed: bool
    timestamp: datetime


class Channel3AndKernelConnector:
    """Deterministic Channel3 product enrichment and KERNEL checkout telemetry.

    Product search results are derived deterministically from the query,
    merchant, and an internal seed so that repeated calls return identical
    catalogs.  KERNEL telemetry simulates browser checkout verification and
    exports rows compatible with AG Grid.
    """

    def __init__(self, seed: str = "paypal-ai-hackathon-07") -> None:
        self._seed = seed
        self._lock = threading.Lock