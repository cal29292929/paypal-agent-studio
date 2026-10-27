"""Deterministic Channel3 + KERNEL + PayPal Orders/Invoicing v2 Simulation & AG Grid Telemetry Exporter."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from .core import IdempotentOrderLedger, InvoiceState, Money, RiskAndFraudPolicyGate


def run_procurement_workflow(seed: int = 42) -> dict[str, Any]:
    """Run a complete, policy-hardened procurement & PayPal settlement flow with AG Grid telemetry rows."""
    gate = RiskAndFraudPolicyGate(
        allowed_merchants={"MERCH-SANDBOX-AUDIO-01", "MERCH-SANDBOX-DEVGEAR-02"},
        max_order_cents=120_000,
        min_kernel_confidence=0.88,
    )
    ledger = IdempotentOrderLedger(gate)

    candidates = [
        {
            "sku": "CH3-USB-MIC-PRO",
            "title": "Studio Dynamic USB-C Podcasting Microphone",
            "merchant_id": "MERCH-SANDBOX-AUDIO-01",
            "product_url": "https://catalog.channel3.example.com/items/ch3-usb-mic-pro",
            "subtotal_usd": "149.00",
            "tax_usd": "13.41",
            "shipping_usd": "8.50",
            "kernel_dom_source": "json_ld_offer",
            "kernel_confidence": 0.96,
            "in_stock": True,
        },
        {
            "sku": "CH3-XLR-BOOM-ARM",
            "title": "Low-Profile Broadcast Boom Arm",
            "merchant_id": "MERCH-SANDBOX-DEVGEAR-02",
            "product_url": "https://catalog.channel3.example.com/items/ch3-xlr-boom-arm",
            "subtotal_usd": "79.00",
            "tax_usd": "7.11",
            "shipping_usd": "0.00",
            "kernel_dom_source": "open_graph_product",
            "kernel_confidence": 0.93,
            "in_stock": True,
        },
    ]

    executed_orders: list[dict[str, Any]] = []
    ag_grid_rows: list[dict[str, Any]] = []
    for idx, c in enumerate(candidates, start=1):
        req_id = f"PP-REQ-20261027-{seed:04d}-{idx:02d}"
        sub = Money.from_decimal_str("USD", c["subtotal_usd"])
        tax = Money.from_decimal_str("USD", c["tax_usd"])
        shp = Money.from_decimal_str("USD", c["shipping_usd"])
        order = ledger.create_order(
            request_id=req_id,
            merchant_id=c["merchant_id"],
            item_sku=c["sku"],
            product_url=c["product_url"],
            subtotal=sub,
            tax=tax,
            shipping=shp,
            kernel_confidence=c["kernel_confidence"],
            provider_mode="sandbox_verified",
        )
        tok = ledger.issue_human_approval(order.order_id)
        captured = ledger.authorize_and_capture(
            order_id=order.order_id,
            approval_token_id=tok.token_id,
            live_rechecked_subtotal_cents=sub.cents,
        )
        row = {
            "order_id": captured.order_id,
            "paypal_request_id": captured.request_id,
            "sku": captured.item_sku,
            "title": c["title"],
            "merchant_id": captured.merchant_id,
            "subtotal_usd": captured.subtotal.to_paypal_value(),
            "tax_usd": captured.tax.to_paypal_value(),
            "shipping_usd": captured.shipping.to_paypal_value(),
            "total_usd": captured.total.to_paypal_value(),
            "kernel_confidence": captured.kernel_confidence,
            "hitl_token_digest": tok.digest()[:16],
            "order_state": captured.state.value,
            "invoice_reconciliation_state": InvoiceState.INVOICE_SENT.value,
        }
        executed_orders.append(row)
        ag_grid_rows.append(row)

    audit_digest = hashlib.sha256(json.dumps(executed_orders, sort_keys=True).encode("utf-8")).hexdigest()
    return {
        "schema_version": "1.0.0",
        "estimation_label": "deterministic_sandbox_simulation",
        "transaction_model": "Marketplace Merchant-of-Record Checkout + Buyer Invoice Reconciliation",
        "seed": seed,
        "orders": executed_orders,
        "ag_grid_rows": ag_grid_rows,
        "audit_chain_head_sha256": audit_digest,
        "pipeline_provenance": {
            "stage1_design_model": "claude-opus-5-5",
            "stage1_session_id": "8f7eb3ec-30c8-42ac-840b-f39361fc83e9",
            "stage2_review_model": "gpt-6-luna",
            "stage2_codex_session_id": "01a17dc3-8fba-7481-92f8-1c1224c588b4",
            "stage3_impl_model": "preview/Kimi-K2.7-Code",
            "stage3_completion_id": "chatcmpl-947a5c8ba1e25cf9",
        },
    }
