"""Input access for Step 7.

Loads the Step 2 firm table and the four Step 1 clean tables used here
(`deals_clean`, `company_investors_clean`, `investors_clean`,
`deal_investors_clean`). No transformation happens here.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from . import config


def log(msg: str) -> None:
    if config.VERBOSE:
        print(msg)


def resolve_firm_table(firm_table_path: Path | None = None) -> Path:
    """Accept either the parquet file or the Step 2 output directory."""
    path = Path(firm_table_path or config.FIRM_TABLE)
    if path.is_dir():
        candidate = path / "company_analysis.parquet"
        if not candidate.exists():
            raise FileNotFoundError(
                f"--firm-table is a directory but {candidate} is missing. "
                "Point --firm-table at company_analysis.parquet, or at the "
                "Step 2 output folder that contains that file."
            )
        return candidate
    return path


def load_firm_table(firm_table_path: Path | None = None) -> pd.DataFrame:
    """Load company_analysis.parquet (one row per firm)."""
    path = resolve_firm_table(firm_table_path)
    df = pd.read_parquet(path)
    log(f"[step7] load firm table: {path} rows={len(df)}")
    return df


def _load_clean(name: str, clean_dir: Path | None = None) -> pd.DataFrame:
    clean_dir = Path(clean_dir or config.CLEAN_DIR)
    path = clean_dir / f"{name}.parquet"
    if not path.exists():
        log(f"[step7] load {name}: {path} MISSING -> empty")
        return pd.DataFrame()
    df = pd.read_parquet(path)
    log(f"[step7] load {name}: {path} rows={len(df)}")
    return df


def load_deals_clean(clean_dir: Path | None = None) -> pd.DataFrame:
    """Load the Step 1 deals_clean parquet (one row per deal); empty if absent."""
    return _load_clean("deals_clean", clean_dir)


def load_company_investors(clean_dir: Path | None = None) -> pd.DataFrame:
    """Load company_investors_clean (one row per firm x investor); empty if absent."""
    return _load_clean("company_investors_clean", clean_dir)


def load_investors(clean_dir: Path | None = None) -> pd.DataFrame:
    """Load investors_clean (one row per investor); empty if absent."""
    return _load_clean("investors_clean", clean_dir)


def load_deal_investors(clean_dir: Path | None = None) -> pd.DataFrame:
    """Load deal_investors_clean (one row per deal x investor); empty if absent."""
    return _load_clean("deal_investors_clean", clean_dir)
