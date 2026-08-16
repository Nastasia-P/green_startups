"""
Extract distinct multi-word PitchBook phrases that contain at least one
candidate-term token, then lexically reduce the list.

Reads candidate_terms.csv and scans Keywords + Description on the start-up
population. A phrase is kept only if it passes, in order:

  1. Structural constraints: 2-4 words, no digits, every word > 3 letters,
     after stopword-boundary trimming.
  2. Collocation gate: minimum adjacent-bigram log-likelihood (Dunning G2)
     over the corpus is >= COLLOC_G2_MIN. Keyword-sourced tags are curated and
     bypass this gate.
  3. POS gate: the phrase is a noun-phrase tag pattern (adjectives / nouns /
     gerunds ending in a noun).

Sources:
  - Keywords: comma-separated tags whose normalised tokens intersect the
    candidate-term set.
  - Description: contiguous 2-4 token windows that contain a candidate term.

Deduplicates on the normalised phrase and writes a hard-filtered CSV with
firm_count and min_bigram_g2 columns.
"""

from __future__ import annotations

import csv
import math
import os
import re
import sys
from collections import Counter
from pathlib import Path


def _ensure_sqlite3() -> None:
    """Guarantee a working sqlite3 before anything imports nltk.

    The turin024 python/3.12 module lacks the stdlib _sqlite3 extension, so a
    plain `import sqlite3` fails. nltk imports sqlite3 at package import time
    (via corpus.reader.panlex_lite); if that fails it poisons sys.modules with
    a half-initialised nltk. pysqlite3-binary supplies a drop-in replacement.
    This must run before importing derive_strong_terms (which imports nltk).
    """
    try:
        import sqlite3  # noqa: F401
    except ModuleNotFoundError:
        import pysqlite3
        import pysqlite3.dbapi2

        sys.modules["sqlite3"] = pysqlite3
        sys.modules["sqlite3.dbapi2"] = pysqlite3.dbapi2


_ensure_sqlite3()

from build_strict_vocabulary_full_audit_algorithmic import (  # noqa: E402
    normalise_phrase,
    set_csv_field_size_limit,
)
from derive_strong_terms import load_stopwords  # noqa: E402

ROOT = Path(__file__).resolve().parent
CANDIDATE_TERMS_PATH = ROOT / "data" / "outputs" / "candidate_terms.csv"
STARTUPS_PATH = ROOT / "startups_stages_filtered.csv"
OUTPUT_PATH = ROOT / "data" / "outputs" / "strong_term_phrases_non_climate.csv"
DESC_WINDOW_MIN = 2
DESC_WINDOW_MAX = 4
MIN_PHRASE_TOKENS = 2
MAX_PHRASE_TOKENS = 4
MIN_WORD_LEN = 4
DIGIT_RE = re.compile(r"\d")

COLLOC_G2_MIN = float(os.environ.get("COLLOC_G2_MIN", "10.83"))

# Green PitchBook verticals to exclude. Matched as exact comma-split, case-
# insensitive tags, mirroring classify_startups_green_algorithmic.py.
EXCLUDED_VERTICALS = {"climate tech", "cleantech"}

STOPWORDS = load_stopwords()


def has_excluded_vertical(raw: str) -> bool:
    return any(
        piece.strip().casefold() in EXCLUDED_VERTICALS
        for piece in (raw or "").split(",")
    )

# POS tags that may appear in a noun phrase, and the subset a noun phrase must
# end with. adjectives (JJ*), nouns (NN*), gerunds (VBG, e.g. "charging").
NP_ALLOWED_TAGS = {"JJ", "JJR", "JJS", "NN", "NNS", "NNP", "NNPS", "VBG"}
NP_HEAD_TAGS = {"NN", "NNS", "NNP", "NNPS"}


def load_candidate_terms(path: Path) -> frozenset[str]:
    terms: set[str] = set()
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if "token" not in (reader.fieldnames or []):
            raise ValueError(f"{path} missing 'token' column")
        for row in reader:
            tok = (row.get("token") or "").strip().casefold()
            if tok:
                terms.add(tok)
    return frozenset(terms)


def matched_terms(tokens: list[str], candidates: frozenset[str]) -> list[str]:
    return sorted({t for t in tokens if t in candidates})


def trim_boundary_stopwords(tokens: list[str]) -> list[str]:
    lo, hi = 0, len(tokens)
    while lo < hi and tokens[lo] in STOPWORDS:
        lo += 1
    while hi > lo and tokens[hi - 1] in STOPWORDS:
        hi -= 1
    return tokens[lo:hi]


def record_phrase(
    store: dict[str, dict],
    firm_phrases: set[str],
    phrase: str,
    hits: list[str],
    source: str,
) -> None:
    if not hits:
        return
    key0 = normalise_phrase(phrase)
    if not key0 or DIGIT_RE.search(key0):
        return
    tokens = trim_boundary_stopwords(key0.split())
    if not (MIN_PHRASE_TOKENS <= len(tokens) <= MAX_PHRASE_TOKENS):
        return
    if any(len(t) < MIN_WORD_LEN for t in tokens):
        return
    # A candidate term must survive boundary trimming.
    hit_set = set(hits)
    surviving = {t for t in tokens if t in hit_set}
    if not surviving:
        return
    key = " ".join(tokens)
    entry = store.get(key)
    if entry is None:
        store[key] = {
            "phrase": key,
            "matched_terms": set(surviving),
            "sources": {source},
            "n_tokens": len(tokens),
            "firm_count": 0,
        }
    else:
        entry["matched_terms"].update(surviving)
        entry["sources"].add(source)
    firm_phrases.add(key)


def extract_from_keywords(
    raw: str,
    candidates: frozenset[str],
    store: dict,
    firm_phrases: set[str],
    uni: Counter,
    bi: Counter,
) -> None:
    for piece in raw.split(","):
        surface = piece.strip()
        if not surface:
            continue
        norm = normalise_phrase(surface)
        if not norm:
            continue
        tokens = norm.split()
        uni.update(tokens)
        bi.update(zip(tokens, tokens[1:]))
        if len(tokens) < MIN_PHRASE_TOKENS:
            continue
        hits = matched_terms(tokens, candidates)
        record_phrase(store, firm_phrases, norm, hits, "keyword")


def extract_from_description(
    raw: str,
    candidates: frozenset[str],
    store: dict,
    firm_phrases: set[str],
    uni: Counter,
    bi: Counter,
) -> None:
    norm = normalise_phrase(raw)
    if not norm:
        return
    tokens = norm.split()
    uni.update(tokens)
    bi.update(zip(tokens, tokens[1:]))
    n = len(tokens)
    for width in range(DESC_WINDOW_MIN, DESC_WINDOW_MAX + 1):
        if n < width:
            continue
        for i in range(0, n - width + 1):
            window = tokens[i : i + width]
            hits = matched_terms(window, candidates)
            if hits:
                record_phrase(
                    store, firm_phrases, " ".join(window), hits, "description"
                )


def bigram_g2(c1: int, c2: int, c12: int, n: int) -> float:
    """Dunning log-likelihood (G2) for the bigram (w1, w2).

    c1  = corpus count of w1, c2 = corpus count of w2,
    c12 = corpus count of adjacent bigram (w1, w2), n = total tokens.
    """
    o11 = c12
    o12 = max(c1 - c12, 0)
    o21 = max(c2 - c12, 0)
    o22 = max(n - o11 - o12 - o21, 0)
    row1 = o11 + o12
    row2 = o21 + o22
    col1 = o11 + o21
    col2 = o12 + o22
    total = row1 + row2
    if total == 0:
        return 0.0
    ll = 0.0
    for obs, r, c in (
        (o11, row1, col1),
        (o12, row1, col2),
        (o21, row2, col1),
        (o22, row2, col2),
    ):
        if obs > 0:
            exp = r * c / total
            if exp > 0:
                ll += obs * math.log(obs / exp)
    return 2.0 * ll


def min_bigram_g2(tokens: list[str], uni: Counter, bi: Counter, n: int) -> float:
    scores = []
    for w1, w2 in zip(tokens, tokens[1:]):
        scores.append(bigram_g2(uni.get(w1, 0), uni.get(w2, 0), bi.get((w1, w2), 0), n))
    return min(scores) if scores else 0.0


def pos_keep(tagged: list[tuple[str, str]]) -> bool:
    if not tagged:
        return False
    tags = [t for _, t in tagged]
    if any(t not in NP_ALLOWED_TAGS for t in tags):
        return False
    return tags[-1] in NP_HEAD_TAGS


def _import_nltk():
    """Import nltk (sqlite3 is already provided by _ensure_sqlite3 at import)."""
    _ensure_sqlite3()
    import nltk

    return nltk


def _ensure_tagger(nltk) -> None:
    for res, pkgs in (
        ("taggers/averaged_perceptron_tagger_eng", ["averaged_perceptron_tagger_eng"]),
        ("taggers/averaged_perceptron_tagger", ["averaged_perceptron_tagger"]),
    ):
        try:
            nltk.data.find(res)
            return
        except LookupError:
            for pkg in pkgs:
                try:
                    if nltk.download(pkg, quiet=True):
                        return
                except Exception:
                    pass


def pos_filter(phrases: list[str]) -> set[str]:
    """Return the subset of phrases whose POS pattern is a noun phrase."""
    nltk = _import_nltk()
    _ensure_tagger(nltk)

    token_lists = [p.split() for p in phrases]
    tagged_lists = nltk.pos_tag_sents(token_lists)
    kept: set[str] = set()
    for phrase, tagged in zip(phrases, tagged_lists):
        if pos_keep(tagged):
            kept.add(phrase)
    return kept


def main() -> int:
    set_csv_field_size_limit()

    if not CANDIDATE_TERMS_PATH.exists():
        print(f"Missing candidate terms: {CANDIDATE_TERMS_PATH}", file=sys.stderr)
        return 1
    if not STARTUPS_PATH.exists():
        print(f"Missing startups CSV: {STARTUPS_PATH}", file=sys.stderr)
        return 1

    candidates = load_candidate_terms(CANDIDATE_TERMS_PATH)
    print(
        f"Loaded {len(candidates):,} candidate terms from "
        f"{CANDIDATE_TERMS_PATH.name}"
    )

    store: dict[str, dict] = {}
    uni: Counter = Counter()
    bi: Counter = Counter()
    firms = 0
    excluded = 0
    kw_nonempty = 0
    desc_nonempty = 0

    with STARTUPS_PATH.open("r", encoding="utf-8-sig", newline="") as fin:
        reader = csv.DictReader(fin)
        required = {"Keywords", "Description", "Verticals"}
        missing = required.difference(reader.fieldnames or [])
        if missing:
            raise ValueError(f"Start-up CSV missing columns: {sorted(missing)}")

        for row in reader:
            if has_excluded_vertical(row.get("Verticals") or ""):
                excluded += 1
                continue
            firms += 1
            raw_kw = row.get("Keywords") or ""
            raw_desc = row.get("Description") or ""
            firm_phrases: set[str] = set()
            if raw_kw.strip():
                kw_nonempty += 1
                extract_from_keywords(
                    raw_kw, candidates, store, firm_phrases, uni, bi
                )
            if raw_desc.strip():
                desc_nonempty += 1
                extract_from_description(
                    raw_desc, candidates, store, firm_phrases, uni, bi
                )
            for key in firm_phrases:
                store[key]["firm_count"] += 1

            if firms % 20_000 == 0:
                print(
                    f"Processed {firms:>7,} firms | unique phrases {len(store):,}",
                    flush=True,
                )

    n_tokens_total = sum(uni.values())
    raw_count = len(store)
    print(f"Corpus tokens: {n_tokens_total:,} | unique unigrams {len(uni):,} "
          f"| unique bigrams {len(bi):,}")
    print(f"Candidate phrases before lexical reduction: {raw_count:,}")

    # Filter 2: collocation gate (description-only phrases must pass).
    after_colloc: dict[str, dict] = {}
    for key, entry in store.items():
        tokens = key.split()
        g2 = min_bigram_g2(tokens, uni, bi, n_tokens_total)
        entry["min_bigram_g2"] = g2
        exempt = "keyword" in entry["sources"]
        if exempt or g2 >= COLLOC_G2_MIN:
            after_colloc[key] = entry
    print(
        f"After collocation gate (G2 >= {COLLOC_G2_MIN}): {len(after_colloc):,} "
        f"(removed {raw_count - len(after_colloc):,})"
    )

    # Filter 3: POS noun-phrase gate.
    kept_phrases = pos_filter(list(after_colloc.keys()))
    final = {k: after_colloc[k] for k in after_colloc if k in kept_phrases}
    print(
        f"After POS noun-phrase gate: {len(final):,} "
        f"(removed {len(after_colloc) - len(final):,})"
    )

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    rows = sorted(
        final.values(),
        key=lambda r: (-r["firm_count"], r["phrase"]),
    )
    with OUTPUT_PATH.open("w", encoding="utf-8", newline="") as fout:
        writer = csv.DictWriter(
            fout,
            fieldnames=[
                "phrase",
                "matched_terms",
                "sources",
                "n_tokens",
                "firm_count",
                "min_bigram_g2",
            ],
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "phrase": row["phrase"],
                    "matched_terms": "|".join(sorted(row["matched_terms"])),
                    "sources": "|".join(sorted(row["sources"])),
                    "n_tokens": row["n_tokens"],
                    "firm_count": row["firm_count"],
                    "min_bigram_g2": f"{row['min_bigram_g2']:.2f}",
                }
            )

    source_counts: Counter[str] = Counter()
    token_counts: Counter[int] = Counter()
    for row in rows:
        source_counts["|".join(sorted(row["sources"]))] += 1
        token_counts[row["n_tokens"]] += 1

    print(f"Firms scanned:          {firms:,}")
    print(f"Firms excluded (climate/cleantech vertical): {excluded:,}")
    print(f"Keywords non-empty:     {kw_nonempty:,}")
    print(f"Description non-empty:  {desc_nonempty:,}")
    print(f"Unique phrases written: {len(rows):,}")
    for src, n in sorted(source_counts.items()):
        print(f"  sources={src}: {n:,}")
    if token_counts:
        print(f"n_tokens min/max: {min(token_counts)} / {max(token_counts)}")
    print(f"Wrote {OUTPUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
