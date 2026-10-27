"""
APIMatic-grounded PayPal Server SDK client initialization & HTTP telemetry catcher.

Built following the APIMatic Context Plugin skills:
- `python-getting-started`: full module path imports from `paypalserversdk.*`
- `python-client-initialization`: flat keyword arguments on `PaypalServersdkClient`, long-lived reuse, `clone_with`
- `python-authentication`: `ClientCredentialsAuthCredentials(o_auth_client_id=..., o_auth_client_secret=...)`
- `python-configuration-resilience`: explicit timeout, retry backoff, and `Environment.SANDBOX`
- `python-testing`: `HttpCallBack` (`ResponseCatcher`) and injectable `http_client_instance`
"""

from __future__ import annotations

import os
from typing import List, Optional, Tuple

import requests
from paypalserversdk.configuration import Environment
from paypalserversdk.http.auth.o_auth_2 import ClientCredentialsAuthCredentials
from paypalserversdk.http.http_call_back import HttpCallBack
from paypalserversdk.paypal_serversdk_client import PaypalServersdkClient


class TelemetryResponseCatcher(HttpCallBack):
    """
    Captures every outgoing `HttpRequest` and incoming `HttpResponse` passing through
    `PaypalServersdkClient`, preserving a full history list so OAuth `/v1/oauth2/token`
    exchanges and subsequent API operations can be inspected independently.
    """

    def __init__(self) -> None:
        self.request = None
        self.response = None
        self.history: List[Tuple[object, object]] = []
        self._pending_request = None

    def on_before_request(self, request) -> None:
        self.request = request
        self._pending_request = request

    def on_after_response(self, response) -> None:
        self.response = response
        self.history.append((self._pending_request, response))


def create_paypal_sdk_client(
    client_id: Optional[str] = None,
    client_secret: Optional[str] = None,
    environment: Environment = Environment.SANDBOX,
    timeout: int = 30,
    max_retries: int = 2,
    backoff_factor: float = 0.5,
    http_client_instance: Optional[requests.Session] = None,
    catcher: Optional[TelemetryResponseCatcher] = None,
) -> Tuple[PaypalServersdkClient, TelemetryResponseCatcher]:
    """
    Construct a long-lived `PaypalServersdkClient` configured with `ClientCredentialsAuthCredentials`
    and a `TelemetryResponseCatcher` (`http_call_back`).
    """
    resolved_id = client_id or os.environ.get("O_AUTH_CLIENT_ID") or "sandbox-demo-client-id"
    resolved_secret = client_secret or os.environ.get("O_AUTH_CLIENT_SECRET") or "sandbox-demo-client-secret"
    resolved_catcher = catcher or TelemetryResponseCatcher()

    credentials = ClientCredentialsAuthCredentials(
        o_auth_client_id=resolved_id,
        o_auth_client_secret=resolved_secret,
    )

    kwargs = {
        "environment": environment,
        "client_credentials_auth_credentials": credentials,
        "http_call_back": resolved_catcher,
        "timeout": timeout,
        "max_retries": max_retries,
        "backoff_factor": backoff_factor,
    }
    if http_client_instance is not None:
        kwargs["http_client_instance"] = http_client_instance
        kwargs["max_retries"] = 0  # per python-testing skill: explicit 0 on custom session

    client = PaypalServersdkClient(**kwargs)
    return client, resolved_catcher
