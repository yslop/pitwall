"""One door to the AI the user connected in setup. Engines call `complete()` and never see which provider answers.

    from setup import ai
    text = ai.complete("Fasse diese Stellenanzeige in drei Punkten zusammen: ...", purpose="jd_summary")

Rules (governance by design):
- No provider configured, or provider "none": raises AINotConfigured. Callers must have a deterministic fallback.
- "local_only" in settings: every remote provider is refused here too, not only in the setup dialogue.
- CLI providers (Claude Code, Codex, Gemini CLI) use the user's own subscription in its own app: called non-interactively.
- Every call is logged to logs/ai_calls.jsonl with time, provider, model, purpose and sizes. Never prompt or answer text.
Stdlib only, Python >= 3.9.
"""
import datetime
import json
import os
import shutil
import subprocess
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)


class AINotConfigured(RuntimeError):
    pass


class AIRefused(RuntimeError):
    pass


def _settings():
    try:
        with open(os.path.join(ROOT, "config", "settings.json"), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _key(env_name):
    if not env_name:
        return ""
    if os.environ.get(env_name):
        return os.environ[env_name]
    try:
        with open(os.path.join(ROOT, ".env"), encoding="utf-8") as f:
            for line in f:
                k, _, v = line.strip().partition("=")
                if k == env_name:
                    return v.strip()
    except OSError:
        pass
    return ""


def _post(url, headers, body, timeout=120):
    req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), headers=dict(headers, **{"Content-Type": "application/json"}))
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def _log(provider, model, purpose, n_in, n_out, ok):
    os.makedirs(os.path.join(ROOT, "logs"), exist_ok=True)
    with open(os.path.join(ROOT, "logs", "ai_calls.jsonl"), "a", encoding="utf-8") as f:
        f.write(json.dumps({"ts": datetime.datetime.now().isoformat(timespec="seconds"), "provider": provider, "model": model,
                            "purpose": purpose, "chars_in": n_in, "chars_out": n_out, "ok": ok}) + "\n")


def status():
    s = _settings()
    ai = s.get("ai") or {}
    return {"provider": ai.get("provider", "none"), "model": ai.get("model", ""), "local_only": bool((s.get("privacy") or {}).get("local_only"))}


def complete(prompt, system="", purpose="general", max_tokens=1200, timeout=180):
    s = _settings()
    ai = s.get("ai") or {}
    prov, model, base = ai.get("provider", "none"), ai.get("model", ""), (ai.get("base_url") or "").rstrip("/")
    local_only = bool((s.get("privacy") or {}).get("local_only"))
    if prov in ("", "none"):
        raise AINotConfigured("Keine KI eingerichtet (python3 setup/xlrte_setup.py)")
    remote = prov not in ("ollama", "openai-compatible")
    if local_only and remote:
        raise AIRefused("'Nur lokal' ist eingestellt: %s wird nicht aufgerufen" % prov)
    text, ok = "", False
    try:
        if prov in ("claude-code", "codex", "gemini-cli"):
            exe = shutil.which({"claude-code": "claude", "codex": "codex", "gemini-cli": "gemini"}[prov])
            if not exe:
                raise AINotConfigured("%s ist nicht installiert" % prov)
            argv = {"claude-code": [exe, "-p"], "codex": [exe, "exec"], "gemini-cli": [exe, "-p"]}[prov]
            full = (system + "\n\n" + prompt) if system else prompt
            r = subprocess.run(argv + [full], capture_output=True, text=True, timeout=timeout, cwd=ROOT)
            text = r.stdout.strip()
        elif prov == "anthropic":
            d = _post("https://api.anthropic.com/v1/messages", {"x-api-key": _key(ai.get("key_env")), "anthropic-version": "2023-06-01"},
                      {"model": model, "max_tokens": max_tokens, "system": system, "messages": [{"role": "user", "content": prompt}]}, timeout)
            text = "".join(b.get("text", "") for b in d.get("content", []))
        elif prov == "google":
            d = _post("https://generativelanguage.googleapis.com/v1beta/models/%s:generateContent" % model, {"x-goog-api-key": _key(ai.get("key_env"))},
                      {"contents": [{"parts": [{"text": (system + "\n\n" if system else "") + prompt}]}]}, timeout)
            text = "".join(p.get("text", "") for c in d.get("candidates", [])[:1] for p in c.get("content", {}).get("parts", []))
        elif prov == "ollama":
            d = _post((base or "http://127.0.0.1:11434") + "/api/chat", {},
                      {"model": model, "stream": False, "messages": ([{"role": "system", "content": system}] if system else []) + [{"role": "user", "content": prompt}]}, timeout)
            text = d.get("message", {}).get("content", "")
        else:   # openai, mistral, openai-compatible
            url = {"openai": "https://api.openai.com/v1", "mistral": "https://api.mistral.ai/v1"}.get(prov, base)
            key = _key(ai.get("key_env"))
            d = _post(url + "/chat/completions", {"Authorization": "Bearer " + key} if key else {},
                      {"model": model, "max_tokens": max_tokens,
                       "messages": ([{"role": "system", "content": system}] if system else []) + [{"role": "user", "content": prompt}]}, timeout)
            text = d["choices"][0]["message"]["content"]
        ok = bool(text)
        return text
    finally:
        _log(prov, model, purpose, len(prompt) + len(system), len(text), ok)
