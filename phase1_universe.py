#!/usr/bin/env python3
"""Phase 1 — Build the universe of candidate NFP lenders/administrators.

Pulls organizations from the ProPublica Nonprofit Explorer API (v2, free, no
key), deduplicates by EIN, writes `universe.csv`, and caches every raw API
response under `filings/` so nothing is ever re-fetched.

Resumable: re-running skips anything already cached on disk.

API notes:
  - Search: GET /nonprofits/api/v2/search.json?q=TERM&page=N  (pages are
    0-indexed, 25 orgs/page; response includes total_results & num_pages).
  - The v2 search endpoint only supports NTEE *major category* filtering
    (ntee[id]=1..10), not fine-grained codes like L20. Fine-grained codes
    (L20, L21, L25, L80, S30, S31, S43) are instead matched against the
    `ntee_code` field returned on each organization, and extra broad queries
    are run to widen the net for those categories.
  - Org detail: GET /nonprofits/api/v2/organizations/{ein}.json returns the
    org plus `filings_with_data` (e-filed, structured) and
    `filings_without_data` (PDF-only). Saved verbatim to filings/{ein}.json.
"""

import csv
import json
import sys
import time
from pathlib import Path

import requests

BASE = "https://projects.propublica.org/nonprofits/api/v2"
ROOT = Path(__file__).resolve().parent
FILINGS_DIR = ROOT / "filings"
SEARCH_CACHE_DIR = FILINGS_DIR / "_search_cache"
UNIVERSE_CSV = ROOT / "universe.csv"

SLEEP_BETWEEN_REQUESTS = 0.5  # polite rate limit
MAX_RETRIES = 4

SEARCH_QUERIES = [
    "community development financial institution",
    "CDFI",
    "loan fund",
    "community loan fund",
    "housing loan fund",
    "revolving loan fund",
    "community development corporation loan",
    "housing finance",
    "green bank",
    "community development entity",
    # extra breadth for the target NTEE categories (fine-grained NTEE
    # filtering isn't supported by the API, so cast a wider text net):
    "housing finance agency",
    "housing trust fund",
    "community capital",
    "development finance",
    "microloan fund",
]

TARGET_NTEE_PREFIXES = ("L20", "L21", "L25", "L80", "S30", "S31", "S43")

session = requests.Session()
session.headers["User-Agent"] = (
    "gaap-precedent-research/1.0 (nonprofit financial-statement research; "
    "polite, cached, rate-limited)"
)


def get_json(url, params=None):
    """GET with retries/backoff. Returns parsed JSON or None on 404."""
    delay = 2
    for attempt in range(MAX_RETRIES + 1):
        try:
            resp = session.get(url, params=params, timeout=60)
            if resp.status_code == 404:
                return None
            if resp.status_code == 429 or resp.status_code >= 500:
                raise requests.RequestException(f"HTTP {resp.status_code}")
            resp.raise_for_status()
            return resp.json()
        except (requests.RequestException, json.JSONDecodeError) as exc:
            if attempt == MAX_RETRIES:
                raise
            print(f"    retry {attempt + 1} after error: {exc} (sleep {delay}s)")
            time.sleep(delay)
            delay *= 2
    return None


def run_search_query(query):
    """Yield organization dicts for every page of a search query, cached."""
    slug = "".join(c if c.isalnum() else "_" for c in query.lower())
    page = 0
    while True:
        cache_file = SEARCH_CACHE_DIR / f"{slug}__p{page}.json"
        if cache_file.exists():
            data = json.loads(cache_file.read_text())
        else:
            data = get_json(f"{BASE}/search.json", {"q": query, "page": page})
            time.sleep(SLEEP_BETWEEN_REQUESTS)
            if data is None:
                break
            cache_file.write_text(json.dumps(data))
        orgs = data.get("organizations") or []
        if page == 0:
            print(f"  '{query}': total_results={data.get('total_results')} "
                  f"num_pages={data.get('num_pages')}")
        yield from orgs
        num_pages = data.get("num_pages") or 0
        page += 1
        if page >= num_pages or not orgs:
            break


def build_universe():
    SEARCH_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    by_ein = {}
    for query in SEARCH_QUERIES:
        for org in run_search_query(query):
            ein = org.get("ein")
            if not ein:
                continue
            rec = by_ein.setdefault(ein, dict(org))
            rec.setdefault("_matched_queries", set()).add(query)
    print(f"\nDeduplicated universe: {len(by_ein)} EINs")
    return by_ein


def fetch_org_details(eins):
    """Fetch /organizations/{ein}.json for each EIN, cached to filings/."""
    done = 0
    for ein in eins:
        out = FILINGS_DIR / f"{ein}.json"
        if out.exists():
            done += 1
            continue
        data = get_json(f"{BASE}/organizations/{ein}.json")
        time.sleep(SLEEP_BETWEEN_REQUESTS)
        out.write_text(json.dumps(data if data is not None else {"_not_found": True}))
        done += 1
        if done % 50 == 0:
            print(f"  org details: {done}/{len(eins)}")
    print(f"  org details complete: {done}/{len(eins)}")


def most_recent_filing_year(ein):
    f = FILINGS_DIR / f"{ein}.json"
    if not f.exists():
        return ""
    try:
        data = json.loads(f.read_text())
    except json.JSONDecodeError:
        return ""
    years = [
        fl.get("tax_prd_yr")
        for fl in (data.get("filings_with_data") or []) + (data.get("filings_without_data") or [])
        if fl.get("tax_prd_yr")
    ]
    return max(years) if years else ""


def write_universe_csv(by_ein):
    with UNIVERSE_CSV.open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow([
            "ein", "name", "state", "ntee_code", "target_ntee_match",
            "most_recent_filing_year", "matched_queries",
        ])
        for ein in sorted(by_ein):
            org = by_ein[ein]
            ntee = (org.get("ntee_code") or "").strip()
            w.writerow([
                ein,
                org.get("name", ""),
                org.get("state", ""),
                ntee,
                "Y" if ntee.upper().startswith(TARGET_NTEE_PREFIXES) else "",
                most_recent_filing_year(ein),
                "; ".join(sorted(org.get("_matched_queries", []))),
            ])
    print(f"Wrote {UNIVERSE_CSV} ({len(by_ein)} rows)")


def main():
    FILINGS_DIR.mkdir(exist_ok=True)
    by_ein = build_universe()
    fetch_org_details(sorted(by_ein))
    write_universe_csv(by_ein)


if __name__ == "__main__":
    sys.exit(main())
