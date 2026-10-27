# PayPal AI Agent Studio — Autonomous Commerce & Dispute Resolution Engine

**Built for the PayPal AI Hackathon (2026) with the [APIMatic Context Plugin for PayPal](https://github.com/paypaldev/server-sdk-context-plugin-preview) & `paypal-server-sdk==2.4.0`**

[![PayPal Server SDK](https://img.shields.io/badge/PayPal_Server_SDK-2.4.0_(APIMatic)-003087?logo=paypal)](https://github.com/paypal/PayPal-Python-Server-SDK)
[![APIMatic Context Plugin](https://img.shields.io/badge/APIMatic-Context_Plugin_Verified-00A3E0)](https://github.com/paypaldev/server-sdk-context-plugin-preview)
[![Tests](https://img.shields.io/badge/pytest-5%2F5_passing-brightgreen)](#testing--verification)

---

## Overview

**PayPal AI Agent Studio** is an autonomous agentic commerce gateway that enables AI agents to discover products, create and capture **PayPal Orders v2**, provision recurring **Billing Subscriptions v1**, verify **PayPal Webhooks / Customer Disputes**, and execute autonomous micro-dispute refunds via **Payments v2 (`refund_captured_payment`)**.

### How We Used the APIMatic Context Plugin for PayPal

We installed the official **APIMatic Context Plugin for PayPal** directly into our AI coding agent environment:

```bash
npx context-plugins install https://github.com/paypaldev/server-sdk-context-plugin-preview
```

Using the 7 companion skills provided by the APIMatic Context Plugin (`python-getting-started`, `python-client-initialization`, `python-authentication`, `python-calling-endpoints`, `python-models`, `python-error-handling`, `python-configuration-resilience`, and `python-testing`), our coding agent synthesized a zero-hallucination integration with `paypal-server-sdk==2.4.0` (`paypalserversdk`):

1. **Exact Module Imports (`python-getting-started`)**:
   - Imported directly from full module paths (`paypalserversdk.paypal_serversdk_client.PaypalServersdkClient`, `paypalserversdk.configuration.Environment`, `paypalserversdk.http.auth.o_auth_2.ClientCredentialsAuthCredentials`) because `paypalserversdk/__init__.py` does not re-export classes at the package root.
2. **Long-Lived Client & Flat Constructor Arguments (`python-client-initialization` & `python-authentication`)**:
   - Constructed `PaypalServersdkClient` once with flat keyword arguments (`environment=Environment.SANDBOX`, `client_credentials_auth_credentials=ClientCredentialsAuthCredentials(o_auth_client_id=..., o_auth_client_secret=...)`, `timeout=30`, `max_retries=2`, `backoff_factor=0.5`).
3. **Lazy Controller Properties & Shape-2 `options` Dict (`python-calling-endpoints`)**:
   - Accessed `client.orders`, `client.subscriptions`, and `client.payments` as `@LazyProperty` attributes on the client rather than instantiating controllers manually.
   - Passed request parameters using Shape-2 `options={...}` dictionaries (`{"body": order_request, "paypal_request_id": req_id, "prefer": "return=representation"}`) and read deserialized models from `api_response.body` (`ApiResponse` envelope).
4. **`APIHelper.SKIP` Safe Model Handling & `ApiException` Recovery (`python-models` & `python-error-handling`)**:
   - Used `AmountWithBreakdown`, `PurchaseUnitRequest`, `OrderRequest`, `CheckoutPaymentIntent.CAPTURE`, `CreateSubscriptionRequest`, `RefundRequest`, and `Money`, reading optional response attributes via `getattr(model, attr, None)` and catching `ApiException` for non-2xx responses.
5. **In-Process Transport Seam & `HttpCallBack` Telemetry (`python-testing`)**:
   - Implemented `TelemetryResponseCatcher(HttpCallBack)` and `PayPalSandboxMockAdapter(HTTPAdapter)` passed via `http_client_instance` and `http_call_back`, routing `/v1/oauth2/token` first so the SDK's `ClientCredentialsAuth` token exchange and all endpoint serializers/deserializers are tested end-to-end without network flakiness.

---

## Repository Structure

```text
paypal-ai-agent-studio/
├── .apimatic/
│   └── context-plugin.json          # APIMatic Context Plugin manifest & verified skills trace
├── .mcp.json                        # PayPal Sandbox MCP configuration
├── paypal_agent_studio/
│   ├── __init__.py
│   ├── client.py                    # PaypalServersdkClient factory + TelemetryResponseCatcher (HttpCallBack)
│   ├── commerce_gateway.py          # Orders v2, Subscriptions v1, Payments v2 Refunds & Webhook verifier
│   ├── sandbox_simulator.py         # Deterministic HTTPAdapter for OAuth2 + Orders/Subscriptions/Refunds
│   └── server.py                    # End-to-end CLI demo runner & JSON trace exporter
├── tests/
│   └── test_paypal_apimatic_sdk.py  # Pytest suite following APIMatic's python-testing skill
├── .env.example
├── LICENSE
├── README.md
└── requirements.txt
```

---

## Quick Start

### 1. Create a Virtual Environment & Install Dependencies

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Run the End-to-End APIMatic + PayPal SDK Demo

```bash
python -m paypal_agent_studio.server --demo
```

### 3. Run the Test Suite

```bash
pytest -v
```

---

## Author

- **Kazutoshi Hayashi** (LUMA LAB)
