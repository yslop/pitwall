"""kit_agent.py: the only contact with the customer's AI account is a look at whether an official agent app is installed."""
import os, sys
SYSTEM = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, SYSTEM)
import kit_agent as K


class Proc:
    def __init__(self, out):
        self.stdout, self.returncode = out, 0


def test_status_not_installed_when_the_binary_is_missing():
    assert K.status("claude", which=lambda name: None) == {"installed": False, "version": None}


def test_status_reads_only_the_version_of_the_right_binary():
    calls = []
    st = K.status("codex", which=lambda name: "/x/" + name, run=lambda cmd, **kw: calls.append(cmd) or Proc("codex 1.2.3\n"))
    assert st == {"installed": True, "version": "codex 1.2.3"} and calls == [["/x/codex", "--version"]]


def test_status_survives_a_broken_binary():
    def boom(cmd, **kw):
        raise OSError("nope")
    assert K.status("claude", which=lambda name: "/x/claude", run=boom) == {"installed": True, "version": None}


def test_installed_agents_lists_what_is_found():
    assert K.installed_agents(which=lambda n: "/x/" + n if n == "codex" else None) == ["codex"]
    assert K.installed_agents(which=lambda n: None) == []


def test_instructions_name_both_official_options_and_say_who_signs_in():
    mac, win = K.instructions("darwin"), K.instructions("windows")
    assert "curl -fsSL https://claude.ai/install.sh | bash" in mac and "irm https://claude.ai/install.ps1 | iex" in win
    assert "curl -fsSL https://chatgpt.com/codex/install.sh | sh" in mac and "https://learn.chatgpt.com/docs/codex/cli" in win
    assert "claude --version" in mac and "codex --search" in mac
    for text in (mac, win):
        assert "meldest dich selbst" in text and "Zugangsdaten" in text and "nie" in text


def test_the_module_never_touches_credentials_or_settings():
    src = open(os.path.join(SYSTEM, "kit_agent.py"), encoding="utf-8").read()
    code = "\n".join(l for l in src.split("\n") if not l.strip().startswith(("#", '"""')))
    for forbidden in ("open(", "/.claude", "/.codex", "environ", "keychain", "oauth", "token", "api_key", "access-token", "--with-"):
        assert forbidden not in code.lower(), forbidden
