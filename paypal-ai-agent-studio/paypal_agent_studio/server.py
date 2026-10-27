"""
Interactive HTTP Server & CLI demo for PayPal AI Agent Studio (APIMatic Context Plugin Edition).
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, Dict

from paypal_agent_studio.client import create_paypal_sdk_client
from paypal_agent_studio.commerce_gateway import PayPalCommerceGateway
from paypal_agent_studio.sandbox_simulator import build_sandbox_session


def run_end_to_end_demo() -> Dict[str, Any]:
    """
    Run a complete, self-contained AI Commerce Agent workflow through the APIMatic-generated
    `paypal-server-sdk==2.4.0` (`PaypalServersdkClient`).
    """
    session = build_sandbox_session()
    client, catcher = create_paypal_sdk_client(http_client_instance=session)
    gateway = PayPalCommerceGateway(client)

    # Step 1: Create Order via OrdersController (/v2/checkout/orders)
    created = gateway.create_checkout_order(
        currency_code="USD",
        value="149.00",
        description="AI Agent Autonomous Procurement - Neural Accelerator Tier",
        reference_id="PU-CHANNEL3-8821",
        custom_id="AGENT-SESSION-001",
    )

    # Step 2: Capture Order via OrdersController (/v2/checkout/orders/{id}/capture)
    captured = gateway.capture_checkout_order(order_id=created.resource_id or "5O190127TN00101X")

    # Step 3: Create Billing Subscription via SubscriptionsController (/v1/billing/subscriptions)
    subscription = gateway.create_billing_subscription(
        plan_id="P-5ML4271244454362WXNWU5NQ",
        custom_id="SUB-AGENT-ENTERPRISE",
    )

    # Step 4: Verify Dispute Webhook & Issue Instant Micro-Dispute Refund via PaymentsController
    webhook_body = json.dumps({
        "id": "WH-EVT-99201",
        "event_type": "CUSTOMER.DISPUTE.CREATED",
        "resource": {
            "dispute_id": "PP-D-40192",
            "dispute_amount": {"currency_code": "USD", "value": "24.50"},
        },
    })
    webhook_id = "WH-2WR32451HC0233532"
    tx_id = "69cd12f0-90a1-11ef-8a22"
    tx_time = "2026-10-27T04:05:00Z"
    secret = "paypal-sandbox-webhook-secret"
    expected_sig = hmac.new(
        secret.encode("utf-8"),
        f"{tx_id}|{tx_time}|{webhook_id}|{webhook_body}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    webhook_check = gateway.verify_webhook_And_dispute_event(
        webhook_id=webhook_id,
        transmission_id=tx_id,
        transmission_time=tx_time,
        raw_event_body=webhook_body,
        expected_signature=expected_sig,
        shared_secret=secret,
    )

    refund = gateway.refund_captured_payment(
        capture_id="2GG279541U471931P",
        currency_code="USD",
        value="24.50",
        note_to_payer="Auto-resolved dispute PP-D-40192 via APIMatic PayPal SDK agent",
    )

    recorded_http_calls = [
        {
            "method": getattr(req, "http_method", None),
            "url": getattr(req, "query_url", None),
            "status_code": getattr(resp, "status_code", None),
        }
        for req, resp in catcher.history
    ]

    return {
        "sdk": "paypal-server-sdk==2.4.0 (APIMatic Context Plugin for PayPal)",
        "steps": {
            "order_created": created.to_dict(),
            "order_captured": captured.to_dict(),
            "subscription_created": subscription.to_dict(),
            "webhook_verified": webhook_check,
            "dispute_refunded": refund.to_dict(),
        },
        "apimatic_http_callback_trace": recorded_http_calls,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="PayPal AI Agent Studio CLI & Demo Runner")
    parser.add_argument("--demo", action="store_true", help="Run full APIMatic PayPal SDK workflow and print JSON report")
    args = parser.parse_args()

    result = run_end_to_end_demo()
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
