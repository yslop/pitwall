"""Per-pilot marks in the customer documents: a visible kit id and slightly different wording in a few fixed sentences.

A deterrent and a trace, not a protection. The mapping pilot -> kit id lives with the owner (dist/pilot_register.csv), never in the kit.
"""
import hashlib
import re

SLOTS = {
    "send": ("Nichts wird gesendet, nichts gelöscht.", "Es wird nichts gesendet und nichts gelöscht.", "Nichts wird versendet, nichts wird gelöscht.", "Weder wird etwas gesendet noch etwas gelöscht."),
    "overwrite": ("Frühere Versionen nie überschreiben.", "Ältere Versionen werden nie überschrieben.", "Vorherige Fassungen niemals überschreiben.", "Frühere Fassungen bleiben unverändert."),
    "open": ("Unbestätigtes nach `open_items`.", "Was unbestätigt ist, gehört nach `open_items`.", "Unbestätigtes wandert nach `open_items`.", "Nicht Bestätigtes kommt nach `open_items`."),
}


def kit_id(pilot):
    return "KIT-" + hashlib.sha256(pilot.encode("utf-8")).hexdigest()[:8].upper()


def _pick(pilot, slot):
    variants = SLOTS[slot]
    return variants[int(hashlib.sha256((pilot + ":" + slot).encode("utf-8")).hexdigest(), 16) % len(variants)]


def apply(text, pilot):
    text = text.replace("{{KIT_ID}}", kit_id(pilot))
    return re.sub(r"\{\{MARK:(\w+)\}\}", lambda m: _pick(pilot, m.group(1)) if m.group(1) in SLOTS else m.group(0), text)


def identify(text, pilots):
    scored = []
    for p in pilots:
        score = 10 if kit_id(p) in text else 0
        score += sum(1 for slot in SLOTS if _pick(p, slot) in text)
        if score:
            scored.append((score, p))
    return [p for _, p in sorted(scored, key=lambda t: (-t[0], t[1]))]
