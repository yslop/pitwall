"""
Shared TypeSafe call ledger.

Appends one line per Jev call to `_system/logs/llm_calls.jsonl`, the same ledger the decision
panel writes, so `python3 -m decision_layer.infrastructure.usage` sees every Jev token (step 2,
discovery, fit score, JD gate, prep) and can flag spikes (Verfassung §5). Tokens and cost only,
never message text. Never raises: a logging problem must not break a run.
TYPESAFE_LEDGER=off disables it (the test runner sets this).
"""
import json
import os
from datetime import datetime, timezone

PRICE_PER_MTOK = 0.042   # USD per million input tokens, as in decisions/governance.json
LOG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs", "llm_calls.jsonl")


def log_call(task: str, data: dict) -> None:
    try:
        if os.environ.get("TYPESAFE_LEDGER", "").lower() == "off":
            return
        usage = (data or {}).get("usage")
        if not isinstance(usage, dict):
            return
        tokens = int(usage.get("input_tokens") or 0)
        os.makedirs(os.path.dirname(LOG), exist_ok=True)
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps({
                "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "backend": "jev", "model": data.get("model"), "task": task,
                "input_tokens": tokens, "cost_usd": tokens * PRICE_PER_MTOK / 1e6,
            }, sort_keys=True) + "\n")
    except Exception:
        pass
