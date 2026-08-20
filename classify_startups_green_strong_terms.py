"""
Sequential (cascading) green start-up classification.

Each firm is evaluated in a fixed order and captured by the FIRST stage that
fires; captured firms are removed from the pool and not re-evaluated:

  Stage 1  Vertical  -> firm carries a curated green PitchBook Vertical
                        (Climate Tech / CleanTech), exact comma-split tag.
  Stage 2  Token     -> a strong-term root (strong_terms_active.csv) appears as
                        a whole word in Keywords or Description.
  Stage 3  Phrase    -> a curated multi-word phrase (strong_term_phrases.csv)
                        appears as a contiguous whole phrase in Keywords or
                        Description.

Matching is case-insensitive and punctuation-insensitive (normalise_phrase);
no stemming, fuzzy matching, or semantic expansion.

Inputs
------
- startups_stages_filtered.csv                     (start-up population)
- data/outputs/strong_terms_active.csv             (single-token green roots)
- data/outputs/strong_term_phrases.csv             (curated multi-word phrases)

Outputs (data/outputs/)
-----------------------
- startups_to_green_startups_strong_terms.csv              (green firms only)
- startup_population_green_classification_strong_terms.csv (full ledger)
- green_classification_strong_terms_report.txt            (per-stage funnel)
"""

from __future__ import annotations

import csv
from collections import Counter
from pathlib import Path

from classify_startups_green_algorithmic import (
    GREEN_VERTICALS,
    build_trie,
    description_matches,
    normalise_phrase,
    set_csv_field_size_limit,
    vertical_matches,
)

ROOT = Path(__file__).resolve().parent
INPUT_PATH = ROOT / "startups_stages_filtered.csv"
OUTPUT_DIR = ROOT / "data" / "outputs"
TOKENS_PATH = OUTPUT_DIR / "strong_terms_active.csv"
PHRASES_PATH = OUTPUT_DIR / "strong_term_phrases.csv"

GREEN_OUTPUT_PATH = OUTPUT_DIR / "startups_to_green_startups_strong_terms.csv"
NON_GREEN_OUTPUT_PATH = (
    OUTPUT_DIR / "startups_to_nongreen_startups_strong_terms.csv"
)
LEDGER_OUTPUT_PATH = (
    OUTPUT_DIR / "startup_population_green_classification_strong_terms.csv"
)
REPORT_PATH = OUTPUT_DIR / "green_classification_strong_terms_report.txt"

AUDIT_FIELDS = [
    "Green",
    "GreenStage",
    "GreenVerticalMatches",
    "GreenTokenMatches",
    "GreenPhraseMatches",
]

LEDGER_BASE_FIELDS = [
    "CompanyID",
    "CompanyName",
    "Description",
    "Keywords",
    "PrimaryIndustrySector",
    "PrimaryIndustryGroup",
    "PrimaryIndustryCode",
    "Verticals",
    "HQCountry",
    "YearFounded",
    "age_years",
]


def load_strong_tokens(path: Path) -> frozenset[str]:
    """Normalised single-token green roots (column 0), one token per row."""
    if not path.exists():
        raise FileNotFoundError(f"Strong tokens file not found: {path}")
    tokens: set[str] = set()
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f)
        header = next(reader, None)  # skip 'token,...'
        for row in reader:
            if not row:
                continue
            norm = normalise_phrase(row[0])
            # A strong root is a single token; keep only the first token if the
            # normalised surface accidentally splits (defensive).
            parts = norm.split()
            if len(parts) == 1 and parts[0]:
                tokens.add(parts[0])
    return frozenset(tokens)


def load_strong_phrases(path: Path) -> dict[str, str]:
    """Normalised multi-word phrase -> canonical surface. Skip 1-token phrases
    (those are covered by the token stage)."""
    if not path.exists():
        raise FileNotFoundError(f"Strong phrases file not found: {path}")
    phrases: dict[str, str] = {}
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if "phrase" not in (reader.fieldnames or []):
            raise ValueError(f"{path} missing 'phrase' column")
        for row in reader:
            surface = (row.get("phrase") or "").strip()
            norm = normalise_phrase(surface)
            if len(norm.split()) < 2:
                continue
            phrases.setdefault(norm, norm)
    return phrases


def token_matches(keywords: str, description: str, tokens: frozenset[str]) -> list[str]:
    """Strong roots appearing as whole words in Keywords (per comma tag) or
    Description."""
    found: set[str] = set()
    for tag in (keywords or "").split(","):
        for tok in normalise_phrase(tag).split():
            if tok in tokens:
                found.add(tok)
    for tok in normalise_phrase(description).split():
        if tok in tokens:
            found.add(tok)
    return sorted(found)


def phrase_matches(keywords: str, description: str, trie: dict) -> list[str]:
    """Curated phrases appearing contiguously in Description or in any single
    comma-delimited Keyword tag (per-tag to avoid crossing tag boundaries)."""
    found: set[str] = set(description_matches(description, trie))
    for tag in (keywords or "").split(","):
        found.update(description_matches(tag, trie))
    return sorted(found)


def main() -> None:
    set_csv_field_size_limit()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    if not INPUT_PATH.exists():
        raise FileNotFoundError(f"Start-up input not found: {INPUT_PATH}")

    strong_tokens = load_strong_tokens(TOKENS_PATH)
    strong_phrases = load_strong_phrases(PHRASES_PATH)
    phrase_trie = build_trie({norm: norm for norm in strong_phrases})

    print("=" * 80)
    print("SEQUENTIAL GREEN START-UP CLASSIFICATION (vertical -> token -> phrase)")
    print("=" * 80)
    print(f"Input:            {INPUT_PATH}")
    print(f"Strong tokens:    {len(strong_tokens):,}  ({TOKENS_PATH.name})")
    print(f"Curated phrases:  {len(strong_phrases):,}  ({PHRASES_PATH.name})")
    print()

    total_rows = 0
    stage_new = Counter()  # vertical / token / phrase
    vertical_tag_counts: Counter[str] = Counter()
    token_counts: Counter[str] = Counter()
    phrase_counts: Counter[str] = Counter()

    with (
        INPUT_PATH.open("r", encoding="utf-8-sig", newline="") as fin,
        GREEN_OUTPUT_PATH.open("w", encoding="utf-8", newline="") as fgreen,
        NON_GREEN_OUTPUT_PATH.open("w", encoding="utf-8", newline="") as fnongreen,
        LEDGER_OUTPUT_PATH.open("w", encoding="utf-8", newline="") as fledger,
    ):
        reader = csv.DictReader(fin)
        if reader.fieldnames is None:
            raise ValueError("Input CSV has no header.")
        required = {"CompanyID", "CompanyName", "Keywords", "Description", "Verticals"}
        missing = required.difference(reader.fieldnames)
        if missing:
            raise ValueError(f"Start-up input missing columns: {sorted(missing)}")

        green_fields = list(reader.fieldnames) + AUDIT_FIELDS
        green_writer = csv.DictWriter(fgreen, fieldnames=green_fields)
        green_writer.writeheader()

        non_green_writer = csv.DictWriter(fnongreen, fieldnames=green_fields)
        non_green_writer.writeheader()

        ledger_base = [f for f in LEDGER_BASE_FIELDS if f in reader.fieldnames]
        ledger_writer = csv.DictWriter(fledger, fieldnames=ledger_base + AUDIT_FIELDS)
        ledger_writer.writeheader()

        for row in reader:
            total_rows += 1
            keywords = row.get("Keywords", "")
            description = row.get("Description", "")

            stage = "none"
            verts: list[str] = []
            toks: list[str] = []
            phrs: list[str] = []

            # Stage 1: vertical.
            verts = vertical_matches(row.get("Verticals", ""))
            if verts:
                stage = "vertical"
                for tag in verts:
                    vertical_tag_counts[tag] += 1
            else:
                # Stage 2: strong token (whole word).
                toks = token_matches(keywords, description, strong_tokens)
                if toks:
                    stage = "token"
                    for t in toks:
                        token_counts[t] += 1
                else:
                    # Stage 3: curated phrase.
                    phrs = phrase_matches(keywords, description, phrase_trie)
                    if phrs:
                        stage = "phrase"
                        for p in phrs:
                            phrase_counts[p] += 1

            is_green = stage != "none"
            if is_green:
                stage_new[stage] += 1

            audit = {
                "Green": "1" if is_green else "0",
                "GreenStage": stage,
                "GreenVerticalMatches": " | ".join(verts),
                "GreenTokenMatches": " | ".join(toks),
                "GreenPhraseMatches": " | ".join(phrs),
            }

            ledger_writer.writerow(
                {**{f: row.get(f, "") for f in ledger_base}, **audit}
            )
            if is_green:
                green_writer.writerow({**row, **audit})
            else:
                non_green_writer.writerow({**row, **audit})

            if total_rows % 20_000 == 0:
                cum = sum(stage_new.values())
                print(
                    f"Processed {total_rows:>7,} firms | green {cum:,}",
                    flush=True,
                )

    # Per-stage funnel.
    order = ["vertical", "token", "phrase"]
    labels = {
        "vertical": "Stage 1  Vertical (Climate Tech / CleanTech)",
        "token": "Stage 2  Strong token (whole word)",
        "phrase": "Stage 3  Curated phrase",
    }
    lines = [
        "SEQUENTIAL GREEN START-UP CLASSIFICATION REPORT",
        f"input: {INPUT_PATH}",
        f"strong_tokens: {len(strong_tokens)} ({TOKENS_PATH.name})",
        f"curated_phrases: {len(strong_phrases)} ({PHRASES_PATH.name})",
        "",
        f"startups_processed: {total_rows}",
        "",
        "FUNNEL (each firm attributed to the first stage that fires):",
    ]
    pool_in = total_rows
    cumulative = 0
    for key in order:
        new = stage_new[key]
        cumulative += new
        remaining = pool_in - new
        lines.append(f"  {labels[key]}")
        lines.append(f"    pool_in:         {pool_in}")
        lines.append(f"    new_green:       {new}")
        lines.append(f"    cumulative_green:{cumulative}")
        lines.append(f"    remaining:       {remaining}")
        pool_in = remaining
    lines.append("")
    lines.append(f"green_total: {cumulative}")
    lines.append(f"not_green: {pool_in}")

    lines.append("")
    lines.append("Stage 1 - vertical tag counts:")
    for tag, cnt in vertical_tag_counts.most_common():
        lines.append(f"  {cnt:>7}  {tag}")
    lines.append("")
    lines.append("Stage 2 - top strong tokens (by firms captured at this stage):")
    for tok, cnt in token_counts.most_common(30):
        lines.append(f"  {cnt:>7}  {tok}")
    lines.append("")
    lines.append("Stage 3 - top curated phrases (by firms captured at this stage):")
    for phr, cnt in phrase_counts.most_common(30):
        lines.append(f"  {cnt:>7}  {phr}")
    lines.extend(
        [
            "",
            f"green_csv: {GREEN_OUTPUT_PATH}",
            f"non_green_csv: {NON_GREEN_OUTPUT_PATH}",
            f"ledger_csv: {LEDGER_OUTPUT_PATH}",
        ]
    )

    report = "\n".join(lines) + "\n"
    REPORT_PATH.write_text(report, encoding="utf-8")
    print()
    print(report)


if __name__ == "__main__":
    main()
