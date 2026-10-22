#!/usr/bin/env python3
"""
Job Search Cockpit & CRM — Renders every browser view from ONE canonical dataset.

    python3 render.py --data pipeline.csv --prep prep.json --out ../out

Inputs:
    pipeline.csv   the canonical record, one row per opportunity (see SCHEMA.md)
    prep.json      optional per-UID prep content for the Briefing view
    folders.tsv    optional Drive folder inventory for integrity reconciliation
Outputs:
    01_cockpit.html          what to do today / live processes / idle decay / hygiene
    02_pipeline_crm.html     all rows, rich filter + sort + search + detail drawer
    03_briefings.html        executive briefing dossier per live process (Hooks/Risks/Assets)
    04_agentur_report.html   German compliance view (DIN A4 print-optimized, sanitized notes)
    04_agentur_report.pdf    PDF print export (when wkhtmltopdf is present)
    sheet_export.csv         flat mirror to paste into Google Sheet

Architecture:
    - Dual-engine rendering: uses jinja2 when installed; seamlessly falls back
      to built-in pure Python template engine when jinja2 is missing. Zero hard dependencies.
    - Privacy-aware: sanitizes raw personal email addresses in external compliance views.
    - Offline-capable: generates self-contained HTML with embedded JSON and styles.
"""
import argparse
import base64, csv, html, json, os, re, shutil, subprocess, sys
from collections import OrderedDict, Counter
from datetime import date
from kit_profile import load_profile

HERE = os.path.dirname(os.path.abspath(__file__))


def load_i18n(system_dir=None):
    """<script> blocks for the English UI layer (i18n.js + i18n_en.json); language from preferences.json ui_language. '' if missing."""
    d = system_dir or HERE
    try:
        with open(os.path.join(d, "i18n.js"), encoding="utf-8") as f:
            js = f.read()
        with open(os.path.join(d, "i18n_en.json"), encoding="utf-8") as f:
            cat = f.read()
    except OSError:
        return ""
    try:
        with open(os.path.join(d, "preferences.json"), encoding="utf-8") as f:
            lang = json.load(f).get("ui_language") or "de"
    except (OSError, ValueError):
        lang = "de"
    return "<script>window.XLRTE_LANG = %s; window.XLRTE_I18N = %s;</script><script>%s</script>" % (json.dumps(lang), cat.replace("</", "<\\/"), js)


def load_goal(today, system_dir=None):
    """The user's own target from preferences.json (set in setup): goal_label ("Vertrag unterschrieben") and goal_date.
    No goal set: the end of the current year, labelled neutrally. Never raises."""
    try:
        with open(os.path.join(system_dir or HERE, "preferences.json"), encoding="utf-8") as f:
            prefs = json.load(f)
    except (OSError, ValueError):
        prefs = {}
    raw = str(prefs.get("goal_date") or "")[:10]
    try:
        until = date.fromisoformat(raw)
        until_txt = until.strftime("%d.%m.%Y")
    except ValueError:
        until = date(today.year, 12, 31)
        until_txt = "Jahresende"
    label = str(prefs.get("goal_label") or "").strip() or "dein Ziel"
    return {"date": until.isoformat(), "until": until_txt, "label": label, "days_left": (until - today).days}


def default_applicant():
    return load_profile(HERE)["name"]
STAGES = ["Watchlist", "Applied", "Screening", "Interviewing", "Final", "Closed"]
STAGE_DE = {
    "Watchlist": "Beobachtung (noch nicht beworben)",
    "Applied": "Beworben – Rückmeldung offen",
    "Screening": "Im Erstkontakt / Screening",
    "Interviewing": "Im Gesprächsverfahren",
    "Final": "Endrunde / Vertragsgespräch",
    "Closed": "Abgeschlossen"
}
OUTCOME_DE = {
    "rejected": "Absage erhalten",
    "withdrawn": "Zurückgezogen",
    "declined": "Von mir abgelehnt",
    "signed": "Vertrag unterschrieben",
    "lapsed": "Verfahren eingeschlafen",
    "": ""
}
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")

def de(iso):
    return f"{iso[8:10]}.{iso[5:7]}.{iso[0:4]}" if (iso and len(iso) >= 10) else "—"

def clean_note_agentur(note):
    """Sanitize note for official compliance reports (GDPR clean, no raw emails/emojis)."""
    if not note:
        return "Bewerbung eingereicht."
    s = EMAIL_RE.sub("[Kontakt hinterlegt]", str(note))
    s = re.sub(r"^[❌🔻🚨✅⚡•\s]+", "", s).strip()
    if len(s) > 260:
        s = s[:256].rsplit(" ", 1)[0] + "…"
    return s or "Bewerbung eingereicht."

# ==============================================================================
# Dual-Mode Template Renderer (Jinja2 or Zero-Dependency Pure Python Fallback)
# ==============================================================================
try:
    from jinja2 import Environment, FileSystemLoader, select_autoescape
    HAS_JINJA = True
except ImportError:
    HAS_JINJA = False

class MiniTemplate:
    """Zero-dependency pure-Python template engine for offline / standard installations."""
    def __init__(self, template_text, loader=None):
        self.text = template_text
        self.loader = loader

    def render(self, **context):
        ext_m = re.search(r'\{%\s*extends\s*["\']([^"\']+)["\']\s*%\}', self.text)
        if ext_m:
            parent_name = ext_m.group(1)
            parent_src = self.loader(parent_name)
            blocks = {}
            for m in re.finditer(r'\{%\s*block\s+(\w+)\s*%\}(.*?)\{%\s*endblock\s*%\}', self.text, re.DOTALL):
                blocks[m.group(1)] = m.group(2)
            def repl_block(m):
                bname = m.group(1)
                return blocks.get(bname, m.group(2))
            full_text = re.sub(r'\{%\s*block\s+(\w+)\s*%\}(.*?)\{%\s*endblock\s*%\}', repl_block, parent_src, flags=re.DOTALL)
        else:
            full_text = self.text

        tokens = re.split(r'(\{%.*?%\}|\{\{.*?\}\})', full_text, flags=re.DOTALL)
        out, _, _ = self._eval_tokens(tokens, 0, context, [])
        return out

    def _eval_expr(self, expr, ctx):
        expr = expr.strip()
        safe = False
        default_val = None
        parts = [p.strip() for p in expr.split("|")]
        main_expr = parts[0]
        for f in parts[1:]:
            if f == "safe":
                safe = True
            elif f.startswith("default("):
                default_val = f[8:-1].strip("'\"")
            elif f == "length":
                val = self._resolve(main_expr, ctx)
                return str(len(val) if val is not None else 0)

        val = self._resolve(main_expr, ctx)
        if val is None or val == "":
            val = default_val if default_val is not None else ""
        val = str(val)
        return val if safe else html.escape(val, quote=True)

    def _resolve(self, expr, ctx):
        expr = expr.strip()
        if not expr:
            return None
        dict_lookup = re.match(r'^(\w+)\[(\w+)\]$', expr)
        if dict_lookup:
            d_name, k_name = dict_lookup.groups()
            d = ctx.get(d_name, {})
            k = ctx.get(k_name, k_name)
            if isinstance(d, dict):
                return d.get(k, "")
            return ""

        parts = expr.split(".")
        val = ctx.get(parts[0])
        for p in parts[1:]:
            if val is None:
                return None
            if isinstance(val, dict):
                val = val.get(p)
            else:
                val = getattr(val, p, None)
        return val

    def _eval_tokens(self, tokens, idx, ctx, stop_tags):
        res = []
        while idx < len(tokens):
            tok = tokens[idx]
            idx += 1
            if not tok:
                continue
            if tok.startswith("{{") and tok.endswith("}}"):
                res.append(self._eval_expr(tok[2:-2], ctx))
            elif tok.startswith("{%") and tok.endswith("%}"):
                content = tok[2:-2].strip()
                words = content.split()
                first_word = words[0] if words else ""
                if first_word in stop_tags:
                    return "".join(res), idx - 1, first_word
                elif first_word == "if":
                    cond_expr = content[2:].strip()
                    cond_val = bool(self._resolve(cond_expr, ctx))
                    if_body, idx, end_tag = self._eval_tokens(tokens, idx, ctx, ["else", "endif"])
                    else_body = ""
                    if end_tag == "else":
                        else_body, idx, _ = self._eval_tokens(tokens, idx, ctx, ["endif"])
                    res.append(if_body if cond_val else else_body)
                elif first_word == "for":
                    m = re.match(r'^for\s+(.*?)\s+in\s+(.*?)$', content)
                    if m:
                        targets = [t.strip() for t in m.group(1).split(",")]
                        iterable_name = m.group(2).strip()
                        loop_start_idx = idx
                        depth = 1
                        while idx < len(tokens):
                            t_tok = tokens[idx]
                            idx += 1
                            if t_tok.startswith("{%") and t_tok.endswith("%}"):
                                tw = t_tok[2:-2].strip().split()[0] if t_tok[2:-2].strip() else ""
                                if tw == "for":
                                    depth += 1
                                elif tw == "endfor":
                                    depth -= 1
                                    if depth == 0:
                                        break
                        loop_tokens = tokens[loop_start_idx : idx - 1]
                        iterable = self._resolve(iterable_name, ctx) or []
                        for item in iterable:
                            sub_ctx = dict(ctx)
                            if len(targets) == 1:
                                sub_ctx[targets[0]] = item
                            elif len(targets) == 2 and isinstance(item, (list, tuple)) and len(item) == 2:
                                sub_ctx[targets[0]] = item[0]
                                sub_ctx[targets[1]] = item[1]
                            rendered_loop, _, _ = self._eval_tokens(loop_tokens, 0, sub_ctx, [])
                            res.append(rendered_loop)
            else:
                res.append(tok)
        return "".join(res), idx, None

class TemplateEngine:
    def __init__(self, template_dir):
        self.template_dir = template_dir
        if HAS_JINJA:
            self.jinja_env = Environment(
                loader=FileSystemLoader(template_dir),
                autoescape=select_autoescape(["html"])
            )

    def load_src(self, name):
        p = os.path.join(self.template_dir, name)
        with open(p, "r", encoding="utf-8") as f:
            return f.read()

    def render(self, template_name, **context):
        if HAS_JINJA:
            return self.jinja_env.get_template(template_name).render(**context)
        else:
            tmpl_src = self.load_src(template_name)
            mini = MiniTemplate(tmpl_src, loader=self.load_src)
            return mini.render(**context)

# ==============================================================================
# Main Orchestration
# ==============================================================================
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=os.path.join(HERE, "pipeline.csv"))
    ap.add_argument("--prep", default=os.path.join(HERE, "prep.json"))
    ap.add_argument("--out",  default=os.path.join(HERE, ".."))
    ap.add_argument("--today", default=date.today().isoformat())
    ap.add_argument("--applicant", default=default_applicant())
    ap.add_argument("--folders", default=os.path.join(HERE, "folders.tsv"),
                    help="TSV: uid <TAB> folder name <TAB> drive folder id — the Drive inventory")
    ap.add_argument("--transitions", default=os.path.join(HERE, "transitions.csv"),
                    help="Path to transitions.csv audit trail")
    ap.add_argument("--health", default=os.path.join(HERE, "health.json"),
                    help="Path to health.json written by health.py (Today page)")
    ap.add_argument("--intel", default=os.path.join(HERE, "intel_index.json"),
                    help="Path to intel_index.json written by intel_index.py (briefing tabs)")
    ap.add_argument("--reader-root", default=os.path.dirname(HERE),
                    help="Career folder the intel_index paths are relative to (reading pane on the Briefings page)")
    ap.add_argument("--channels", default=os.path.join(HERE, "channels.json"),
                    help="Path to channels.json: uids that are channels (e.g. headhunters) with their leads (Today page)")
    ap.add_argument("--top10", default=os.path.join(HERE, "top10.json"),
                    help="Path to top10.json: the pinned uids (Today page)")
    ap.add_argument("--intake-report", default=os.path.join(HERE, "intake_report.json"),
                    help="Path to intake_report.json written by intake.py (Today page)")
    ap.add_argument("--coverage", default=os.path.join(HERE, "coverage_state.json"),
                    help="Path to coverage_state.json written by coverage.py (Today page)")
    ap.add_argument("--drafts", default=os.path.join(HERE, "draft_state.json"),
                    help="Path to draft_state.json written by draft_job.py / draft_lint.py (Today page)")
    ap.add_argument("--renders", default=os.path.join(HERE, "render_state.json"),
                    help="Path to render_state.json written by render_docs.py (Today page)")
    ap.add_argument("--intel-state", default=os.path.join(HERE, "intel_state.json"),
                    help="Path to intel_state.json written by intel_job.py / intel_lint.py / intel_pdf.py (Today page)")
    ap.add_argument("--archive-dir", default=os.path.join(HERE, "archive"),
                    help="Folder with the dated pipeline snapshots the run archives before overwriting (Today: what changed since the last run)")
    ap.add_argument("--events", default=os.path.join(HERE, "events.csv"),
                    help="Path to events.csv, one row per run (Today: when the last run was)")
    ap.add_argument("--rank", default=os.path.join(HERE, "rank_state.json"),
                    help="Path to rank_state.json written by rank.py (Today: suggestions for the free Top-10 places)")
    ap.add_argument("--no-pdf", action="store_true")
    ap.add_argument("--mode", default="full", choices=["full", "prep"],
                    help="full = all views (default); prep = regenerate prep docs for one UID only")
    ap.add_argument("--uid", type=int, default=None,
                    help="UID for --mode prep")
    a = ap.parse_args()

    # ── Standalone prep re-run for a single UID ───────────────────────────────
    if a.mode == "prep":
        if not a.uid:
            sys.exit("--mode prep requires --uid NNN")
        sys.path.insert(0, HERE)
        from prep_engine import run_prep
        from pathlib import Path
        result = run_prep(
            uid=a.uid,
            pipeline_path=a.data,
            prep_json_path=a.prep,
            base_dir=str(Path(a.data).parent.parent),
            today=a.today,
        )
        import json as _json
        print(_json.dumps(result, indent=2))
        return

    try:
        today = date.fromisoformat(a.today)
    except Exception:
        today = date.today()
        a.today = today.isoformat()

    out_dir = os.path.abspath(a.out)
    system_dir = os.path.abspath(HERE)
    try:
        os.makedirs(out_dir, exist_ok=True)
    except (PermissionError, OSError):
        pass

    if not os.path.exists(out_dir) or not os.access(out_dir, os.W_OK):
        print(f"  ℹ️  Hinweis: Zielverzeichnis '{out_dir}' nicht beschreibbar. Weiche auf '{system_dir}' aus.", file=sys.stderr)
        out_dir = system_dir
        os.makedirs(out_dir, exist_ok=True)

    # 1. Load canonical data
    if not os.path.exists(a.data):
        print(f"❌ FEHLER: Datendatei nicht gefunden: {a.data}", file=sys.stderr)
        sys.exit(1)

    with open(a.data, "r", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    for r in rows:
        try:
            r["score"] = int(float(r.get("score") or 0))
        except (ValueError, TypeError):
            r["score"] = 0
        r["applied_de"] = de(r.get("applied", ""))
        stage = r.get("stage", "Watchlist")
        outcome = r.get("outcome", "")
        r["outcome_de"] = OUTCOME_DE.get(outcome, outcome) or STAGE_DE.get(stage, stage).split(" –")[0]
        r["note_short"] = clean_note_agentur(r.get("note", ""))
        _est = None
        try:
            import confidence as _cf
            import folder_utils as _fu
            _folder, _ = _fu.locate_role_folder(os.path.dirname(HERE), r.get("uid", ""), r.get("role", ""), r.get("folder_id", ""))
            _est = (_cf.observer_judgement(str(_folder)) if _folder else None) or _cf.estimate(r, _cf.conversations_done(str(_folder)) if _folder else 0)
            if _est and _folder and _cf.observer_judgement(str(_folder)):
                r["confidence_source"] = "Einschätzung"
        except Exception:
            _est = None
        r["confidence"] = _est["pct"] if _est else ""
        r["confidence_why"] = "; ".join(_est["why"]) if _est else ""
        r.setdefault("confidence_source", "Heuristik")

    prep = {}
    if os.path.exists(a.prep):
        try:
            with open(a.prep, "r", encoding="utf-8") as f:
                prep = json.load(f)
        except Exception as e:
            print(f"⚠️ Hinweis: prep.json konnte nicht geladen werden ({e})", file=sys.stderr)

    intel = {}
    if os.path.exists(a.intel):
        try:
            with open(a.intel, "r", encoding="utf-8") as f:
                intel = json.load(f)
        except Exception as e:
            print(f"⚠️ Hinweis: intel_index.json konnte nicht geladen werden ({e})", file=sys.stderr)

    channels = {}
    if os.path.exists(a.channels):
        try:
            with open(a.channels, "r", encoding="utf-8") as f:
                channels = json.load(f)
        except Exception as e:
            print(f"⚠️ Hinweis: channels.json konnte nicht geladen werden ({e})", file=sys.stderr)

    import top10 as _top10
    top10_data = _top10.load(a.top10) if os.path.exists(a.top10) else None
    intake_report = {}
    if os.path.exists(a.intake_report):
        try:
            with open(a.intake_report, "r", encoding="utf-8") as f:
                intake_report = json.load(f)
        except Exception as e:
            print(f"⚠️ Hinweis: intake_report.json konnte nicht geladen werden ({e})", file=sys.stderr)

    coverage = {}
    if os.path.exists(a.coverage):
        try:
            with open(a.coverage, "r", encoding="utf-8") as f:
                coverage = json.load(f)
        except Exception as e:
            print(f"⚠️ Hinweis: coverage_state.json konnte nicht geladen werden ({e})", file=sys.stderr)

    drafts = {}
    if os.path.exists(a.drafts):
        try:
            with open(a.drafts, "r", encoding="utf-8") as f:
                drafts = json.load(f)
        except Exception as e:
            print(f"⚠️ Hinweis: draft_state.json konnte nicht geladen werden ({e})", file=sys.stderr)

    renders = {}
    if os.path.exists(a.renders):
        try:
            with open(a.renders, "r", encoding="utf-8") as f:
                renders = json.load(f)
        except Exception as e:
            print(f"⚠️ Hinweis: render_state.json konnte nicht geladen werden ({e})", file=sys.stderr)

    intel_state = {}
    if os.path.exists(a.intel_state):
        try:
            with open(a.intel_state, "r", encoding="utf-8") as f:
                intel_state = json.load(f)
        except Exception as e:
            print(f"⚠️ Hinweis: intel_state.json konnte nicht geladen werden ({e})", file=sys.stderr)

    rank_state = {}
    if os.path.exists(a.rank):
        try:
            with open(a.rank, "r", encoding="utf-8") as f:
                rank_state = json.load(f)
        except Exception as e:
            print(f"⚠️ Hinweis: rank_state.json konnte nicht geladen werden ({e})", file=sys.stderr)
    import today_view as _tv
    baseline, baseline_label = _tv.latest_baseline(a.archive_dir, rows)
    events = []
    if os.path.exists(a.events):
        try:
            with open(a.events, newline="", encoding="utf-8") as f:
                events = list(csv.DictReader(f))
        except (OSError, UnicodeDecodeError, csv.Error) as e:
            print(f"⚠️ Hinweis: events.csv konnte nicht gelesen werden ({e})", file=sys.stderr)

    openr = [r for r in rows if r.get("stage") != "Closed"]
    closed = [r for r in rows if r.get("stage") == "Closed"]

    # Deterministic interview conversion metric:
    # 1. Ingest transitions.csv for audit-verified interview stages (nach in ("Interviewing", "Final"))
    # 2. Add active opportunities currently in Interviewing or Final stages (including headhunter channels)
    # Replaces fragile rejection note substring matching to eliminate false positives.
    def norm_uid(u):
        u = str(u or "").strip()
        try:
            return str(int(u))
        except ValueError:
            return u

    interview_uids = set()
    if os.path.exists(a.transitions):
        try:
            with open(a.transitions, "r", encoding="utf-8") as f:
                for t in csv.DictReader(f):
                    if t.get("nach") in ("Interviewing", "Final") and t.get("uid"):
                        u = norm_uid(t["uid"])
                        if u:
                            interview_uids.add(u)
        except Exception as e:
            print(f"⚠️ Hinweis: transitions.csv konnte nicht geladen werden ({e})", file=sys.stderr)

    for r in rows:
        if r.get("stage") in ("Interviewing", "Final"):
            u = norm_uid(r.get("uid"))
            if u:
                interview_uids.add(u)

    non_uid_live_interviews = sum(
        1 for r in rows
        if r.get("stage") in ("Interviewing", "Final") and not norm_uid(r.get("uid"))
    )
    reached = len(interview_uids) + non_uid_live_interviews
    offers = sum(1 for r in rows if r.get("outcome") == "signed")
    goal = load_goal(today)
    days_left = goal["days_left"]

    # 2. Drive folder reconciliation & hygiene
    folders, dupes = {}, []
    if os.path.exists(a.folders):
        seen = set()
        with open(a.folders, "r", encoding="utf-8") as f:
            for ln in f:
                if not ln.strip(): continue
                parts = (ln.rstrip("\n").split("\t") + ["", ""])[:3]
                uid, name, fid = parts[0], parts[1], parts[2]
                try:
                    uid_str = str(int(uid))
                except ValueError:
                    uid_str = uid.strip()
                if uid_str in seen:
                    dupes.append(f"{uid_str} {name}")
                seen.add(uid_str)
                folders[uid_str] = dict(name=name, id=fid)

    uids_in_data = {r["uid"] for r in rows if r.get("uid")}
    hygiene = dict(
        no_folder   = sorted({f'{r["company"]} · {(r.get("role") or "")[:44]}' for r in rows if not r.get("folder_id")}),
        orphan      = sorted([f'{u} {folders[u]["name"]}' for u in folders if u not in uids_in_data],
                             key=lambda s: int(s.split()[0]) if s.split()[0].isdigit() else 9999),
        dupes       = dupes,
        stale       = sorted([f'{r["company"]} · {r.get("days_idle")}d · {r.get("stage")}' for r in rows
                              if r.get("stage") != "Closed" and r.get("days_idle") and int(r.get("days_idle", 0) or 0) > 45],
                             key=lambda s: -int(s.split(" · ")[1][:-1]) if " · " in s else 0),
        no_date     = sorted({r["company"] for r in rows if r.get("stage") != "Closed" and not r.get("applied")}),
        n_folders   = len(folders),
    )

    try:
        if HERE not in sys.path:
            sys.path.insert(0, HERE)
        import intel_reader
        reader = intel_reader.build(intel, rows, a.reader_root, a.today)
    except Exception as e:      # the reading pane is a convenience: the page must render without it
        print(f"⚠️ Hinweis: Lesezone konnte nicht aufgebaut werden ({e})", file=sys.stderr)
        reader = {}

    meta = dict(
        generated=a.today, expect_rows=len(rows), hygiene=hygiene, intel=intel,
        interviews_reached=reached,
        interview_rate=round(reached / max(len(rows), 1) * 100),
        offers=offers, days_left=days_left, rows=rows, prep=prep,
        goal_label=goal["label"], goal_date=goal["date"],
    )
    # "</" is escaped so text from a row (third-party job posts) can never close the <script> block early.
    data_json = json.dumps(meta, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/").replace("<!--", "\\u003c!--")
    # the reading pane documents are large: only the Briefings page carries them
    brief_json = json.dumps(dict(meta, reader=reader), ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/").replace("<!--", "\\u003c!--")

    # 3. Assets & Engine Setup
    engine = TemplateEngine(os.path.join(HERE, "templates"))
    with open(os.path.join(HERE, "theme.css"), "r", encoding="utf-8") as f:
        theme = f.read()
    with open(os.path.join(HERE, "core.js"), "r", encoding="utf-8") as f:
        core = f.read()

    def load_asset(name):
        try:
            with open(os.path.join(HERE, "assets", name), encoding="utf-8") as f:
                return f.read()
        except OSError:
            return ""
    logo_svg = load_asset("xlrte-logo.svg")
    monogram = load_asset("x-monogram.svg")
    favicon_uri = ("data:image/svg+xml;base64," + base64.b64encode(monogram.encode("utf-8")).decode("ascii")) if monogram else ""

    files = [
        ("00_today.html", "Heute"),
        ("01_cockpit.html", "Cockpit"),
        ("02_pipeline_crm.html", "Pipeline CRM"),
        ("03_briefings.html", "Briefings"),
        ("04_agentur_report.html", "Agentur für Arbeit"),
        ("05_expert.html", "Experte"),
    ]
    def nav(active):
        return [dict(href=f, label=l, on=(l == active)) for f, l in files]

    base = dict(
        today=a.today, theme_css=theme, core_js=core, data_json=data_json, i18n_js=load_i18n(),
        logo_svg=logo_svg, favicon_uri=favicon_uri,
        footer=(f'Generiert am {de(a.today)} aus <span class="mono">_system/pipeline.csv</span> · '
                f'{len(rows)} Datensätze · {len(openr)} offen · '
                f'Quelle der Wahrheit: pipeline.csv + Ordnerstruktur · '
                f'Score-Modell: <span class="mono">_system/SCHEMA.md</span>')
    )

    sub = (f'{a.applicant} · <b>{len(rows)}</b> Bewerbungen · <b>{len(openr)}</b> offen · '
           f'Stand {de(a.today)} · <b>{days_left}</b> Tage bis {html.escape(goal["until"])}')

    # 4. Render the 4 views
    engine_name = "Jinja2" if HAS_JINJA else "Built-in Zero-Dependency Engine"
    print(f"\n  Render-Engine: {engine_name}")

    out = {}
    health = None
    if os.path.exists(a.health):
        try:
            with open(a.health, "r", encoding="utf-8") as f:
                health = json.load(f)
        except Exception as e:
            print(f"⚠️ Hinweis: health.json konnte nicht geladen werden ({e})", file=sys.stderr)
    sys.path.insert(0, HERE)
    from today_view import build_context
    out["00_today.html"] = engine.render(
        "today.html",
        title="Heute — Job Search 2026", heading="Heute", subtitle=f"Systemgesundheit und Fälligkeiten · Stand {de(a.today)}",
        nav=nav("Heute"), **build_context(rows, health, a.today, intel, channels, top10_data, prep, intake_report, coverage, drafts, renders, intel_state, baseline, baseline_label, events, rank_state), **base
    )
    import expert_view as _xv
    transitions_rows = []
    if os.path.exists(a.transitions):
        try:
            with open(a.transitions, "r", encoding="utf-8") as f:
                transitions_rows = list(csv.DictReader(f))
        except Exception:
            transitions_rows = []
    out["05_expert.html"] = engine.render(
        "expert.html",
        title="Experte — Gespräche und Endrunde", heading="Experte", subtitle=f"Verfahren in Gesprächsphasen mit Vorbereitung und Verlauf · Stand {de(a.today)}",
        nav=nav("Experte"),
        cards=_xv.build_expert(rows, transitions_rows, a.today, intel, intel_state, coverage, drafts, renders, _xv.scan_folders(out_dir if out_dir != HERE else os.path.dirname(HERE), rows), channels), **base
    )
    out["01_cockpit.html"] = engine.render(
        "cockpit.html",
        title="Cockpit — Job Search 2026", heading="⚡ Cockpit", subtitle=sub,
        nav=nav("Cockpit"), **base
    )
    out["02_pipeline_crm.html"] = engine.render(
        "crm.html",
        title="Pipeline CRM — Job Search 2026", heading="📊 Pipeline CRM", subtitle=sub,
        nav=nav("Pipeline CRM"), **base
    )
    out["03_briefings.html"] = engine.render(
        "brief.html",
        title="Gesprächs-Briefings — Job Search 2026", heading="🎯 Gesprächs-Briefings",
        subtitle=f'{len([r for r in openr if r.get("stage") in ("Screening", "Interviewing", "Final")])} '
                 f'aktive Verfahren in Gesprächsphasen · Stand {de(a.today)}',
        nav=nav("Briefings"), **dict(base, data_json=brief_json)
    )

    by_stage = [(s, [r for r in rows if r.get("stage") == s])
                for s in ["Final", "Interviewing", "Screening", "Applied", "Watchlist", "Closed"]]
    by_stage = [(s, sorted(g, key=lambda r: r.get("applied") or "0", reverse=True)) for s, g in by_stage if g]

    out["04_agentur_report.html"] = engine.render(
        "agentur.html",
        title="Bewerbungsübersicht — Agentur für Arbeit", lang="de",
        heading="Bewerbungsübersicht", subtitle=f"{a.applicant} · Stand {de(a.today)}",
        nav=nav("Agentur für Arbeit"), by_stage=by_stage, stage_de=STAGE_DE,
        n_total=len(rows), n_open=len(openr), n_closed=len(closed),
        close_rate=round(len(closed) / max(len(rows), 1) * 100),
        n_interviews=reached, interview_rate=round(reached / max(len(rows), 1) * 100),
        applicant=a.applicant, today_de=de(a.today), period="Feb 2026 – laufend",
        targets="CDO, CTO, Head of IT, Director Data & AI, Head of Enterprise Architecture",
        **base
    )

    for name, html_content in out.items():
        target_path = os.path.join(out_dir, name)
        try:
            with open(target_path, "w", encoding="utf-8") as f:
                f.write(html_content)
            print(f"  ✓ {name:<26} {len(html_content):>8,} bytes")
        except (PermissionError, OSError) as e:
            fallback_path = os.path.join(HERE, name)
            with open(fallback_path, "w", encoding="utf-8") as f:
                f.write(html_content)
    ALIASES = {
        "00_today.html": "today.html",
        "01_cockpit.html": "cockpit.html",
        "02_pipeline_crm.html": "pipeline_crm.html",
        "03_briefings.html": "briefings.html",
        "04_agentur_report.html": "agentur_report.html",
        "05_expert.html": "expert.html",
    }
    for orig, alias in ALIASES.items():
        if orig in out:
            target_alias = os.path.join(out_dir, alias)
            try:
                with open(target_alias, "w", encoding="utf-8") as f:
                    f.write(out[orig])
                print(f"  ✓ {alias:<26} {len(out[orig]):>8,} bytes (alias -> {orig})")
            except (PermissionError, OSError):
                fallback_alias = os.path.join(HERE, alias)
                try:
                    with open(fallback_alias, "w", encoding="utf-8") as f:
                        f.write(out[orig])
                except (PermissionError, OSError):
                    pass

    # 5. Flat mirror for the Google Sheet
    cols = ["uid", "company", "role", "lane", "stage", "outcome", "applied", "last_event", "days_idle",
            "score", "salary_fit", "location", "contacts", "next_action", "due", "folder_url", "note"]
    sheet_export_path = os.path.join(out_dir, "sheet_export.csv")
    try:
        with open(sheet_export_path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=cols)
            w.writeheader()
            for r in sorted(rows, key=lambda r: (-r.get("score", 0), r.get("company", ""))):
                fid = r.get("folder_id", "")
                w.writerow({
                    **{c: r.get(c, "") for c in cols},
                    "folder_url": f"https://drive.google.com/drive/folders/{fid}" if fid else ""
                })
        print(f"  ✓ sheet_export.csv           {os.path.getsize(sheet_export_path):>8,} bytes")
    except (PermissionError, OSError) as e:
        fallback_sheet = os.path.join(HERE, "sheet_export.csv")
        with open(fallback_sheet, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=cols)
            w.writeheader()
            for r in sorted(rows, key=lambda r: (-r.get("score", 0), r.get("company", ""))):
                fid = r.get("folder_id", "")
                w.writerow({
                    **{c: r.get(c, "") for c in cols},
                    "folder_url": f"https://drive.google.com/drive/folders/{fid}" if fid else ""
                })
        print(f"  ✓ sheet_export.csv           {os.path.getsize(fallback_sheet):>8,} bytes (fallback -> {fallback_sheet})")

    # 6. PDF export handling
    if not a.no_pdf:
        pdf_path = os.path.join(out_dir, "04_agentur_report.pdf")
        html_path = os.path.join(out_dir, "04_agentur_report.html")
        pdf_done = False
        if shutil.which("wkhtmltopdf"):
            try:
                subprocess.run([
                    "wkhtmltopdf", "--enable-local-file-access", "--print-media-type",
                    "--page-size", "A4", "--margin-top", "12mm", "--margin-bottom", "14mm",
                    "--margin-left", "10mm", "--margin-right", "10mm",
                    "--footer-right", "Seite [page]/[toPage]", "--footer-font-size", "8",
                    html_path, pdf_path
                ], check=True, capture_output=True)
                print(f"  ✓ 04_agentur_report.pdf      {os.path.getsize(pdf_path):>8,} bytes")
                pdf_done = True
            except Exception as e:
                print(f"  ! wkhtmltopdf fehlgeschlagen: {e}", file=sys.stderr)

        if not pdf_done:
            print("  ℹ️  PDF-Export: wkhtmltopdf nicht installiert. 04_agentur_report.html verfügt über eine DIN-A4-Druckoptimierung und kann über den Druck-Button direkt im Browser verlustfrei als PDF exportiert werden.")

    # 7. Asset synchronization to both _system/ and root career folder
    root_dir = os.path.abspath(os.path.join(HERE, ".."))
    system_dir = os.path.abspath(HERE)
    sync_targets = []
    if os.path.samefile(out_dir, system_dir) or out_dir == system_dir:
        sync_targets.append(root_dir)
    elif os.path.samefile(out_dir, root_dir) or out_dir == root_dir:
        sync_targets.append(system_dir)

    for target_sync_dir in sync_targets:
        if os.path.exists(target_sync_dir):
            sync_files = list(out.keys()) + ["sheet_export.csv"]
            for orig, alias in ALIASES.items():
                if orig in out and alias not in sync_files:
                    sync_files.append(alias)
            if os.path.exists(os.path.join(out_dir, "04_agentur_report.pdf")):
                sync_files.append("04_agentur_report.pdf")
            synced_count = 0
            for sf in sync_files:
                src_file = os.path.join(out_dir, sf)
                dst_file = os.path.join(target_sync_dir, sf)
                if os.path.exists(src_file):
                    try:
                        shutil.copyfile(src_file, dst_file)
                        synced_count += 1
                    except (PermissionError, OSError):
                        try:
                            with open(src_file, "rb") as fin, open(dst_file, "wb") as fout:
                                fout.write(fin.read())
                            synced_count += 1
                        except (PermissionError, OSError):
                            pass
            if synced_count > 0:
                print(f"  ✓ Synchronized {synced_count} generated dashboard assets to: {target_sync_dir}")

    print(f"\n  Erfolgreich: {len(rows)} Zeilen · {len(openr)} offen · {reached} Interviews erreicht "
          f"({round(reached / max(len(rows), 1) * 100)}%) · {days_left} Tage bis {goal['until']}\n")

if __name__ == "__main__":
    main()
