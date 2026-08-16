"""
Derive green-tech anchor tokens (STRONG_TERMS) from the regulatory corpus
instead of hand-curating them, and compare against the current hand-curated
list in build_strict_vocabulary_full_audit_algorithmic.py.

Method
------
1. Corpus 1 (regulatory) = the full extracted body text of every source in
   data/sources/text/*.txt. Count per-token term frequency and the number of
   distinct source documents each token appears in (doc frequency).
2. Corpus 2 (background) = the natural-language PitchBook Description field of
   every start-up. Using a real English register (not keyword tags) means
   ordinary words such as "against", "been" or "than" are common in BOTH
   corpora and therefore score LOW, unlike a keyword-only background.
3. Salience = signed log-likelihood keyness (G2) of each token's frequency in
   corpus 1 vs corpus 2. Keep tokens OVER-represented in the regulatory corpus
   (G2 >= G2_MIN, rate1 > rate2) that also clear frequency / doc-frequency
   floors.
4. Filters: comprehensive English stopword list, alphabetic + MIN_LEN, must
   appear in >= DOC_DF_MIN distinct source documents (kills single-document PDF
   artifacts), and subtract BROAD_DENYLIST objective/dual-use terms.
5. Emit per-token provenance CSV and a diff vs the current STRONG_TERMS.

Outputs (data/outputs/)
-----------------------
- strong_terms_provenance.csv
- strong_terms_derivation_report.txt
"""

from __future__ import annotations

import csv
import math
import os
import re
import sys
from collections import Counter
from pathlib import Path

from build_strict_vocabulary_full_audit_algorithmic import (
    BROAD_DENYLIST,
    STRONG_TERMS,
    normalise_phrase,
)

ROOT = Path(__file__).resolve().parent
SOURCE_TEXT_DIR = ROOT / "data" / "sources" / "text"
STARTUPS_PATH = ROOT / "startups_stages_filtered.csv"
OUTPUT_DIR = ROOT / "data" / "outputs"
PROVENANCE_PATH = OUTPUT_DIR / "strong_terms_provenance.csv"
REPORT_PATH = OUTPUT_DIR / "strong_terms_derivation_report.txt"

# Tunable thresholds (env-overridable for calibration).
MIN_LEN = int(os.environ.get("STRONG_MIN_LEN", "4"))
DOC_DF_MIN = int(os.environ.get("STRONG_DOC_DF_MIN", "2"))
MIN_C1 = int(os.environ.get("STRONG_MIN_C1", "5"))
G2_MIN = float(os.environ.get("STRONG_G2_MIN", "10.83"))  # p < 0.001, 1 dof

TOKEN_RE = re.compile(r"[a-z]+")


def load_stopwords() -> set[str]:
    """Comprehensive English stopword list; augmented with NLTK if available."""
    base = set(
        """
        a about above after again against all am an and any are aren't as at be
        because been before being below between both but by can cannot could
        couldn't did didn't do does doesn't doing don't down during each few for
        from further had hadn't has hasn't have haven't having he he'd he'll he's
        her here here's hers herself him himself his how how's i i'd i'll i'm
        i've if in into is isn't it it's its itself let's me more most mustn't my
        myself no nor not of off on once only or other ought our ours ourselves
        out over own same shan't she she'd she'll she's should shouldn't so some
        such than that that's the their theirs them themselves then there there's
        these they they'd they'll they're they've this those through to too under
        until up very was wasn't we we'd we'll we're we've were weren't what
        what's when when's where where's which while who who's whom why why's
        with won't would wouldn't you you'd you'll you're you've your yours
        yourself yourselves
        """.split()
    )
    # Legal / administrative / generic business & process vocabulary that is not
    # a green-tech root even when frequent in regulatory text.
    domain_stop = set(
        """
        shall may must article annex paragraph point subparagraph regulation
        directive decision commission parliament council union european member
        state states official journal referred accordance pursuant thereof
        hereby whereas recital provision provisions requirement requirements
        criteria criterion measure measures activity activities sector sectors
        area areas plan plans planning system systems service services product
        products technology technologies company companies platform based new
        high low general related including include included provision provided
        provides provide ensure ensures ensuring relevant specific specified
        specify apply applies applied application applicable comply complies
        compliance concerned appropriate necessary means method methods process
        processes model models data information design designs total national
        level levels stock share cost costs future existing subsequent operation
        operations operator operators production reduction where when whether
        which does contain contains containing involve involves takes take taken
        offer offered following another available associated best least been
        than there same more when place used using use identify identifying
        elements element instrument instruments bodies body purpose purposes
        conditions condition case cases part parts type types form forms setting
        set covered covering
        """.split()
    )
    stop = base | domain_stop
    try:
        from nltk.corpus import stopwords  # type: ignore

        stop |= set(stopwords.words("english"))
    except Exception:
        pass
    return stop


STOPWORDS = load_stopwords()


def tokenize(text: str) -> list[str]:
    return TOKEN_RE.findall(normalise_phrase(text))


def is_candidate(tok: str) -> bool:
    return len(tok) >= MIN_LEN and not tok.isdigit() and tok not in STOPWORDS


def g2_keyness(a: int, b: int, n1: int, n2: int) -> tuple[float, bool]:
    """Signed log-likelihood (G2). over1 True when over-represented in corpus 1."""
    if a == 0 and b == 0:
        return 0.0, False
    total = n1 + n2
    e1 = n1 * (a + b) / total
    e2 = n2 * (a + b) / total
    ll = 0.0
    if a > 0 and e1 > 0:
        ll += a * math.log(a / e1)
    if b > 0 and e2 > 0:
        ll += b * math.log(b / e2)
    g2 = 2.0 * ll
    over1 = (a / n1) > (b / n2) if n1 and n2 else False
    return g2, over1


def main() -> None:
    csv.field_size_limit(sys.maxsize)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    if not SOURCE_TEXT_DIR.is_dir():
        raise FileNotFoundError(f"Missing source text dir: {SOURCE_TEXT_DIR}")
    if not STARTUPS_PATH.exists():
        raise FileNotFoundError(f"Missing startups: {STARTUPS_PATH}")

    # Corpus 1: regulatory full text.
    corpus1: Counter[str] = Counter()
    doc_df: Counter[str] = Counter()
    doc_tokens_sample: dict[str, str] = {}
    n_docs = 0
    for txt in sorted(SOURCE_TEXT_DIR.glob("*.txt")):
        n_docs += 1
        toks = tokenize(txt.read_text(encoding="utf-8", errors="ignore"))
        corpus1.update(toks)
        for tok in set(toks):
            doc_df[tok] += 1
            doc_tokens_sample.setdefault(tok, txt.stem)

    # Corpus 2: background natural-language register (start-up Descriptions).
    corpus2: Counter[str] = Counter()
    with STARTUPS_PATH.open("r", encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            corpus2.update(tokenize(row.get("Description") or ""))

    n1 = sum(corpus1.values())
    n2 = sum(corpus2.values())

    rows: list[dict] = []
    derived: set[str] = set()
    for tok, c1 in corpus1.items():
        if not is_candidate(tok):
            continue
        c2 = int(corpus2.get(tok, 0))
        g2, over1 = g2_keyness(c1, c2, n1, n2)
        ddf = int(doc_df.get(tok, 0))
        in_denylist = tok in BROAD_DENYLIST
        reasons: list[str] = []
        if c1 < MIN_C1:
            reasons.append(f"c1<{MIN_C1}")
        if ddf < DOC_DF_MIN:
            reasons.append(f"docDF<{DOC_DF_MIN}")
        if not over1:
            reasons.append("under-represented")
        if g2 < G2_MIN:
            reasons.append(f"G2<{G2_MIN:g}")
        if in_denylist:
            reasons.append("denylist")
        accept = not reasons
        if accept:
            derived.add(tok)
        rows.append(
            {
                "token": tok,
                "corpus1_freq": c1,
                "corpus1_doc_df": ddf,
                "background_freq": c2,
                "keyness_g2": f"{g2:.2f}",
                "over_in_regulatory": "1" if over1 else "0",
                "in_denylist": "1" if in_denylist else "0",
                "in_original_strong_terms": "1" if tok in STRONG_TERMS else "0",
                "decision": "ACCEPT" if accept else "REJECT",
                "reject_reason": ";".join(reasons),
                "first_source": doc_tokens_sample.get(tok, ""),
            }
        )

    rows.sort(key=lambda r: (r["decision"] != "ACCEPT", -float(r["keyness_g2"])))

    with PROVENANCE_PATH.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "token",
                "corpus1_freq",
                "corpus1_doc_df",
                "background_freq",
                "keyness_g2",
                "over_in_regulatory",
                "in_denylist",
                "in_original_strong_terms",
                "decision",
                "reject_reason",
                "first_source",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)

    original = set(STRONG_TERMS)
    kept = sorted(derived & original)
    added = sorted(derived - original)
    dropped = sorted(original - derived)
    accepted_sorted = [r["token"] for r in rows if r["decision"] == "ACCEPT"]

    report = [
        "STRONG_TERMS DERIVATION REPORT (full-text corpus)",
        f"source_documents: {n_docs}",
        f"corpus1_tokens (regulatory): {n1}",
        f"corpus2_tokens (descriptions background): {n2}",
        f"candidate_types_in_corpus1: {sum(1 for t in corpus1 if is_candidate(t))}",
        f"stopwords: {len(STOPWORDS)}",
        f"thresholds: MIN_LEN={MIN_LEN} DOC_DF_MIN={DOC_DF_MIN} "
        f"MIN_C1={MIN_C1} G2_MIN={G2_MIN:g}",
        "",
        f"derived_strong_terms: {len(derived)}",
        f"original_strong_terms: {len(original)}",
        f"  kept (in both): {len(kept)}",
        f"  added (derived only): {len(added)}",
        f"  dropped (original only, not re-derived): {len(dropped)}",
        "",
        f"re_derivation_rate: {len(kept)}/{len(original)} "
        f"= {len(kept) / len(original):.0%}",
        "",
        "TOP 60 DERIVED BY KEYNESS:",
        "  " + ", ".join(accepted_sorted[:60]),
        "",
        "KEPT (re-derived from corpus):",
        "  " + ", ".join(kept),
        "",
        "ADDED (derived, not in original - review candidates):",
        "  " + ", ".join(added),
        "",
        "DROPPED (original, not re-derived; why each failed):",
    ]
    by_tok = {r["token"]: r for r in rows}
    for tok in dropped:
        r = by_tok.get(tok)
        reason = r["reject_reason"] if r else "absent from regulatory corpus"
        report.append(f"  {tok}: {reason or 'accepted?'}")
    report.extend(
        [
            "",
            f"provenance_csv: {PROVENANCE_PATH}",
            "",
            "NOTE: algorithm proposes; ADDED/DROPPED still need human review.",
        ]
    )
    text = "\n".join(report) + "\n"
    REPORT_PATH.write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
