"""
Build the reproducible green-tech anchor lexicon (STRONG_TERMS) from multiple
authoritative sources via a deterministic multi-source vote.

  green-defining families (a single one can promote an anchor):
      cpc_y02 (patent taxonomy) + wikidata (emerging terms)
      + taxonomy_compass (EU Taxonomy activities) + egss (Reg 2015/2174 goods)
  corroboration-only families (evidence, never sole reason):
      gemet (SKOS thesaurus) + eu_reg (regulatory seeds)

  a cleaned token is ACCEPTED as a strong term iff
      it is a single-token WHOLE label/alias/name in a green-defining family
        (a green "atom": Wikidata green subclass, or a one-word CPC/Compass/EGSS
         item name), OR
      it is attested (as any token) in >= 2 distinct green-defining families
  and it is not on BROAD_DENYLIST and not a stopword.

  Component tokens of multiword titles (e.g. `argentina` from "solar power in
  Argentina", `aircraft` from a CPC title) do NOT self-promote: they must earn a
  cross-source vote. This keeps precision high while still letting a single
  authoritative source promote a genuinely one-word green concept.

Inputs  : data/sources/lexicon_raw/*  (from fetch_lexicon_sources.py)
          data/sources/concept_seeds.csv
Outputs : data/outputs/strong_terms_v1.csv
          data/outputs/strong_terms_provenance.csv
          data/outputs/strong_terms_candidates_review.csv
          data/outputs/strong_terms_multiword_candidates.csv
          data/outputs/strong_terms_build_report.txt
"""

from __future__ import annotations

import csv
import gzip
import json
import os
import re
from pathlib import Path

from build_strict_vocabulary_full_audit_algorithmic import (
    BROAD_DENYLIST,
    normalise_phrase,
)

ROOT = Path(__file__).resolve().parent
RAW_DIR = ROOT / "data" / "sources" / "lexicon_raw"
SEEDS_PATH = ROOT / "data" / "sources" / "concept_seeds.csv"
OUTPUT_DIR = ROOT / "data" / "outputs"

LEXICON_PATH = OUTPUT_DIR / "strong_terms_v1.csv"
PROVENANCE_PATH = OUTPUT_DIR / "strong_terms_provenance.csv"
CANDIDATES_PATH = OUTPUT_DIR / "strong_terms_candidates_review.csv"
MULTIWORD_PATH = OUTPUT_DIR / "strong_terms_multiword_candidates.csv"
REPORT_PATH = OUTPUT_DIR / "strong_terms_build_report.txt"

MIN_LEN = 4
TOKEN_RE = re.compile(r"^[a-z]+$")

# Path P3: allow the EU regulatory corpus (eu_reg) to promote a token on its own.
# DISABLED by default: when tried (REG_SOLE_ENABLED=1) it accepts ~376 eu_reg-only
# tokens that are overwhelmingly administrative boilerplate (acceptance,
# administration, compliance, assessment, ...) and PDF fragments (addresse,
# anagement), with only a few genuine greens - confirming that regulatory text
# alone cannot derive anchors (see strong_terms_derivation_report.txt). A length
# floor does not help because the junk words are long too. Enable to reproduce
# the experiment: REG_SOLE_ENABLED=1 [REG_SOLE_MIN=8].
REG_SOLE_ENABLED = os.environ.get("REG_SOLE_ENABLED", "0") == "1"
REG_SOLE_MIN = int(os.environ.get("REG_SOLE_MIN", "8"))

CPC_SUBCLASSES = ("Y02A", "Y02B", "Y02C", "Y02D", "Y02E", "Y02P", "Y02T", "Y02W", "Y04S")

# Comprehensive stopwords: English function words + generic technical / patent /
# legal / administrative vocabulary that is not itself a green-tech root. Kept
# deliberately broad because the multi-source vote plus this list is what stops
# generic words (system, technology, ...) from being accepted as anchors.
STOPWORDS: set[str] = set(
    """
    a about above after again against all also am an and any are aren't as at be
    because been before being below between both but by can cannot could
    couldn't did didn't do does doesn't doing don't down during each few for
    from further had hadn't has hasn't have haven't having he her here hers him
    his how i if in into is isn't it its itself let's me more most my no nor not
    of off on once only or other ought our ours out over own same she should so
    some such than that the their theirs them then there these they this those
    through to too under until up very was we were what when where which while
    who whom why will with would you your yours
    """.split()
) | set(
    # generic technical / patent / classification / legal / admin words
    """
    technology technologies technological system systems method methods process
    processes apparatus device devices equipment product products production
    material materials management managing control controls controlling
    measure measures measuring monitoring monitor operation operations operating
    application applications applied use uses using used related relating
    general specific specifically e.g. i.e. etc thereof therein thereby herein
    means unit units component components module modules type types kind form
    forms based including include includes included provided providing provides
    said other others new development developments technical subject subjects
    field fields area areas sector sectors section sections part parts step steps
    tagging cross sectional several spanning covered former digests digest
    collection collections reference art scheme classification classified
    indexing index code codes symbol symbols document documents patents patent
    uspto epo cpc ipc title titles definition definitions notes note browse
    search help home page next previous list version versions info
    regulation regulations directive directives article articles annex annexes
    paragraph commission council parliament member states union european journal
    official technologies mitigation adaptation change climate against relating
    industrial buildings building transportation goods persons information
    communication impact reduction reducing efficient efficiency effective
    potential indirect contribution enabling smart networks network operation
    energy waste water carbon emission emissions greenhouse gas gases
    """.split()
)
# NOTE: `energy/waste/water/carbon/emission(s)/greenhouse/gas` are organising
# objectives already on BROAD_DENYLIST; listing them here too keeps them out even
# if the denylist wording changes.


def tokens_of(text: str) -> list[str]:
    norm = normalise_phrase(text)
    if not norm:
        return []
    return [t for t in norm.split() if TOKEN_RE.match(t)]


def add_family_tokens(
    fam_tokens: dict[str, dict[str, str]], family: str, label: str
) -> None:
    """Record every token of `label` under `family` (keep first example label)."""
    bucket = fam_tokens.setdefault(family, {})
    for tok in tokens_of(label):
        bucket.setdefault(tok, label.strip())


def add_multiword(multiword: dict[str, str], family: str, label: str) -> None:
    toks = tokens_of(label)
    if 2 <= len(toks) <= 4:
        phrase = " ".join(toks)
        multiword.setdefault(phrase, family)


def add_green_atom(green_atoms: set[str], label: str) -> None:
    """Record a token that is the SOLE token of a green-defining source label /
    name / alias. Such a one-word item name is an authoritative green concept on
    its own (`desalination`, `biofuels`, `afforestation`, `agrivoltaics`), so it
    may be promoted by a single family. All-caps acronyms (BOOT, VRES) are skipped
    because they are too ambiguous as anchors."""
    toks = tokens_of(label)
    if len(toks) == 1 and len(toks[0]) >= MIN_LEN and not label.strip().isupper():
        green_atoms.add(toks[0])


# --------------------------------------------------------------------------- #
# Per-family extractors
# --------------------------------------------------------------------------- #
PREF_RE = re.compile(
    r"<[^>]*prefLabel[^>]*xml:lang=\"en\"[^>]*>(.*?)</[^>]*prefLabel>",
    re.IGNORECASE | re.DOTALL,
)
ALT_RE = re.compile(
    r"<[^>]*altLabel[^>]*xml:lang=\"en\"[^>]*>(.*?)</[^>]*altLabel>",
    re.IGNORECASE | re.DOTALL,
)


def extract_gemet(fam_tokens, multiword) -> int:
    path = RAW_DIR / "gemet.rdf.gz"
    if not path.exists():
        print(f"[gemet] MISSING {path}")
        return 0
    with gzip.open(path, "rt", encoding="utf-8", errors="ignore") as f:
        text = f.read()
    labels = PREF_RE.findall(text) + ALT_RE.findall(text)
    for raw in labels:
        label = re.sub(r"\s+", " ", raw).strip()
        if not label:
            continue
        add_family_tokens(fam_tokens, "gemet", label)
        add_multiword(multiword, "gemet", label)
    print(f"[gemet] {len(labels)} en labels")
    return len(labels)


TAG_RE = re.compile(r"<(script|style)[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL)
ANYTAG_RE = re.compile(r"<[^>]+>")


def extract_cpc(fam_tokens, multiword, green_atoms) -> int:
    n = 0
    for sc in CPC_SUBCLASSES:
        path = RAW_DIR / f"cpc-{sc}.html"
        if not path.exists():
            print(f"[cpc_y02] MISSING {path}")
            continue
        html = path.read_text(encoding="utf-8", errors="ignore")
        html = TAG_RE.sub(" ", html)
        # Extract visible text from table cells (titles live in <td>).
        cells = re.findall(r"<td[^>]*>(.*?)</td>", html, re.IGNORECASE | re.DOTALL)
        chunks = cells if cells else [html]
        for chunk in chunks:
            text = ANYTAG_RE.sub(" ", chunk)
            text = re.sub(r"&[a-z]+;", " ", text)
            text = re.sub(r"\s+", " ", text).strip()
            if not text:
                continue
            add_family_tokens(fam_tokens, "cpc_y02", text)
            add_multiword(multiword, "cpc_y02", text)
            add_green_atom(green_atoms, text)
            n += 1
    print(f"[cpc_y02] {n} title cells")
    return n


def extract_wikidata(fam_tokens, multiword, green_atoms: set[str]) -> int:
    """Extract Wikidata tokens; also collect green ATOMS.

    Every returned item is a subclass of a green-tech root (by the pinned query),
    so a single-token item label/alias is a green concept by ontology. Those
    single-token forms are recorded in `green_atoms` and are accepted even if
    they appear in no other family (this is how emerging terms such as
    `agrivoltaics` - present only in Wikidata - are recognised).
    """
    path = RAW_DIR / "wikidata_green_tech.json"
    if not path.exists():
        print(f"[wikidata] MISSING {path}")
        return 0
    data = json.loads(path.read_text(encoding="utf-8"))
    bindings = data.get("results", {}).get("bindings", [])
    n = 0
    for b in bindings:
        for key in ("itemLabel", "alias"):
            val = b.get(key, {}).get("value", "")
            if not val:
                continue
            # Skip unlabeled entities returned as bare Q-ids.
            if re.fullmatch(r"[Qq]\d+", val.strip()):
                continue
            add_family_tokens(fam_tokens, "wikidata", val)
            add_multiword(multiword, "wikidata", val)
            add_green_atom(green_atoms, val)
            n += 1
    print(f"[wikidata] {n} label/alias values ({len(bindings)} bindings)")
    return n


def extract_eu_reg(fam_tokens, multiword) -> int:
    if not SEEDS_PATH.exists():
        print(f"[eu_reg] MISSING {SEEDS_PATH}")
        return 0
    n = 0
    with SEEDS_PATH.open("r", encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            label = (row.get("normalised_phrase") or row.get("seed_phrase") or "").strip()
            if not label:
                continue
            add_family_tokens(fam_tokens, "eu_reg", label)
            add_multiword(multiword, "eu_reg", label)
            n += 1
    print(f"[eu_reg] {n} seeds")
    return n


def _compass_activity_names(obj) -> list[str]:
    """Collect delineated activity `name` fields from the Compass JSON. Sector
    names are deliberately NOT used: the Compass `sector` field is a broad NACE
    grouping (Accommodation, Financial and insurance, Education, ...) that is not
    itself green, and the prose `description` is free text."""
    names: list[str] = []
    items = obj if isinstance(obj, list) else obj.get("content", []) if isinstance(obj, dict) else []
    for it in items:
        if not isinstance(it, dict):
            continue
        name = (it.get("name") or "").strip()
        if name:
            names.append(name)
    return names


def extract_taxonomy_compass(fam_tokens, multiword) -> int:
    """EU Taxonomy Compass: use the delineated activity names for corroboration
    and multiword phrase candidates only - NOT as green atoms.

    The Compass covers activities across ALL economic sectors that can
    substantially contribute to an environmental objective, so its single-word
    activity names include non-green-tech items (it has activities literally named
    `Education` and `Reinsurance`). Minting atoms from them injects false
    positives, so Compass is treated as a corroboration source for token
    promotion (EGSS, an environmental-goods compendium, remains atom-capable)."""
    path = RAW_DIR / "taxonomy_compass_activities.json"
    if not path.exists():
        print(f"[taxonomy_compass] MISSING {path}")
        return 0
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"[taxonomy_compass] bad JSON: {exc}")
        return 0
    n = 0
    for name in _compass_activity_names(data):
        add_family_tokens(fam_tokens, "taxonomy_compass", name)
        add_multiword(multiword, "taxonomy_compass", name)
        n += 1
    print(f"[taxonomy_compass] {n} activity names (corroboration only)")
    return n


def extract_egss(fam_tokens, multiword, green_atoms) -> int:
    """EGSS indicative compendium (Reg (EU) 2015/2174): each ANNEX list item is a
    green good/service/activity. Only lines inside a `# ...` section are used, so
    the file header/provenance block is skipped."""
    path = RAW_DIR / "egss_2015_2174.txt"
    if not path.exists():
        print(f"[egss] MISSING {path}")
        return 0
    n = 0
    in_section = False
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("#"):
            in_section = True
            continue
        if not in_section:
            continue
        add_family_tokens(fam_tokens, "egss", line)
        add_multiword(multiword, "egss", line)
        add_green_atom(green_atoms, line)
        n += 1
    print(f"[egss] {n} compendium items")
    return n


# --------------------------------------------------------------------------- #
# Selection
# --------------------------------------------------------------------------- #
def is_clean(tok: str) -> bool:
    if len(tok) < MIN_LEN:
        return False
    if tok in STOPWORDS:
        return False
    if tok in BROAD_DENYLIST:
        return False
    return True


# A green-tech ROOT must be attested in at least one "green-defining" taxonomy -
# a source that is green by legal/ontological construction, not merely a broad
# environmental thesaurus or regulatory corpus (GEMET and the EU texts also carry
# socio-economic and administrative vocabulary, e.g. `service`, `market`,
# `policy`, so they stay corroboration-only). The green-defining families are:
#   cpc_y02          - climate-change-mitigation patent taxonomy (Y02/Y04S)
#   wikidata         - subclasses of renewable/environmental/clean technology
#   taxonomy_compass - EU Taxonomy delineated sustainable activities
#   egss             - EGSS indicative compendium of environmental goods (2015/2174)
GREEN_DEFINING = frozenset({"cpc_y02", "wikidata", "taxonomy_compass", "egss"})

# The two STRUCTURED taxonomies whose labels are concise concept names (not prose
# descriptions), so their component tokens are trustworthy enough to carry the
# cross-source vote. Compass and EGSS are green-defining but their multiword
# activity/goods descriptions only contribute via atoms + corroboration.
STRUCTURED_VOTE = frozenset({"cpc_y02", "wikidata"})


def decide(tok: str, present: list[str], is_atom: bool) -> tuple[str, str]:
    """Return (decision, accept_path)."""
    if not is_clean(tok):
        return "REJECT", ""
    # Path P_atom - green atom: the token is the SOLE token of a label / name /
    # alias in a green-defining family (a Wikidata green subclass, or a one-word
    # CPC / Compass / EGSS item name). Such a one-word item is authoritatively
    # green on its own, so it is accepted from a single family. This is what lets
    # single-source terms through (agrivoltaics, desalination, biofuels,
    # afforestation) WITHOUT admitting component tokens of multiword titles.
    if is_atom:
        return "ACCEPT", "atom"
    # Path P_vote - cross-source vote over the two STRUCTURED taxonomies (CPC Y02
    # AND Wikidata). Their tokens are concept names, so an intersection isolates
    # genuine green-tech roots (solar, photovoltaic, turbine, biomass). Compass
    # and EGSS entries are prose-like multiword descriptions whose *component*
    # tokens are generic (electricity, generation, construction, maintenance);
    # counting them toward the vote is what floods the pool, so they contribute
    # only via atoms (their one-word names, P_atom) and as corroboration - never
    # by lending a component token a vote.
    n = len(present)
    n_struct = sum(1 for fam in present if fam in STRUCTURED_VOTE)
    if n_struct >= 2:
        if len(tok) >= 6:
            return "ACCEPT", "vote"
        if 4 <= len(tok) <= 5 and n >= 3:
            return "ACCEPT", "vote"
    # Path P3 - regulatory-grounded (eu_reg as a sole source). A token attested
    # in the EU regulatory corpus is accepted on its own, subject to a length
    # guard (>= REG_SOLE_MIN chars) plus the shared denylist/stopword filters.
    # Longer tokens are far more likely to be delineated activities than bare
    # objective/dual-use nouns (which the denylist already removes). Disable with
    # REG_SOLE_ENABLED=0.
    if REG_SOLE_ENABLED and "eu_reg" in present and len(tok) >= REG_SOLE_MIN:
        return "ACCEPT", "regulatory"
    if len(present) >= 1:
        return "CANDIDATE", ""
    return "REJECT", ""


# Endings where a trailing 's' is NOT an English plural (mass/Latin/Greek nouns),
# so stripping it would create garbage (biogas -> bioga, biomass -> bioma).
# Note "ics" is intentionally excluded here so photovoltaics -> photovoltaic and
# agrivoltaics -> agrivoltaic still work.
NON_PLURAL_ENDINGS = ("ss", "as", "us", "is", "ous", "ns", "ys")


def variants_of(tok: str) -> set[str]:
    """Deterministic singular/plural variants (so agrivoltaics -> agrivoltaic)."""
    out: set[str] = set()
    if tok.endswith("s"):
        if not tok.endswith(NON_PLURAL_ENDINGS) and len(tok) - 1 >= MIN_LEN:
            out.add(tok[:-1])
    else:
        out.add(tok + "s")
    return {v for v in out if v != tok}


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    fam_tokens: dict[str, dict[str, str]] = {}
    multiword: dict[str, str] = {}
    green_atoms: set[str] = set()

    extract_gemet(fam_tokens, multiword)
    extract_cpc(fam_tokens, multiword, green_atoms)
    extract_wikidata(fam_tokens, multiword, green_atoms)
    extract_taxonomy_compass(fam_tokens, multiword)
    extract_egss(fam_tokens, multiword, green_atoms)
    extract_eu_reg(fam_tokens, multiword)
    print(f"[green_atoms] {len(green_atoms)} single-token green-defining names")

    families = ["gemet", "cpc_y02", "wikidata", "taxonomy_compass", "egss", "eu_reg"]
    all_tokens: set[str] = set()
    for fam in families:
        all_tokens |= set(fam_tokens.get(fam, {}))

    accepted: list[str] = []
    candidates: list[str] = []
    prov_rows: list[dict] = []
    prov_by_tok: dict[str, dict] = {}
    for tok in sorted(all_tokens):
        present = [fam for fam in families if tok in fam_tokens.get(fam, {})]
        n = len(present)
        decision, path = decide(tok, present, tok in green_atoms)
        examples = "; ".join(
            f"{fam}:{fam_tokens[fam][tok]}" for fam in present
        )[:400]
        row = {
            "token": tok,
            "length": str(len(tok)),
            "n_families": str(n),
            "source_families": "|".join(present),
            "accept_path": path,
            "example_labels": examples,
            "decision": decision,
            "on_denylist": "1" if tok in BROAD_DENYLIST else "0",
        }
        prov_rows.append(row)
        prov_by_tok[tok] = row
        if decision == "ACCEPT":
            accepted.append(tok)
        elif decision == "CANDIDATE":
            candidates.append(tok)

    accepted_set = set(accepted)

    # Deterministic singular/plural expansion of accepted tokens (so both
    # `agrivoltaics` and `agrivoltaic` resolve). Variants must still be clean.
    for tok in list(accepted_set):
        for var in variants_of(tok):
            if var in accepted_set or not is_clean(var):
                continue
            accepted_set.add(var)
            accepted.append(var)
            vrow = {
                "token": var,
                "length": str(len(var)),
                "n_families": prov_by_tok[tok]["n_families"],
                "source_families": prov_by_tok[tok]["source_families"],
                "accept_path": f"variant_of:{tok}",
                "example_labels": prov_by_tok[tok]["example_labels"],
                "decision": "ACCEPT",
                "on_denylist": "1" if var in BROAD_DENYLIST else "0",
            }
            prov_rows.append(vrow)
            prov_by_tok[var] = vrow
    prov_rows.sort(key=lambda r: r["token"])

    # ---- write lexicon (accepted only) ----
    with LEXICON_PATH.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["token", "n_families", "source_families", "accept_path"])
        for r in prov_rows:
            if r["decision"] == "ACCEPT":
                w.writerow([r["token"], r["n_families"], r["source_families"], r["accept_path"]])

    # ---- provenance (all tokens) ----
    with PROVENANCE_PATH.open("w", encoding="utf-8", newline="") as f:
        cols = [
            "token", "length", "n_families", "source_families", "accept_path",
            "example_labels", "decision", "on_denylist",
        ]
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(prov_rows)

    # ---- candidates for review ----
    with CANDIDATES_PATH.open("w", encoding="utf-8", newline="") as f:
        cols = ["token", "length", "n_families", "source_families", "example_labels"]
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in prov_rows:
            if r["decision"] == "CANDIDATE":
                w.writerow({k: r[k] for k in cols})

    # ---- multiword candidates (contain an accepted token) ----
    with MULTIWORD_PATH.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["phrase", "n_tokens", "first_family"])
        for phrase, fam in sorted(multiword.items()):
            toks = phrase.split()
            if any(t in accepted_set for t in toks):
                w.writerow([phrase, str(len(toks)), fam])

    # ---- build summary report ----
    by_path: dict[str, int] = {}
    for r in prov_rows:
        if r["decision"] == "ACCEPT":
            key = "variant_of" if r["accept_path"].startswith("variant_of") else r["accept_path"]
            by_path[key] = by_path.get(key, 0) + 1
    spot = ["solar", "photovoltaic", "wind", "geothermal", "biofuel", "biomass",
            "recycling", "wastewater", "hydrogen", "agrivoltaic", "agrivoltaics",
            "electrolysis", "compost", "reforestation"]

    prov_by_tok = {r["token"]: r for r in prov_rows}
    lines = []
    lines.append("STRONG_TERMS multi-source derivation report")
    lines.append("=" * 60)
    lines.append("")
    lines.append("Families and distinct clean-eligible tokens per family:")
    for fam in families:
        lines.append(f"  {fam:10s}: {len(fam_tokens.get(fam, {}))} tokens")
    lines.append("")
    lines.append(f"Accepted (ACCEPT)          : {len(accepted_set)}")
    lines.append(f"Candidates (single/under)  : {len(candidates)}")
    lines.append("Accepted by path:")
    for key in sorted(by_path):
        lines.append(f"  {key:12s}: {by_path[key]}")
    lines.append("")
    lines.append("Spot check of critical roots (decision | families):")
    for tok in spot:
        r = prov_by_tok.get(tok)
        if r:
            lines.append(f"  {tok:16s} {r['decision']:10s} n={r['n_families']} [{r['source_families']}]")
        else:
            lines.append(f"  {tok:16s} ABSENT from all sources")
    lines.append("")
    lines.append(f"ACCEPTED ({len(accepted_set)}): " + ", ".join(sorted(accepted_set)))
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print("\n".join(lines[:24]))
    print(f"\nWrote:\n  {LEXICON_PATH.relative_to(ROOT)}"
          f"\n  {PROVENANCE_PATH.relative_to(ROOT)}"
          f"\n  {CANDIDATES_PATH.relative_to(ROOT)}"
          f"\n  {MULTIWORD_PATH.relative_to(ROOT)}"
          f"\n  {REPORT_PATH.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
