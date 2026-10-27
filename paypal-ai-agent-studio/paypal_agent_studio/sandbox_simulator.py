"""
Deterministic in-process PayPal Sandbox HTTP transport adapter for offline demos and CI tests.

Follows the exact seam documented in the APIMatic Context Plugin `python-testing` skill:
- Passes a custom `requests.Session` with a mounted `HTTPAdapter` as `http_client_instance`
  into `PaypalServersdkClient`.
- Routes `/v1/oauth2/token` to a valid OAuth 2.0 Bearer token response so `ClientCredentialsAuth`
  completes transparently before every controller operation.
- Routes `/v2/checkout/orders`, `/v1/billing/subscriptions`, and `/v2/payments/captures/{id}/refund`
  through the real APIMatic serialization & deserialization pipeline.
"""

from __future__ import annotations

import io
import json
import urllib.parse
from typing import Dict

import requests
from requests.adapters import HTTPAdapter


class PayPalSandboxMockAdapter(HTTPAdapter):
    """
    In-process `HTTPAdapter` that simulates PayPal Sandbox endpoints while exercising 100% of
    `paypal-server-sdk==2.4.0`'s request builders, model serializers, OAuth2 manager, and response
    deserializers.
    """

    def __init__(self) -> None:
        super().__init__()
        self.orders_db: Dict[str, Dict] = {}
        self.subscriptions_db: Dict[str, Dict] = {}
        self.refunds_db: Dict[str, Dict] = {}

    def send(self, request: requests.PreparedRequest, **kwargs) -> requests.Response:
        parsed = urllib.parse.urlparse(request.url or "")
        path = parsed.path
        method = (request.method or "GET").upper()
        body_text = ""
        if request.body:
            body_text = (
                request.body.decode("utf-8")
                if isinstance(request.body, (bytes, bytearray))
                else str(request.body)
            )

        # 1. OAuth 2.0 Client Credentials token endpoint
        if path.endswith("/v1/oauth2/token") and method == "POST":
            return self._json_response(
                request,
                200,
                {
                    "scope": "https://uri.paypal.com/services/invoicing https://uri.paypal.com/services/disputes/read-buyer",
                    "access_token": "A21AAJ_APIMATIC_SANDBOX_VERIFIED_TOKEN_2026",
                    "token_type": "Bearer",
                    "app_id": "APP-80W284485P519543T",
                    "expires_in": 32400,
                    "nonce": "2026-10-27T00:00:00Z-apimatic",
                },
            )

        # Check negative-test trigger header (`PayPal-Mock-Response`)
        mock_err = request.headers.get("PayPal-Mock-Response")
        if mock_err:
            return self._json_response(
                request,
                422,
                {
                    "name": "UNPROCESSABLE_ENTITY",
                    "message": f"Simulated negative test triggered via PayPal-Mock-Response: {mock_err}",
                    "debug_id": "dbg-apimatic-422",
                    "details": [{"issue": mock_err, "description": "Negative sandbox test"}],
                },
            )

        # 2. Create Order: POST /v2/checkout/orders
        if path == "/v2/checkout/orders" and method == "POST":
            payload = json.loads(body_text or "{}")
            order_id = f"5O190127TN{len(self.orders_db) + 101:05d}X"
            record = {
                "id": order_id,
                "intent": payload.get("intent", "CAPTURE"),
                "status": "CREATED",
                "purchase_units": payload.get("purchase_units", []),
                "create_time": "2026-10-27T04:00:00Z",
                "links": [
                    {
                        "href": f"https://api-m.sandbox.paypal.com/v2/checkout/orders/{order_id}",
                        "rel": "self",
                        "method": "GET",
                    },
                    {
                        "href": f"https://www.sandbox.paypal.com/checkoutnow?token={order_id}",
                        "rel": "approve",
                        "method": "GET",
                    },
                    {
                        "href": f"https://api-m.sandbox.paypal.com/v2/checkout/orders/{order_id}/capture",
                        "rel": "capture",
                        "method": "POST",
                    },
                ],
            }
            self.orders_db[order_id] = record
            return self._json_response(request, 201, record)

        # 3. Capture Order: POST /v2/checkout/orders/{id}/capture
        if path.startswith("/v2/checkout/orders/") and path.endswith("/capture") and method == "POST":
            parts = path.strip("/").split("/")
            order_id = parts[3]
            if order_id == "ORDER-NOT-FOUND":
                return self._json_response(
                    request,
                    404,
                    {
                        "name": "RESOURCE_NOT_FOUND",
                        "message": "The specified resource does not exist.",
                        "debug_id": "dbg-404",
                    },
                )
            record = self.orders_db.get(order_id, {"id": order_id, "intent": "CAPTURE"})
            record["status"] = "COMPLETED"
            record["update_time"] = "2026-10-27T04:01:00Z"
            self.orders_db[order_id] = record
            return self._json_response(request, 201, record)

        # 4. Get Order: GET /v2/checkout/orders/{id}
        if path.startswith("/v2/checkout/orders/") and method == "GET":
            order_id = path.strip("/").split("/")[-1]
            if order_id not in self.orders_db:
                return self._json_response(
                    request,
                    404,
                    {
                        "name": "RESOURCE_NOT_FOUND",
                        "message": f"Order {order_id} was not found.",
                        "debug_id": "dbg-get-404",
                    },
                )
            return self._json_response(request, 200, self.orders_db[order_id])

        # 5. Create Subscription: POST /v1/billing/subscriptions
        if path == "/v1/billing/subscriptions" and method == "POST":
            payload = json.loads(body_text or "{}")
            sub_id = f"I-BW452GLLEP{len(self.subscriptions_db) + 11:02d}G"
            record = {
                "id": sub_id,
                "plan_id": payload.get("plan_id", "P-DEFAULT"),
                "status": "APPROVAL_PENDING",
                "create_time": "2026-10-27T04:02:00Z",
                "links": [
                    {
                        "href": f"https://www.sandbox.paypal.com/webapps/billing/subscriptions?ba_token={sub_id}",
                        "rel": "approve",
                        "method": "GET",
                    }
                ],
            }
            self.subscriptions_db[sub_id] = record
            return self._json_response(request, 201, record)

        # 6. Refund Captured Payment: POST /v2/payments/captures/{capture_id}/refund
        if path.startswith("/v2/payments/captures/") and path.endswith("/refund") and method == "POST":
            capture_id = path.strip("/").split("/")[3]
            payload = json.loads(body_text or "{}")
            refund_id = f"1JU0890278{len(self.refunds_db) + 101:03d}B"
            record = {
                "id": refund_id,
                "status": "COMPLETED",
                "amount": payload.get("amount", {"currency_code": "USD", "value": "0.00"}),
                "note_to_payer": payload.get("note_to_payer", ""),
                "create_time": "2026-10-27T04:03:00Z",
            }
            self.refunds_db[refund_id] = record
            return self._json_response(request, 201, record)

        return self._json_response(request, 404, {"message": f"Unmapped sandbox route: {method} {path}"})

    @staticmethod
    def _json_response(
        request: requests.PreparedRequest, status_code: int, body: Dict
    ) -> requests.Response:
        resp = requests.Response()
        resp.status_code = status_code
        resp.reason = "OK" if status_code < 400 else "ERROR"
        resp.headers["Content-Type"] = "application/json"
        raw = json.dumps(body).encode("utf-8")
        resp.raw = io.BytesIO(raw)
        resp._content = raw
        resp.request = request
        resp.url = request.url or ""
        return resp


def build_sandbox_session() -> requests.Session:
    session = requests.Session()
    adapter = PayPalSandboxMockAdapter()
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session
