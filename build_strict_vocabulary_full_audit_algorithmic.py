"""
Build the algorithmic green-vocabulary full-audit CSV.

Inputs
------
- startups_stages_filtered.csv  (Keywords + Description)
- data/sources/concept_seeds.csv (from scrape_environmental_sources.py)

Outputs
-------
- data/outputs/strict_green_vocabulary_full_audit_algorithmic.csv
- data/outputs/expression_field_evidence.csv
- data/outputs/vocabulary_algorithm_report.txt

Method (fully explicit)
-----------------------
1. Expression universe =
     (a) every distinct PitchBook Keywords token (casefold/trim), AND
     (b) every cleaned concept-seed phrase that appears as a controlled
         whole-phrase match in at least one Description.
2. Evidence: keyword-hit firms and description-hit firms per expression.
3. Seed cleaning: drop scraped seeds whose normalised form contains legal/admin
   noise fragments (member state, commission, article, etc.).
4. Decision rules (first match wins):
     - broad denylist (full expression) -> EXCLUDE / residual YES
     - exact seed match (+ specificity) -> STRICT_GREEN / STRICT_GREEN_EXACT_SEED
     - multi-token seed containment (trie) -> STRICT_GREEN / STRICT_GREEN_SEED_CONTAINED
     - curated green-tech anchor (compound or long single) ->
           STRICT_GREEN / STRICT_GREEN_GREEN_ANCHOR
     - curated green anchor lexicon (multi-token containment: electromobility,
           storage, water, emissions, ...) ->
           STRICT_GREEN / STRICT_GREEN_CURATED_ANCHOR
     - [optional, off by default] semantic similarity to green seeds with a
           contrastive margin vs non-green anchors ->
           STRICT_GREEN / STRICT_GREEN_SEMANTIC_SEED_SIMILARITY
     - else -> EXCLUDE / residual NO

Firm labeling against this vocabulary (Keywords OR Description) is a later step.
"""

from __future__ import annotations

import csv
import os
import re
import sys
import unicodedata
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parent
STARTUPS_PATH = ROOT / "startups_stages_filtered.csv"
SEEDS_PATH = ROOT / "data" / "sources" / "concept_seeds.csv"
OUTPUT_DIR = ROOT / "data" / "outputs"
AUDIT_PATH = OUTPUT_DIR / "strict_green_vocabulary_full_audit_algorithmic.csv"
EVIDENCE_PATH = OUTPUT_DIR / "expression_field_evidence.csv"
REPORT_PATH = OUTPUT_DIR / "vocabulary_algorithm_report.txt"
SIMILARITY_PATH = OUTPUT_DIR / "expression_semantic_similarity.csv"
SOURCE_TEXT_DIR = ROOT / "data" / "sources" / "text"
DENYLIST_PROVENANCE_PATH = OUTPUT_DIR / "denylist_provenance.csv"

# Optional semantic-similarity stage (unsupervised, source-grounded).
# Disabled by default: threshold calibration (see
# data/outputs/semantic_threshold_calibration.txt) found no operating point
# that beats the deterministic rule cascade on F1 at precision >= 0.70.
# Enable with SEMANTIC_ENABLED=1 to add STRICT_GREEN_SEMANTIC_SEED_SIMILARITY
# rows (higher recall, lower precision). Requires the similarity cache from
# build_semantic_similarity.py.
SEMANTIC_ENABLED = os.environ.get("SEMANTIC_ENABLED", "0") == "1"
SEMANTIC_DELTA = float(os.environ.get("SEMANTIC_DELTA", "0.40"))  # contrastive margin
SEMANTIC_GREEN_FLOOR = float(os.environ.get("SEMANTIC_GREEN_FLOOR", "0.35"))
SEMANTIC_MODEL_TAG = os.environ.get("SEMANTIC_MODEL_TAG", "all-MiniLM-L6-v2")

# ---------------------------------------------------------------------------
# Broad denylist, organised into four tiers with an explicit justification and
# primary-source citation per tier.
#
# Why the tiers are declared rather than inferred from the scrape: the seed
# metadata cannot separate organising concepts from specific activities. In
# concept_seeds.csv the `CONCEPT_HEADING` rule and the "organising" objective
# flag label BOTH the six statutory objectives AND specific technologies found
# in the same recitals (`renewable energy`, `carbon capture`, `water reuse`,
# `remanufacturing`). Inferring "deny" from those flags would reject the
# strongest true positives, so Tier A quotes the statutory list verbatim
# instead. Corpus presence/absence is then verified per term and exported to
# data/outputs/denylist_provenance.csv as auditable evidence.
# ---------------------------------------------------------------------------
DENYLIST_TIERS: dict[str, dict] = {
    "A_FRAMEWORK_OBJECTIVE_OR_PURPOSE": {
        "principle": (
            "Names an organising environmental objective/purpose, not a "
            "delineated economic activity. The frameworks are two-level: "
            "objectives/purposes classify WHY an activity is environmental, "
            "while annex activity titles define WHAT is done. A firm label "
            "equal to an objective states a goal, not an activity."
        ),
        "citation": (
            "Regulation (EU) 2020/852 Art. 9 (six environmental objectives); "
            "Eurostat Classification of Environmental Purposes (CEP) classes"
        ),
        "terms": (
            "biodiversity",
            "climate",
            "climate change",
            "energy",
            "waste management",
            "water management",
        ),
    },
    "B_DUAL_USE_OR_UNQUALIFIED": {
        "principle": (
            "Dual-use component, energy carrier, outcome metric or bare "
            "process noun. The frameworks admit these only inside a qualified "
            "activity subject to technical screening criteria and DNSH, never "
            "as a bare noun (a 'battery' firm may be consumer electronics). "
            "The qualified compound is admitted by the seed/anchor rules."
        ),
        "citation": (
            "Regulation (EU) 2020/852 Arts. 3 and 17 (screening criteria, "
            "do-no-significant-harm); Commission Delegated Regulation (EU) "
            "2021/2139 annex activity thresholds; Regulation (EU) 2024/1735 "
            "(NZIA) net-zero technology list"
        ),
        "terms": (
            "battery",
            "hydrogen",
            "charging",
            "carbon",
            "carbon footprint",
            "emissions",
            "renewable",
            "renewables",
            "recycling",
            "alternative",
            "alternatives",
        ),
    },
    "C_NO_SOURCE_REFERENT": {
        "principle": (
            "Self-declared marketing/ESG umbrella label with no delineated "
            "referent anywhere in the scraped framework corpus. Absence of a "
            "source-defined activity is the ground for exclusion; these are "
            "precisely the unsubstantiated claims the frameworks discipline."
        ),
        "citation": (
            "Regulation (EU) 2024/1781 (ESPR) and Regulation (EU) 2020/852 "
            "recitals on substantiating environmental claims; verified by "
            "absence from data/sources/concept_seeds.csv"
        ),
        "terms": (
            "sustainability",
            "sustainable",
            "esg",
            "environment",
            "environmental",
            "green",
            "greentech",
            "cleantech",
        ),
    },
    "D_EXTRACTION_BOILERPLATE": {
        "principle": (
            "Legislative/administrative boilerplate introduced by PDF text "
            "extraction, not business vocabulary. Same rationale as the "
            "NOISE_FRAGMENTS seed filter."
        ),
        "citation": "Artifact of scrape_environmental_sources.py text extraction",
        "terms": (
            "assets under management",
            "member state",
            "member states",
            "european commission",
            "european union",
            "official journal",
            "technical screening criteria",
            "delegated regulation",
            "delegated act",
            "financial guarantee",
            "research and development",
        ),
    },
}

BROAD_DENYLIST = {
    term for tier in DENYLIST_TIERS.values() for term in tier["terms"]
}

DENYLIST_TIER_OF = {
    term: tier_name
    for tier_name, tier in DENYLIST_TIERS.items()
    for term in tier["terms"]
}

# Legal/admin noise fragments: any scraped seed whose normalised form contains
# one of these substrings is dropped before matching.
NOISE_FRAGMENTS = (
    "member state",
    "commission",
    "article ",
    "assets under",
    "financial guarantee",
    "household",
    "housing financ",
    "data processing",
    "research and development",
    "delegated regulation",
    "delegated act",
    "technical screening",
    "official journal",
    "regulation eu",
    "directive",
    "paragraph",
    "annex ",
    "european parliament",
)

# Strong green-tech tokens. A compound expression (>=2 tokens) that contains one
# of these is STRICT_GREEN; long single tokens (>=6 chars) that are themselves
# strong terms and not on the denylist are also STRICT_GREEN.
#
# STRONG_TERMS_LEGACY is the original AI-hand-curated set, kept for auditability
# and as a fallback. The active STRONG_TERMS is loaded from the reproducible
# multi-source lexicon (strong_terms_v1.csv, produced by build_green_lexicon.py)
# when present; see STRONG_TERMS_PROTOCOL.md.
STRONG_TERMS_LEGACY = {
    "solar",
    "photovoltaic",
    "photovoltaics",
    "agrivoltaic",
    "agrivoltaics",
    "wind",
    "geothermal",
    "hydropower",
    "hydroelectric",
    "hydrogen",
    "biofuel",
    "biofuels",
    "biodiesel",
    "bioethanol",
    "biogas",
    "biomethane",
    "biomass",
    "bioenergy",
    "biochar",
    "electrolyser",
    "electrolyzer",
    "electrolysis",
    "heatpump",
    "microgrid",
    "recycling",
    "recycled",
    "recyclable",
    "upcycling",
    "compost",
    "composting",
    "remanufacturing",
    "refurbishment",
    "ecodesign",
    "wastewater",
    "desalination",
    "stormwater",
    "afforestation",
    "reforestation",
    "rewilding",
    "decarbonization",
    "decarbonisation",
    "biowaste",
    "pyrolysis",
    "photovoltaic",
    "electromobility",
}

# The reproducible pipeline (build_green_lexicon.py) writes strong_terms_v1.csv:
# the machine-generated ACCEPT pool with full provenance. That pool is high-recall
# but leaks generic/component tokens (single-token voting on multiword green
# labels), so it is NOT activated automatically. To promote a reviewed lexicon,
# copy the approved tokens into strong_terms_active.csv (see STRONG_TERMS_PROTOCOL.md
# adjudication step). Until then the frozen legacy set is used.
STRONG_TERMS_ACTIVE_PATH = OUTPUT_DIR / "strong_terms_active.csv"


def _load_strong_terms() -> frozenset[str]:
    """Load the reviewed/promoted lexicon; fall back to the legacy set.

    Reads strong_terms_active.csv (the human-reviewed, provenance-backed lexicon)
    when present and non-empty; otherwise uses the frozen legacy hand-curated set
    so the pipeline still runs deterministically.

    Denylist enforcement lives here, not in the source-only builder: any loaded
    token that equals a BROAD_DENYLIST term (dual-use/objective nouns such as
    `battery`, `energy`) is dropped so it can never act as a bare anchor. This is
    the safety net that lets the builder emit source candidates unfiltered.
    """
    if STRONG_TERMS_ACTIVE_PATH.exists():
        tokens: set[str] = set()
        with STRONG_TERMS_ACTIVE_PATH.open("r", encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f):
                tok = (row.get("token") or "").strip()
                if tok and tok not in BROAD_DENYLIST:
                    tokens.add(tok)
        if tokens:
            return frozenset(tokens)
    return frozenset(t for t in STRONG_TERMS_LEGACY if t not in BROAD_DENYLIST)


STRONG_TERMS = _load_strong_terms()

# Curated strong prefixes. Deliberately excludes bare `photo` / `hydro`
# (photography / hydraulics false positives in simulation).
STRONG_PREFIXES = (
    "solar",
    "photovolta",
    "agrivolta",
    "geotherm",
    "hydropower",
    "hydroelectric",
    "biofuel",
    "biogas",
    "biomethan",
    "biomass",
    "bioenerg",
    "biochar",
    "recycl",
    "compost",
    "electrolys",
    "afforest",
    "reforest",
    "decarbon",
    "wastewater",
    "desalin",
    "pyrolys",
    "anaerob",
    "rewild",
    "ecodesign",
    "remanufact",
    "refurbish",
    "microgrid",
    "upcycl",
)

# Curated multi-token green anchor lexicon (synonym-expansion, not a re-scrape).
# Matched by contiguous-token containment; each group is a hand-verified set of
# green compounds that regulatory seeds/strong-term anchors miss. Plural/variant
# spellings are listed directly (subsumes a separate seed->keyword synonym map).
# carbon/waste/renewable groups are curated down to drop FP-heavy phrases.
CURATED_GREEN_GROUPS: dict[str, tuple[str, ...]] = {
    "electromobility_storage": (
        "electric vehicle",
        "electric vehicles",
        "ev charging",
        "ev charger",
        "ev chargers",
        "ev charging station",
        "charging station",
        "charging stations",
        "charging infrastructure",
        "charging point",
        "vehicle charging",
        "energy storage",
        "energy storage system",
        "battery storage",
        "battery storage system",
        "battery energy storage",
        "heat pump",
        "heat pumps",
        "electric mobility",
        "electric car",
        "electric cars",
        "electric bike",
        "electric bikes",
        "electric scooter",
        "electric scooters",
    ),
    "energy_eff_mgmt": (
        "energy efficiency",
        "energy management",
        "energy management system",
        "energy optimization",
        "energy saving",
        "energy savings",
        "energy efficient",
    ),
    "water": (
        "water treatment",
        "water purification",
        "water monitoring",
        "water quality",
        "water reuse",
        "water recycling",
    ),
    "pollution_air": (
        "pollution control",
        "air quality",
        "air pollution",
    ),
    "circular": (
        "circular economy",
        "circular fashion",
        "reusable packaging",
    ),
    "emissions": (
        "emission reduction",
        "emissions reduction",
        "emission control",
        "emission tracking",
        "emission monitoring",
        "emissions monitoring",
        "emissions management",
    ),
    "carbon": (
        "carbon accounting",
        "carbon capture",
        "carbon capture and storage",
        "carbon removal",
        "carbon sequestration",
        "carbon dioxide removal",
        "carbon utilization",
    ),
    "waste": (
        "waste reduction",
        "waste treatment",
        "waste collection",
        "waste sorting",
        "waste recovery",
        "material recovery",
        "zero waste",
        "food waste reduction",
    ),
    "renewable_elec": (
        "renewable electricity",
        "renewable power",
    ),
    "alternative_energy_fuel": (
        "alternative energy",
        "alternative fuel",
        "alternative fuels",
    ),
}

# Minimum specificity for STRICT_GREEN when matched to a seed.
MIN_SEED_TOKENS = 2
MIN_SINGLE_TOKEN_CHARS = 8
# Single-token STRICT_GREEN only for long strong terms.
MIN_ANCHOR_SINGLE_TOKEN_CHARS = 6

AUDIT_FIELDS = [
    "pitchbook_expression",
    "startup_keyword_frequency",
    "decision",
    "residual_environmental_candidate",
    "decision_reason",
    "objectives",
    "objective_codes",
    "environmental_concepts",
    "official_framework_alignment_reference",
    "source_urls",
]

DENYLIST_PROVENANCE_FIELDS = [
    "expression",
    "tier",
    "principle",
    "citation",
    "in_concept_seeds",
    "in_source_corpus",
    "corpus_source_ids",
    "evidence_consistent_with_tier",
]

EVIDENCE_FIELDS = [
    "pitchbook_expression",
    "keyword_hit_firms",
    "description_hit_firms",
    "either_hit_firms",
    "in_keyword_universe",
    "in_seed_universe",
    "semantic_similarity",
    "semantic_margin",
]

END = "__END__"


def normalise_phrase(value: str) -> str:
    value = unicodedata.normalize("NFKC", value or "").casefold()
    value = re.sub(r"[^\w]+", " ", value, flags=re.UNICODE)
    value = re.sub(r"_+", " ", value)
    return " ".join(value.split())


def set_csv_field_size_limit() -> None:
    limit = sys.maxsize
    while True:
        try:
            csv.field_size_limit(limit)
            return
        except OverflowError:
            limit //= 10


def is_noise_seed(norm: str) -> bool:
    padded = f" {norm} "
    for frag in NOISE_FRAGMENTS:
        if frag in norm or frag in padded:
            return True
    return False


def load_seeds(path: Path) -> dict[str, dict]:
    """Map cleaned normalised_phrase -> best seed metadata (prefer longer)."""
    best: dict[str, dict] = {}
    dropped = 0
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            norm = (row.get("normalised_phrase") or "").strip()
            if not norm:
                norm = normalise_phrase(row.get("seed_phrase") or "")
            if not norm:
                continue
            if is_noise_seed(norm):
                dropped += 1
                continue
            phrase = (row.get("seed_phrase") or "").strip() or norm
            candidate = {
                "seed_phrase": phrase,
                "normalised_phrase": norm,
                "source_id": row.get("source_id", ""),
                "source_url": row.get("source_url", ""),
                "objective_guess": row.get("objective_guess", ""),
                "extraction_rule": row.get("extraction_rule", ""),
                "excerpt": row.get("excerpt", ""),
            }
            prev = best.get(norm)
            if prev is None or len(phrase) > len(prev["seed_phrase"]):
                best[norm] = candidate
    load_seeds.dropped_noise = dropped  # type: ignore[attr-defined]
    return best


def load_similarity_cache(path: Path) -> dict[str, dict]:
    """Map expression (casefold) -> semantic scores + nearest-seed metadata."""
    cache: dict[str, dict] = {}
    if not path.exists():
        return cache
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            expr = (row.get("pitchbook_expression") or "").strip().casefold()
            if not expr:
                continue
            try:
                gsim = float(row.get("similarity") or 0.0)
            except ValueError:
                gsim = 0.0
            try:
                margin = float(row.get("margin") or 0.0)
            except ValueError:
                margin = 0.0
            cache[expr] = {
                "similarity": gsim,
                "margin": margin,
                "nearest_seed_phrase": row.get("nearest_seed_phrase", ""),
                "nearest_source_url": row.get("nearest_source_url", ""),
                "nearest_objective": row.get("nearest_objective", ""),
            }
    return cache


def build_seed_trie(seed_norms: set[str]) -> dict:
    """Trie over multi-token seeds; END node stores the seed norm string."""
    trie: dict = {}
    for phrase in seed_norms:
        tokens = phrase.split()
        if len(tokens) < 2:
            continue
        node = trie
        for token in tokens:
            node = node.setdefault(token, {})
        node[END] = phrase
    return trie


def longest_seed_in_tokens(tokens: list[str], trie: dict) -> str | None:
    """Return the longest multi-token seed contained as a contiguous run."""
    best: str | None = None
    best_len = 0
    n = len(tokens)
    for i in range(n):
        node = trie
        for j in range(i, n):
            token = tokens[j]
            if token not in node:
                break
            node = node[token]
            if END in node:
                length = j - i + 1
                if length > best_len:
                    best_len = length
                    best = node[END]
    return best


def write_denylist_provenance(seeds: dict[str, dict], path: Path) -> Counter:
    """Export per-term denylist justification + machine-checked corpus evidence.

    Evidence rules:
      - Tiers A/B assert the term IS framework vocabulary -> expect a corpus hit.
      - Tier C asserts the term has NO framework referent -> expect no seed hit.
      - Tier D is an extraction artifact, so corpus presence is expected and
        carries no weight either way.
    """
    corpus: dict[str, str] = {}
    if SOURCE_TEXT_DIR.is_dir():
        for txt in sorted(SOURCE_TEXT_DIR.glob("*.txt")):
            try:
                corpus[txt.stem] = normalise_phrase(
                    txt.read_text(encoding="utf-8", errors="ignore")
                )
            except OSError:
                continue

    tier_counts: Counter = Counter()
    rows: list[dict[str, str]] = []
    for tier_name, tier in DENYLIST_TIERS.items():
        for term in tier["terms"]:
            tier_counts[tier_name] += 1
            padded = f" {term} "
            hits = [sid for sid, text in corpus.items() if padded in f" {text} "]
            in_seeds = term in seeds
            if tier_name.startswith(("A_", "B_")):
                consistent = bool(hits) or in_seeds
            elif tier_name.startswith("C_"):
                consistent = not in_seeds
            else:
                consistent = True
            rows.append(
                {
                    "expression": term,
                    "tier": tier_name,
                    "principle": tier["principle"],
                    "citation": tier["citation"],
                    "in_concept_seeds": "1" if in_seeds else "0",
                    "in_source_corpus": "1" if hits else "0",
                    "corpus_source_ids": " | ".join(hits[:6]),
                    "evidence_consistent_with_tier": "1" if consistent else "0",
                }
            )

    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=DENYLIST_PROVENANCE_FIELDS)
        writer.writeheader()
        writer.writerows(rows)

    write_denylist_provenance.rows = rows  # type: ignore[attr-defined]
    return tier_counts


def build_curated_index() -> tuple[dict, dict[str, str]]:
    """Build a containment trie + phrase->group map from CURATED_GREEN_GROUPS."""
    trie: dict = {}
    phrase_group: dict[str, str] = {}
    for group, phrases in CURATED_GREEN_GROUPS.items():
        for phrase in phrases:
            norm = normalise_phrase(phrase)
            tokens = norm.split()
            if not tokens:
                continue
            phrase_group.setdefault(norm, group)
            node = trie
            for token in tokens:
                node = node.setdefault(token, {})
            node[END] = norm
    return trie, phrase_group


CURATED_TRIE, CURATED_PHRASE_GROUP = build_curated_index()


def longest_curated_in_tokens(tokens: list[str]) -> str | None:
    """Return the longest curated green phrase contained as a contiguous run."""
    return longest_seed_in_tokens(tokens, CURATED_TRIE)


def find_desc_seed_hits(text: str, trie: dict) -> set[str]:
    """Return multi-token seed norms matched as complete runs in Description."""
    if not text or not trie:
        return set()
    tokens = normalise_phrase(text).split()
    found: set[str] = set()
    n = len(tokens)
    for i in range(n):
        node = trie
        for j in range(i, n):
            token = tokens[j]
            if token not in node:
                break
            node = node[token]
            if END in node:
                found.add(node[END])
    return found


def passes_specificity(norm: str) -> bool:
    tokens = norm.split()
    if len(tokens) >= MIN_SEED_TOKENS:
        return True
    if len(tokens) == 1 and len(tokens[0]) >= MIN_SINGLE_TOKEN_CHARS:
        return True
    return False


def anchor_hit(tokens: list[str]) -> str | None:
    """Return the anchor token that qualifies the expression, or None.

    - Compound (>=2 tokens): any token that is a STRONG_TERM or starts with a
      STRONG_PREFIX.
    - Single token: only long strong terms (>= MIN_ANCHOR_SINGLE_TOKEN_CHARS).
    """
    if not tokens:
        return None
    if len(tokens) >= 2:
        for tok in tokens:
            if tok in STRONG_TERMS:
                return tok
            for pref in STRONG_PREFIXES:
                if tok.startswith(pref):
                    return tok
        return None
    tok = tokens[0]
    if tok in STRONG_TERMS and len(tok) >= MIN_ANCHOR_SINGLE_TOKEN_CHARS:
        return tok
    for pref in STRONG_PREFIXES:
        if tok.startswith(pref) and len(tok) >= MIN_ANCHOR_SINGLE_TOKEN_CHARS:
            return tok
    return None


def _seed_strict_row(seed: dict, expression: str, reason: str) -> dict[str, str]:
    objective = (seed.get("objective_guess") or "").strip()
    concept = (seed.get("seed_phrase") or expression).strip()
    source_id = seed.get("source_id") or ""
    source_url = seed.get("source_url") or ""
    rule = seed.get("extraction_rule") or ""
    return {
        "decision": "STRICT_GREEN",
        "residual_environmental_candidate": "NO",
        "decision_reason": reason,
        "objectives": objective,
        "objective_codes": "",
        "environmental_concepts": concept,
        "official_framework_alignment_reference": (
            f"{source_id} / {rule}" if source_id or rule else ""
        ),
        "source_urls": source_url,
    }


def decide(
    expression: str,
    norm: str,
    seeds: dict[str, dict],
    seed_trie: dict,
    semantic: dict | None = None,
) -> dict[str, str]:
    """Apply explicit decision rules (first match wins)."""
    tokens = norm.split()

    # 1. Broad denylist on the full expression.
    if norm in BROAD_DENYLIST or expression in BROAD_DENYLIST:
        tier = DENYLIST_TIER_OF.get(norm) or DENYLIST_TIER_OF.get(expression, "")
        return {
            "decision": "EXCLUDE",
            "residual_environmental_candidate": "YES",
            "decision_reason": "ENVIRONMENTAL_CANDIDATE_NOT_SPECIFIC_ENOUGH",
            "objectives": "",
            "objective_codes": "",
            "environmental_concepts": "",
            "official_framework_alignment_reference": (
                f"denylist tier {tier}" if tier else ""
            ),
            "source_urls": "",
        }

    # 2. Exact seed match.
    seed = seeds.get(norm)
    if seed is not None and passes_specificity(norm):
        return _seed_strict_row(seed, expression, "STRICT_GREEN_EXACT_SEED")

    # 3. Multi-token seed containment (contiguous run in the expression).
    contained = longest_seed_in_tokens(tokens, seed_trie)
    if contained is not None:
        cseed = seeds.get(contained, seed or {})
        return _seed_strict_row(cseed, expression, "STRICT_GREEN_SEED_CONTAINED")

    # 4. Strong-term / prefix anchor.
    anchor = anchor_hit(tokens)
    if anchor is not None:
        return {
            "decision": "STRICT_GREEN",
            "residual_environmental_candidate": "NO",
            "decision_reason": "STRICT_GREEN_GREEN_ANCHOR",
            "objectives": "",
            "objective_codes": "",
            "environmental_concepts": anchor,
            "official_framework_alignment_reference": "curated green-tech anchor lexicon",
            "source_urls": "",
        }

    # 5. Curated green anchor lexicon (multi-token containment).
    curated = longest_curated_in_tokens(tokens)
    if curated is not None:
        group = CURATED_PHRASE_GROUP.get(curated, "curated")
        return {
            "decision": "STRICT_GREEN",
            "residual_environmental_candidate": "NO",
            "decision_reason": "STRICT_GREEN_CURATED_ANCHOR",
            "objectives": "",
            "objective_codes": "",
            "environmental_concepts": curated,
            "official_framework_alignment_reference": (
                f"curated green anchor ({group})"
            ),
            "source_urls": "",
        }

    # 6. Optional semantic similarity (unsupervised, source-grounded).
    if SEMANTIC_ENABLED and semantic is not None and passes_specificity(norm):
        if (
            semantic.get("similarity", 0.0) >= SEMANTIC_GREEN_FLOOR
            and semantic.get("margin", 0.0) >= SEMANTIC_DELTA
        ):
            nearest = (semantic.get("nearest_seed_phrase") or expression).strip()
            return {
                "decision": "STRICT_GREEN",
                "residual_environmental_candidate": "NO",
                "decision_reason": "STRICT_GREEN_SEMANTIC_SEED_SIMILARITY",
                "objectives": (semantic.get("nearest_objective") or "").strip(),
                "objective_codes": "",
                "environmental_concepts": nearest,
                "official_framework_alignment_reference": (
                    f"semantic:{SEMANTIC_MODEL_TAG} "
                    f"sim={semantic.get('similarity', 0.0):.3f} "
                    f"margin={semantic.get('margin', 0.0):.3f}"
                ),
                "source_urls": semantic.get("nearest_source_url") or "",
            }

    # 7. Weak seed (single short token) -> residual candidate.
    if seed is not None:
        return {
            "decision": "EXCLUDE",
            "residual_environmental_candidate": "YES",
            "decision_reason": "ENVIRONMENTAL_CANDIDATE_NOT_SPECIFIC_ENOUGH",
            "objectives": "",
            "objective_codes": "",
            "environmental_concepts": "",
            "official_framework_alignment_reference": "",
            "source_urls": seed.get("source_url") or "",
        }

    # 8. No signal.
    return {
        "decision": "EXCLUDE",
        "residual_environmental_candidate": "NO",
        "decision_reason": "NO_SOURCE_INFORMED_ENVIRONMENTAL_SIGNAL",
        "objectives": "",
        "objective_codes": "",
        "environmental_concepts": "",
        "official_framework_alignment_reference": "",
        "source_urls": "",
    }


def main() -> None:
    set_csv_field_size_limit()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    if not STARTUPS_PATH.exists():
        raise FileNotFoundError(f"Missing start-up file: {STARTUPS_PATH}")
    if not SEEDS_PATH.exists():
        raise FileNotFoundError(f"Missing concept seeds: {SEEDS_PATH}")

    seeds = load_seeds(SEEDS_PATH)
    dropped_noise = getattr(load_seeds, "dropped_noise", 0)
    seed_norms = set(seeds)
    seed_trie = build_seed_trie(seed_norms)

    denylist_tier_counts = write_denylist_provenance(seeds, DENYLIST_PROVENANCE_PATH)
    denylist_rows = getattr(write_denylist_provenance, "rows", [])
    denylist_inconsistent = [
        r["expression"]
        for r in denylist_rows
        if r["evidence_consistent_with_tier"] == "0"
    ]

    semantic_cache: dict[str, dict] = {}
    if SEMANTIC_ENABLED:
        semantic_cache = load_similarity_cache(SIMILARITY_PATH)
        if not semantic_cache:
            print(
                f"WARNING: SEMANTIC_ENABLED but no cache at {SIMILARITY_PATH}; "
                "run build_semantic_similarity.py first. Continuing rule-only.",
                flush=True,
            )

    print("=" * 72)
    print("ALGORITHMIC FULL-AUDIT BUILDER")
    print("=" * 72)
    print(f"Start-ups: {STARTUPS_PATH}")
    print(
        f"Seeds:     {SEEDS_PATH} ({len(seeds):,} cleaned unique; "
        f"{dropped_noise:,} noise dropped)"
    )
    if SEMANTIC_ENABLED:
        print(
            f"Semantic:  ENABLED ({SEMANTIC_MODEL_TAG}, "
            f"delta>={SEMANTIC_DELTA}, green_floor>={SEMANTIC_GREEN_FLOOR}, "
            f"cache rows {len(semantic_cache):,})"
        )
    else:
        print("Semantic:  disabled (rule-only baseline)")
    print()

    keyword_freq: Counter[str] = Counter()
    keyword_firms: Counter[str] = Counter()
    description_firms: Counter[str] = Counter()
    firms_processed = 0
    keyword_nonempty = 0
    description_nonempty = 0

    with STARTUPS_PATH.open("r", encoding="utf-8-sig", newline="") as fin:
        reader = csv.DictReader(fin)
        required = {"Keywords", "Description"}
        missing = required.difference(reader.fieldnames or [])
        if missing:
            raise ValueError(f"Start-up CSV missing columns: {sorted(missing)}")

        for row in reader:
            firms_processed += 1
            raw_kw = row.get("Keywords") or ""
            raw_desc = row.get("Description") or ""

            if raw_kw.strip():
                keyword_nonempty += 1
            if raw_desc.strip():
                description_nonempty += 1

            seen_kw: set[str] = set()
            for piece in raw_kw.split(","):
                term = piece.strip().casefold()
                if not term:
                    continue
                keyword_freq[term] += 1
                seen_kw.add(term)
            for term in seen_kw:
                keyword_firms[term] += 1

            desc_hits = find_desc_seed_hits(raw_desc, seed_trie)
            for norm in desc_hits:
                description_firms[norm] += 1

            if firms_processed % 20_000 == 0:
                print(
                    f"Processed {firms_processed:>7,} firms | "
                    f"keyword exprs {len(keyword_freq):,} | "
                    f"desc-seed hits {len(description_firms):,}",
                    flush=True,
                )

    universe: dict[str, str] = {}
    for term, _freq in keyword_freq.items():
        universe[term] = normalise_phrase(term) or term

    for norm in description_firms:
        seed = seeds.get(norm)
        if seed is None:
            continue
        expr = (seed.get("seed_phrase") or norm).strip().casefold()
        if expr not in universe:
            universe[expr] = norm

    audit_rows: list[dict[str, str]] = []
    evidence_rows: list[dict[str, str]] = []
    decision_counts: Counter[str] = Counter()
    reason_counts: Counter[str] = Counter()
    curated_group_counts: Counter[str] = Counter()

    for expression in sorted(universe):
        norm = universe[expression]
        kw_hits = int(keyword_firms.get(expression, 0))
        desc_hits = int(description_firms.get(norm, 0))
        either_approx = (
            max(kw_hits, desc_hits)
            if not (kw_hits and desc_hits)
            else kw_hits + desc_hits
        )

        sem = semantic_cache.get(expression)
        decision = decide(expression, norm, seeds, seed_trie, sem)
        decision_counts[decision["decision"]] += 1
        reason_counts[decision["decision_reason"]] += 1
        if decision["decision_reason"] == "STRICT_GREEN_CURATED_ANCHOR":
            grp = CURATED_PHRASE_GROUP.get(
                decision["environmental_concepts"], "curated"
            )
            curated_group_counts[grp] += 1

        freq = int(keyword_freq.get(expression, 0))
        audit_rows.append(
            {
                "pitchbook_expression": expression,
                "startup_keyword_frequency": str(freq),
                **decision,
            }
        )
        evidence_rows.append(
            {
                "pitchbook_expression": expression,
                "keyword_hit_firms": str(kw_hits),
                "description_hit_firms": str(desc_hits),
                "either_hit_firms": str(either_approx),
                "in_keyword_universe": "1" if expression in keyword_freq else "0",
                "in_seed_universe": "1" if norm in seeds else "0",
                "semantic_similarity": (
                    f"{sem['similarity']:.4f}" if sem else ""
                ),
                "semantic_margin": (f"{sem['margin']:.4f}" if sem else ""),
            }
        )

    with AUDIT_PATH.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=AUDIT_FIELDS)
        writer.writeheader()
        writer.writerows(audit_rows)

    with EVIDENCE_PATH.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=EVIDENCE_FIELDS)
        writer.writeheader()
        writer.writerows(evidence_rows)

    strict_n = decision_counts.get("STRICT_GREEN", 0)
    exclude_n = decision_counts.get("EXCLUDE", 0)
    residual_yes = sum(
        1 for r in audit_rows if r["residual_environmental_candidate"] == "YES"
    )
    desc_only = sum(
        1
        for r in evidence_rows
        if r["in_keyword_universe"] == "0" and int(r["description_hit_firms"]) > 0
    )
    kw_and_seed = sum(
        1
        for r in evidence_rows
        if r["in_keyword_universe"] == "1" and r["in_seed_universe"] == "1"
    )

    report_lines = [
        "ALGORITHMIC VOCABULARY AUDIT REPORT",
        f"firms_processed: {firms_processed}",
        f"keywords_nonempty_firms: {keyword_nonempty}",
        f"description_nonempty_firms: {description_nonempty}",
        f"concept_seeds_cleaned_unique: {len(seeds)}",
        f"concept_seeds_dropped_noise: {dropped_noise}",
        (
            f"semantic_stage: ENABLED {SEMANTIC_MODEL_TAG} "
            f"delta>={SEMANTIC_DELTA} green_floor>={SEMANTIC_GREEN_FLOOR}"
            if SEMANTIC_ENABLED
            else "semantic_stage: disabled (rule-only baseline)"
        ),
        f"universe_rows: {len(audit_rows)}",
        f"  keyword_origin_exprs: {len(keyword_freq)}",
        f"  description_only_seed_exprs: {desc_only}",
        f"  keyword_exprs_matching_a_seed: {kw_and_seed}",
        "",
        "decisions:",
        f"  STRICT_GREEN: {strict_n}",
        f"  EXCLUDE: {exclude_n}",
        f"  residual_YES: {residual_yes}",
        "",
        "decision_reason counts:",
    ]
    for reason, cnt in reason_counts.most_common():
        report_lines.append(f"  {cnt:>8}  {reason}")
    if curated_group_counts:
        report_lines.append("")
        report_lines.append("curated_anchor STRICT_GREEN by group:")
        for grp, cnt in curated_group_counts.most_common():
            report_lines.append(f"  {cnt:>8}  {grp}")

    report_lines.append("")
    report_lines.append(
        f"denylist terms by justification tier (total {len(BROAD_DENYLIST)}):"
    )
    for tier_name, cnt in sorted(denylist_tier_counts.items()):
        report_lines.append(f"  {cnt:>8}  {tier_name}")
    report_lines.append(
        "  corpus-evidence inconsistencies: "
        + (", ".join(denylist_inconsistent) if denylist_inconsistent else "none")
    )
    report_lines.append(f"  provenance_csv: {DENYLIST_PROVENANCE_PATH}")
    report_lines.extend(
        [
            "",
            f"audit_csv: {AUDIT_PATH}",
            f"evidence_csv: {EVIDENCE_PATH}",
            "",
            "NOTE: Operational source-seed grounding; not legal Taxonomy firm alignment.",
        ]
    )
    report = "\n".join(report_lines) + "\n"
    REPORT_PATH.write_text(report, encoding="utf-8")
    print()
    print(report)


if __name__ == "__main__":
    main()
