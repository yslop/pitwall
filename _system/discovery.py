#!/usr/bin/env python3
"""
RUNBOOK Step 4b — Discovery Engine.
Searches EURES and BA-Jobbörse for new executive opportunities.
Verifies each on the employer's own page before adding to Watchlist.

CLI:
    python3 discovery.py --uid-start NNN --out-csv /path/new_rows.csv \
      --today YYYY-MM-DD --jd-cache _system/jd_cache.json
"""
import argparse, csv, html, json, os, re, sys, urllib.request, urllib.parse
from datetime import date as _date
from _typesafe_env import get_typesafe_api_key
from _typesafe_ledger import log_call

try:
    import requests
except ImportError:
    requests = None

try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None

TYPESAFE_URL = "https://api.typesafe.ai/v1/systemone"

# ── Search keywords ──────────────────────────────────────────────────────────
_KEYWORDS_PRECISE = [
    "Head of Data", "CDO", "CDAO", "Head of AI",
    "Director Data AI", "Leiter IT", "CIO",
    "Head of Digital Transformation", "IT-Leitung", "Head of Analytics",
]

_KEYWORDS_BROAD = [
    "Team Lead Data", "Teamleiter Daten", "Solution Architect",
    "Enterprise Architect", "Principal Data", "Manager Data",
    "Head of BI", "Bereichsleiter IT", "Abteilungsleiter Digital",
    "Data Architect",
]


def _daily_slice(keywords: list, today_str: str, n: int = 2) -> list:
    """
    Pick a rotating subset of `n` keywords for the given ISO date, cycling
    through the full list across days instead of using the same subset
    every run — keeps external search calls bounded per day while still
    covering the whole list across a week.
    """
    day_ordinal = _date.fromisoformat(today_str).toordinal()
    start = (day_ordinal * n) % len(keywords)
    return [keywords[(start + i) % len(keywords)] for i in range(n)]


def _daily_keywords(today_str: str) -> list:
    """Combined precise + broad search terms for today's discovery run."""
    return _daily_slice(_KEYWORDS_PRECISE, today_str, 2) + _daily_slice(_KEYWORDS_BROAD, today_str, 2)

# ── Lane detection ───────────────────────────────────────────────────────────
_LANE_RULES = [
    ("Data/AI Arch",   r"data|ai\b|analytics|cdo|cdao|bi\b|daten|k.nstliche.intelligenz"),
    ("IT Leadership",  r"cio|leiter.it|it.leitung|it.leadership|infrastruktur"),
    ("Transformation", r"transformation|digital|change|erp|reorgani"),
    ("Executive",      r"vorstand|ceo|coo|gesch.ftsf.hr"),
]


def detect_lane(title: str, description: str = "") -> str:
    text = (title + " " + description).lower()
    for lane, pattern in _LANE_RULES:
        if re.search(pattern, text):
            return lane
    return "Other"


def _tier_for_title(title: str) -> str:
    """
    'precise' if the title contains one of the unambiguous senior titles
    verbatim, else 'broad' — a broad-tier title needs the TypeSafe
    scope-equivalence judgment before it can be trusted.
    """
    lowered = title.lower()
    for kw in _KEYWORDS_PRECISE:
        if kw.lower() in lowered:
            return "precise"
    return "broad"


_LANE_CRITERIA = {
    "data_ai_arch": "Data/AI Architecture — owns data platform, AI/ML, or analytics strategy",
    "it_leadership": "IT Leadership — owns infrastructure, IT operations, or technology at org level",
    "transformation": "Digital Transformation — owns change, ERP, or reorg-scale digital initiatives",
    "executive": "Executive — board/C-level scope beyond a single function",
    "not_equivalent": "None of the above — role's actual scope/seniority does not match, "
                       "even accounting for a smaller organization having flatter titles",
}

_LANE_LABELS = {
    "data_ai_arch": "Data/AI Arch",
    "it_leadership": "IT Leadership",
    "transformation": "Transformation",
    "executive": "Executive",
}


def _typesafe_lane_and_maturity(role: str, company: str, jd_text: str) -> dict:
    """
    One combined TypeSafe call: is this role scope-equivalent to a target
    lane (regardless of literal title), and is the posting mature enough to
    track? Returns {"lane": str|None, "mature": bool} on success — "lane" is
    None when not equivalent or not mature, meaning "drop this candidate".
    Returns {"error": str} on any failure; callers must fail closed (drop).
    """
    api_key = get_typesafe_api_key()
    if not api_key:
        return {"error": "TYPESAFE_API_KEY not set"}

    state = json.dumps({"role": role, "company": company, "jd_text": jd_text[:1500]})
    payload = json.dumps({
        "state": state,
        "model": "jev-latest",
        "questions": {
            "lane_fit": {
                "type": "choice",
                "instructions": (
                    "Which lane, if any, does this role's actual scope and decision "
                    "authority match? A title like Team Lead, Architect, Manager, or "
                    "Principal at a smaller/SME organization can carry equivalent scope "
                    "to a Head-of or C-level title at a larger one — judge by scope, not "
                    "title alone."
                ),
                "criteria": _LANE_CRITERIA,
            },
            "mature": {
                "type": "noul",
                "instructions": (
                    "Does this posting contain enough concrete detail about scope, "
                    "responsibilities, or requirements to judge fit, rather than being "
                    "a vague, templated, or clearly stub/expired listing?"
                ),
            },
        }
    }).encode()

    req = urllib.request.Request(
        TYPESAFE_URL,
        data=payload,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
            log_call("discovery", data)
        answers = data["answers"]
        choice = answers["lane_fit"]["choice"]
        is_mature = answers["mature"]["noul"] >= 0.5
    except Exception as exc:
        return {"error": str(exc)}

    if choice == "not_equivalent" or not is_mature:
        return {"lane": None, "mature": is_mature}
    return {"lane": _LANE_LABELS.get(choice), "mature": is_mature}


# ── Posting verification ─────────────────────────────────────────────────────
_FILLED_SIGNALS = [
    "position has been filled", "stelle ist besetzt", "die stelle wurde besetzt",
    "no longer accepting", "vacancy closed", "bewerbung nicht mehr möglich",
]


def verify_posting(employer_url: str, timeout: int = 10) -> tuple:
    """
    Fetch the employer's own job page, confirm the role is still open, and
    extract its visible text for downstream JD scoring.

    Returns (is_open: bool, text: str). `text` is "" whenever `is_open` is
    False or the page couldn't be parsed — callers must not rely on `text`
    unless `is_open` is True.
    """
    if not employer_url or not employer_url.startswith("http"):
        return False, ""
    try:
        if requests is not None:
            resp = requests.get(employer_url, timeout=timeout,
                                headers={"User-Agent": "Mozilla/5.0"})
            if resp.status_code >= 400:
                return False, ""
            raw_text = resp.text
        else:
            req = urllib.request.Request(employer_url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw_text = resp.read().decode("utf-8", errors="ignore")

        lower = raw_text.lower()
        for sig in _FILLED_SIGNALS:
            if sig in lower:
                return False, ""
        if BeautifulSoup is not None:
            visible = BeautifulSoup(raw_text, "html.parser").get_text(separator=" ", strip=True)
        else:
            clean = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", raw_text, flags=re.DOTALL | re.IGNORECASE)
            clean = re.sub(r"<[^>]+>", " ", clean)
            clean = html.unescape(clean)
            visible = clean
        visible = re.sub(r"\s+", " ", visible)[:4000]
        return True, visible
    except Exception:
        return False, ""


# ── EURES search ─────────────────────────────────────────────────────────────
_EURES_URL = "https://europa.eu/eures/eures-searchengine/page/jv/search"


def _search_eures(uid_start: int, today_str: str) -> list:
    results = []
    uid = uid_start
    for keyword in _daily_keywords(today_str):
        try:
            payload = json.dumps({
                "keywords": keyword,
                "locationCodes": ["DE", "AT", "CH"],
                "pageSize": 10,
                "page": 0,
            }).encode("utf-8")
            if requests is not None:
                resp = requests.post(
                    _EURES_URL,
                    data=payload,
                    timeout=15,
                    headers={"Content-Type": "application/json", "Accept": "application/json"},
                )
                if resp.status_code != 200:
                    continue
                data = resp.json()
            else:
                req = urllib.request.Request(
                    _EURES_URL,
                    data=payload,
                    headers={"Content-Type": "application/json", "Accept": "application/json"},
                )
                with urllib.request.urlopen(req, timeout=15) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
            for item in (data.get("jobVacancies") or []):
                employer = (item.get("hiringOrganization") or {}).get("name", "").strip()
                role      = item.get("title", "").strip()
                url       = item.get("jobPageUrl") or item.get("applyUri", "")
                if not employer or not role or not url:
                    continue
                uid += 1
                results.append({
                    "uid": uid,
                    "company": employer,
                    "role": role,
                    "employer_url": url,
                    "lane": detect_lane(role),
                    "salary_fit": "mid",
                    "location": "DACH",
                })
        except Exception:
            continue
    return results


# ── BA-Jobbörse search ───────────────────────────────────────────────────────
# v6 confirmed working 2026-09-22 (v4 now returns 403); result list key,
# title/employer field names, and the lack of a direct URL field are all
# different from the old v4 shape this code was originally written against.
_BA_URL = "https://rest.arbeitsagentur.de/jobboerse/jobsuche-service/pc/v6/jobs"
_BA_JOB_DETAIL_URL = "https://www.arbeitsagentur.de/jobsuche/jobdetail/{}"


def _search_ba(uid_start: int, today_str: str) -> list:
    results = []
    uid = uid_start
    try:
        params = {
            "was": " OR ".join(_daily_keywords(today_str)),
            "wo": "Deutschland",
            "page": "1",
            "size": "20",
        }
        if requests is not None:
            resp = requests.get(
                _BA_URL, params=params, timeout=15,
                headers={"X-API-Key": "jobboerse-jobsuche", "Accept": "application/json"},
            )
            if resp.status_code != 200:
                return []
            data = resp.json()
        else:
            query_str = urllib.parse.urlencode(params)
            req = urllib.request.Request(
                f"{_BA_URL}?{query_str}",
                headers={"X-API-Key": "jobboerse-jobsuche", "Accept": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        for item in (data.get("ergebnisliste") or []):
            employer  = item.get("firma", "").strip()
            role      = item.get("stellenangebotsTitel", "").strip()
            reference = item.get("referenznummer", "").strip()
            if not employer or not role or not reference:
                continue
            uid += 1
            results.append({
                "uid": uid,
                "company": employer,
                "role": role,
                "employer_url": _BA_JOB_DETAIL_URL.format(reference),
                "lane": detect_lane(role),
                "salary_fit": "mid",
                "location": "Deutschland",
            })
    except Exception:
        pass
    return results


# ── Public API ────────────────────────────────────────────────────────────────
def search_portals(
    last_uid: int,
    existing_companies: set,
    today: str,
    stats: dict = None,
) -> tuple:
    """
    Search all configured portals. Returns (rows, jd_cache):
      rows     - new pipeline.csv Watchlist row dicts
      jd_cache - {str(uid): jd_text} for every row in `rows`, the full
                 visible text captured from the employer's own posting page
    Skips companies already in existing_companies (normalised to lower-case).
    Verifies each posting on the employer's own page.

    `stats`, if given, is updated in place with "typesafe_errors" (a
    candidate was dropped because the TypeSafe call itself failed — a
    signal worth surfacing separately from an ordinary judgment-based
    rejection) and "rejected" (dropped as not mature / not scope-equivalent).
    Optional and defaults to None so existing callers are unaffected.
    """
    if stats is None:
        stats = {}
    stats.setdefault("typesafe_errors", 0)
    stats.setdefault("rejected", 0)

    uid_cursor = last_uid
    raw = []
    raw += _search_eures(uid_cursor, today)
    uid_cursor = max((r["uid"] for r in raw), default=uid_cursor)
    raw += _search_ba(uid_cursor, today)

    seen_companies = set(existing_companies)
    rows = []
    jd_cache = {}
    next_uid = last_uid

    for item in raw:
        company_key = item["company"].lower().strip()
        if company_key in seen_companies:
            continue
        is_open, jd_text = verify_posting(item.get("employer_url", ""))
        if not is_open:
            continue

        tier = _tier_for_title(item["role"])
        lane = item.get("lane", "Other")
        if tier == "precise" and lane != "Other":
            final_lane = lane
        else:
            result = _typesafe_lane_and_maturity(item["role"], item["company"], jd_text)
            if result.get("error"):
                stats["typesafe_errors"] += 1
                continue
            if not result.get("mature") or not result.get("lane"):
                stats["rejected"] += 1
                continue
            final_lane = result["lane"]

        seen_companies.add(company_key)
        next_uid += 1
        jd_cache[str(next_uid)] = jd_text
        rows.append({
            "uid": next_uid,
            "company": item["company"],
            "role": item["role"],
            "lane": final_lane,
            "stage": "Watchlist",
            "outcome": "",
            "applied": "",
            "last_event": today,
            "days_idle": "0",
            "score": "0",
            "boost": "0",
            "salary_fit": item.get("salary_fit", "mid"),
            "location": item.get("location", ""),
            "contacts": "",
            "folder_id": "",
            "next_action": "",
            "due": "",
            "note": f"Discovered via portal {today} — pending TypeSafe fit score",
            "ts_confidence": "",
            "ts_fit_score": "",
        })
    return rows, jd_cache


def _load_jd_cache(path: str) -> dict:
    """Load the existing JD text cache, tolerating a missing or corrupt file."""
    if not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (ValueError, OSError):
        # ValueError covers both json.JSONDecodeError (bad JSON syntax) and
        # UnicodeDecodeError (a truncation landing mid multi-byte UTF-8
        # character, e.g. from a Google-Drive sync conflict) — either way
        # the file is unreadable, treat it as an empty cache.
        return {}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--uid-start", type=int, required=True)
    ap.add_argument("--out-csv",   required=True)
    ap.add_argument("--today",     default=_date.today().isoformat())
    ap.add_argument("--pipeline",  default=None)
    ap.add_argument("--jd-cache",  default="_system/jd_cache.json")
    a = ap.parse_args()

    existing_companies: set = set()
    if a.pipeline and os.path.exists(a.pipeline):
        with open(a.pipeline, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if row.get("company"):
                    existing_companies.add(row["company"].lower().strip())

    stats = {}
    rows, new_jd_cache = search_portals(a.uid_start, existing_companies, a.today, stats)

    # Run stamp for the health check: written on every run, also when nothing new was found
    # (jd_cache.json is only rewritten when there are new candidates).
    try:
        from datetime import datetime as _dt
        with open(os.path.join(os.path.dirname(a.jd_cache) or ".", "discovery_last.json"), "w", encoding="utf-8") as f:
            json.dump({"ts": _dt.now().isoformat(timespec="seconds"), "day": a.today, "new": len(rows)}, f)
    except OSError as exc:
        print(f"  ⚠ Could not write discovery_last.json: {exc}")

    if new_jd_cache:
        # A cache-write failure (e.g. a bad path, a Drive-sync hiccup) must
        # never discard the day's already-discovered rows below — it only
        # means next run's Quality Gate won't have this run's JD text cached.
        try:
            jd_cache = _load_jd_cache(a.jd_cache)
            jd_cache.update(new_jd_cache)
            with open(a.jd_cache, "w", encoding="utf-8") as f:
                json.dump(jd_cache, f, ensure_ascii=False, indent=2)
        except OSError as exc:
            print(f"  ⚠ Could not update {a.jd_cache}: {exc}")

    if rows:
        with open(a.out_csv, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)
        print(f"Discovered {len(rows)} new Watchlist entries → {a.out_csv}")
    else:
        print("No new verified entries found this run.")

    if stats.get("typesafe_errors"):
        print(f"  ⚠ {stats['typesafe_errors']} candidate(s) dropped due to TypeSafe errors "
              f"(check TYPESAFE_API_KEY / service status) — not the same as a normal rejection")


if __name__ == "__main__":
    main()
