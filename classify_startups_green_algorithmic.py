"""
Firm-level green classification using the algorithmic STRICT_GREEN vocabulary.

A firm is StrictGreen = 1 when:
  A) an accepted expression appears as an exact comma-delimited PitchBook
     Keyword; OR
  B) an accepted expression appears as a controlled whole-phrase match in the
     Description; OR
  C) the firm carries a curated green PitchBook Vertical (CleanTech / Climate
     Tech), matched as an exact comma-split tag.

Matching is case-insensitive; Description punctuation/hyphens are token
boundaries. No stemming, fuzzy matching, semantic expansion, or firm-level
manual override. Operational environmental-relevance, not legal Taxonomy
alignment of individual companies.

Inputs
------
- startups_stages_filtered.csv                              (startup population)
- data/outputs/strict_green_vocabulary_full_audit_algorithmic.csv
      (decision == STRICT_GREEN rows only)

Outputs (data/outputs/)
-----------------------
- startups_to_green_startups_algorithmic.csv               (green firms only)
- startup_population_green_classification_algorithmic.csv  (full ledger)
- green_classification_algorithmic_report.txt             (summary)
"""

from __future__ import annotations

import csv
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parent
INPUT_PATH = ROOT / "startups_stages_filtered.csv"
OUTPUT_DIR = ROOT / "data" / "outputs"
VOCAB_PATH = OUTPUT_DIR / "strict_green_vocabulary_full_audit_algorithmic.csv"

GREEN_OUTPUT_PATH = OUTPUT_DIR / "startups_to_green_startups_algorithmic.csv"
LEDGER_OUTPUT_PATH = (
    OUTPUT_DIR / "startup_population_green_classification_algorithmic.csv"
)
REPORT_PATH = OUTPUT_DIR / "green_classification_algorithmic_report.txt"

EXPECTED_STARTUP_ROWS = 116_005
END = "__END__"

AUDIT_FIELDS = [
    "StrictGreen",
    "StrictGreenKeywordMatches",
    "StrictGreenDescriptionMatches",
    "StrictGreenVerticalMatches",
    "StrictGreenObjectives",
    "StrictGreenObjectiveCodes",
    "StrictGreenConcepts",
]

# Curated PitchBook Verticals treated as a standalone green signal. Analyst-
# assigned environmental taxonomy tags (not company self-declared keywords).
GREEN_VERTICALS: dict[str, dict] = {
    "cleantech": {
        "canonical": "CleanTech",
        "objective": "cross-sector clean technology (PitchBook vertical)",
        "concept": "cleantech vertical",
    },
    "climate tech": {
        "canonical": "Climate Tech",
        "objective": "1 Climate change mitigation",
        "concept": "climate tech vertical",
    },
}

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


def set_csv_field_size_limit() -> None:
    limit = sys.maxsize
    while True:
        try:
            csv.field_size_limit(limit)
            return
        except OverflowError:
            limit //= 10


def normalise_phrase(value: str) -> str:
    value = unicodedata.normalize("NFKC", value or "").casefold()
    value = re.sub(r"[^\w]+", " ", value, flags=re.UNICODE)
    value = re.sub(r"_+", " ", value)
    return " ".join(value.split())


def split_pipe(value: str) -> set[str]:
    return {item.strip() for item in (value or "").split("|") if item.strip()}


def load_vocabulary(path: Path) -> tuple[dict[str, dict], dict[str, str]]:
    """Load STRICT_GREEN rows -> (term metadata, canonical normalised map)."""
    if not path.exists():
        raise FileNotFoundError(f"Vocabulary file not found: {path}")

    metadata: dict[str, dict] = {}
    normalised_to_terms: dict[str, list[str]] = defaultdict(list)

    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        required = {
            "pitchbook_expression",
            "decision",
            "startup_keyword_frequency",
            "objectives",
            "objective_codes",
            "environmental_concepts",
        }
        missing = required.difference(reader.fieldnames or [])
        if missing:
            raise ValueError(f"Vocabulary missing required columns: {sorted(missing)}")

        for row in reader:
            if (row.get("decision") or "").strip() != "STRICT_GREEN":
                continue
            term = (row.get("pitchbook_expression") or "").strip().casefold()
            if not term:
                continue
            try:
                frequency = int(row.get("startup_keyword_frequency") or 0)
            except ValueError:
                frequency = 0
            metadata[term] = {
                "frequency": frequency,
                "objectives": split_pipe(row.get("objectives", "")),
                "objective_codes": split_pipe(row.get("objective_codes", "")),
                "concepts": split_pipe(row.get("environmental_concepts", "")),
            }
            normalised = normalise_phrase(term)
            if normalised:
                normalised_to_terms[normalised].append(term)

    canonical_normalised: dict[str, str] = {}
    for normalised, terms in normalised_to_terms.items():
        canonical_normalised[normalised] = sorted(
            terms,
            key=lambda t: (-metadata[t]["frequency"], len(t), t),
        )[0]

    return metadata, canonical_normalised


def build_trie(canonical_normalised: dict[str, str]) -> dict:
    trie: dict = {}
    for normalised_phrase, canonical_term in canonical_normalised.items():
        node = trie
        for token in normalised_phrase.split():
            node = node.setdefault(token, {})
        node.setdefault(END, []).append(canonical_term)
    return trie


def keyword_matches(text: str, vocabulary_terms: set[str]) -> list[str]:
    if not text:
        return []
    found = {
        piece.strip().casefold()
        for piece in text.split(",")
        if piece.strip().casefold() in vocabulary_terms
    }
    return sorted(found)


def vertical_matches(text: str) -> list[str]:
    if not text:
        return []
    found = {
        GREEN_VERTICALS[key]["canonical"]
        for piece in text.split(",")
        if (key := piece.strip().casefold()) in GREEN_VERTICALS
    }
    return sorted(found)


def description_matches(text: str, trie: dict) -> list[str]:
    if not text:
        return []
    tokens = normalise_phrase(text).split()
    found: set[str] = set()
    n_tokens = len(tokens)
    for i in range(n_tokens):
        node = trie.get(tokens[i])
        if node is None:
            continue
        if END in node:
            found.update(node[END])
        j = i + 1
        while j < n_tokens:
            next_node = node.get(tokens[j])
            if next_node is None:
                break
            node = next_node
            if END in node:
                found.update(node[END])
            j += 1
    return sorted(found)


def metadata_for_matches(
    matches: set[str], metadata: dict[str, dict]
) -> tuple[list[str], list[str], list[str]]:
    objectives: set[str] = set()
    objective_codes: set[str] = set()
    concepts: set[str] = set()
    for term in matches:
        meta = metadata[term]
        objectives.update(meta["objectives"])
        objective_codes.update(meta["objective_codes"])
        concepts.update(meta["concepts"])
    return sorted(objectives), sorted(objective_codes), sorted(concepts)


def main() -> None:
    set_csv_field_size_limit()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    if not INPUT_PATH.exists():
        raise FileNotFoundError(f"Start-up input not found: {INPUT_PATH}")

    metadata, canonical_normalised = load_vocabulary(VOCAB_PATH)
    vocabulary_terms = set(metadata)
    trie = build_trie(canonical_normalised)

    print("=" * 80)
    print("ALGORITHMIC GREEN START-UP CLASSIFICATION")
    print("=" * 80)
    print(f"Input:                {INPUT_PATH}")
    print(f"Vocabulary:           {VOCAB_PATH}")
    print(f"Accepted expressions: {len(vocabulary_terms):,}")
    print()

    total_rows = 0
    keyword_nonempty = 0
    description_nonempty = 0
    at_least_one_text = 0
    neither_text = 0

    strict_green_count = 0
    keyword_green_count = 0
    description_green_count = 0
    both_green_count = 0
    vertical_green_count = 0
    vertical_only_count = 0

    seen_ids: set[str] = set()
    duplicate_ids = 0

    objective_company_counts: Counter[str] = Counter()
    top_keyword_matches: Counter[str] = Counter()
    top_description_matches: Counter[str] = Counter()
    vertical_tag_counts: Counter[str] = Counter()

    with (
        INPUT_PATH.open("r", encoding="utf-8-sig", newline="") as fin,
        GREEN_OUTPUT_PATH.open("w", encoding="utf-8", newline="") as fgreen,
        LEDGER_OUTPUT_PATH.open("w", encoding="utf-8", newline="") as fledger,
    ):
        reader = csv.DictReader(fin)
        if reader.fieldnames is None:
            raise ValueError("Input CSV has no header.")
        required_input = {"CompanyID", "CompanyName", "Keywords", "Description"}
        missing = required_input.difference(reader.fieldnames)
        if missing:
            raise ValueError(f"Start-up input missing columns: {sorted(missing)}")

        green_fields = list(reader.fieldnames) + AUDIT_FIELDS
        green_writer = csv.DictWriter(fgreen, fieldnames=green_fields)
        green_writer.writeheader()

        ledger_base = [f for f in LEDGER_BASE_FIELDS if f in reader.fieldnames]
        ledger_fields = ledger_base + AUDIT_FIELDS
        ledger_writer = csv.DictWriter(fledger, fieldnames=ledger_fields)
        ledger_writer.writeheader()

        for row in reader:
            total_rows += 1
            cid = (row.get("CompanyID") or "").strip()
            if cid:
                if cid in seen_ids:
                    duplicate_ids += 1
                seen_ids.add(cid)

            raw_keywords = row.get("Keywords", "")
            raw_description = row.get("Description", "")
            has_keywords = bool(raw_keywords.strip())
            has_description = bool(raw_description.strip())
            if has_keywords:
                keyword_nonempty += 1
            if has_description:
                description_nonempty += 1
            if has_keywords or has_description:
                at_least_one_text += 1
            else:
                neither_text += 1

            kw = keyword_matches(raw_keywords, vocabulary_terms)
            desc = description_matches(raw_description, trie)
            verts = vertical_matches(row.get("Verticals", ""))
            all_matches = set(kw) | set(desc)
            is_green = bool(all_matches) or bool(verts)

            objectives_list, objective_codes, concepts_list = metadata_for_matches(
                all_matches, metadata
            )
            objectives = set(objectives_list)
            concepts = set(concepts_list)
            for tag in verts:
                info = GREEN_VERTICALS[tag.casefold()]
                objectives.add(info["objective"])
                concepts.add(info["concept"])

            audit = {
                "StrictGreen": "1" if is_green else "0",
                "StrictGreenKeywordMatches": " | ".join(kw),
                "StrictGreenDescriptionMatches": " | ".join(desc),
                "StrictGreenVerticalMatches": " | ".join(verts),
                "StrictGreenObjectives": " | ".join(sorted(objectives)),
                "StrictGreenObjectiveCodes": " | ".join(objective_codes),
                "StrictGreenConcepts": " | ".join(sorted(concepts)),
            }

            ledger_writer.writerow(
                {**{f: row.get(f, "") for f in ledger_base}, **audit}
            )

            if is_green:
                strict_green_count += 1
                if kw:
                    keyword_green_count += 1
                if desc:
                    description_green_count += 1
                if kw and desc:
                    both_green_count += 1
                if verts:
                    vertical_green_count += 1
                    if not all_matches:
                        vertical_only_count += 1
                for obj in objectives:
                    objective_company_counts[obj] += 1
                for term in kw:
                    top_keyword_matches[term] += 1
                for term in desc:
                    top_description_matches[term] += 1
                for tag in verts:
                    vertical_tag_counts[tag] += 1
                green_writer.writerow({**row, **audit})

            if total_rows % 20_000 == 0:
                print(
                    f"Processed {total_rows:>7,} firms | green {strict_green_count:,}",
                    flush=True,
                )

    report_lines = [
        "ALGORITHMIC GREEN START-UP CLASSIFICATION REPORT",
        f"input: {INPUT_PATH}",
        f"vocabulary: {VOCAB_PATH}",
        f"accepted_expressions: {len(vocabulary_terms)}",
        "",
        f"startups_processed: {total_rows}",
        f"  keywords_nonempty: {keyword_nonempty}",
        f"  description_nonempty: {description_nonempty}",
        f"  at_least_one_text: {at_least_one_text}",
        f"  neither_text: {neither_text}",
        f"  duplicate_company_ids: {duplicate_ids}",
        "",
        f"strict_green: {strict_green_count}",
        f"  keyword_signal_firms: {keyword_green_count}",
        f"  description_signal_firms: {description_green_count}",
        f"  both_text_signals: {both_green_count}",
        f"  vertical_signal_firms: {vertical_green_count}",
        f"  vertical_only_firms: {vertical_only_count}",
        "",
        "green vertical tag counts (green firms):",
    ]
    for tag, cnt in vertical_tag_counts.most_common():
        report_lines.append(f"  {cnt:>7}  {tag}")
    report_lines.append("")
    report_lines.append("green firms by environmental objective:")
    for obj, cnt in objective_company_counts.most_common():
        report_lines.append(f"  {cnt:>7}  {obj}")
    report_lines.append("")
    report_lines.append("top keyword-matched expressions (green firms):")
    for term, cnt in top_keyword_matches.most_common(20):
        report_lines.append(f"  {cnt:>7}  {term}")
    report_lines.append("")
    report_lines.append("top description-matched expressions (green firms):")
    for term, cnt in top_description_matches.most_common(20):
        report_lines.append(f"  {cnt:>7}  {term}")
    report_lines.extend(
        [
            "",
            f"green_sample_csv: {GREEN_OUTPUT_PATH}",
            f"ledger_csv: {LEDGER_OUTPUT_PATH}",
            "",
            "NOTE: Operational environmental-relevance; not legal Taxonomy alignment.",
        ]
    )
    if total_rows != EXPECTED_STARTUP_ROWS:
        report_lines.insert(
            6,
            f"  WARNING: expected {EXPECTED_STARTUP_ROWS} startup rows, got {total_rows}",
        )

    report = "\n".join(report_lines) + "\n"
    REPORT_PATH.write_text(report, encoding="utf-8")
    print()
    print(report)


if __name__ == "__main__":
    main()
