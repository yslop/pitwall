"""Who the kit serves: `profile.json` next to the engine. Every field is optional and a broken file never raises.

Fields: name, brand_name, photo (path), exit_file (path of the canonical exit narrative), exit_summary {de, en},
proof_examples (up to 5 short examples used in templates). Python 3.9 compatible.
"""
import copy
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULTS = {
    "name": "Bewerber:in",
    "brand_name": "STAR",
    "photo": "",
    "exit_file": "",
    "exit_summary": {"de": "", "en": ""},
    "proof_examples": [],
}


def load_profile(system_dir=None):
    out = copy.deepcopy(DEFAULTS)
    try:
        with open(os.path.join(system_dir or HERE, "profile.json"), encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return out
    if not isinstance(data, dict):
        return out
    for key in ("name", "brand_name", "photo", "exit_file"):
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            out[key] = value.strip()
    summary = data.get("exit_summary")
    if isinstance(summary, dict):
        for lang in ("de", "en"):
            if isinstance(summary.get(lang), str):
                out["exit_summary"][lang] = summary[lang].strip()
    examples = data.get("proof_examples")
    if isinstance(examples, list):
        out["proof_examples"] = [x.strip() for x in examples if isinstance(x, str) and x.strip()][:5]
    return out


def salary_band(system_dir=None):
    """The user's own salary band from preferences.json (setup): salary_band {floor, target, currency} or salary_floor.
    -> {"text", "low", "high", "labels" {top, high, mid, stretch, below}, "instructions", "criteria"}; neutral words if no band is set."""
    try:
        with open(os.path.join(system_dir or HERE, "preferences.json"), encoding="utf-8") as f:
            prefs = json.load(f)
    except (OSError, ValueError):
        prefs = {}
    band = prefs.get("salary_band") if isinstance(prefs.get("salary_band"), dict) else {}
    cur = str(band.get("currency") or "€")
    try:
        lo = float(band.get("floor") or prefs.get("salary_floor") or 0)
        hi = float(band.get("target") or 0) or (lo * 1.5 if lo else 0)
    except (TypeError, ValueError):
        lo = hi = 0
    if not lo:
        words = {"top": "deutlich über Ziel", "high": "oberes Zielband", "mid": "im Zielband", "stretch": "unteres Zielband", "below": "unter Zielband"}
        return {"text": "", "low": "", "high": "", "labels": words,
                "instructions": "Rate salary fit against the candidate's target band (not specified: judge seniority and market level of the role).",
                "criteria": ["Below the candidate's band", "Low end of the band", "Mid band with upside", "Clearly at or above the target"]}
    k = lambda v: "%s%dk" % (cur, round(v / 1000))
    m1, m2 = lo + (hi - lo) / 3, lo + 2 * (hi - lo) / 3
    return {"text": "%s–%s+" % (k(lo), k(hi)), "low": k(lo), "high": k(hi) + "+",
            "labels": {"top": "≥%s (top)" % k(hi), "high": "%s–%s" % (k(m2), k(hi)), "mid": "%s–%s" % (k(m1), k(m2)), "stretch": "%s–%s" % (k(lo), k(m1)), "below": "<%s" % k(lo)},
            "instructions": "Rate salary fit against the band %s–%s+. Score high if clearly ≥%s, mid if %s–%s with upside, low if %s–%s, minimal if below %s."
                            % (k(lo), k(hi), k(hi), k(m1), k(hi), k(lo), k(m1), k(lo)),
            "criteria": ["Below band — clearly under %s or no indication of meeting the band" % k(lo), "Low end of the band — roughly %s–%s" % (k(lo), k(m1)),
                         "Mid band with upside — roughly %s–%s" % (k(m1), k(hi)), "High — clearly ≥%s" % k(hi)]}
