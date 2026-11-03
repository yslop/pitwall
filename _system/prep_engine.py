#!/usr/bin/env python3
"""
RUNBOOK Step 4d — TOP3 Preparation Engine.
For each top-scoring new Watchlist entry: org research → Noul gate →
Intel HTML + Prep Brief HTML + CV/CL Input Brief → prep.json entry.

CLI:
    python3 prep_engine.py --uid NNN [--today YYYY-MM-DD] [--pipeline PATH] [--lang auto|de|en]

Fill the two HTML files from researched content (Prep_Inhalt.json in 20 Vorbereitung), no scoring or API call:
    python3 prep_engine.py --uid NNN --from-content

Standalone re-run for a single opportunity (also invokable via render.py --mode prep):
    python3 prep_engine.py --uid NNN --today YYYY-MM-DD
"""
import argparse, csv, json, os, re, sys, urllib.request
from datetime import date as _date
from pathlib import Path

HERE = Path(__file__).parent
SYS_DIR = HERE

sys.path.insert(0, str(HERE))
from _typesafe_env import get_typesafe_api_key
from _typesafe_ledger import log_call
from folder_utils import find_company_folder, find_role_folder
from kit_profile import load_profile

# ── Lazy imports (resilient to missing deps) ─────────────────────────────────
def _get_extract_ci():
    try:
        from employer_ci import extract_employer_ci
        return extract_employer_ci
    except Exception:
        return lambda url: "#1e3a8a"


def _get_score_opportunity():
    try:
        from fit_score import score_opportunity
        return score_opportunity
    except Exception:
        return lambda *a, **kw: {"ts_fit_score": 0.0, "salary_fit": "mid",
                                  "boost_contribution": 0, "dimensions": {}}


# ── Language detection ────────────────────────────────────────────────────────
_DE = re.compile(r"\b(wir|suchen|für|und|mit|eine[rn]?|der|die|das|werden|haben|sind|bei|von|zu|als)\b", re.I)
_EN = re.compile(r"\b(we|are|looking|for|and|with|the|will|have|our|join|your|team|you)\b", re.I)


def detect_language(text: str) -> str:
    de = len(_DE.findall(text[:600]))
    en = len(_EN.findall(text[:600]))
    return "de" if de >= en else "en"


# ── TypeSafe Noul gate ────────────────────────────────────────────────────────
TYPESAFE_URL = "https://api.typesafe.ai/v1/systemone"
NOUL_THRESHOLD = 0.60


def noul_readiness_gate(job_title: str, company: str, jd_text: str) -> dict:
    """
    Returns {"research_sufficient": bool, "bypass_identified": bool}.
    Falls back to False/False on error (safe default — never fabricate).
    """
    api_key = get_typesafe_api_key()
    if not api_key:
        return {"research_sufficient": False, "bypass_identified": False}

    state = f"{job_title}\n{company}\n{jd_text[:1000]}"
    payload = json.dumps({
        "state": state,
        "model": "jev-latest",
        "questions": {
            "research_sufficient": {
                "type": "noul",
                "instructions": (
                    "Is there enough verified organisational context to write a tailored "
                    "cover letter for this role without fabricating any facts about the employer?"
                ),
            },
            "bypass_identified": {
                "type": "noul",
                "instructions": (
                    "Has a named contact or warm-channel entry point been identified "
                    "for this opportunity?"
                ),
            },
        },
    }).encode()

    req = urllib.request.Request(
        TYPESAFE_URL, data=payload,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
            log_call("prep_engine", data)
        answers = data["answers"]
        return {
            "research_sufficient": answers["research_sufficient"]["noul"] >= NOUL_THRESHOLD,
            "bypass_identified":   answers["bypass_identified"]["noul"] >= NOUL_THRESHOLD,
        }
    except Exception:
        return {"research_sufficient": False, "bypass_identified": False}


# ── Guardrails ────────────────────────────────────────────────────────────────
_GUARDRAILS_BASE = {
    "de": [
        "Zuhören vor Pitchen — erste 5–10 Min. den Schmerzpunkt verifizieren, nicht die eigene Agenda abspulen.",
        "Comp nicht anschneiden — nicht selbst anbieten oder vorschnell reduzieren.",
        "Nach dem Gespräch: Follow-up-Deliverable tatsächlich liefern — das ist das Differenzierungsmerkmal.",
        "Foundations vor Flash: Governance/Datenqualität vor AI-Glanz betonen.",
    ],
    "en": [
        "Listen first — spend the first 5–10 min verifying the pain point, not pitching.",
        "Do not pre-discount compensation — let them adjust up.",
        "After the conversation: actually deliver the follow-up artefact — that is the differentiator.",
        "Foundations before flash: lead with governance/data quality before AI.",
    ],
}


def guardrails_for(lang, profile=None):
    """Base guardrails; the exit-story line (third position, as before) only when the profile carries a summary."""
    items = list(_GUARDRAILS_BASE[lang])
    summary = ((profile or {}).get("exit_summary") or {}).get(lang, "")
    if summary:
        items.insert(2, ("Exit-Story (falls gefragt): %s Nie anders formulieren." if lang == "de"
                         else "Exit story (if asked): %s Never frame differently.") % summary)
    return items

# ── KEYFACTS field labels ───────────────────────────────────────────────────────
_KEYFACTS_LABELS = {
    "de": [
        ("Diagnostizierter Schmerzpunkt", "diagnosed_pain"),
        ("Value Statement (ihre Metrik)", "value_statement"),
        ("Follow-up-Deliverable gesendet?", "followup_sent"),
        ("Agenda-Artefakt", "agenda_artifact"),
    ],
    "en": [
        ("Diagnosed pain", "diagnosed_pain"),
        ("Value statement (their metric)", "value_statement"),
        ("Follow-up deliverable sent?", "followup_sent"),
        ("Agenda-setting artefact", "agenda_artifact"),
    ],
}


# ── CV/CL Input Brief generator ───────────────────────────────────────────────
def _generate_input_brief(row: dict, lang: str, noul: dict, today: str, profile=None) -> str:
    company = row["company"]
    role    = row["role"]
    uid     = row["uid"]
    rerun   = "Nein" if noul["research_sufficient"] else f"JA — python3 _system/prep_engine.py --uid {uid}"
    P_ = profile or load_profile(str(SYS_DIR))
    name = P_["name"]
    examples = ", ".join(P_["proof_examples"])
    ex_de = "z. B. " + (examples or "ein Programm, eine Kennzahl, ein Ergebnis")
    ex_en = "e.g. " + (examples or "a programme, a metric, an outcome")
    exit_de = P_["exit_summary"]["de"] or "— (noch keine Erzählung im Profil: profile.json → exit_summary)"
    exit_en = P_["exit_summary"]["en"] or "— (no narrative in the profile yet: profile.json → exit_summary)"
    exit_src = os.path.basename(P_["exit_file"]) if P_["exit_file"] else "profile.json"

    if lang == "de":
        return f"""# CV/CL Input Brief — {company} · {role}
*Erstellt: {today} · UID {uid} · Sprache: DE*

---

## 1. Positioning Headline

> *[Einzeiler DE: Value Proposition von {name}, verankert an der Rolle — kein Jobtitel-Echo]*

Vorlage: **„Ich baue Data- und AI-Funktionen, die von Anfang an regierbar und vom ersten Tag an lieferbar sind — und ich habe das bei [Referenz] bewiesen."**

*Quelle: Bio_Bausteine.json · Gespraechs_Playbook.json*

---

## 2. Drei Capability-Anker

### Anker 1 — Governance-by-Design
Was: Controls, Audit und Security von D0 — nicht als Nacharbeit.
Beleg: [{ex_de} — konkret ausfüllen]
Relevanz hier: [{company} — diagnostizierter Schmerzpunkt eintragen]

### Anker 2 — Foundations before Flash
Was: Datenqualität und Governance als Enabler, nicht Bremse — vor AI-Use-Cases.
Beleg: [KPI-Pyramide, Lighthouse Use Case, Programm nennen]
Relevanz hier: [Bezug zu {company} JD-Sprache]

### Anker 3 — Human-in-the-Loop Delivery
Was: Agentic-% pro Workstream sichtbar — System schlägt vor, Mensch entscheidet.
Beleg: [WBS mit agentic-%, MCP-Layer, Governance-Vorlage]
Relevanz hier: [Bezug zu {company} Transformationskontext]

*Quelle: PEA_Leadership_and_Delivery_Playbook.md §1–§6*

---

## 3. Employer Connector

*[Einen Absatz: Wo der diagnostizierte Schmerzpunkt von {company} auf die drei Anker trifft.
Nur dieser Abschnitt ist JD-zugewandt — er verbindet, subordiniert das Profil aber nicht.]*

Vorlage: „{company} steht vor [Schmerzpunkt in JD-Sprache]. Genau das ist der Kontext, in dem
[Anker] den größten Hebel hat — weil [Begründung in ihrer Metrik]."

---

## 4. Exit-Narrativ (kanonisch — nicht abweichen)

{exit_de}

*Quelle: {exit_src}*

---

## 5. Open Hook / Close Hook (K4)

### Open Hook (30 Sek.)
> [Warum diese Rolle, warum jetzt — DE, ~80–100 Wörter. Vorlage aus einer früheren Vorbereitung anpassen.]

### Close Hook (60 Sek.)
> [Konkreter Next-Step-Ask mit Follow-up-Deliverable — DE]

---

## Status
- Research sufficient: {"✓ JA" if noul['research_sufficient'] else "✗ NEIN — erst nach weiterer Recherche finalisieren"}
- Bypass identified: {"✓ JA — Kontakt eintragen" if noul['bypass_identified'] else "✗ kein Warm-Channel gefunden"}
- Rerun needed: {rerun}
"""
    else:
        return f"""# CV/CL Input Brief — {company} · {role}
*Created: {today} · UID {uid} · Language: EN*

---

## 1. Positioning Headline

> *[One sentence EN: {name}'s value proposition anchored to the role — not a job title echo]*

Template: **"I build Data and AI functions that are governable from day zero and deliverable from day one — and I have done it at [reference]."**

*Source: Bio_Bausteine.json · Gespraechs_Playbook.json*

---

## 2. Three Capability Anchors

### Anchor 1 — Governance-by-Design
What: Controls, audit and security from D0 — not as afterthought.
Evidence: [{ex_en} — fill in concretely]
Relevance here: [{company} — fill in diagnosed pain]

### Anchor 2 — Foundations before Flash
What: Data quality and governance as enabler, not brake — before AI use-cases scale.
Evidence: [KPI pyramid, lighthouse use case, programme]
Relevance here: [link to {company} JD language]

### Anchor 3 — Human-in-the-Loop Delivery
What: Make agentic % per workstream visible — system proposes, human decides.
Evidence: [WBS with agentic %, MCP layer, Governance-Vorlage]
Relevance here: [link to {company} transformation context]

*Source: PEA_Leadership_and_Delivery_Playbook.md §1–§6*

---

## 3. Employer Connector

*[One paragraph: where {company}'s diagnosed pain meets the three anchors.
Only this section is JD-facing — it bridges, does not subordinate the profile.]*

Template: "{company} faces [pain in JD language]. That is exactly the context where [Anchor]
has the highest leverage — because [reason in their metric]."

---

## 4. Exit Narrative (canonical — do not deviate)

{exit_en}

*Source: {exit_src}*

---

## 5. Open Hook / Close Hook (K4)

### Open Hook (30 sec)
> [Why this role, why now — EN, ~80–100 words. Adapt a previous template to {company} context.]

### Close Hook (60 sec)
> [Concrete next-step ask with follow-up deliverable — EN]

---

## Status
- Research sufficient: {"✓ YES" if noul['research_sufficient'] else "✗ NO — complete after further research"}
- Bypass identified: {"✓ YES — add contact name" if noul['bypass_identified'] else "✗ no warm channel found"}
- Rerun needed: {rerun}
"""


# ── Jinja2 HTML renderer ──────────────────────────────────────────────────────
TEMPLATE_ERROR = "<html><body><pre>Template render error"


def _render_html(template_name: str, context: dict) -> str:
    try:
        from jinja2 import Environment, FileSystemLoader
        env = Environment(loader=FileSystemLoader(str(SYS_DIR / "templates")))
        tpl = env.get_template(template_name)
        return tpl.render(**context)
    except Exception as exc:
        return f"{TEMPLATE_ERROR}: {exc}</pre></body></html>"



# ── Content file (Prep_Inhalt.json): researched text for the Prep Brief and the JD Intel ──────────────────
CONTENT_FILE = "Prep_Inhalt.json"


def load_content(vorbereitung):
    """Researched content next to the documents, or None. Keys: company_snapshot, strategic_context, contacts, keyfacts,
    open_hook, close_hook, questions [{rank, question, to, why}], open_items, intel {...}. Written from the current briefing."""
    path = Path(vorbereitung) / CONTENT_FILE
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else None
    except (OSError, ValueError):
        return None


def _ranked_questions(content):
    qs = [q for q in (content.get("questions") or []) if isinstance(q, dict) and q.get("question")]
    return sorted(qs, key=lambda q: (q.get("rank") if isinstance(q.get("rank"), (int, float)) else 999))


def _apply_prep_content(ctx, content, lang):
    """Fill the prep-brief context from the content file; whatever it does not carry stays a visible gap."""
    if not content:
        return ctx
    for key in ("company_snapshot", "strategic_context", "open_hook", "close_hook"):
        if content.get(key):
            ctx[key] = content[key]
    if content.get("contacts"):
        ctx["contacts_detail"] = [c for c in content["contacts"] if isinstance(c, dict) and c.get("name")]
    b = content.get("keyfacts") or {}
    ctx["keyfacts_fields"] = [{"label": lbl, "value": b.get(key) or ""} for lbl, key in _KEYFACTS_LABELS[lang]]
    ctx["questions"] = _ranked_questions(content)
    ctx["open_items"] = [o for o in (content.get("open_items") or []) if o]
    return ctx


def _apply_intel_content(ctx, content):
    intel = (content or {}).get("intel") or {}
    for key in ("diagnosed_pain", "decision_maker", "bypass_channel", "scope_signal", "salary_estimate", "anchoring_note", "bypass_label", "jd_bullets", "snapshot"):
        if intel.get(key):
            ctx[key] = intel[key]
    return ctx


PLAYBOOK_FILE = "Gespraechs_Playbook.json"


BIO_FILE = "Bio_Bausteine.json"


def _read_ref(base_dir, name):
    try:
        with open(Path(base_dir) / "00 references" / name, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def load_forbidden(base_dir):
    """Phrases that must never appear in prepared content (00 references/Bio_Bausteine.json, key nicht_sagen_woerter), e.g. a wrong job title."""
    words = _read_ref(base_dir, BIO_FILE).get("nicht_sagen_woerter")
    return [w for w in words if isinstance(w, str) and w] if isinstance(words, list) else []


def load_panik(base_dir):
    """Generic panic-card answers from the playbook (key panik: [{frage, antwort}]); [] if absent."""
    items = _read_ref(base_dir, PLAYBOOK_FILE).get("panik")
    return [i for i in items if isinstance(i, dict) and i.get("frage")] if isinstance(items, list) else []


def load_playbook(base_dir):
    """Lessons learned from earlier conversations (00 references/Gespraechs_Playbook.json, {"items": [{id, titel, problem, stattdessen, quelle}]}); [] if absent."""
    try:
        with open(Path(base_dir) / "00 references" / PLAYBOOK_FILE, encoding="utf-8") as f:
            items = json.load(f).get("items")
        return [i for i in items if isinstance(i, dict) and i.get("titel")] if isinstance(items, list) else []
    except (OSError, ValueError, AttributeError):
        return []


def _cockpit_context(common, row, content, lg, playbook, base_dir):
    ck = content.get("cockpit") or {}
    ctx = dict(common, notes_filename="Interview_Notizen_%s_%s.txt" % (re.sub(r"[^\w\-]", "_", row["company"])[:30], common["today"]), termin=ck.get("termin", ""), partner_line=" · ".join(c.get("name", "") for c in content.get("contacts") or [] if isinstance(c, dict) and c.get("name")),
               lage=ck.get("lage") or {}, stand=ck.get("stand") or [], contacts_detail=[c for c in content.get("contacts") or [] if isinstance(c, dict) and c.get("name")],
               vorschlag=ck.get("vorschlag") or {}, fuehrung=ck.get("fuehrung") or {}, questions=_ranked_questions(content), flanken=ck.get("flanken") or [],
               playbook=playbook, belegt=(ck.get("faktenhygiene") or {}).get("belegt") or [], unbelegt=(ck.get("faktenhygiene") or {}).get("unbelegt") or [],
               vorher=ck.get("vorher") or [], bio=ck.get("bio") or {}, panik=(ck.get("panik") or []) + load_panik(base_dir), title="Cockpit — %s" % row["company"], heading="Cockpit")
    try:                                    # the decision matrix is optional: the cockpit must render without it
        import decision_matrix as DM
        ctx["decision"] = DM.cockpit_context(row, content, DM.load_prefs(str(SYS_DIR)), "en" if lg == "en" else "de", common.get("today", ""))
    except Exception:
        ctx["decision"] = None
    return ctx


# Lehre aus einer Absage (2026-10-15): die Staffing-/Budget-Frage wurde in fünf Gesprächen nie gestellt, die Absage kam genau damit.
STAFFING_RE = re.compile(r"budget|auslastung|staffing|headcount|stellenfreigabe|freigabe|besetz|einsatzplan|wirtschaftlich", re.I)


def validate_content(content, forbidden=()):
    """Findings about thin content (German, one per problem); [] means complete. Rendering still happens, the findings are reported."""
    out = []
    qs = [q for q in (content.get("questions") or []) if isinstance(q, dict) and q.get("question")]
    if len(qs) < 3:
        out.append("weniger als 3 Fragen in questions")
    ranks = [q.get("rank") for q in qs]
    if len(set(ranks)) != len(ranks):
        out.append("doppelter Rang in questions")
    if any(not q.get("to") or not q.get("why") for q in qs):
        out.append("Fragen ohne to/why")
    if not any(STAFFING_RE.search(q["question"]) for q in qs):
        out.append("keine Frage zu Staffing/Budget/Auslastung in questions (Lehre 2026-10-15: Stelle bezahlt, besetzt, mit Auslastung hinterlegt?)")
    if not content.get("company_snapshot"):
        out.append("company_snapshot fehlt")
    b = content.get("keyfacts") or {}
    missing = [k for _, k in _KEYFACTS_LABELS["de"] if not b.get(k)]
    if missing:
        out.append("keyfacts unvollständig (%s)" % ", ".join(missing))
    if not content.get("contacts"):
        out.append("contacts fehlt")
    if not (content.get("intel") or {}).get("jd_bullets"):
        out.append("intel.jd_bullets fehlt")
    ck = content.get("cockpit")
    if not isinstance(ck, dict) or not ck:
        out.append("cockpit fehlt")
    else:
        for key, ok in (("lage", (ck.get("lage") or {}).get("lede")), ("vorschlag", (ck.get("vorschlag") or {}).get("satz")),
                        ("fuehrung", (ck.get("fuehrung") or {}).get("einstieg")), ("vorher", ck.get("vorher")),
                        ("bio", (ck.get("bio") or {}).get("kurz")), ("panik", ck.get("panik"))):
            if not ok:
                out.append("cockpit.%s fehlt" % key)
    import confidence as _cf
    if "confidence" not in content:
        out.append("confidence fehlt (Einschätzung der Chance nach den Gesprächen: pct, begruendung, stand)")
    elif not _cf.valid_judgement(content.get("confidence")):
        out.append("confidence ungültig (pct 1 bis 95 und begruendung nötig)")
    text = json.dumps(content, ensure_ascii=False)
    out += ["verbotene Formulierung im Inhalt: „%s“" % w for w in forbidden if w in text]
    return out


def _live_rows(pipeline_path):
    seen, rows = set(), []
    with open(pipeline_path, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if (r.get("stage") or "") in ("Interviewing", "Final"):
                key = (str(r.get("uid", "")).strip().lstrip("0"), r.get("role"))
                if key not in seen:
                    seen.add(key)
                    rows.append(r)
    return rows


def _vorbereitung_of(row, base_dir):
    folder, _ = find_company_folder(base_dir, row.get("uid", ""), row.get("folder_id", ""))
    if folder is None:
        return None
    chosen, _ = find_role_folder(folder, row.get("role") or "")
    return (chosen or folder) / "20 Vorbereitung"


_NOT_BRIEFING = ("recherche_auftrag", "nachbereitung_auftrag", "prep_auftrag", "cv_cl", "prep_brief", "jd_intel", "prep_inhalt")


def _newest(vorbereitung, test):
    best = None
    try:
        for n in os.listdir(vorbereitung):
            if test(n.lower()):
                m = os.path.getmtime(os.path.join(vorbereitung, n))
                if best is None or m > best[0]:
                    best = (m, n)
    except OSError:
        pass
    return best


def refresh_live(pipeline_path, base_dir, today):
    """Mechanical daily step for every Interviewing/Final process: render when Prep_Inhalt.json is newer than the prep brief; write
    Prep_Auftrag_<Firma>.md when a briefing exists but the content is missing or older than the briefing. Nothing is deleted."""
    rendered, needs, flags = [], [], []
    for row in _live_rows(pipeline_path):
        uid = str(row.get("uid", "")).strip().lstrip("0") or "0"
        vor = _vorbereitung_of(row, base_dir)
        if vor is None or not vor.is_dir():
            continue
        content = _newest(vor, lambda n: n == CONTENT_FILE.lower())
        brief = _newest(vor, lambda n: n.startswith("prep_brief") and n.endswith(".html"))
        briefing = _newest(vor, lambda n: re.search(r"(?<![a-z])briefing", n) and n.endswith((".md", ".html", ".pdf")) and not n.startswith(_NOT_BRIEFING))
        cockpit_file = _newest(vor, lambda n: re.match(r"cockpit[\s_-]", n) and n.endswith(".html"))
        wants_cockpit = False
        if content and not cockpit_file:
            try:
                wants_cockpit = bool((json.load(open(vor / CONTENT_FILE, encoding="utf-8")) or {}).get("cockpit"))
            except (OSError, ValueError):
                wants_cockpit = False
        if content and (not brief or content[0] > brief[0] or wants_cockpit):
            res = render_from_content(uid, pipeline_path, base_dir, today)
            if res["files"]:
                rendered.append(uid)
            flags += ["%s: %s" % (row.get("company"), f) for f in res["flags"]]
        if briefing and (not content or briefing[0] > content[0]):
            why = "Prep_Inhalt.json fehlt" if not content else "Prep_Inhalt.json älter als %s" % briefing[1]
            needs.append({"uid": uid, "company": row.get("company"), "reason": why})
            order = vor / ("Prep_Auftrag_%s.md" % re.sub(r"[^\w\-]", "_", row["company"]))
            order.write_text(
                "# Prep-Auftrag — %s · %s\n\nStand %s · uid %s · Grund: %s\n\n"
                "1. Das aktuelle Briefing lesen: `%s` (und `30 Verlauf`, falls ein Debrief neuer ist).\n"
                "2. `Prep_Inhalt.json` in diesem Ordner schreiben oder aktualisieren. Nur Inhalt aus dem Briefing, keine neuen Fakten; Unbestätigtes nach `open_items`.\n"
                "   Schlüssel: company_snapshot, strategic_context, contacts, keyfacts (diagnosed_pain, value_statement, followup_sent, agenda_artifact), open_hook, close_hook,\n"
                "   questions (rank, question, to, why; mindestens 3, nach Priorität), open_items, intel (snapshot, jd_bullets, diagnosed_pain, decision_maker, scope_signal, salary_estimate),\n"
                "   confidence (pct 1 bis 95, begruendung, stand): deine Einschätzung als Beobachter, wie wahrscheinlich die Stelle gelingt, aus Inhalt der Gespräche und Signalen (nicht aus der Stufe); ehrlich, auch niedrig.\n"
                "3. `python3 _system/prep_engine.py --uid %s --from-content --today %s` ausführen; Befunde (flags) beheben.\n"
                % (row["company"], row["role"], today, uid, why, briefing[1], uid, today), encoding="utf-8")
    return {"rendered": rendered, "needs_content": needs, "flags": flags}


def _photo_path(profile, base_dir):
    return str(Path(base_dir) / profile["photo"]) if profile["photo"] else str(SYS_DIR.parent / "00 references" / "photo.jpg")


def render_from_content(uid, pipeline_path, base_dir, today, lang="auto", profile=None):
    profile = profile or load_profile(str(SYS_DIR))
    """Write JD_Intel and Prep_Brief from Prep_Inhalt.json only: no fit scoring, no TypeSafe call, pipeline.csv/prep.json/CV brief untouched."""
    target = str(uid).strip().lstrip("0") or "0"
    row = None
    with open(pipeline_path, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if str(r.get("uid", "")).strip().lstrip("0") == target and (r.get("stage") or "") not in ("Closed",):
                row = r
                break
    if not row:
        return {"status": "error", "files": [], "flags": ["UID %s has no open row in pipeline.csv" % uid]}
    company_folder, flags = find_company_folder(base_dir, uid, row.get("folder_id", ""))
    if company_folder is None:
        return {"status": "error", "files": [], "flags": flags}
    chosen, more = find_role_folder(company_folder, row.get("role") or "")
    flags += more
    vorbereitung = (chosen or company_folder) / "20 Vorbereitung"
    content = load_content(vorbereitung)
    if content is None:
        return {"status": "error", "files": [], "flags": flags + ["%s fehlt in %s" % (CONTENT_FILE, vorbereitung)]}
    flags += validate_content(content, load_forbidden(base_dir))
    company, role = row["company"], row["role"]
    lg = lang if lang in ("de", "en") else (content.get("lang") if content.get("lang") in ("de", "en") else detect_language(role))
    safe = lambda x: re.sub(r"[^\w\-]", "_", x)
    try:
        ts_fit = float(row.get("ts_fit_score") or 0)
    except ValueError:
        ts_fit = 0.0
    fit = row.get("salary_fit") or "mid"
    from kit_profile import salary_band
    band = salary_band(str(SYS_DIR))
    labels = band["labels"]
    pct = {"top": 95, "high": 75, "mid": 55, "stretch": 35, "below": 15}
    theme = (SYS_DIR / "theme.css").read_text(encoding="utf-8")
    common = {"company": company, "role": role, "uid": uid, "today": today, "lang": lg, "nav": [], "data_json": "{}", "theme_css": theme,
              "footer": "Generated by RUNBOOK · %s · Confidential" % today, "subtitle": "%s · %s" % (company, role)}
    intel_ctx = dict(common, employer_url="", employer_color="#1e3a8a", lane=row.get("lane", ""), ts_fit_score="%.2f" % ts_fit, fit_pct=round(ts_fit * 100),
                     salary_label=labels.get(fit, fit), salary_pct=pct.get(fit, 50), band_text=band["text"], band_low=band["low"], band_high=band["high"], salary_estimate="— pending org research",
                     anchoring_note="Anchor on mandate and value; let them adjust up.", scope_signal="— pending research", bypass_label="— none found",
                     diagnosed_pain="", decision_maker="", bypass_channel="",
                     snapshot=[{"label": "Stage", "value": row.get("stage", "")}, {"label": "Location", "value": row.get("location", "—")},
                               {"label": "Salary fit", "value": labels.get(fit, fit)}],
                     jd_bullets=["— JD text pending"], logo_url="", photo_path=_photo_path(profile, base_dir), applicant_name=profile["name"],
                     title="Intel Brief — %s" % company, heading="Intelligence Brief")
    prep_ctx = dict(common, next_action=row.get("next_action", ""), company_snapshot="%s — pending org research." % company, strategic_context="",
                    contacts_detail=[], keyfacts_fields=[{"label": l, "value": ""} for l, _ in _KEYFACTS_LABELS[lg]], open_hook="", close_hook="",
                    guardrails=guardrails_for(lg, profile), questions=[], open_items=[], title="Prep Brief — %s" % company, heading="Prep Brief")
    def stem(prefix):
        """File name base of an existing document of this kind (so the new dated copy supersedes it instead of living beside it)."""
        old = sorted(n for n in os.listdir(vorbereitung) if n.startswith(prefix + "_") and n.endswith(".html"))
        m = re.match(r"(.+?)_\d{4}-\d{2}-\d{2}\.html$", old[-1]) if old else None
        return m.group(1) if m else "%s_%s_%s" % (prefix, safe(company), safe(role))
    files = []
    jobs = [("%s_%s.html" % (stem("JD_Intel"), today), "intel.html", _apply_intel_content(intel_ctx, content)),
            ("%s_%s.html" % (stem("Prep_Brief"), today), "prep_brief.html", _apply_prep_content(prep_ctx, content, lg))]
    if isinstance(content.get("cockpit"), dict) and content["cockpit"]:
        jobs.append(("%s_%s.html" % (stem("Cockpit"), today), "conversation_cockpit.html", _cockpit_context(common, row, content, lg, load_playbook(base_dir), base_dir)))
    pages = [(name, _render_html(tpl, ctx)) for name, tpl, ctx in jobs]
    if any(page.startswith(TEMPLATE_ERROR) for _, page in pages):
        return {"status": "error", "files": [], "flags": flags + ["Vorlagen-Bibliothek fehlt oder Vorlage fehlerhaft (jinja2): keine Seite geschrieben"]}
    for name, page in pages:
        out = vorbereitung / name
        out.write_text(page, encoding="utf-8")
        files.append(str(out))
    return {"status": "partial" if flags else "ok", "files": files, "flags": flags}


# ── Main prep runner ──────────────────────────────────────────────────────────
def run_prep(
    uid: int,
    pipeline_path: str,
    prep_json_path: str,
    base_dir: str,
    today: str,
    lang: str = "auto",
    profile=None,
) -> dict:
    """
    Run full preparation for a single UID.
    Returns {"status": "ok"|"partial"|"error", "files": list[str], "flags": list[str]}
    """
    profile = profile or load_profile(str(SYS_DIR))
    # Load pipeline row
    def _norm(val):
        s = str(val or "").strip()
        try:
            return str(int(s))
        except ValueError:
            return s

    target_uid = _norm(uid)
    row = None
    with open(pipeline_path, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if _norm(r.get("uid", "")) == target_uid:
                row = r
                break
    if not row:
        return {"status": "error", "files": [], "flags": [f"UID {uid} not found in pipeline.csv"]}

    company = row["company"]
    role    = row["role"]
    jd_text = row.get("note", "") or ""

    # Language detection
    detected_lang = lang if lang in ("de", "en") else detect_language(jd_text or role)

    # Employer CI
    extract_ci = _get_extract_ci()
    employer_url = ""   # URL not stored in pipeline; CI falls back to personal brand
    ci_color = extract_ci(employer_url) if employer_url.startswith("http") else "#1e3a8a"

    # Fit score
    score_fn = _get_score_opportunity()
    fit_result = score_fn(role, company, jd_text, "")
    if "error" in fit_result:
        fit_result = {"ts_fit_score": 0.0, "salary_fit": row.get("salary_fit", "mid"),
                      "boost_contribution": 0, "dimensions": {}}

    # Noul readiness gate
    noul = noul_readiness_gate(role, company, jd_text)

    # Locate Vorbereitung folder — match the role subfolder against the
    # pipeline row's `role` text instead of taking the alphabetically-first
    # one, so companies with more than one role subfolder (parallel tracks)
    # don't silently get their dossier written into the wrong one. Also
    # resolves pre-existing uid-prefix collisions (e.g. uids 167-170) via
    # the row's folder_id instead of guessing.
    company_folder, company_flags = find_company_folder(base_dir, uid, row.get("folder_id", ""))
    if company_folder is None:
        return {"status": "error", "files": [], "flags": company_flags}

    chosen, subfolder_flags = find_role_folder(company_folder, role)
    role_flags = company_flags + subfolder_flags
    if chosen is None:
        # No role subfolders yet — write directly under the company folder
        # (matches prior fallback behaviour).
        chosen = company_folder

    vorbereitung = chosen / "20 Vorbereitung"
    vorbereitung.mkdir(parents=True, exist_ok=True)

    files_written = []
    flags = list(role_flags)
    safe_company = re.sub(r"[^\w\-]", "_", company)
    safe_role    = re.sub(r"[^\w\-]", "_", role)

    # ── 1. CV/CL Input Brief (Markdown) ─────────────────────────────────────
    brief_md = _generate_input_brief(row, detected_lang, noul, today, profile)
    brief_path = vorbereitung / f"CV_CL_Input_Brief_{safe_company}_{safe_role}.md"
    brief_path.write_text(brief_md, encoding="utf-8")
    files_written.append(str(brief_path))
    if not noul["research_sufficient"]:
        flags.append("research_sufficient=False — CV/CL Brief is a skeleton; rerun after research")

    # ── 2. Intel HTML ────────────────────────────────────────────────────────
    ts_fit = fit_result.get("ts_fit_score", 0.0)
    fit_pct = round(ts_fit * 100)
    salary_fit_val = fit_result.get("salary_fit", row.get("salary_fit", "mid"))
    from kit_profile import salary_band
    band = salary_band(str(SYS_DIR))
    salary_labels = band["labels"]
    salary_pct_map = {"top": 95, "high": 75, "mid": 55, "stretch": 35, "below": 15}

    photo_path = _photo_path(profile, base_dir)

    intel_ctx = {
        "company": company, "role": role, "uid": uid,
        "employer_url": employer_url, "employer_color": ci_color,
        "today": today, "lane": row.get("lane", ""),
        "ts_fit_score": f"{ts_fit:.2f}", "fit_pct": fit_pct,
        "salary_label": salary_labels.get(salary_fit_val, salary_fit_val),
        "salary_pct": salary_pct_map.get(salary_fit_val, 50),
        "band_text": band["text"], "band_low": band["low"], "band_high": band["high"],
        "salary_estimate": "— pending org research",
        "anchoring_note": "Anchor on mandate and value; let them adjust up.",
        "scope_signal": "— pending research",
        "bypass_label": "✓ identified" if noul["bypass_identified"] else "— none found",
        "diagnosed_pain": jd_text[:120] if jd_text else "",
        "decision_maker": "", "bypass_channel": "",
        "snapshot": [
            {"label": "Stage", "value": row.get("stage", "Watchlist")},
            {"label": "Location", "value": row.get("location", "—")},
            {"label": "Salary fit", "value": salary_labels.get(salary_fit_val, salary_fit_val)},
        ],
        "jd_bullets": [jd_text[:200]] if jd_text else ["— JD text pending"],
        "logo_url": "", "photo_path": photo_path, "applicant_name": profile["name"],
        "title": f"Intel Brief — {company}", "heading": f"Intelligence Brief",
        "subtitle": f"{company} · {role}",
        "footer": f"Generated by RUNBOOK · {today} · Confidential",
        "nav": [], "data_json": "{}",
        "theme_css": (SYS_DIR / "theme.css").read_text(encoding="utf-8"),
        "lang": detected_lang,
    }
    content = load_content(vorbereitung)
    intel_ctx = _apply_intel_content(intel_ctx, content)
    intel_html = _render_html("intel.html", intel_ctx)
    intel_path = vorbereitung / f"JD_Intel_{safe_company}_{safe_role}_{today}.html"
    intel_path.write_text(intel_html, encoding="utf-8")
    files_written.append(str(intel_path))

    # ── 3. Prep Brief HTML ───────────────────────────────────────────────────
    keyfacts_labels = _KEYFACTS_LABELS[detected_lang]
    keyfacts_fields = [{"label": lbl, "value": ""} for lbl, _ in keyfacts_labels]

    guardrails = guardrails_for(detected_lang, profile)

    prep_ctx = {
        "company": company, "role": role, "uid": uid,
        "today": today, "lang": detected_lang,
        "next_action": row.get("next_action", ""),
        "company_snapshot": f"{company} — pending org research.",
        "strategic_context": "",
        "contacts_detail": [],
        "keyfacts_fields": keyfacts_fields,
        "open_hook": "", "close_hook": "",
        "guardrails": guardrails, "questions": [], "open_items": [],
        "title": f"Prep Brief — {company}", "heading": "Prep Brief",
        "subtitle": f"{company} · {role}",
        "footer": f"Generated by RUNBOOK · {today} · Confidential",
        "nav": [], "data_json": "{}",
        "theme_css": (SYS_DIR / "theme.css").read_text(encoding="utf-8"),
    }
    prep_ctx = _apply_prep_content(prep_ctx, content, detected_lang)
    prep_html = _render_html("prep_brief.html", prep_ctx)
    prep_path = vorbereitung / f"Prep_Brief_{safe_company}_{safe_role}_{today}.html"
    prep_path.write_text(prep_html, encoding="utf-8")
    files_written.append(str(prep_path))

    # ── 4. Update prep.json ──────────────────────────────────────────────────
    try:
        with open(prep_json_path, encoding="utf-8") as f:
            prep = json.load(f)
    except Exception:
        prep = {}

    prep[str(uid)] = {
        "management_summary": f"Prioritäres Verfahren für {role} bei {company}. "
                              + (f"Nächster Meilenstein: {row.get('next_action', 'Erstgespräch terminieren')}. " if row.get("next_action") else "Initiale Vorbereitung abgeschlossen. ")
                              + f"Gehaltseinstufung: {salary_labels.get(salary_fit_val, salary_fit_val)}.",
        "next_steps": [
            {
                "action": row.get("next_action") or f"Terminabstimmung für {role} durchführen",
                "owner": "Kandidat",
                "due": row.get("due") or today,
                "status": "fällig" if row.get("due") else "offen"
            },
            {
                "action": "Dossier & Stakeholder-Briefing überprüfen",
                "owner": "Kandidat",
                "due": today,
                "status": "geplant"
            },
            {
                "action": "Gehaltsanker & Value Proposition bereitstellen",
                "owner": "Kandidat",
                "due": today,
                "status": "bereit"
            }
        ],
        "hooks": [jd_text[:120] + "…" if len(jd_text) > 120 else (jd_text or "— pending research")],
        "risks": ["Comp gap — below the target band" if salary_fit_val in ("stretch", "below") else ""],
        "rerun_needed": not noul["research_sufficient"],
        "assets": [
            {"name": "CV/CL Input Brief", "where": f"Drive · {uid} {company}/Role/20 Vorbereitung"},
            {"name": "Intel Brief (HTML)", "where": f"Drive · {uid} {company}/Role/20 Vorbereitung"},
            {"name": "Prep Brief (HTML)",  "where": f"Drive · {uid} {company}/Role/20 Vorbereitung"},
        ],
    }
    with open(prep_json_path, "w", encoding="utf-8") as f:
        json.dump(prep, f, indent=2, ensure_ascii=False)

    # ── 5. Update pipeline.csv ───────────────────────────────────────────────
    rows_out = []
    with open(pipeline_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = list(reader.fieldnames or [])
        for r in reader:
            if r.get("uid", "").strip() == str(uid):
                r["ts_fit_score"] = str(round(fit_result.get("ts_fit_score", 0), 4))
                r["salary_fit"]   = salary_fit_val
            rows_out.append(r)
    with open(pipeline_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows_out)

    return {
        "status": "partial" if flags else "ok",
        "files": files_written,
        "flags": flags,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--uid",      default="", help="UID of the opportunity (e.g. 133 or 09)")
    ap.add_argument("--today",    default=_date.today().isoformat())
    ap.add_argument("--pipeline", default=str(SYS_DIR / "pipeline.csv"))
    ap.add_argument("--prep",     default=str(SYS_DIR / "prep.json"))
    ap.add_argument("--base-dir", default=str(SYS_DIR.parent))
    ap.add_argument("--lang",     default="auto", choices=["auto", "de", "en"])
    ap.add_argument("--refresh-live", action="store_true", help="daily: render where Prep_Inhalt.json is newer, order content where it is missing or stale (uid not needed)")
    ap.add_argument("--from-content", action="store_true", help="render only JD Intel + Prep Brief from Prep_Inhalt.json (no scoring, no TypeSafe)")
    a = ap.parse_args()
    if a.refresh_live:
        print(json.dumps(refresh_live(a.pipeline, a.base_dir, a.today), indent=2, ensure_ascii=False))
        return
    if not a.uid:
        ap.error("--uid is required unless --refresh-live")
    if a.from_content:
        print(json.dumps(render_from_content(a.uid, a.pipeline, a.base_dir, a.today, a.lang), indent=2, ensure_ascii=False))
        return

    result = run_prep(
        uid=a.uid,
        pipeline_path=a.pipeline,
        prep_json_path=a.prep,
        base_dir=a.base_dir,
        today=a.today,
        lang=a.lang,
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
