#!/usr/bin/env python3
"""
verify-dora-citations.py -- check every register row against the DORA text.

WHY THIS EXISTS
---------------
The requirements register was reconciled against the deployed policies (each row
joins to a live policy through its dora.requirement annotation) but it was never
checked against the legal text it claims to derive from. Internal consistency and
external correctness are different properties, and the register had the first
without the second.

This harness supplies the second. It reads the article corpus in
requirements/dora-articles.json and applies four checks to every row:

  1. EXISTS      Does the cited article exist in Chapter II?
  2. ADDRESSEE   Does the cited article bind financial entities at all? Article 15
                 mandates the ESAs to write technical standards; it imposes no
                 obligation on a regulated entity, so it cannot be the basis for
                 a technical control.
  3. FORM        Does the cited subdivision exist? Articles 7 and 15 have no
                 numbered paragraphs, only lettered points, so a citation of the
                 form "Art. 7(1)" is malformed regardless of subject matter.
  4. SUBJECT     Does the requirement's subject match the cited provision better
                 than some other provision in the same article? Scored by term
                 overlap against a controlled vocabulary.

Check 4 is ADVISORY. Term overlap is a heuristic and legal interpretation is not
a scoring exercise: the script proposes, a human decides. Checks 1 to 3 are
decisive, because they are questions of fact about the regulation's structure.

USAGE
    python3 scripts/verify-dora-citations.py
    python3 scripts/verify-dora-citations.py --out results/citation-audit

OUTPUTS
    <out>/citation-audit.csv     one row per requirement, with verdict
    <out>/citation-audit.md      narrative report grouped by severity
"""

import argparse
import csv
import json
import os
import re
from collections import defaultdict

# Controlled vocabulary linking requirement subject matter to legal wording.
# Deliberately small and auditable rather than a general language model: a
# reader must be able to see exactly why a suggestion was made.
TERMS = {
    "inventory": ["inventor", "identify all", "asset"],
    "classify": ["classif", "criticality", "map those considered critical"],
    "document": ["document", "documentation"],
    "dependency": ["interdependenc", "dependenc", "links", "interconnection"],
    "encryption": ["encrypt", "cryptographic", "confidentialit"],
    "transit": ["transfer of data", "in transit", "transmission"],
    "integrity": ["integrity", "authenticit"],
    "access": ["access", "least privilege", "legitimate and approved",
               "access rights"],
    "authentication": ["authentication", "strong authentication"],
    "segmentation": ["network", "severed", "segment", "isolate"],
    "change": ["change management", "recorded, tested, assessed"],
    "detection": ["detect", "anomalous", "alert"],
    "logging": ["monitor user activity", "monitor", "occurrence of ICT anomalies"],
    "resilience": ["continuity", "redundanc", "business impact"],
    "testing": ["test", "at least yearly"],
    "backup": ["backup", "restoration", "recovery"],
    "communication": ["communication", "disclosure", "media"],
    "supplychain": ["authenticit", "integrity", "change management"],
}

# Which vocabulary buckets each requirement's subject falls into. Derived from
# the register's own technical_domain plus its requirement text.
DOMAIN_TERMS = {
    "asset-management": ["inventory", "classify", "document", "dependency"],
    "documentation": ["document"],
    "risk-management": [],
    "encryption": ["encryption", "transit", "integrity"],
    "integrity": ["integrity", "supplychain"],
    "network-security": ["segmentation"],
    "resource-isolation": ["segmentation", "resilience"],
    "access-control": ["access", "authentication"],
    "detection": ["detection"],
    "logging": ["logging", "detection"],
    "resilience": ["resilience", "testing"],
    "change-management": ["change"],
    "supply-chain": ["supplychain", "integrity", "change"],
    "communication": ["communication"],
}


def _pretty_cite(art, sub):
    """Render '4(c)' as 'Art. 9(4)(c)' rather than 'Art. 9(4(c))'."""
    if not sub:
        return f"Art. {art}"
    m = re.match(r"^(\d+)\(([a-z])\)$", sub)
    if m:
        return f"Art. {art}({m.group(1)})({m.group(2)})"
    return f"Art. {art}({sub})"


def parse_citation(article_field, subsection_field):
    """Return (article_number, subdivision) from the register's two columns."""
    m = re.search(r"(\d+)", article_field or "")
    art = m.group(1) if m else None
    sub = (subsection_field or "").strip()
    # "9(4)(a)" -> "4(a)";  "14(1)-(3)" -> "1"
    sub = re.sub(r"^" + re.escape(art or "") + r"\(", "(", sub) if art else sub
    m2 = re.match(r"\(?(\d+)\)?(\([a-z]\))?", sub)
    if m2:
        para = m2.group(1)
        point = m2.group(2) or ""
        return art, (f"{para}{point}" if point else para)
    m3 = re.match(r"\(([a-z])\)", sub)
    if m3:
        return art, f"({m3.group(1)})"
    return art, sub or None


def score_provision(text, buckets):
    """Term-overlap score between a provision's text and a subject's vocabulary."""
    low = (text or "").lower()
    score = 0
    for b in buckets:
        for term in TERMS.get(b, []):
            if term.lower() in low:
                score += 1
    return score


def audit(register_path, corpus_path):
    corpus = json.load(open(corpus_path))
    rows = list(csv.DictReader(open(register_path)))
    out = []

    for r in rows:
        art, sub = parse_citation(r["dora_article"], r["dora_subsection"])
        rec = {
            "req_id": r["req_id"],
            "cited": _pretty_cite(art, sub),
            "requirement": r["requirement_text"],
            "domain": r["technical_domain"],
            "verdict": "",
            "severity": "",
            "reason": "",
            "suggestion": "",
        }

        # ---- check 1: article exists
        if art not in corpus or art.startswith("_"):
            rec.update(verdict="INVALID", severity="ERROR",
                       reason=f"Article {art} is not in Chapter II (Articles 5 to 16).")
            out.append(rec)
            continue

        entry = corpus[art]

        # ---- check 2: addressee
        if entry.get("addressee") == "ESA":
            rec.update(
                verdict="INVALID", severity="ERROR",
                reason=(f"Article {art} ({entry['title']}) mandates the ESAs to "
                        "develop regulatory technical standards. It imposes no "
                        "obligation on financial entities, so it cannot be the "
                        "legal basis for a technical control."),
                suggestion="Re-cite to the substantive article this control implements.")
            out.append(rec)
            continue

        # ---- unverified corpus coverage
        if entry.get("_unverified"):
            rec.update(verdict="UNVERIFIED", severity="INFO",
                       reason=(f"Article {art} text is not yet in the corpus, so "
                               "this citation could not be checked."))
            out.append(rec)
            continue

        paras = entry.get("paragraphs", {})

        # ---- check 3: citation form
        if entry.get("no_numbered_paragraphs") and sub and sub[0].isdigit():
            rec.update(
                verdict="MALFORMED", severity="ERROR",
                reason=(f"Article {art} has no numbered paragraphs, only lettered "
                        f"points, so '({sub})' cannot exist."),
                suggestion=f"Valid subdivisions: {', '.join(sorted(paras))}")
            out.append(rec)
            continue

        if sub and sub not in paras:
            rec.update(
                verdict="MALFORMED", severity="ERROR",
                reason=f"Article {art} has no subdivision ({sub}).",
                suggestion=f"Valid subdivisions: {', '.join(sorted(paras))}")
            out.append(rec)
            continue

        # ---- check 4: subject match (advisory)
        buckets = DOMAIN_TERMS.get((r["technical_domain"] or "").strip(), [])
        if not buckets:
            rec.update(verdict="OK", severity="INFO",
                       reason="Article and subdivision valid; no subject vocabulary "
                              "defined for this domain, so subject not scored.")
            out.append(rec)
            continue

        cited_score = score_provision(paras.get(sub, ""), buckets)

        # Best-scoring alternative anywhere in Chapter II
        best, best_score = None, cited_score
        for a2, e2 in corpus.items():
            if a2.startswith("_") or e2.get("addressee") == "ESA":
                continue
            for p2, text2 in (e2.get("paragraphs") or {}).items():
                s = score_provision(text2, buckets)
                if s > best_score:
                    best, best_score = f"Art. {a2}({p2})", s

        if best and best_score > cited_score:
            rec.update(
                verdict="REVIEW", severity="WARN",
                reason=(f"Cited provision scores {cited_score} on subject terms; "
                        f"{best} scores {best_score}."),
                suggestion=f"Consider {best}.")
        else:
            rec.update(verdict="OK", severity="OK",
                       reason=f"Article, subdivision and subject all consistent "
                              f"(score {cited_score}).")
        out.append(rec)

    return out


def build_report(results, corpus_path):
    corpus = json.load(open(corpus_path))
    by_sev = defaultdict(list)
    for r in results:
        by_sev[r["severity"]].append(r)

    L = ["# DORA citation audit\n"]
    L.append(f"\nRegister rows checked: {len(results)}. "
             f"Corpus: `{os.path.basename(corpus_path)}` "
             f"({corpus['_meta']['source']}).\n")
    L.append(
        "\nChecks 1 to 3 (article exists, article binds financial entities, "
        "subdivision exists) are questions of fact about the regulation's "
        "structure and are decisive. Check 4 (subject match) is advisory: term "
        "overlap is a heuristic, and legal interpretation is a matter for the "
        "author, not a score.\n")

    counts = {k: len(v) for k, v in by_sev.items()}
    L.append(f"\n| Severity | Count |\n|---|---|\n")
    for sev in ("ERROR", "WARN", "INFO", "OK"):
        L.append(f"| {sev} | {counts.get(sev, 0)} |\n")

    for sev, heading in [("ERROR", "Errors: citations that cannot stand"),
                         ("WARN", "Review: subject may fit another provision better"),
                         ("INFO", "Not checked"),
                         ("OK", "Verified")]:
        rs = by_sev.get(sev, [])
        if not rs:
            continue
        L.append(f"\n## {heading}\n\n")
        L.append("| REQ | Cited | Requirement | Finding | Suggestion |\n")
        L.append("|---|---|---|---|---|\n")
        for r in rs:
            L.append(f"| {r['req_id']} | {r['cited']} | {r['requirement'][:44]} | "
                     f"{r['reason']} | {r['suggestion'] or '-'} |\n")
    return "".join(L)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--register",
                    default="requirements/dora-requirements-register.csv")
    ap.add_argument("--corpus", default="requirements/dora-articles.json")
    ap.add_argument("--out", default="results/citation-audit")
    args = ap.parse_args()

    results = audit(args.register, args.corpus)
    os.makedirs(args.out, exist_ok=True)

    with open(f"{args.out}/citation-audit.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(results[0].keys()))
        w.writeheader()
        w.writerows(results)

    report = build_report(results, args.corpus)
    open(f"{args.out}/citation-audit.md", "w").write(report)
    print(report)

    # Article coverage: every article in scope should have at least one row,
    # EXCEPT Article 15, which binds the ESAs and therefore cannot yield an
    # entity requirement. Reporting this explicitly stops a future reader
    # mistaking the absence for the silent omission found for Article 14.
    import collections
    reg = list(csv.DictReader(open(args.register)))
    seen = collections.Counter(
        int(re.search(r"(\d+)", r["dora_article"]).group(1)) for r in reg)
    corpus2 = json.load(open(args.corpus))
    # Articles that yield no requirement enforceable at admission. The register
    # decomposes each article into its technical requirements; where an article
    # yields none, that is recorded here and in the thesis scope section rather
    # than as a register row, so the register holds technical requirements only.
    NO_TECHNICAL_REQUIREMENT = {
        5:  "binds the management body, not the systems",
        6:  "governs the risk management framework document",
        13: "governs learning and post-incident review",
        14: "governs crisis communication and staffing",
    }
    gaps = []
    for a in range(5, 16):
        if seen.get(a):
            continue
        if (corpus2.get(str(a)) or {}).get("addressee") == "ESA":
            print(f"Article {a}: no requirement, correct "
                  f"(binds the ESAs, not financial entities).")
        elif a in NO_TECHNICAL_REQUIREMENT:
            print(f"Article {a}: no requirement, correct "
                  f"({NO_TECHNICAL_REQUIREMENT[a]}).")
        else:
            gaps.append(a)
    if gaps:
        print(f"WARNING: articles with no register entry: {gaps}")

    errs = sum(1 for r in results if r["severity"] == "ERROR")
    warns = sum(1 for r in results if r["severity"] == "WARN")
    print(f"\nWrote {args.out}/")
    print(f"Errors: {errs}   Review: {warns}")


if __name__ == "__main__":
    main()
