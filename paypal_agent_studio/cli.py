"""CLI entrypoint for PayPal Agentic Commerce Studio (`paypal_agent_studio`)."""

from __future__ import annotations

import json
from pathlib import Path

from .engine import run_procurement_workflow


def main() -> int:
    res = run_procurement_workflow()
    out = Path(__file__).resolve().parent.parent / "artifacts" / "latest_procurement_run.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(res, indent=2), encoding="utf-8")
    print(json.dumps(res, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
