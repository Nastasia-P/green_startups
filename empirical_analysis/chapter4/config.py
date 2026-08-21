"""Configuration for Chapter 4 empirical analysis.

Paths, constants, taxonomies and the coverage anchors for the T4.0 audit.
All values trace to `empirical_analysis/Empirical_Analysis_Specification.md`
and `empirical_analysis/HANDOVER.md`.
"""

from __future__ import annotations

from pathlib import Path

# Repository root: chapter4/config.py -> chapter4 -> empirical_analysis -> repo
REPO_ROOT = Path(__file__).resolve().parents[2]

# --- Committed inputs (runnable now) --------------------------------------
# Merged startup population spine: 116,005 firms, full PitchBook company cols.
COMPANY_MERGED = REPO_ROOT / "startups_stages_filtered.csv"
# Green classification ledger (authoritative for population_key: strong_terms).
LEDGER = REPO_ROOT / "data" / "outputs" / "startup_population_green_classification_strong_terms.csv"
# Smoke-test fixture: ~20 rows per raw PitchBook table, tagged by `source_file`.
FIXTURE = REPO_ROOT / "empirical_analysis" / "preview_summary.csv"

# --- Full 43-table extract (not committed; set to run on real data) -------
# Default directory to drop the raw tables into (Deal.csv, Investor.csv, ...).
# Override with --extract-dir on the CLI or by reassigning this at runtime.
FULL_EXTRACT_DIR: Path | None = REPO_ROOT / "data" / "raw"

# Columns actually needed per raw table (intersected with the real header at
# read time). Keeps memory bounded on the large tables (spec §A2).
FULL_EXTRACT_USECOLS = {
    "Deal": ["CompanyID", "DealID", "DealDate", "DealType", "DealSize", "DealSizeStatus", "DealStatus"],
    "CompanyInvestorRelation": ["CompanyID", "InvestorID", "InvestorStatus"],
    "Investor": ["InvestorID", "PrimaryInvestorType", "OtherInvestorTypes", "HQCountry", "Country"],
    "CompanyEmployeeHistoryRelation": ["CompanyID"],
    "CompanyVerticalRelation": ["CompanyID", "Vertical"],
    "CompanyIndustryRelation": ["CompanyID"],
    "DealInvestorRelation": ["DealID", "InvestorID"],
}

# Which key each table is filtered on when subsetting to the population.
# Investor is filtered on InvestorID (two-pass, see FullExtractRelationalSource);
# DealInvestorRelation is keyed by DealID so it is not company-filtered here.
FULL_EXTRACT_FILTER_COL = {
    "Deal": "CompanyID",
    "CompanyInvestorRelation": "CompanyID",
    "CompanyEmployeeHistoryRelation": "CompanyID",
    "CompanyVerticalRelation": "CompanyID",
    "CompanyIndustryRelation": "CompanyID",
    "Investor": "InvestorID",
    "DealInvestorRelation": None,
}

# Candidate column names for an investor's country (raw vs merged schemas).
INVESTOR_COUNTRY_CANDIDATES = ["HQCountry", "Country"]

# --- Outputs --------------------------------------------------------------
OUTPUT_DIR = REPO_ROOT / "data" / "outputs"

# --- Population constants --------------------------------------------------
# Spec/HANDOVER load-bearing anchors (full Chapter 3 inputs).
SPEC_POP_TOTAL = 116_005
SPEC_GREEN_TOTAL = 8_306
SPEC_GREEN_STAGES = {"vertical": 6_636, "token": 834, "phrase": 836}

# --- Group labels (rule N10) ----------------------------------------------
GROUP_GREEN = "Green start-ups"
GROUP_OTHER = "Other European start-ups"

# --- Deal filters (spec Part III) -----------------------------------------
DEAL_STATUS_COMPLETED = "Completed"           # F2
EXTRACT_DATE = "2026-07-07"                    # F3 upper bound
DEAL_DATE_FORMAT = "%m/%d/%Y"                  # Deal.csv date format
# F4: deal types that are not new capital into the firm.
DEAL_TYPE_EXCLUSIONS = {
    "Bankruptcy: Liquidation",
    "Out of Business",
    "IPO",
    "Merger/Acquisition",
    "Share Repurchase",
    "Secondary Transaction",
}

# --- Investor type grouping (spec Part V4) ---------------------------------
INVESTOR_TYPE_GRP = {
    "Venture Capital": "Independent VC",
    "Government": "Public/Government",
    "Not-For-Profit Venture Capital": "Public/Government",
    "Corporation": "Corporate",
    "Corporate Venture Capital": "Corporate",
    "PE-Backed Company": "Corporate",
    "PE/Buyout": "PE/Growth",
    "Growth/Expansion": "PE/Growth",
    "Infrastructure": "PE/Growth",
    "Accelerator/Incubator": "Accelerator/Incubator",
    "Individual": "Angel",
    "Angel Group": "Angel",
    "Angel (individual)": "Angel",
    "Lender/Debt Provider": "Lender/Debt",
    "Commercial Bank": "Lender/Debt",
    "Asset Manager": "Other/Unclassified",
}

# --- Coverage anchors (spec Part P4) --------------------------------------
# Field -> (green_pct, other_pct). Used to sanity-check a full-data run.
# The committed strong_terms grouping (green=8,698) will not reproduce these
# exactly; mismatches are warned, never raised.
COVERAGE_ANCHORS = {
    "total_raised": (59.3, 24.2),
    "FirstFinancingDealType": (97.0, 42.6),
    "Verticals": (91.0, 36.5),
    "employees": (82.0, 49.9),
    "FirstFinancingDate": (70.4, 32.6),
    "ActiveInvestors": (89.6, 39.0),
}
ANCHOR_TOLERANCE_PP = 1.0  # percentage points

# --- Engineering ----------------------------------------------------------
CHUNKSIZE = 400_000
COHORT_BINS = [
    (2016, 2018, "2016-2018"),
    (2019, 2021, "2019-2021"),
    (2022, 2024, "2022-2024"),
    (2025, 2026, "2025-2026"),
]
