#!/usr/bin/env python3
"""XLRTE setup: the dialogue after the first install. Asks what you want, connects your own AI (subscription, API key or a
local model) and writes everything to this folder. Nothing leaves your machine except the connection test you click.

    python3 setup/xlrte_setup.py            # opens the dialogue in your browser (local only, 127.0.0.1)
    python3 setup/xlrte_setup.py --cli      # the same questions in the terminal
    python3 setup/xlrte_setup.py --status   # is setup done? which AI is connected?

Writes: config/settings.json (answers, no secrets) and .env (API keys, file mode 600, git-ignored). Then it runs the
product's own step (setup/apply_product.py), for example the empty pipeline or the exam plan.
Governance by design: the server binds to 127.0.0.1 only, every request needs a one-time token, keys are never logged,
echoed back or written to settings.json, and "local only" blocks every remote provider in setup/ai.py as well.
Stdlib only, Python >= 3.9.
"""
import argparse
import datetime
import http.server
import json
import os
import secrets
import shutil
import subprocess
import sys
import threading
import urllib.error
import urllib.request
import webbrowser

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SETTINGS = os.path.join(ROOT, "config", "settings.json")
ENV = os.path.join(ROOT, ".env")

# kind: cli (your subscription, signs in in its own app), api (key), local (runs on this machine), none
PROVIDERS = {
    "none": {"label": "Ohne KI (alles Deterministische läuft trotzdem)", "kind": "none", "remote": False},
    "claude-code": {"label": "Claude Code (Claude-Abo Pro/Max)", "kind": "cli", "binary": "claude", "remote": True,
                    "install": "https://code.claude.com/docs/en/setup"},
    "codex": {"label": "Codex CLI (ChatGPT-Abo)", "kind": "cli", "binary": "codex", "remote": True,
              "install": "https://developers.openai.com/codex/cli"},
    "gemini-cli": {"label": "Gemini CLI (Google-Konto)", "kind": "cli", "binary": "gemini", "remote": True,
                   "install": "https://github.com/google-gemini/gemini-cli"},
    "anthropic": {"label": "Anthropic API (Schlüssel)", "kind": "api", "env": "ANTHROPIC_API_KEY", "remote": True,
                  "test": "https://api.anthropic.com/v1/models", "default_model": "claude-sonnet-5-5"},
    "openai": {"label": "OpenAI API (Schlüssel)", "kind": "api", "env": "OPENAI_API_KEY", "remote": True,
               "test": "https://api.openai.com/v1/models", "default_model": ""},
    "google": {"label": "Google Gemini API (Schlüssel)", "kind": "api", "env": "GEMINI_API_KEY", "remote": True,
               "test": "https://generativelanguage.googleapis.com/v1beta/models", "default_model": ""},
    "mistral": {"label": "Mistral API (EU-Anbieter, Schlüssel)", "kind": "api", "env": "MISTRAL_API_KEY", "remote": True,
                "test": "https://api.mistral.ai/v1/models", "default_model": ""},
    "ollama": {"label": "Ollama (lokales Modell, nichts verlässt den Rechner)", "kind": "local", "remote": False,
               "base_url": "http://127.0.0.1:11434"},
    "openai-compatible": {"label": "Lokaler Server, OpenAI-kompatibel (LM Studio, vLLM …)", "kind": "local", "env": "XLRTE_LOCAL_API_KEY",
                          "remote": False, "base_url": "http://127.0.0.1:1234/v1"},
}


# ----------------------------------------------------------------------------- files
def load_settings():
    try:
        with open(SETTINGS, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def needs_setup():
    return not load_settings().get("setup_completed")


def read_env():
    out = {}
    try:
        with open(ENV, encoding="utf-8") as f:
            for line in f:
                k, sep, v = line.strip().partition("=")
                if sep and not k.startswith("#"):
                    out[k.strip()] = v.strip()
    except OSError:
        pass
    return out


def write_env(updates):
    env = read_env()
    env.update({k: v for k, v in updates.items() if v})
    tmp = ENV + ".tmp"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write("# Secrets for this folder only. Never commit, never share. Written by setup/xlrte_setup.py\n")
        for k in sorted(env):
            f.write("%s=%s\n" % (k, env[k]))
    os.replace(tmp, ENV)
    try:
        os.chmod(ENV, 0o600)
    except OSError:
        pass


def save(payload):
    """payload: {answers: {...}, ai: {provider, model, base_url, key}, privacy: {local_only: bool}} -> messages"""
    answers = payload.get("answers") or {}
    ai = dict(payload.get("ai") or {})
    privacy = payload.get("privacy") or {}
    prov = ai.get("provider") or "none"
    if prov not in PROVIDERS:
        raise ValueError("unknown provider %s" % prov)
    spec = PROVIDERS[prov]
    if privacy.get("local_only") and spec["remote"]:
        raise ValueError("'Nur lokal' ist gewählt, %s ist aber ein entfernter Anbieter." % spec["label"])
    key = (ai.pop("key", "") or "").strip()
    if key and spec.get("env"):
        write_env({spec["env"]: key})
    settings = load_settings()
    settings.update({
        "version": 1,
        "product": _product_name(),
        "answers": answers,
        "ai": {"provider": prov, "model": ai.get("model") or spec.get("default_model", ""),
               "base_url": ai.get("base_url") or spec.get("base_url", ""), "key_env": spec.get("env", "")},
        "privacy": {"local_only": bool(privacy.get("local_only")), "telemetry": False},
        "language": answers.get("ui_language") or answers.get("language") or "de",
        "setup_completed": datetime.datetime.now().isoformat(timespec="seconds"),
    })
    os.makedirs(os.path.dirname(SETTINGS), exist_ok=True)
    with open(SETTINGS, "w", encoding="utf-8") as f:
        json.dump(settings, f, ensure_ascii=False, indent=2)
    en = settings["language"] == "en"
    msgs = ["Settings saved: config/settings.json" if en else "Einstellungen gespeichert: config/settings.json"]
    if key:
        msgs.append("Key saved in .env (readable only by you)" if en else "Schlüssel gespeichert in .env (nur lesbar für dich)")
    try:
        sys.path.insert(0, HERE)
        import apply_product
        msgs += apply_product.apply(ROOT, settings) or []
    except ImportError:
        pass
    return msgs


def _product_name():
    try:
        with open(os.path.join(HERE, "schema.json"), encoding="utf-8") as f:
            return json.load(f).get("product", "xlrte")
    except (OSError, ValueError):
        return "xlrte"


# ----------------------------------------------------------------------------- AI detection and test
def detect():
    out = {"cli": {}, "local": {}, "keys": {}}
    for pid, p in PROVIDERS.items():
        if p["kind"] == "cli":
            exe = shutil.which(p["binary"])
            ver = None
            if exe:
                try:
                    ver = subprocess.run([exe, "--version"], capture_output=True, text=True, timeout=15).stdout.strip()[:60] or None
                except (OSError, subprocess.SubprocessError):
                    pass
            out["cli"][pid] = {"installed": bool(exe), "version": ver}
    tags = _get_json("http://127.0.0.1:11434/api/tags", timeout=1.5)
    out["local"]["ollama"] = {"running": tags is not None, "models": [m.get("name") for m in (tags or {}).get("models", [])][:20]}
    env = read_env()
    for pid, p in PROVIDERS.items():
        if p.get("env"):
            out["keys"][pid] = bool(env.get(p["env"]) or os.environ.get(p["env"]))   # only "present", never the value
    return out


def _get_json(url, headers=None, timeout=10):
    try:
        req = urllib.request.Request(url, headers=headers or {})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8") or "{}")
    except (urllib.error.URLError, OSError, ValueError):
        return None


MSG = {
    "unknown": ("unbekannter Anbieter", "unknown provider"),
    "blocked": ("'Nur lokal' ist an: entfernte Anbieter sind gesperrt.", "'Local only' is on: remote providers are blocked."),
    "none": ("Keine KI: nichts zu prüfen.", "No AI: nothing to test."),
    "found": ("Gefunden: %s. Anmeldung erfolgt in der App selbst.", "Found: %s. You sign in inside that app."),
    "missing": ("Nicht installiert. Anleitung: ", "Not installed. Guide: "),
    "ollama_off": ("Ollama läuft nicht. Starte die Ollama-App und lade ein Modell (z. B. 'ollama pull llama3.2').",
                   "Ollama is not running. Start the Ollama app and pull a model (e.g. 'ollama pull llama3.2')."),
    "ollama_n": ("%d lokale Modelle", "%d local models"), "ollama_empty": ("Ollama läuft, aber ohne Modell.", "Ollama runs, but has no model."),
    "need_key": ("Bitte Schlüssel eintragen.", "Please enter a key."),
    "bad": ("Keine gültige Antwort (Schlüssel falsch oder kein Netz).", "No valid answer (wrong key or no network)."),
    "ok": ("Verbunden, %d Modelle sichtbar.", "Connected, %d models visible."),
}


def _t(key, lang):
    return MSG[key][1 if lang == "en" else 0]


def test_provider(provider, key="", base_url="", local_only=False, lang="de"):
    """One harmless call (list models). Only ever triggered by a click. -> {ok, detail, models}"""
    p = PROVIDERS.get(provider)
    if not p:
        return {"ok": False, "detail": _t("unknown", lang)}
    if local_only and p["remote"]:
        return {"ok": False, "detail": _t("blocked", lang)}
    if p["kind"] == "none":
        return {"ok": True, "detail": _t("none", lang)}
    if p["kind"] == "cli":
        d = detect()["cli"].get(provider, {})
        if d.get("installed"):
            return {"ok": True, "detail": _t("found", lang) % (d.get("version") or p["binary"])}
        return {"ok": False, "detail": _t("missing", lang) + p["install"]}
    key = key or read_env().get(p.get("env", ""), "") or os.environ.get(p.get("env", ""), "")
    if provider == "ollama":
        tags = _get_json((base_url or p["base_url"]).rstrip("/") + "/api/tags", timeout=3)
        if tags is None:
            return {"ok": False, "detail": _t("ollama_off", lang)}
        models = [m.get("name") for m in tags.get("models", [])]
        return {"ok": bool(models), "detail": _t("ollama_n", lang) % len(models) if models else _t("ollama_empty", lang), "models": models[:20]}
    if provider == "openai-compatible":
        url = (base_url or p["base_url"]).rstrip("/") + "/models"
        hdr = {"Authorization": "Bearer " + key} if key else {}
    elif provider == "anthropic":
        url, hdr = p["test"], {"x-api-key": key, "anthropic-version": "2023-06-01"}
    elif provider == "google":
        url, hdr = p["test"], {"x-goog-api-key": key}
    else:
        url, hdr = p["test"], {"Authorization": "Bearer " + key}
    if not key and provider != "openai-compatible":
        return {"ok": False, "detail": _t("need_key", lang)}
    data = _get_json(url, hdr, timeout=12)
    if data is None:
        return {"ok": False, "detail": _t("bad", lang)}
    items = data.get("data") or data.get("models") or []
    models = [m.get("id") or m.get("name", "").split("/")[-1] for m in items if isinstance(m, dict)]
    return {"ok": True, "detail": _t("ok", lang) % len(models), "models": models[:25]}


# ----------------------------------------------------------------------------- web dialogue
def _page(token):
    with open(os.path.join(HERE, "wizard.html"), encoding="utf-8") as f:
        html = f.read()
    with open(os.path.join(HERE, "schema.json"), encoding="utf-8") as f:
        schema = json.load(f)
    prov = {k: {kk: vv for kk, vv in v.items() if kk in ("label", "kind", "remote", "install", "default_model", "base_url", "env")}
            for k, v in PROVIDERS.items()}
    boot = {"token": token, "schema": schema, "providers": prov, "settings": {k: v for k, v in load_settings().items() if k != "ai"} | {
        "ai": {k: v for k, v in (load_settings().get("ai") or {}).items() if k != "key"}}}
    return html.replace("/*__BOOT__*/", "window.BOOT = " + json.dumps(boot, ensure_ascii=False).replace("</", "<\\/") + ";")


def serve(open_browser=True, port=0):
    token = secrets.token_urlsafe(18)
    done = threading.Event()

    class H(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a):          # no request logging: bodies can hold keys
            pass

        def _send(self, code, body, ctype="application/json"):
            data = body if isinstance(body, bytes) else (body if isinstance(body, str) else json.dumps(body, ensure_ascii=False)).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", ctype + "; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Content-Security-Policy", "default-src 'self' 'unsafe-inline'; connect-src 'self'")
            self.end_headers()
            self.wfile.write(data)

        def _ok_token(self):
            return self.headers.get("X-Setup-Token") == token

        def do_GET(self):
            if self.path.split("?")[0] == "/" and ("t=" + token) in self.path:
                return self._send(200, _page(token), "text/html")
            if self.path == "/api/detect" and self._ok_token():
                return self._send(200, detect())
            return self._send(404, {"error": "not found"})

        def do_POST(self):
            if not self._ok_token() or self.headers.get("Origin") not in (None, "http://127.0.0.1:%d" % self.server.server_port):
                return self._send(403, {"error": "forbidden"})
            try:
                n = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(min(n, 200_000)).decode("utf-8") or "{}")
            except ValueError:
                return self._send(400, {"error": "bad json"})
            try:
                if self.path == "/api/test":
                    return self._send(200, test_provider(body.get("provider"), body.get("key", ""), body.get("base_url", ""), bool(body.get("local_only")), body.get("lang", "de")))
                if self.path == "/api/save":
                    return self._send(200, {"ok": True, "messages": save(body)})
                if self.path == "/api/quit":
                    self._send(200, {"ok": True})
                    done.set()
                    return
            except Exception as e:                       # show the reason in the dialogue, never a key
                return self._send(200, {"ok": False, "error": str(e)[:300]})
            return self._send(404, {"error": "not found"})

    srv = http.server.ThreadingHTTPServer(("127.0.0.1", port), H)
    url = "http://127.0.0.1:%d/?t=%s" % (srv.server_port, token)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    print("Einrichtung läuft lokal: " + url, flush=True)
    print("(Fenster schließen oder hier Strg+C beendet sie.)")
    if open_browser:
        webbrowser.open(url)
    try:
        done.wait()
    except KeyboardInterrupt:
        pass
    srv.shutdown()
    print("Einrichtung beendet." + ("" if needs_setup() else " Gespeichert."))
    return 0


# ----------------------------------------------------------------------------- terminal dialogue
def cli():
    with open(os.path.join(HERE, "schema.json"), encoding="utf-8") as f:
        schema = json.load(f)
    lang = (input("Sprache / language [de/en] (de): ").strip().lower() or "de")[:2]
    lang = lang if lang in ("de", "en") else "de"
    L = lambda v: (v.get(lang) or v.get("de") or "") if isinstance(v, dict) else (v or "")
    print("\n" + L(schema.get("title")) + "\n" + L(schema.get("intro")) + "\n")
    answers = {"ui_language": lang}
    for step in schema["steps"]:
        print("— " + L(step["title"]))
        for fld in step["fields"]:
            default = fld.get("default", "")
            opts = fld.get("options")
            hint = (" [%s]" % "/".join(o["value"] for o in opts)) if opts else ""
            v = input("%s%s%s: " % (L(fld["label"]), hint, (" (%s)" % default) if default not in ("", None) else "")).strip()
            if fld.get("type") == "checkbox":
                answers[fld["key"]] = (v or str(default)).lower() in ("j", "ja", "y", "yes", "true", "1")
            elif fld.get("type") == "lines":
                answers[fld["key"]] = [x.strip() for x in (v or "").split(";") if x.strip()] or fld.get("default_list", [])
            else:
                answers[fld["key"]] = v or default
    print("— " + ("AI connection" if lang == "en" else "KI-Anbindung"))
    for i, (pid, p) in enumerate(PROVIDERS.items(), 1):
        print("  %d) %s" % (i, p["label"]))
    choice = input("Nummer (1): ").strip() or "1"
    pid = list(PROVIDERS)[int(choice) - 1] if choice.isdigit() and 0 < int(choice) <= len(PROVIDERS) else "none"
    key = ""
    if PROVIDERS[pid]["kind"] == "api":
        import getpass
        key = getpass.getpass("API-Schlüssel (Eingabe unsichtbar): ").strip()
    local_only = input("Nur lokal arbeiten, keine Daten an entfernte KI (j/N): ").strip().lower() in ("j", "ja", "y")
    print(test_provider(pid, key, local_only=local_only, lang=lang)["detail"])
    for m in save({"answers": answers, "ai": {"provider": pid, "key": key}, "privacy": {"local_only": local_only}}):
        print("✓ " + m)
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="XLRTE Einrichtung")
    ap.add_argument("--cli", action="store_true")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--no-browser", action="store_true")
    ap.add_argument("--port", type=int, default=0)
    a = ap.parse_args(argv)
    if a.status:
        s = load_settings()
        print(json.dumps({"setup_completed": s.get("setup_completed"), "ai": s.get("ai"), "privacy": s.get("privacy"),
                          "keys_present": detect()["keys"]}, ensure_ascii=False, indent=1))
        return 0
    return cli() if a.cli else serve(open_browser=not a.no_browser, port=a.port)


if __name__ == "__main__":
    sys.exit(main())
