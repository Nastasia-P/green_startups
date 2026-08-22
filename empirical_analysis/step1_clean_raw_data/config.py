"""Configuration for Step 1 (clean the raw data).

Self-contained: paths, the four filters, the deal-stage taxonomy and the
investor-type taxonomy all live here, so the module can be read and run
without opening another document.
"""

from __future__ import annotations

import os
from pathlib import Path

# Repository root: step1_clean_raw_data/config.py -> package -> empirical_analysis -> repo
REPO_ROOT = Path(__file__).resolve().parents[2]

# --- Population inputs (committed) ----------------------------------------
# Merged startup population spine: 116,005 firms with the PitchBook company columns.
COMPANY_MERGED = REPO_ROOT / "startups_stages_filtered.csv"
# Green classification ledger: supplies green / green_stage per firm.
LEDGER = REPO_ROOT / "data" / "outputs" / "startup_population_green_classification_strong_terms.csv"
# Smoke-test fixture: ~20 rows per raw table, tagged by `source_file`.
FIXTURE = REPO_ROOT / "empirical_analysis" / "preview_summary.csv"

# --- Raw extract directory -------------------------------------------------
# Resolution order (first existing wins); --extract-dir overrides all of these.
#   1. env var PITCHBOOK_EXTRACT_DIR
#   2. the target machine's OneDrive extract folder
#   3. <repo>/data/raw
_EXTRACT_DIR_CANDIDATES = [
    r"C:\Users\nastj\OneDrive - Universitat Ramón Llull\ESADE\MIM\Thesis Folder Structure\02_Data\esade_20260707",
    str(REPO_ROOT / "data" / "raw"),
]


def _resolve_extract_dir() -> Path:
    env = os.environ.get("PITCHBOOK_EXTRACT_DIR")
    for cand in ([env] if env else []) + _EXTRACT_DIR_CANDIDATES:
        try:
            path = Path(cand)
            if path.exists():
                return path
        except OSError:
            continue
    return REPO_ROOT / "data" / "raw"


EXTRACT_DIR: Path = _resolve_extract_dir()

# --- Output directory ------------------------------------------------------
# Resolution order (first usable wins); --output-dir overrides all of these.
#   1. env var STEP1_OUTPUT_DIR
#   2. the target machine's OneDrive clean-tables folder (Windows only)
#   3. <repo>/data/interim
_OUTPUT_DIR_CANDIDATES = [
    r"C:\Users\nastj\OneDrive - Universitat Ramón Llull\ESADE\MIM\Thesis Folder Structure\09_Python_Empirical Analysis\clean_tables",
]


def _resolve_output_dir() -> Path:
    env = os.environ.get("STEP1_OUTPUT_DIR")
    # The hard-coded candidate is a Windows path; only consider it on Windows.
    # On POSIX a backslash path collapses to one component whose parent (".")
    # always exists, which would be a false positive.
    win_candidates = _OUTPUT_DIR_CANDIDATES if os.name == "nt" else []
    for cand in ([env] if env else []) + win_candidates:
        try:
            path = Path(cand)
            # The leaf is created at write time; accepting an existing parent
            # lets the first run create `clean_tables` itself.
            if path.exists() or path.parent.exists():
                return path
        except OSError:
            continue
    return REPO_ROOT / "data" / "interim"


OUTPUT_DIR: Path = _resolve_output_dir()

# --- Raw tables consumed ---------------------------------------------------
# Columns read per table, intersected with the real header at read time.
USECOLS = {
    "Deal": [
        "CompanyID", "DealID", "DealDate", "DealType", "DealType2", "DealClass",
        "DealSize", "DealSizeStatus", "DealStatus", "DealNo", "VCRound",
        "PostValuation", "Investors", "NewInvestors",
    ],
    "DealInvestorRelation": [
        "DealID", "InvestorID", "InvestorName", "InvestorStatus", "IsLeadInvestor",
    ],
    "CompanyInvestorRelation": [
        "CompanyID", "InvestorID", "InvestorName", "InvestorStatus", "Holding", "InvestorSince",
    ],
    "Investor": [
        "InvestorID", "InvestorName", "PrimaryInvestorType", "OtherInvestorTypes",
        "HQCountry", "Country",
    ],
    "CompanyIndustryRelation": [
        "CompanyID", "IsPrimary", "IndustrySector", "IndustryGroup", "IndustryCode",
    ],
    "CompanyVerticalRelation": ["CompanyID", "Vertical"],
    "CompanyEmployeeHistoryRelation": ["CompanyID", "EmployeeCount", "Date"],
}

# Key each table is filtered on. Deal/company tables filter on CompanyID;
# DealInvestorRelation filters on the surviving DealIDs; Investor filters on
# the InvestorIDs actually referenced (two-pass).
FILTER_COL = {
    "Deal": "CompanyID",
    "CompanyInvestorRelation": "CompanyID",
    "CompanyIndustryRelation": "CompanyID",
    "CompanyVerticalRelation": "CompanyID",
    "CompanyEmployeeHistoryRelation": "CompanyID",
    "DealInvestorRelation": "DealID",
    "Investor": "InvestorID",
}

# Candidate column names for an investor's country (raw vs merged schemas).
INVESTOR_COUNTRY_CANDIDATES = ["HQCountry", "Country"]

# --- The four filters ------------------------------------------------------
# 1. Population : CompanyID must be one of the 116,005 study firms.
# 2. Completed  : drop Announced/In Progress and Failed/Cancelled deals.
# 3. Valid date : DealDate must parse and fall on/before the extract date.
# 4. Real financing : drop deal types that are not new capital into the firm.
DEAL_STATUS_COMPLETED = "Completed"
EXTRACT_DATE = "2026-07-07"
DEAL_DATE_FORMAT = "%m/%d/%Y"
DEAL_TYPE_EXCLUSIONS = {
    "Bankruptcy: Liquidation",
    "Out of Business",
    "IPO",
    "Merger/Acquisition",
    "Share Repurchase",
    "Secondary Transaction",
}

# --- Deal stage taxonomy ---------------------------------------------------
# DealType -> stage_group. Any value not listed here is reported in
# deal_types_seen.csv as unmapped so it can be classified deliberately rather
# than silently bucketed.
STAGE_GROUP_MAP = {
    "Grant": "Grant",
    "Accelerator/Incubator": "Accelerator/Incubator",
    "Seed Round": "Angel/Seed",
    "Angel (individual)": "Angel/Seed",
    "Restart - Angel": "Angel/Seed",
    "Early Stage VC": "Early-stage VC",
    "Restart - Early VC": "Early-stage VC",
    "Later Stage VC": "Later-stage VC",
    "Restart - Later VC": "Later-stage VC",
    "PE Growth/Expansion": "Growth/PE",
    "Buyout/LBO": "Growth/PE",
    "Mezzanine": "Growth/PE",
    "GP Stakes": "Growth/PE",
    "Leveraged Recap": "Growth/PE",
    "Dividend Recap": "Growth/PE",
    "Debt - General": "Debt",
    "Debt - Acquisition": "Debt",
    "Debt Refinancing": "Debt",
    "Debt Repayment": "Debt",
    "Debt - Spinoff": "Debt",
    "Convertible Debt": "Debt",
    "Sale-Lease back": "Debt",
    "Equity Crowdfunding": "Crowdfunding",
    "Product Crowdfunding": "Crowdfunding",
    "University Spin-Out": "Spin-out/Corporate",
    "Spin-Off": "Spin-out/Corporate",
    "Corporate": "Spin-out/Corporate",
    "Joint Venture": "Spin-out/Corporate",
    "Platform Creation": "Spin-out/Corporate",
    "Corporate Asset Purchase": "Spin-out/Corporate",
    "Project Financing": "Other",
    "Capitalization": "Other",
    "Capital Spending": "Other",
    "Working Capital": "Other",
    "General Corporate Purpose": "Other",
    "Continuation Fund": "Other",
    "PIPE": "Other",
    "Reverse Merger": "Other",
    "Merger of Equals": "Other",
    "Debt Conversion": "Other",
    "Investor Buyout by Mgmt": "Other",
}
UNMAPPED_STAGE_GROUP = "Unmapped"

# --- Investor type taxonomy ------------------------------------------------
# PrimaryInvestorType -> investor_type_grp. Unlisted values fall into
# Other/Unclassified and are reported in investor_types_seen.csv.
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
UNCLASSIFIED_INVESTOR_GRP = "Other/Unclassified"

# --- Investor relationship scope (stated decisions) ------------------------
# Deal-level: only financing participants count.
DEAL_INVESTOR_STATUS_KEEP = {"New Investor", "Shareholder"}
# Firm-level: all historical investors except non-financing relationships.
COMPANY_INVESTOR_STATUS_DROP = {"Acquirer", "Add-on Sponsor"}

# --- Acceptance anchors ----------------------------------------------------
SPEC_POP_TOTAL = 116_005
SPEC_GREEN_TOTAL = 8_306
SPEC_GREEN_STAGES = {"vertical": 6_636, "token": 834, "phrase": 836}
# A table matching less than this share of the population is flagged.
MIN_MATCH_RATE = 0.30

# --- Engineering -----------------------------------------------------------
CHUNKSIZE = 400_000
VERBOSE = False
