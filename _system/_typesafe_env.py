"""
Shared TypeSafe API key loader.

Checks the environment first (TYPESAFE_API_KEY), then falls back to a local
`_system/.env` file next to this module. The fallback exists because the
RUNBOOK's automated/scheduled runs execute in a fresh shell each time with
no exported environment variables, so a file next to the scripts is the
only thing that reliably persists the key across runs.
"""
import os


def get_typesafe_api_key() -> str:
    key = os.environ.get("TYPESAFE_API_KEY", "")
    if key:
        return key
    # TYPESAFE_ENV_FILE lets tests point at an empty file so a real .env can't leak in.
    env_path = os.environ.get("TYPESAFE_ENV_FILE") or os.path.join(
        os.path.dirname(os.path.abspath(__file__)), ".env")
    try:
        with open(env_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if line.startswith("TYPESAFE_API_KEY="):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
    except OSError:
        pass
    return ""
