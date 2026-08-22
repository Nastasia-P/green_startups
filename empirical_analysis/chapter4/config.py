"""Configuration for Chapter 4 empirical analysis.

Paths, constants, taxonomies and the coverage anchors for the T4.0 audit.
All values trace to `empirical_analysis/Empirical_Analysis_Specification.md`
and `empirical_analysis/HANDOVER.md`.
"""

from __future__ import annotations

import os
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
# Directory holding the raw tables (Deal.csv, Investor.csv, ...). Resolution
# order (first existing wins):
#   1. env var PITCHBOOK_EXTRACT_DIR
#   2. the target machine's OneDrive extract folder
#   3. <repo>/data/raw
# The --extract-dir CLI flag overrides all of these at runtime.
_EXTRACT_DIR_CANDIDATES = [
    r"C:\Users\nastj\OneDrive - Universitat Ramón Llull\ESADE\MIM\Thesis Folder Structure\02_Data\esade_20260707",
    str(REPO_ROOT / "data" / "raw"),
]


def _resolve_extract_dir() -> Path:
    env = os.environ.get("PITCHBOOK_EXTRACT_DIR")
    candidates = ([env] if env else []) + _EXTRACT_DIR_CANDIDATES
    for cand in candidates:
        try:
            path = Path(cand)
            if path.exists():
                return path
        except OSError:
            continue
    return REPO_ROOT / "data" / "raw"


FULL_EXTRACT_DIR: Path | None = _resolve_extract_dir()

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
# Default output directory. Resolution order (first existing parent wins):
#   1. env var T4_OUTPUT_DIR
#   2. the target machine's OneDrive empirical-analysis folder
#   3. <repo>/data/outputs
# The --output-dir CLI flag overrides all of these at runtime.
_OUTPUT_DIR_CANDIDATES = [
    r"C:\Users\nastj\OneDrive - Universitat Ramón Llull\ESADE\MIM\Thesis Folder Structure\09_Python_Empirical Analysis",
]


def _resolve_output_dir() -> Path:
    env = os.environ.get("T4_OUTPUT_DIR")
    # The hard-coded OneDrive candidate is a Windows path; only consider it on
    # Windows. On POSIX a backslash path collapses to a single-component name
    # whose parent (".") always exists, which would be a false positive.
    win_candidates = _OUTPUT_DIR_CANDIDATES if os.name == "nt" else []
    candidates = ([env] if env else []) + win_candidates
    for cand in candidates:
        try:
            path = Path(cand)
            # Accept if the leaf exists, or its parent tree exists (write_outputs
            # creates the leaf dir itself).
            if path.exists() or path.parent.exists():
                return path
        except OSError:
            continue
    return REPO_ROOT / "data" / "outputs"


OUTPUT_DIR = _resolve_output_dir()

# --- Population constants --------------------------------------------------
# Spec/HANDOVER load-bearing anchors (full Chapter 3 inputs).
SPEC_POP_TOTAL = 116_005
SPEC_GREEN_TOTAL = 8_306
SPEC_GREEN_STAGES = {"vertical": 6_636, "token": 834, "phrase": 836}

# --- Group labels (rule N10) ----------------------------------------------
GROUP_GREEN = "Green start-ups"
GROUP_OTHER = "Other European start-ups"

# --- Per-variable source_table label (editable) ---------------------------
# The `source_table` column in the audit output. Keyed by the row's `field`
# label. Edit any value here to change what provenance a given variable
# reports (e.g. swap "Company" for "startups_stages_filtered" to cite the
# derived European-startup dataset instead of the canonical PitchBook table).
# A field missing from this map falls back to the default passed in code.
SOURCE_TABLE_BY_FIELD = {
    # Company-level scalar attributes (read from COMPANY_MERGED spine).
    "year_founded": "Company",
    "hq_country": "Company",
    "hq_city": "Company",
    "employees": "Company",
    "business_status": "Company",
    "primary_sector": "Company",
    "total_raised": "Company",
    "revenue": "Company",
    "EBITDA": "Company",
    # Relational presence rows.
    "employee_history": "CompanyEmployeeHistoryRelation",
    ">=1 deal record": "Deal",
    "deal_size": "Deal",
    "deal_size actual": "Deal",
    "first_deal_date": "Deal",
    "investor relation present": "CompanyInvestorRelation",
    "investor type matched": "Investor",
    "investor country matched": "Investor",
    # §P4 validation anchors.
    "FirstFinancingDealType": "Company",
    "Verticals": "Company",
    "FirstFinancingDate": "Company",
    "ActiveInvestors": "Company",
}

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
# PitchBook suffixes these families ("Secondary Transaction - Open Market",
# "Bankruptcy: Admin/Reorg", ...), so they are matched by prefix. Kept in sync
# with step1_clean_raw_data.config.
DEAL_TYPE_EXCLUSION_PREFIXES = ("Secondary Transaction", "Bankruptcy")

# --- Investor type grouping (spec Part V4) ---------------------------------
# Kept in sync with step1_clean_raw_data.config.INVESTOR_TYPE_GRP.
INVESTOR_TYPE_GRP = {
    "Venture Capital": "Independent VC",
    "Government": "Public/Government",
    "Not-For-Profit Venture Capital": "Public/Government",
    "University": "Public/Government",
    "Sovereign Wealth Fund": "Public/Government",
    "SBIC": "Public/Government",
    "Corporation": "Corporate",
    "Corporate Venture Capital": "Corporate",
    "PE-Backed Company": "Corporate",
    "VC-Backed Company": "Corporate",
    "Holding Company": "Corporate",
    "Corporate Development": "Corporate",
    "PE/Buyout": "PE/Growth",
    "Growth/Expansion": "PE/Growth",
    "Infrastructure": "PE/Growth",
    "Mezzanine": "PE/Growth",
    "Other Private Equity": "PE/Growth",
    "Fundless Sponsor": "PE/Growth",
    "Merchant Banking Firm": "PE/Growth",
    "Secondary Buyer": "PE/Growth",
    "Real Estate": "PE/Growth",
    "Accelerator/Incubator": "Accelerator/Incubator",
    "Individual": "Angel",
    "Angel Group": "Angel",
    "Angel (individual)": "Angel",
    "Family Office": "Family Office",
    "Impact Investing": "Impact Investing",
    "Lender/Debt Provider": "Lender/Debt",
    "Commercial Bank": "Lender/Debt",
    "Investment Bank": "Lender/Debt",
    "Business Development Company": "Lender/Debt",
    "Leasing": "Lender/Debt",
    "Asset Manager": "Other/Unclassified",
    "Hedge Fund": "Other/Unclassified",
    "Mutual Fund": "Other/Unclassified",
    "Fund of Funds": "Other/Unclassified",
    "Limited Partner": "Other/Unclassified",
    "Special Purpose Acquisition Company (SPAC)": "Other/Unclassified",
    "Other": "Other/Unclassified",
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
# When True, the full-extract source logs per-table file paths and row counts.
VERBOSE = False
COHORT_BINS = [
    (2016, 2018, "2016-2018"),
    (2019, 2021, "2019-2021"),
    (2022, 2024, "2022-2024"),
    (2025, 2026, "2025-2026"),
]
