"""The only contact with the customer's AI account: is an official agent app installed? Never reads, stores or sends credentials,
never installs or starts an agent app. The customer installs it with the provider's own command and signs in himself."""
import shutil
import subprocess
import sys

AGENTS = {
    "claude": {
        "label": "Claude Code (Claude-Abo, Pro oder Max)", "binary": "claude", "start": "claude",
        "install": {"darwin": "curl -fsSL https://claude.ai/install.sh | bash", "linux": "curl -fsSL https://claude.ai/install.sh | bash",
                    "windows": "irm https://claude.ai/install.ps1 | iex"},
        "docs": "https://code.claude.com/docs/en/setup", "check": "claude --version",
    },
    "codex": {
        "label": "Codex (ChatGPT-Abo, ungetestet)", "binary": "codex", "start": "codex --search",
        "install": {"darwin": "curl -fsSL https://chatgpt.com/codex/install.sh | sh", "linux": "curl -fsSL https://chatgpt.com/codex/install.sh | sh",
                    "windows": None},
        "docs": "https://learn.chatgpt.com/docs/codex/cli", "check": "codex --version",
    },
}
SHELL = {"darwin": "Terminal", "linux": "Terminal", "windows": "PowerShell"}


def status(agent, which=shutil.which, run=subprocess.run):
    exe = which(AGENTS[agent]["binary"])
    if not exe:
        return {"installed": False, "version": None}
    try:
        out = run([exe, "--version"], capture_output=True, text=True, timeout=20)
        return {"installed": True, "version": (out.stdout or "").strip() or None}
    except (OSError, subprocess.SubprocessError):
        return {"installed": True, "version": None}


def installed_agents(which=shutil.which):
    return [name for name, a in AGENTS.items() if which(a["binary"])]


def instructions(platform):
    key = platform if platform in SHELL else "linux"
    lines = ["Deine Vorbereitung läuft in einer KI-Anwendung auf deinem Rechner. Du brauchst eines der beiden Abos und installierst die Anwendung selbst:"]
    for i, (name, a) in enumerate(AGENTS.items(), 1):
        cmd = a["install"][key]
        how = ("Öffne %s und füge den offiziellen Befehl ein: %s" % (SHELL[key], cmd)) if cmd else "Installation: Anleitung des Anbieters unter " + a["docs"]
        lines.append("%d. %s. %s. Prüfen mit: %s. Starten im Bewerbungsordner mit: %s" % (i, a["label"], how, a["check"], a["start"]))
    lines += ["Du meldest dich selbst beim Anbieter an (im Browser). Dieses Kit sieht, speichert und sendet deine Zugangsdaten nie und startet die Anwendung nie selbst.",
              "Anleitungen: " + " | ".join(a["docs"] for a in AGENTS.values())]
    return "\n".join(lines)


def main():
    for name in AGENTS:
        print(name, status(name))
    print(instructions({"win32": "windows", "darwin": "darwin"}.get(sys.platform, "linux")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
