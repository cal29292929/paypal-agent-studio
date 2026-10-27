# PayPal Agentic Commerce Studio (`paypal_agent_studio`) — PayPal AI Hackathon

**PayPal Agentic Commerce Studio** combines the official APIMatic-generated **PayPal Python Server SDK (`paypalserversdk`)** with an idempotent integer-cents order ledger, Channel3 catalog discovery, SSRF-hardened KERNEL price verification, Human-in-the-Loop (HITL) cryptographic approval tokens, and AG Grid telemetry export.

- **Public GitHub Repository (Target)**: `https://github.com/cal29292929/paypal-agent-studio`
- **Author**: Kazutoshi Hayashi (`cal29292929 <cal29292929@users.noreply.github.com>`)
- **License**: MIT

## Multi-Model Pipeline Provenance
1. **Stage 1 — Architecture Design (`claude-opus-5-5`)**: [`DESIGN_OPUS55.md`](DESIGN_OPUS55.md) (Session `8f7eb3ec-30c8-42ac-840b-f39361fc83e9`)
2. **Stage 2 — Adversarial Architecture Review (`gpt-6-luna`)**: [`REVIEW_LUNA56.md`](REVIEW_LUNA56.md) (Codex Session `01a17dc3-8fba-7481-92f8-1c1224c588b4`)
3. **Stage 3 — Core Implementation (`preview/Kimi-K2.7-Code` @ Sakura AI Engine)**: `pipeline_logs/03_impl_sakura_kimi.json` (`chatcmpl-947a5c8ba1e25cf9`) + [`paypal_agent_studio/`](paypal_agent_studio/)
4. **Stage 4 — Post-Implementation Code Review (`gpt-6-luna`)**: [`CODE_REVIEW_LUNA56.md`](CODE_REVIEW_LUNA56.md)

## Quickstart
```bash
PYTHONPATH=. paypal-ai-agent-studio/.venv/bin/pytest -v
PYTHONPATH=. python3 -m paypal_agent_studio.cli
```
