"""Configuration for Step 9 (keyword-recovery robustness diagnostic).

Self-contained: every input path, the output directory, the acceptance anchors,
and the small vocabulary bookkeeping all live here, so the module can be read and
run without opening another document.

All inputs are overridable so a custom location can be pointed at without editing
code. Resolution order for each input (first usable wins), highest priority last
applied by ``build.main`` via CLI flags:

    CLI flag  >  env var  >  repo/OneDrive defaults below
"""

from __future__ import annotations

import os
from pathlib import Path

# Repository root: step9_keyword_recovery/config.py -> package -> empirical_analysis -> repo
REPO_ROOT = Path(__file__).resolve().parents[2]

# --- Baseline green labels (canonical, read-only) --------------------------
# The thesis anchor is clean_tables/population_key.parquet: 116,005 firms with
# company_id, green, green_stage, green_signal_group (green=8,306; stage1
# vertical=6,636; token=834; phrase=836; none=107,699). NEVER written here.
#
# Population file resolution: env KWR_POPULATION -> <clean_dir>/population_key.parquet
# where the clean dir resolves like Step 2 (env KWR_CLEAN_DIR / STEP2_CLEAN_DIR ->
# the target machine's OneDrive clean_tables (Windows) -> repo defaults).
POPULATION_FILENAME = "population_key.parquet"

_CLEAN_DIR_CANDIDATES_WIN = [
    r"C:\Users\nastj\OneDrive - Universitat Ramón Llull\ESADE\MIM\Thesis Folder Structure\09_Python_Empirical Analysis\clean_tables",
]
_CLEAN_DIR_CANDIDATES_ANY = [
    str(REPO_ROOT / "data" / "outputs" / "clean_tables"),
    str(REPO_ROOT / "data" / "interim"),
]


def _resolve_clean_dir() -> Path:
    env = os.environ.get("KWR_CLEAN_DIR") or os.environ.get("STEP2_CLEAN_DIR")
    win = _CLEAN_DIR_CANDIDATES_WIN if os.name == "nt" else []
    for cand in ([env] if env else []) + win + _CLEAN_DIR_CANDIDATES_ANY:
        try:
            path = Path(cand)
            if path.exists():
                return path
        except OSError:
            continue
    return REPO_ROOT / "data" / "outputs" / "clean_tables"


CLEAN_DIR: Path = _resolve_clean_dir()


def _resolve_population() -> Path:
    env = os.environ.get("KWR_POPULATION")
    if env:
        return Path(env)
    return CLEAN_DIR / POPULATION_FILENAME


POPULATION: Path = _resolve_population()

# --- Text spine (committed) ------------------------------------------------
# 94-column merged population; supplies Keywords / Description / Verticals text.
# Join key CompanyID <-> population_key.company_id.
SPINE: Path = Path(os.environ.get("KWR_SPINE") or (REPO_ROOT / "startups_stages_filtered.csv"))
SPINE_USECOLS = ["CompanyID", "Keywords", "Description", "Verticals"]

# --- Vocabulary (current on-disk files; report actual counts) --------------
# Standalone tokens and multi-word phrases, loaded exactly as the live classifier
# loads them. Thesis references 64/458; the on-disk files carry 68/456 (the
# thesis 64 == 68 minus the four dual-use tokens below; 458 has no on-disk source,
# closest committed count is 456). The reconciliation output records both.
STANDALONE: Path = Path(
    os.environ.get("KWR_STANDALONE") or (REPO_ROOT / "data" / "outputs" / "strong_terms_active.csv")
)
PHRASES: Path = Path(
    os.environ.get("KWR_PHRASES") or (REPO_ROOT / "data" / "outputs" / "strong_term_phrases.csv")
)

# --- Output directory ------------------------------------------------------
OUT_DIR: Path = Path(os.environ.get("KWR_OUT_DIR") or (REPO_ROOT / "data" / "outputs" / "chapter4"))

FIRM_LEVEL_TABLE = "keyword_recovery_firm_level.parquet"
STAGE1_TABLE = "T_keyword_recovery_stage1.csv"
BY_VERTICAL_TABLE = "T_keyword_recovery_by_vertical.csv"
RECONCILIATION_TABLE = "keyword_recovery_reconciliation.csv"
REPORT_FILE = "step9_keyword_recovery_report.txt"

# --- Acceptance anchors (canonical baseline) -------------------------------
POP_TOTAL = 116_005
GREEN_TOTAL = 8_306
STAGE1_N = 6_636      # green_stage == "vertical"
TOKEN_N = 834         # green_stage == "token"
PHRASE_N = 836        # green_stage == "phrase"
NONE_N = 107_699      # green_stage == "none"

# --- Vocabulary bookkeeping ------------------------------------------------
# Thesis-quoted vocabulary sizes, recorded alongside the actual on-disk counts.
THESIS_STANDALONE = 64
THESIS_MWE = 458

# The four dual-use tokens whose removal reconciles the on-disk 68 with the
# thesis's 64. A standalone-recovery sensitivity is reported excluding these.
DUAL_USE_TOKENS = frozenset({"nuclear", "nuclears", "biological", "biologicals"})

# Vertical-name surfaces that must NOT appear as search terms (guard: this
# exercise recovers via the environmental vocabulary, not via the vertical names
# it is meant to be independent of).
VERTICAL_NAME_TERMS = frozenset({"cleantech", "climatetech", "clean tech", "climate tech"})
