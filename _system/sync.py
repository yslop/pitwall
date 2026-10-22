#!/usr/bin/env python3
"""
sync.py — Orchestrates and executes the complete Job Search Sync pipeline.

Cohesively integrates all feature scripts and rendering steps defined in RUNBOOK.md:
  1. Pre-flight data integrity check (career_check.py)
  2. Revisit Interviewing/Final folders for new transcripts/briefings (revisit.py)
  3. Intake self-found postings from _Eingang/ (intake.py)
  4. Coverage analysis for pinned roles (coverage.py)
  5. Draft job generation for pinned roles (draft_job.py)
  6. Company brand extraction for pinned roles (company_brand.py)
  7. Document rendering: ATS .docx/.pdf and CI .pdf (render_docs.py)
  8. Intel orders for active stages (intel_job.py)
  9. Score & days_idle recomputation (recompute_scores.py)
 10. API Contract smoke test & ITIL Service Health calculation (api_contract.py, health.py)
 11. Intel index refresh (intel_index.py)
 12. Render HTML dashboards & export sheet (render.py), syncing to both _system/ and root.

CLI:
    python3 _system/sync.py [--today YYYY-MM-DD] [--dry-run] [--quiet] [--render-only] [--skip-preflight]
"""
import argparse
import os
import subprocess
import sys
from datetime import date

import kit_run

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.abspath(os.path.join(HERE, ".."))
KIT_SKIP = ("intake.py", "coverage.py", "draft_job.py", "company_brand.py", "render_docs.py", "api_contract.py")
KIT_MODE = False


def _resolve(cmd):
    """A step names its script as 'x.py' relative to HERE; in the installed kit only x.pyc exists."""
    if len(cmd) > 1 and isinstance(cmd[1], str) and cmd[1].endswith(".py") and not os.path.isabs(cmd[1]):
        return [cmd[0], kit_run.script_path(HERE, cmd[1])] + list(cmd[2:])
    return cmd


def run_step(name, cmd, cwd=HERE, check=False, quiet=False):
    cmd = _resolve(cmd)
    if KIT_MODE and len(cmd) > 1 and os.path.splitext(os.path.basename(str(cmd[1])))[0] + ".py" in KIT_SKIP:
        if not quiet:
            print(f"  ▶ {name}... übersprungen (Kit)")
        return True, None
    if not quiet:
        print(f"  ▶ {name}...")
    res = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if res.returncode != 0:
        if not quiet:
            err_msg = (res.stderr or res.stdout or "").strip()
            print(f"    ⚠️ {name} beendete mit Code {res.returncode}: {err_msg[-300:]}")
        if check:
            return False, res
    else:
        if not quiet:
            first_line = (res.stdout or "").strip().split("\n")[0]
            if first_line:
                print(f"    ✓ {first_line[:90]}")
            else:
                print(f"    ✓ OK")
    return True, res


def main(argv=None):
    ap = argparse.ArgumentParser(description="Unified Job Search Sync Runner")
    ap.add_argument("--today", default=date.today().isoformat(), help="Reference date YYYY-MM-DD")
    ap.add_argument("--dry-run", action="store_true", help="Dry-run mode where supported")
    ap.add_argument("--quiet", action="store_true", help="Quiet output")
    ap.add_argument("--render-only", action="store_true", help="Only recompute scores, health, and re-render views")
    ap.add_argument("--kit", action="store_true", help="pilot kit: skip steps that need the owner's masters, connectors or TypeSafe")
    ap.add_argument("--skip-preflight", action="store_true", help="Continue even if pre-flight integrity check warns/fails")
    a = ap.parse_args(argv)
    global KIT_MODE
    KIT_MODE = a.kit

    today = a.today
    py = sys.executable

    print("=" * 70)
    print(f"  JOB SEARCH SYNC — Stand {today}")
    print("=" * 70)

    # 1. Pre-flight integrity check
    if not a.render_only:
        ok, res = run_step(
            "1. Pre-flight Integritäts-Check (career_check.py)",
            [py, "career_check.py", "--quiet"],
            check=not a.skip_preflight,
            quiet=a.quiet
        )
        if not ok and not a.skip_preflight:
            print("\n❌ Abbruch: Pre-flight Integritätsfehler. Mit --skip-preflight überspringen.", file=sys.stderr)
            return 1

        # 2. Revisit active interviewing folders
        run_step(
            "2. Revisit Interviewing/Final (revisit.py)",
            [py, "revisit.py", "--pipeline", "pipeline.csv", "--base-dir", ROOT_DIR,
             "--state", "revisit_state.json", "--today", today],
            quiet=a.quiet
        )

        # 3. Intake new self-found postings from _Eingang/
        intake_args = [py, "intake.py", "--today", today]
        if a.dry_run:
            intake_args.append("--dry-run")
        run_step("3. Intake Funde aus _Eingang (intake.py)", intake_args, quiet=a.quiet)

        # 4. Coverage analysis for pinned roles
        cov_args = [py, "coverage.py", "--pinned", "--today", today]
        if a.dry_run:
            cov_args.append("--dry-run")
        run_step("4. Abdeckungsanalyse Top 10 (coverage.py)", cov_args, quiet=a.quiet)

        # 5. Draft job generation for pinned roles
        draft_args = [py, "draft_job.py", "--pinned", "--today", today]
        if a.dry_run:
            draft_args.append("--dry-run")
        run_step("5. Entwurfsaufträge Top 10 (draft_job.py)", draft_args, quiet=a.quiet)

        # 6. Company branding extraction
        brand_args = [py, "company_brand.py", "--pinned", "--today", today]
        if a.dry_run:
            brand_args.append("--dry-run")
        run_step("6. Unternehmensmarke Top 10 (company_brand.py)", brand_args, quiet=a.quiet)

        # 7. Document renderings (ATS .docx/.pdf & CI .pdf)
        render_docs_args = [py, "render_docs.py", "--pinned", "--today", today]
        if a.dry_run:
            render_docs_args.append("--dry-run")
        run_step("7. Dokumenten-Renderings ATS/CI (render_docs.py)", render_docs_args, quiet=a.quiet)

        # 8. Intel research orders for live opportunities
        intel_job_args = [py, "intel_job.py", "--live", "--today", today]
        if a.dry_run:
            intel_job_args.append("--dry-run")
        run_step("8. Intel-Aufträge laufende Verfahren (intel_job.py)", intel_job_args, quiet=a.quiet)

        # 8a. Conversation date passed, no debrief yet: write the after-interview order (RUNBOOK step 3j.3); the session writes the debrief
        held_args = [py, "intel_job.py", "--held", "--today", today]
        if a.dry_run:
            held_args.append("--dry-run")
        run_step("8a. Nachbereitungsaufträge nach Gesprächen (intel_job.py --held)", held_args, quiet=a.quiet)

        # 8b. Prep brief + JD intel from Prep_Inhalt.json (Interviewing/Final); orders content where it is missing or older than the briefing
        if not a.dry_run:
            run_step("8b. Prep-Brief/JD-Intel aus Prep_Inhalt.json (prep_engine.py --refresh-live)",
                     [py, "prep_engine.py", "--refresh-live", "--pipeline", "pipeline.csv", "--base-dir", ROOT_DIR, "--today", today], quiet=a.quiet)

    # 9. Recompute idle days and scores for today
    run_step(
        "9. Scores & Stillstandstage neu berechnen (recompute_scores.py)",
        [py, "recompute_scores.py", "--pipeline", "pipeline.csv", "--today", today],
        quiet=a.quiet
    )

    # 10. Service health checks (API contract smoke + ITIL health)
    run_step(
        "10a. API-Kontrakt Smoke-Test (api_contract.py)",
        [py, "api_contract.py", "--smoke"],
        quiet=a.quiet
    )
    run_step(
        "10b. ITIL Service-Gesundheit (health.py)",
        [py, "health.py", "--data", "pipeline.csv", "--today", today],
        quiet=a.quiet
    )

    # 11. Intel index refresh
    run_step(
        "11. Intel-Index aktualisieren (intel_index.py)",
        [py, "intel_index.py", "--data", "pipeline.csv"],
        quiet=a.quiet
    )

    # 11b. Intel work queue for the session: the stage drives the research, no manual trigger (RUNBOOK step 3h)
    q = subprocess.run(_resolve([py, "intel_queue.py", "--data", "pipeline.csv", "--base-dir", ROOT_DIR, "--today", today]), cwd=HERE, capture_output=True, text=True)
    print("\n  ▶ 11b. Intel-Warteschlange (intel_queue.py): " + (q.stdout.strip() or q.stderr.strip()[-200:]).replace("\n", "\n    "))

    # 12. Render HTML dashboards and sync to root & _system/
    print("\n  ▶ 12. Dashboards rendern & synchronisieren (render.py)...")
    render_cmd = [
        py, "render.py",
        "--data", "pipeline.csv",
        "--prep", "prep.json",
        "--folders", "folders.tsv",
        "--today", today,
        "--out", ROOT_DIR
    ]
    ok, res = run_step("render.py", render_cmd, check=True, quiet=False)
    if not ok:
        print("  ! render.py fehlgeschlagen", file=sys.stderr)
        return 2

    print("\n" + "=" * 70)
    print("  ✓ JOB SEARCH SYNC ERFOLGREICH ABGESCHLOSSEN")
    print(f"    Startseite:  {os.path.join(ROOT_DIR, '00_today.html')} (auch today.html)")
    print(f"    Pipeline:    {os.path.join(ROOT_DIR, '02_pipeline_crm.html')} (auch pipeline_crm.html)")
    print("=" * 70 + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
