# Devpost Submission Draft — PayPal AI Hackathon (`07-paypal-ai`)

- **Devpost URL**: https://paypal-ai.devpost.com/
- **Submission Deadline (JST)**: `2026-11-13T05:00:00+09:00`
- **Project Name**: PayPal Agentic Commerce Studio: Policy-Gated Orders, Disputes & Invoice Ledger
- **Elevator Pitch**: Autonomous B2B procurement & dispute resolution studio built with the APIMatic PayPal Python Server SDK v2.4.0, integer-minor-unit policy gates, UUIDv5 idempotency, and SHA-256 audit chains.
- **Target GitHub Repository URL**: `https://github.com/cal29292929/paypal-agent-studio`
- **Target GitHub Release URL**: `https://github.com/cal29292929/paypal-agent-studio/releases/tag/v1.0.0`
- **Demo Video**: `/workspace/hackathons/07-paypal-ai/submission_assets/demo_video.mp4` (1920x1080, 150s, H.264/AAC)
- **Unit Test Suite**: `9 passed`

## Built With Tags
- `paypal-server-sdk`
- `apimatic`
- `claude-opus-5-5`
- `gpt-6-luna`
- `sakura-ai-engine`
- `model-context-protocol`
- `python`

## Try It Out URLs
- https://github.com/cal29292929/paypal-agent-studio
- https://github.com/cal29292929/paypal-ai-agent-studio

## About the Project (Copy-Paste Ready for Devpost)

## Inspiration
Agentic commerce requires strict financial invariants: floating-point rounding bugs, duplicate order captures on network retries, or unapproved autonomous captures above policy limits can cause real monetary loss.

## What it does
**PayPal Agentic Commerce Studio** (`paypal_agent_studio`) combines the official APIMatic-generated `paypal-server-sdk==2.4.0` with a deterministic financial policy engine:
1. **APIMatic SDK Integration (`OrdersController`)**: Uses `ClientCredentialsAuthCredentials`, `Environment.SANDBOX`, and `TelemetryResponseCatcher` (`HttpCallBack`) to capture full HTTP telemetry.
2. **Exact Integer Minor-Unit Policy Gate**: Rejects float currency amounts, enforces merchant category allowlists (`software_saas`, `cloud_compute`, `office_supplies`), auto-captures orders `<= $50.00`, and holds `$50.01-$200.00` in `PENDING_HUMAN_APPROVAL` until a single-use human approval token is verified.
3. **Deterministic UUIDv5 `PayPal-Request-Id` & SHA-256 Audit Ledger**: Guarantees idempotent retries and cryptographic tamper evidence across the full order lifecycle.

## Verification & Testing
- **Unit Tests**: `9 passed` (`pytest -q`, including APIMatic `OrdersController` + policy gate tests)
- **Demo Video**: `submission_assets/demo_video.mp4` (1920x1080, 150s, H.264/AAC)


## Multi-Model Pipeline Provenance & Custom Questions
```json
{
  "opus55_session_id": "8f7eb3ec-30c8-42ac-840b-f39361fc83e9",
  "luna56_review_session_id": "01a17dc3-8fba-7481-92f8-1c1224c588b4",
  "luna56_codereview_session_id": "01a17dce-1c52-76f1-884b-f68cab64a8bd",
  "sakura_completion_id": "chatcmpl-947a5c8ba1e25cf9"
}
```

## Screenshots (1920x1080 PNG)
- `/workspace/hackathons/07-paypal-ai/submission_assets/00_thumbnail.png`
- `/workspace/hackathons/07-paypal-ai/submission_assets/01_idempotent_order_ledger.png`
- `/workspace/hackathons/07-paypal-ai/submission_assets/02_hitl_and_price_drift_guard.png`
- `/workspace/hackathons/07-paypal-ai/submission_assets/03_apimatic_sdk_integration.png`
- `/workspace/hackathons/07-paypal-ai/submission_assets/04_ssrf_and_security.png`
- `/workspace/hackathons/07-paypal-ai/submission_assets/05_ag_grid_telemetry.png`
- `/workspace/hackathons/07-paypal-ai/submission_assets/06_tests_and_quickstart.png`
