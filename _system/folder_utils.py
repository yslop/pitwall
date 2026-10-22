"""
Shared Drive-folder resolution for the Job Search Sync pipeline.

Two distinct ambiguity problems live here, both discovered during the
2026-09-24 dossier-staleness investigation:

1. One company, multiple role subfolders (parallel tracks — sourced
   conversations, multiple open reqs at the same employer). Must pick the
   one matching the pipeline row's `role` text, not an arbitrary order —
   see the earlier wrong-folder incident (prep_engine.py wrote a dossier into the wrong
   role folder because it took whichever subfolder sorted first).

2. Pre-existing Drive naming collisions: more than one top-level company
   folder starts with the same `NNN ` uid prefix (found across uids
   167-170 — apparent leftover numbering mistakes from folder creation,
   e.g. "167 Bohnenhaus Gruppe (active)" actually belongs to uid 168).
   Name-prefix matching alone can silently resolve to the wrong company.
   Google Drive for Desktop exposes the real Drive folder ID as a local
   xattr (`com.google.drivefs.item-id`), which pipeline.csv already
   stores per row as `folder_id` — so a collision can be disambiguated
   authoritatively instead of guessed.
"""
import re
import subprocess
from pathlib import Path
from typing import List, Optional, Tuple

CANON_SUBDIRS = ("10 Bewerbung", "20 Vorbereitung", "30 Verlauf")

_STOPWORDS = {
    "of", "the", "and", "m", "w", "f", "d", "new", "active", "rejected",
    "closed", "role", "tbd", "via", "gmbh", "co", "kg", "senior", "manager",
    "head", "director", "team", "lead", "leader", "ai", "data", "digital",
    "global", "platform",
}


def _tokens(s: str) -> set:
    # Pure-digit tokens (dates, times, years) are excluded: they're noise for
    # identifying *which role* a folder is, and two unrelated role folders
    # routinely share a year/date fragment (e.g. both mention "2026"),
    # which previously produced false "matches" with no ambiguity flag.
    return {t for t in re.findall(r"[a-zA-Z0-9äöüÄÖÜß]+", s.lower())
            if t not in _STOPWORDS and len(t) > 1 and not t.isdigit()}


def _plain(s: str) -> str:
    return re.sub(r"[^a-z0-9äöüß]+", "", re.sub(r"\([^)]*\)", "", s.lower()))


def _drive_item_id(path: Path) -> Optional[str]:
    """Read the Google Drive for Desktop item-id xattr for a local path, if present."""
    for attr_name in ("com.google.drivefs.item-id#S", "com.google.drivefs.item-id"):
        try:
            out = subprocess.run(
                ["xattr", "-p", attr_name, str(path)],
                capture_output=True, text=True, timeout=5,
            )
            val = out.stdout.strip()
            if val:
                return val
        except (OSError, subprocess.SubprocessError):
            continue
    return None


def find_company_folder(base_dir: str, uid, folder_id: str = "") -> Tuple[Optional[Path], List[str]]:
    """
    Find the company folder for `uid`. Returns (folder_or_None, flags).
    When more than one folder shares the `NNN ` prefix (a known pre-existing
    Drive naming collision — see module docstring), resolves via `folder_id`
    against each candidate's Drive item-id xattr. Never guesses: if it can't
    disambiguate, returns None and a flag rather than picking one.
    """
    base = Path(base_dir)
    if not base.is_dir():
        return None, [f"Base directory '{base_dir}' does not exist or is not a directory."]

    raw_uid = str(uid).strip()
    prefixes = {raw_uid + " "}
    if raw_uid.isdigit():
        val = int(raw_uid)
        prefixes.add(f"{val} ")
        prefixes.add(f"{val:02d} ")

    candidates = [d for d in sorted(base.iterdir())
                  if d.is_dir() and any(d.name.startswith(p) for p in prefixes)]
    if not candidates:
        return None, []
    if len(candidates) == 1:
        return candidates[0], []

    flags = [f"uid {uid}: {len(candidates)} folders share this prefix "
             f"({[c.name for c in candidates]}) — pre-existing Drive naming collision."]
    if folder_id:
        matches = [c for c in candidates if _drive_item_id(c) == folder_id]
        if len(matches) == 1:
            return matches[0], flags
    flags.append(f"uid {uid}: could not disambiguate by folder_id — skipped, needs manual check.")
    return None, flags


def find_role_folder(company_folder: Path, role: str) -> Tuple[Optional[Path], List[str]]:
    """
    Pick the role subfolder under `company_folder` that matches `role`.
    Returns (folder_or_None, flags). `flags` carries a note when the match
    was ambiguous (more than one candidate, no clear token-overlap winner) —
    callers should surface that in the run report rather than staying
    silent about the guess.
    """
    flags: List[str] = []
    if not company_folder.is_dir():
        return None, [f"Company folder '{company_folder}' is not a directory."]

    all_subs = [d for d in sorted(company_folder.iterdir())
                if d.is_dir() and not d.name.startswith("_") and not d.name.startswith(".")]
    # Archived/merged stub folders (see the 2026-09-24 folder merge) are never a
    # valid write/scan target even when their name happens to share words
    # with the live role — they exist only as a historical pointer.
    # Canonical subfolders (10 Bewerbung, 20 Vorbereitung, 30 Verlauf) are also excluded.
    subs = [d for d in all_subs if "merged into" not in d.name.lower() and d.name not in CANON_SUBDIRS]
    if not subs:
        return None, flags
    if len(subs) == 1:
        return subs[0], flags

    # Names made only of stopwords ("Lead Data & AI") have no tokens: compare the plain names, ignoring
    # parentheticals such as "(m/w/d)" or the status suffix "(rejected)".
    exact = [sd for sd in subs if _plain(sd.name) and _plain(sd.name) == _plain(role or "")]
    if len(exact) == 1:
        return exact[0], flags

    role_tok = _tokens(role or "")
    scored = sorted(((len(role_tok & _tokens(s.name)), s) for s in subs), key=lambda t: -t[0])
    if scored[0][0] > 0 and (len(scored) == 1 or scored[0][0] > scored[1][0]):
        return scored[0][1], flags

    chosen = subs[0]
    flags.append(
        f"Multiple role folders under '{company_folder.name}' "
        f"({[s.name for s in subs]}) and none matched role text "
        f"'{role}' unambiguously — used '{chosen.name}', verify placement."
    )
    return chosen, flags


def locate_role_folder(base_dir: str, uid, role: str, folder_id: str = "") -> Tuple[Optional[Path], List[str]]:
    """Convenience wrapper: base_dir + uid -> role folder, in one call."""
    company_folder, flags = find_company_folder(base_dir, uid, folder_id)
    if not company_folder:
        if not flags:
            flags = [f"No folder starting with '{uid} ' found in {base_dir}"]
        return None, flags
    role_folder, role_flags = find_role_folder(company_folder, role)
    if role_folder is None:
        role_folder = company_folder
    return role_folder, flags + role_flags
