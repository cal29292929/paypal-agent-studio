"""
PayPal Commerce Gateway using the APIMatic-generated `paypal-server-sdk==2.4.0`.

Follows APIMatic Context Plugin rules:
- Controller access via lazy properties (`client.orders`, `client.subscriptions`, `client.payments`).
- Shape-2 `options={...}` dictionary calls for `create_order`, `capture_order`, `get_order`,
  `create_subscription`, `get_subscription`, and `refund_captured_payment`.
- Deserialized payload read from `api_response.body` (`ApiResponse` envelope).
- Optional model attributes checked safely via `getattr(model, attr, None)` because omitted optional
  fields use the `APIHelper.SKIP` sentinel.
- Non-2xx responses caught via `ApiException` with structured error diagnostics.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import uuid
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional

from paypalserversdk.exceptions.api_exception import ApiException
from paypalserversdk.models.amount_with_breakdown import AmountWithBreakdown
from paypalserversdk.models.checkout_payment_intent import CheckoutPaymentIntent
from paypalserversdk.models.create_subscription_request import CreateSubscriptionRequest
from paypalserversdk.models.money import Money
from paypalserversdk.models.order_request import OrderRequest
from paypalserversdk.models.purchase_unit_request import PurchaseUnitRequest
from paypalserversdk.models.refund_request import RefundRequest
from paypalserversdk.paypal_serversdk_client import PaypalServersdkClient


@dataclass
class GatewayOperationResult:
    ok: bool
    operation: str
    status_code: int
    resource_id: Optional[str]
    status: Optional[str]
    payload: Dict[str, Any]
    request_id: str
    error_message: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class PayPalCommerceGateway:
    """
    Production-grade wrapper around `PaypalServersdkClient` for AI Commerce Agents.
    Covers Orders v2, Subscriptions v1, Payments v2 Refunds, and Dispute/Webhook verification.
    """

    def __init__(self, client: PaypalServersdkClient) -> None:
        self.client = client

    def create_checkout_order(
        self,
        currency_code: str,
        value: str,
        description: str,
        reference_id: str = "PU-AGENT-001",
        custom_id: Optional[str] = None,
        request_id: Optional[str] = None,
    ) -> GatewayOperationResult:
        """
        Create a PayPal Orders v2 order (`POST /v2/checkout/orders`) using Shape-2 `options` dict.
        """
        req_id = request_id or f"ord-{uuid.uuid4().hex[:12]}"
        amount = AmountWithBreakdown(currency_code=currency_code, value=value)
        pu_kwargs: Dict[str, Any] = {
            "reference_id": reference_id,
            "amount": amount,
            "description": description,
        }
        if custom_id is not None:
            pu_kwargs["custom_id"] = custom_id

        purchase_unit = PurchaseUnitRequest(**pu_kwargs)
        order_request = OrderRequest(
            intent=CheckoutPaymentIntent.CAPTURE,
            purchase_units=[purchase_unit],
        )

        try:
            # Shape-2 options dict as specified in python-calling-endpoints
            api_response = self.client.orders.create_order({
                "body": order_request,
                "paypal_request_id": req_id,
                "prefer": "return=representation",
            })
            order_model = api_response.body
            order_id = getattr(order_model, "id", None)
            order_status = getattr(order_model, "status", None)
            links = [
                {
                    "href": getattr(link, "href", None),
                    "rel": getattr(link, "rel", None),
                    "method": getattr(link, "method", None),
                }
                for link in (getattr(order_model, "links", None) or [])
            ]
            return GatewayOperationResult(
                ok=True,
                operation="orders.create_order",
                status_code=api_response.status_code,
                resource_id=order_id,
                status=str(order_status) if order_status else None,
                payload={
                    "id": order_id,
                    "status": str(order_status) if order_status else None,
                    "intent": str(getattr(order_model, "intent", CheckoutPaymentIntent.CAPTURE)),
                    "currency_code": currency_code,
                    "value": value,
                    "description": description,
                    "links": links,
                },
                request_id=req_id,
            )
        except ApiException as exc:
            return self._handle_api_exception("orders.create_order", req_id, exc)

    def capture_checkout_order(
        self,
        order_id: str,
        request_id: Optional[str] = None,
    ) -> GatewayOperationResult:
        """
        Capture an approved PayPal Orders v2 order (`POST /v2/checkout/orders/{id}/capture`).
        """
        req_id = request_id or f"cap-{uuid.uuid4().hex[:12]}"
        try:
            api_response = self.client.orders.capture_order({
                "id": order_id,
                "paypal_request_id": req_id,
                "prefer": "return=representation",
            })
            order_model = api_response.body
            resolved_id = getattr(order_model, "id", order_id)
            resolved_status = getattr(order_model, "status", None)
            return GatewayOperationResult(
                ok=True,
                operation="orders.capture_order",
                status_code=api_response.status_code,
                resource_id=resolved_id,
                status=str(resolved_status) if resolved_status else None,
                payload={
                    "id": resolved_id,
                    "status": str(resolved_status) if resolved_status else None,
                },
                request_id=req_id,
            )
        except ApiException as exc:
            return self._handle_api_exception("orders.capture_order", req_id, exc)

    def get_checkout_order(self, order_id: str) -> GatewayOperationResult:
        """
        Retrieve an order (`GET /v2/checkout/orders/{id}`).
        """
        req_id = f"get-{uuid.uuid4().hex[:12]}"
        try:
            api_response = self.client.orders.get_order({"id": order_id})
            order_model = api_response.body
            resolved_id = getattr(order_model, "id", order_id)
            resolved_status = getattr(order_model, "status", None)
            return GatewayOperationResult(
                ok=True,
                operation="orders.get_order",
                status_code=api_response.status_code,
                resource_id=resolved_id,
                status=str(resolved_status) if resolved_status else None,
                payload={
                    "id": resolved_id,
                    "status": str(resolved_status) if resolved_status else None,
                },
                request_id=req_id,
            )
        except ApiException as exc:
            return self._handle_api_exception("orders.get_order", req_id, exc)

    def create_billing_subscription(
        self,
        plan_id: str,
        custom_id: Optional[str] = None,
        auto_renewal: bool = True,
        request_id: Optional[str] = None,
    ) -> GatewayOperationResult:
        """
        Create a PayPal Billing Subscription (`POST /v1/billing/subscriptions`) via `client.subscriptions`.
        """
        req_id = request_id or f"sub-{uuid.uuid4().hex[:12]}"
        sub_kwargs: Dict[str, Any] = {
            "plan_id": plan_id,
            "auto_renewal": auto_renewal,
        }
        if custom_id is not None:
            sub_kwargs["custom_id"] = custom_id

        sub_request = CreateSubscriptionRequest(**sub_kwargs)
        try:
            api_response = self.client.subscriptions.create_subscription({
                "body": sub_request,
                "paypal_request_id": req_id,
                "prefer": "return=representation",
            })
            sub_model = api_response.body
            sub_id = getattr(sub_model, "id", None)
            sub_status = getattr(sub_model, "status", None)
            return GatewayOperationResult(
                ok=True,
                operation="subscriptions.create_subscription",
                status_code=api_response.status_code,
                resource_id=sub_id,
                status=str(sub_status) if sub_status else None,
                payload={
                    "id": sub_id,
                    "plan_id": getattr(sub_model, "plan_id", plan_id),
                    "status": str(sub_status) if sub_status else None,
                },
                request_id=req_id,
            )
        except ApiException as exc:
            return self._handle_api_exception("subscriptions.create_subscription", req_id, exc)

    def refund_captured_payment(
        self,
        capture_id: str,
        currency_code: str,
        value: str,
        note_to_payer: str = "Autonomous AI Dispute Resolution Refund",
        request_id: Optional[str] = None,
    ) -> GatewayOperationResult:
        """
        Issue a full or partial refund on a captured payment (`POST /v2/payments/captures/{capture_id}/refund`)
        via `client.payments.refund_captured_payment`.
        """
        req_id = request_id or f"ref-{uuid.uuid4().hex[:12]}"
        refund_body = RefundRequest(
            amount=Money(currency_code=currency_code, value=value),
            note_to_payer=note_to_payer,
        )
        try:
            api_response = self.client.payments.refund_captured_payment({
                "capture_id": capture_id,
                "body": refund_body,
                "paypal_request_id": req_id,
                "prefer": "return=representation",
            })
            refund_model = api_response.body
            refund_id = getattr(refund_model, "id", None)
            refund_status = getattr(refund_model, "status", None)
            return GatewayOperationResult(
                ok=True,
                operation="payments.refund_captured_payment",
                status_code=api_response.status_code,
                resource_id=refund_id,
                status=str(refund_status) if refund_status else None,
                payload={
                    "id": refund_id,
                    "capture_id": capture_id,
                    "status": str(refund_status) if refund_status else None,
                    "currency_code": currency_code,
                    "value": value,
                    "note_to_payer": note_to_payer,
                },
                request_id=req_id,
            )
        except ApiException as exc:
            return self._handle_api_exception("payments.refund_captured_payment", req_id, exc)

    @staticmethod
    def verify_webhook_And_dispute_event(
        webhook_id: str,
        transmission_id: str,
        transmission_time: str,
        raw_event_body: str,
        expected_signature: str,
        shared_secret: str = "paypal-sandbox-webhook-secret",
    ) -> Dict[str, Any]:
        """
        Verify PayPal Webhook / Customer Dispute event integrity (`CHECKOUT.ORDER.APPROVED`,
        `PAYMENT.CAPTURE.COMPLETED`, `CUSTOMER.DISPUTE.CREATED`) and classify autonomous agent action.
        """
        signing_payload = f"{transmission_id}|{transmission_time}|{webhook_id}|{raw_event_body}"
        computed_sig = hmac.new(
            shared_secret.encode("utf-8"),
            signing_payload.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        verified = hmac.compare_digest(computed_sig, expected_signature)

        event = json.loads(raw_event_body)
        event_type = event.get("event_type", "UNKNOWN")
        resource = event.get("resource", {})

        recommended_action = "LOG_ONLY"
        if event_type == "CHECKOUT.ORDER.APPROVED":
            recommended_action = "CAPTURE_ORDER_VIA_APIMATIC_SDK"
        elif event_type == "CUSTOMER.DISPUTE.CREATED":
            dispute_amount = float(
                resource.get("dispute_amount", {}).get("value", "0.0") or "0.0"
            )
            recommended_action = (
                "AUTO_REFUND_VIA_PAYMENTS_CONTROLLER"
                if dispute_amount <= 50.0
                else "ESCALATE_WITH_EVIDENCE_PACKAGE"
            )
        elif event_type == "BILLING.SUBSCRIPTION.ACTIVATED":
            recommended_action = "PROVISION_AI_AGENT_SEAT"

        return {
            "signature_verified": verified,
            "webhook_id": webhook_id,
            "transmission_id": transmission_id,
            "event_type": event_type,
            "resource_id": resource.get("id") or resource.get("dispute_id"),
            "recommended_action": recommended_action,
        }

    @staticmethod
    def _handle_api_exception(
        operation: str, request_id: str, exc: ApiException
    ) -> GatewayOperationResult:
        raw_text = getattr(exc.response, "text", None) if getattr(exc, "response", None) else str(exc)
        parsed_body: Dict[str, Any] = {}
        if raw_text:
            try:
                parsed_body = json.loads(raw_text)
            except Exception:
                parsed_body = {"raw": raw_text}
        return GatewayOperationResult(
            ok=False,
            operation=operation,
            status_code=getattr(exc, "response_code", 500),
            resource_id=None,
            status="ERROR",
            payload=parsed_body,
            request_id=request_id,
            error_message=parsed_body.get("message") or str(exc),
        )
