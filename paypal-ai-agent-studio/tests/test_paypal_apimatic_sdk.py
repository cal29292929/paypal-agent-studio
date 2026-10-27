"""
Unit & integration test suite for PayPal AI Agent Studio.

Follows the APIMatic Context Plugin `python-testing` skill:
- Uses `http_client_instance` (`requests.Session` with `PayPalSandboxMockAdapter`) and
  `http_call_back` (`TelemetryResponseCatcher`) on `PaypalServersdkClient`.
- Verifies that the OAuth `/v1/oauth2/token` request and each API operation (`OrdersController`,
  `SubscriptionsController`, `PaymentsController`) serialize models, unwrap `ApiResponse.body`,
  and raise `ApiException` on non-2xx responses.
"""

from __future__ import annotations

import hashlib
import hmac
import json

from paypal_agent_studio.client import create_paypal_sdk_client
from paypal_agent_studio.commerce_gateway import PayPalCommerceGateway
from paypal_agent_studio.sandbox_simulator import build_sandbox_session
from paypal_agent_studio.server import run_end_to_end_demo


def test_create_and_capture_order_via_apimatic_sdk() -> None:
    session = build_sandbox_session()
    client, catcher = create_paypal_sdk_client(http_client_instance=session)
    gateway = PayPalCommerceGateway(client)

    create_res = gateway.create_checkout_order(
        currency_code="USD",
        value="89.99",
        description="APIMatic Context Plugin Verified Order",
        reference_id="PU-TEST-01",
    )
    assert create_res.ok is True
    assert create_res.status_code == 201
    assert create_res.resource_id is not None
    assert create_res.status == "CREATED"

    # First request in catcher.history is OAuth2 token POST; second is /v2/checkout/orders
    assert len(catcher.history) == 2
    assert catcher.history[0][0].query_url.endswith("/v1/oauth2/token")
    assert catcher.history[1][0].query_url.endswith("/v2/checkout/orders")

    capture_res = gateway.capture_checkout_order(create_res.resource_id)
    assert capture_res.ok is True
    assert capture_res.status == "COMPLETED"
    assert catcher.request.query_url.endswith(f"/v2/checkout/orders/{create_res.resource_id}/capture")


def test_get_order_not_found_handles_api_exception() -> None:
    session = build_sandbox_session()
    client, _ = create_paypal_sdk_client(http_client_instance=session)
    gateway = PayPalCommerceGateway(client)

    res = gateway.get_checkout_order("ORDER-DOES-NOT-EXIST")
    assert res.ok is False
    assert res.status_code == 404
    assert res.status == "ERROR"
    assert "not found" in (res.error_message or "").lower()


def test_create_subscription_and_refund_via_apimatic_sdk() -> None:
    session = build_sandbox_session()
    client, catcher = create_paypal_sdk_client(http_client_instance=session)
    gateway = PayPalCommerceGateway(client)

    sub_res = gateway.create_billing_subscription(
        plan_id="P-ENTERPRISE-AI-2026",
        custom_id="CUST-99",
    )
    assert sub_res.ok is True
    assert sub_res.status_code == 201
    assert sub_res.status == "APPROVAL_PENDING"

    ref_res = gateway.refund_captured_payment(
        capture_id="CAP-12345",
        currency_code="USD",
        value="19.99",
        note_to_payer="Automated dispute refund",
    )
    assert ref_res.ok is True
    assert ref_res.status_code == 201
    assert ref_res.status == "COMPLETED"
    assert catcher.request.query_url.endswith("/v2/payments/captures/CAP-12345/refund")


def test_webhook_and_dispute_verification() -> None:
    raw_body = json.dumps({
        "id": "WH-001",
        "event_type": "CUSTOMER.DISPUTE.CREATED",
        "resource": {
            "dispute_id": "PP-D-100",
            "dispute_amount": {"currency_code": "USD", "value": "15.00"},
        },
    })
    sig = hmac.new(
        b"test-secret",
        f"tx-1|2026-10-27T00:00:00Z|WH-ID|{raw_body}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    result = PayPalCommerceGateway.verify_webhook_And_dispute_event(
        webhook_id="WH-ID",
        transmission_id="tx-1",
        transmission_time="2026-10-27T00:00:00Z",
        raw_event_body=raw_body,
        expected_signature=sig,
        shared_secret="test-secret",
    )
    assert result["signature_verified"] is True
    assert result["recommended_action"] == "AUTO_REFUND_VIA_PAYMENTS_CONTROLLER"


def test_end_to_end_demo_runner() -> None:
    report = run_end_to_end_demo()
    assert report["steps"]["order_created"]["ok"] is True
    assert report["steps"]["order_captured"]["status"] == "COMPLETED"
    assert report["steps"]["subscription_created"]["ok"] is True
    assert report["steps"]["webhook_verified"]["signature_verified"] is True
    assert report["steps"]["dispute_refunded"]["status"] == "COMPLETED"
    assert len(report["apimatic_http_callback_trace"]) == 5
