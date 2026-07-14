#!/usr/bin/env python3
"""Phase 2b — Extract screening fields from downloaded 990 XMLs and apply
the arithmetic flags. Text-judgment flags (F2/F3/F4) are prepared as
readable batches for in-session review, not decided here.

Outputs:
  - extracted.jsonl          : one record per filing, all extracted fields
  - screen_arithmetic.csv    : per-EIN arithmetic screen (F1 + ratio inputs)
  - screen_text_batches/*.md : Part III / revenue-line text for LLM review
"""

import csv
import json
import re
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
XML_DIR = ROOT / "filings" / "xml"
BATCH_DIR = ROOT / "screen_text_batches"
EXTRACTED = ROOT / "extracted.jsonl"
ARITH_CSV = ROOT / "screen_arithmetic.csv"

PART3_GROUPS = {
    "ProgSrvcAccomplishmentActyGrp", "ProgSrvcAccomActy2Grp",
    "ProgSrvcAccomActy3Grp", "ProgSrvcAccomActyOtherGrp",
    "ActivityOther",
}
ESCROW_KEYWORDS = re.compile(r"escrow|custodial|fiduciary", re.I)


def ln(el):
    return el.tag.split("}")[-1]


def to_num(txt):
    try:
        return float(txt)
    except (TypeError, ValueError):
        return None


def first_num(root, *names):
    wanted = set(names)
    for el in root.iter():
        if ln(el) in wanted:
            v = to_num((el.text or "").strip())
            if v is not None:
                return v
            for c in el:
                if ln(c) == "EOYAmt":
                    return to_num((c.text or "").strip())
    return None


def truthy_ind(root, name):
    for el in root.iter():
        if ln(el) == name:
            t = (el.text or "").strip().lower()
            return t in ("1", "true", "x", "yes")
    return None


def extract(path):
    try:
        root = ET.parse(path).getroot()
    except ET.ParseError as exc:
        return {"file": path.name, "parse_error": str(exc)}

    ein, oid = path.stem.split("_", 1)
    rec = {"file": path.name, "ein": ein, "object_id": oid}

    for el in root.iter():
        if ln(el) == "TaxYr":
            rec["tax_year"] = (el.text or "").strip()
            break
    for el in root.iter():
        if ln(el) == "Filer":
            for c in el.iter():
                if ln(c) == "BusinessNameLine1Txt":
                    rec["name"] = (c.text or "").strip()
                    break
            break

    rec["total_assets"] = first_num(root, "TotalAssetsEOYAmt")
    rec["total_liab"] = first_num(root, "TotalLiabilitiesEOYAmt")
    rec["escrow_liab_x21"] = first_num(root, "EscrowAccountLiabilityGrp")
    rec["notes_loans_recv"] = first_num(
        root, "OthNotesLoansReceivableNetGrp", "OthNotesLoansReceivableGrp",
        "OtherNotesLoansReceivableNetGrp")
    rec["program_related_inv"] = first_num(
        root, "InvestmentsProgramRelatedGrp", "InvstProgramRelatedGrp")
    rec["mortg_notes_payable"] = first_num(root, "MortgNotesPyblScrdInvstPropGrp")
    rec["unsecured_notes_payable"] = first_num(root, "UnsecuredNotesLoansPayableGrp")
    rec["part4_line9_escrow_ind"] = truthy_ind(root, "CreditCounselingInd")

    # Schedule D escrow/custodial (Part IV) — capture generically
    schd_escrow = {}
    for el in root.iter():
        if ESCROW_KEYWORDS.search(ln(el)):
            if list(el):
                for c in el.iter():
                    if c is not el and (c.text or "").strip():
                        schd_escrow[f"{ln(el)}/{ln(c)}"] = (c.text or "").strip()
            elif (el.text or "").strip():
                schd_escrow[ln(el)] = (el.text or "").strip()
    rec["escrow_custodial_tags"] = schd_escrow

    # Schedule D other liabilities captions (funds held for others live here)
    other_liab = []
    for el in root.iter():
        if ln(el) == "OtherLiabilitiesOrgGrp":
            d = {ln(c): (c.text or "").strip() for c in el}
            other_liab.append(d)
    rec["schd_other_liabilities"] = other_liab

    # Part III text
    texts = []
    for el in root.iter():
        if ln(el) in ("MissionDesc", "ActivityOrMissionDesc"):
            if (el.text or "").strip():
                texts.append(("mission", (el.text or "").strip()))
    for el in root.iter():
        if ln(el) in PART3_GROUPS:
            d = {ln(c): (c.text or "").strip() for c in el}
            if d.get("Desc") or d.get("DescriptionTxt"):
                texts.append(("activity", json.dumps(d)))
    for form in root.iter():
        if ln(form) == "IRS990":
            expense = revenue = None
            for c in form:
                n = ln(c)
                if n == "ExpenseAmt":
                    expense = (c.text or "").strip()
                elif n == "RevenueAmt":
                    revenue = (c.text or "").strip()
                elif n == "Desc":
                    texts.append(("activity", json.dumps(
                        {"Desc": (c.text or "").strip(),
                         "ExpenseAmt": expense, "RevenueAmt": revenue})))
                    expense = revenue = None
    # Schedule O continuations referencing Part III
    for el in root.iter():
        if ln(el) == "SupplementalInformationDetail":
            d = {ln(c): (c.text or "").strip() for c in el}
            ref = d.get("FormAndLineReferenceDesc", "")
            if "III" in ref.upper():
                texts.append(("schO_part3", d.get("ExplanationTxt", "")))
    rec["part3_texts"] = texts

    # Part VIII program service revenue lines
    rev_lines = []
    for el in root.iter():
        if ln(el) == "ProgramServiceRevenueGrp":
            d = {ln(c): (c.text or "").strip() for c in el}
            rev_lines.append(d)
    rec["program_revenue_lines"] = rev_lines
    return rec


def money_amounts(text):
    out = []
    for m in re.finditer(
            r"\$\s?([\d,.]+)\s*(BILLION|MILLION|B\b|MM?\b)?", text, re.I):
        try:
            v = float(m.group(1).replace(",", ""))
        except ValueError:
            continue
        unit = (m.group(2) or "").upper()
        if unit.startswith("B"):
            v *= 1e9
        elif unit.startswith("M"):
            v *= 1e6
        out.append(v)
    return out


def arithmetic_screen(recs_by_ein):
    rows = []
    for ein, recs in recs_by_ein.items():
        recs = sorted(recs, key=lambda r: r.get("tax_year") or "", reverse=True)
        r = recs[0]
        ta = r.get("total_assets") or 0
        escrow_amt = r.get("escrow_liab_x21") or 0
        for k, v in (r.get("escrow_custodial_tags") or {}).items():
            n = to_num(v)
            if n:
                escrow_amt = max(escrow_amt, n)
        ind = bool(r.get("part4_line9_escrow_ind")) or bool(
            r.get("escrow_custodial_tags"))
        f1 = (ta > 0 and escrow_amt > 0.5 * ta) or (ind and escrow_amt > 10e6)

        loans = (r.get("notes_loans_recv") or 0) + (r.get("program_related_inv") or 0)
        text_all = " ".join(t for _, t in r.get("part3_texts") or [])
        max_txt = max(money_amounts(text_all), default=0)
        f2_candidate = ta > 0 and max_txt >= 2 * ta

        agency_captions = [
            d for d in r.get("schd_other_liabilities") or []
            if re.search(r"held for others|agency|custodial|due to|"
                         r"pass.?thr|fiscal|on behalf", json.dumps(d), re.I)
        ]
        rows.append({
            "ein": ein,
            "name": r.get("name", ""),
            "tax_year": r.get("tax_year", ""),
            "total_assets": ta,
            "total_liab": r.get("total_liab"),
            "loans_recv_incl_pri": loans,
            "escrow_custodial_amt": escrow_amt,
            "escrow_ind": ind,
            "F1": f1,
            "max_part3_dollar": max_txt,
            "F2_candidate": f2_candidate,
            "agency_liab_captions": json.dumps(agency_captions) if agency_captions else "",
        })
    with ARITH_CSV.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    n_f1 = sum(1 for r in rows if r["F1"])
    n_f2c = sum(1 for r in rows if r["F2_candidate"])
    n_cap = sum(1 for r in rows if r["agency_liab_captions"])
    print(f"Arithmetic screen: {len(rows)} orgs | F1={n_f1} "
          f"F2_candidates={n_f2c} agency_captions={n_cap}")
    return rows


def write_text_batches(recs_by_ein, per_batch=40):
    BATCH_DIR.mkdir(exist_ok=True)
    eins = sorted(recs_by_ein)
    for b in range(0, len(eins), per_batch):
        lines = []
        for ein in eins[b:b + per_batch]:
            r = sorted(recs_by_ein[ein],
                       key=lambda x: x.get("tax_year") or "", reverse=True)[0]
            ta = r.get("total_assets")
            loans = (r.get("notes_loans_recv") or 0) + (r.get("program_related_inv") or 0)
            lines.append(f"## EIN {ein} — {r.get('name','?')} (TY{r.get('tax_year','?')})")
            lines.append(f"assets={ta} loans_recv={loans} "
                         f"escrow_x21={r.get('escrow_liab_x21')} "
                         f"liab={r.get('total_liab')}")
            for d in r.get("program_revenue_lines") or []:
                lines.append(f"REV: {d.get('Desc','')} = {d.get('TotalRevenueColumnAmt','')}")
            for kind, t in r.get("part3_texts") or []:
                lines.append(f"[{kind}] {t}")
            lines.append("")
        out = BATCH_DIR / f"batch_{b // per_batch:02d}.md"
        out.write_text("\n".join(lines))
    print(f"Wrote {len(list(BATCH_DIR.glob('batch_*.md')))} text batches to {BATCH_DIR}")


def main():
    recs = []
    for p in sorted(XML_DIR.glob("*.xml")):
        recs.append(extract(p))
    with EXTRACTED.open("w") as fh:
        for r in recs:
            fh.write(json.dumps(r) + "\n")
    print(f"Extracted {len(recs)} filings -> {EXTRACTED}")
    by_ein = defaultdict(list)
    for r in recs:
        if "ein" in r and not r.get("parse_error"):
            by_ein[r["ein"]].append(r)
    arithmetic_screen(by_ein)
    write_text_batches(by_ein)


if __name__ == "__main__":
    main()
