"""Unit tests for PayPal Agentic Commerce Studio (`paypal_agent_studio`)."""

from __future__ import annotations

import pytest

from paypal_agent_studio.core import (
    IdempotentOrderLedger,
    Money,
    OrderState,
    RiskAndFraudPolicyGate,
    validate_public_https_url,
)
from paypal_agent_studio.engine import run_procurement_workflow


def test_money_decimal_cents_and_strict_bool() -> None:
    m1 = Money.from_decimal_str("USD", "19.99")
    m2 = Money.from_decimal_str("USD", "1.65")
    total = m1 + m2
    assert total.cents == 2164
    assert total.to_paypal_value() == "21.64"
    with pytest.raises(ValueError, match="strict int"):
        Money("USD", True)  # type: ignore[arg-type]


def test_ssrf_url_guard() -> None:
    assert validate_public_https_url("https://catalog.channel3.example.com/item/1")
    with pytest.raises(ValueError):
        validate_public_https_url("http://catalog.channel3.example.com/item/1")
    with pytest.raises(ValueError):
        validate_public_https_url("https://127.0.0.1/admin")
    with pytest.raises(ValueError):
        validate_public_https_url("https://192.168.1.10/internal")


def test_idempotency_conflict_and_price_drift_void() -> None:
    gate = RiskAndFraudPolicyGate(allowed_merchants={"M-01"}, max_order_cents=50_000, min_kernel_confidence=0.85)
    ledger = IdempotentOrderLedger(gate)
    o1 = ledger.create_order(
        request_id="REQ-IDEMP-0001",
        merchant_id="M-01",
        item_sku="SKU-1",
        product_url="https://shop.example.com/p/1",
        subtotal=Money("USD", 10000),
        tax=Money("USD", 800),
        shipping=Money("USD", 500),
        kernel_confidence=0.92,
    )
    # Same request_id and identical payload returns same order
    o1_retry = ledger.create_order(
        request_id="REQ-IDEMP-0001",
        merchant_id="M-01",
        item_sku="SKU-1",
        product_url="https://shop.example.com/p/1",
        subtotal=Money("USD", 10000),
        tax=Money("USD", 800),
        shipping=Money("USD", 500),
        kernel_confidence=0.92,
    )
    assert o1.order_id == o1_retry.order_id

    # Same request_id with mutated subtotal raises conflict
    with pytest.raises(ValueError, match="Idempotency conflict"):
        ledger.create_order(
            request_id="REQ-IDEMP-0001",
            merchant_id="M-01",
            item_sku="SKU-1",
            product_url="https://shop.example.com/p/1",
            subtotal=Money("USD", 12000),
            tax=Money("USD", 800),
            shipping=Money("USD", 500),
            kernel_confidence=0.92,
        )

    # Price drift before capture voids the order
    tok = ledger.issue_human_approval(o1.order_id)
    with pytest.raises(ValueError, match="Price drift"):
        ledger.authorize_and_capture(
            order_id=o1.order_id,
            approval_token_id=tok.token_id,
            live_rechecked_subtotal_cents=10500,
        )
    assert o1.state == OrderState.VOIDED


def test_end_to_end_procurement_workflow() -> None:
    res = run_procurement_workflow(seed=42)
    assert len(res["orders"]) == 2
    assert all(o["order_state"] == "CAPTURED" for o in res["orders"])
