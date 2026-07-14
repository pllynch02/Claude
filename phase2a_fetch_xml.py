#!/usr/bin/env python3
"""Phase 2a — Map universe EINs to 990 e-file XML object IDs and download XMLs.

Source: GivingTuesday 990 data lake (public S3 bucket `gt990datalake-rawdata`),
which mirrors the IRS 990 e-file XML corpus and publishes a parquet index of
every filing. ProPublica's own per-filing XML endpoint sits behind a bot
check, so the data lake is used instead. The parquet index is queried
remotely via DuckDB httpfs (HTTP range reads — the ~1.4 GB file is never
downloaded in full).

Outputs:
  - filings/xml_index.csv : EIN -> up to 3 most recent Form 990 filings
  - filings/xml/{ein}_{object_id}.xml : raw 990 XML (cached, never re-fetched)
"""

import csv
import json
import time
from pathlib import Path

import duckdb
import requests

ROOT = Path(__file__).resolve().parent
FILINGS_DIR = ROOT / "filings"
XML_DIR = FILINGS_DIR / "xml"
XML_INDEX_CSV = FILINGS_DIR / "xml_index.csv"

HTTPFS_PATH = ("/tmp/claude-0/-home-user-Claude/29e9eb30-df53-55ef-b591-38c365fc88f8/"
               "scratchpad/httpfs.duckdb_extension")
INDEX_URL = ("https://gt990datalake-rawdata.s3.amazonaws.com/Indices/990xmls/"
             "index_all_years_efiledata_xmls_created_on_2026-06-04.parquet")
XML_URL_TMPL = ("https://gt990datalake-rawdata.s3.amazonaws.com/EfileData/XmlFiles/"
                "{object_id}_public.xml")

FILINGS_PER_ORG = 3
SLEEP = 0.25
MAX_RETRIES = 4


def universe_eins():
    with (ROOT / "universe.csv").open() as fh:
        return [row["ein"] for row in csv.DictReader(fh)]


def build_xml_index(eins):
    if XML_INDEX_CSV.exists():
        with XML_INDEX_CSV.open() as fh:
            rows = list(csv.DictReader(fh))
        print(f"xml_index.csv already exists ({len(rows)} rows); reusing")
        return rows

    con = duckdb.connect()
    con.execute(f"LOAD '{HTTPFS_PATH}'")
    padded = ",".join(f"'{int(e):09d}'" for e in eins)
    q = f"""
        SELECT EIN, ObjectId, FormType, TaxPeriod, TaxYear,
               OrganizationName, TotalAssetsBkEOY, TotalLiabilitiesBkEOY
        FROM read_parquet('{INDEX_URL}')
        WHERE FormType = '990'
          AND lpad(regexp_replace(EIN, '[^0-9]', '', 'g'), 9, '0') IN ({padded})
        QUALIFY row_number() OVER (
            PARTITION BY EIN ORDER BY TaxPeriod DESC, ObjectId DESC
        ) <= {FILINGS_PER_ORG}
    """
    print("Querying remote parquet index (range reads)…")
    t0 = time.time()
    result = con.execute(q).fetchall()
    cols = [d[0] for d in con.description]
    print(f"  {len(result)} filings matched in {time.time() - t0:.0f}s")

    rows = [dict(zip(cols, r)) for r in result]
    with XML_INDEX_CSV.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)
    print(f"Wrote {XML_INDEX_CSV}")
    return rows


def download_xmls(rows):
    XML_DIR.mkdir(exist_ok=True)
    sess = requests.Session()
    ok = cached = miss = 0
    for i, row in enumerate(rows, 1):
        ein = f"{int(row['EIN']):09d}"
        oid = row["ObjectId"]
        out = XML_DIR / f"{ein}_{oid}.xml"
        if out.exists():
            cached += 1
            continue
        url = XML_URL_TMPL.format(object_id=oid)
        delay = 2
        for attempt in range(MAX_RETRIES + 1):
            try:
                resp = sess.get(url, timeout=60)
                break
            except requests.RequestException as exc:
                if attempt == MAX_RETRIES:
                    raise
                print(f"  retry after {exc} (sleep {delay}s)")
                time.sleep(delay)
                delay *= 2
        if resp.status_code == 200:
            out.write_bytes(resp.content)
            ok += 1
        else:
            miss += 1
            (XML_DIR / f"{ein}_{oid}.MISSING").write_text(str(resp.status_code))
        time.sleep(SLEEP)
        if i % 100 == 0:
            print(f"  {i}/{len(rows)} (new={ok} cached={cached} missing={miss})")
    print(f"XML download complete: new={ok} cached={cached} missing={miss}")


def main():
    eins = universe_eins()
    print(f"Universe: {len(eins)} EINs")
    rows = build_xml_index(eins)
    covered = len({r["EIN"] for r in rows})
    print(f"EINs with at least one e-filed 990: {covered}/{len(eins)}")
    download_xmls(rows)


if __name__ == "__main__":
    main()
