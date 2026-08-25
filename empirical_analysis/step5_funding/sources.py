"""Input access for Step 5.

Loads the Step 2 firm table and the Step 1 `deals_clean` table. No transformation
happens here.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from . import config


def log(msg: str) -> None:
    if config.VERBOSE:
        print(msg)


def resolve_firm_table(firm_table_path: Path | None = None) -> Path:
    """Accept either the parquet file or the Step 2 output directory.

    Passing the directory is a common mistake: pandas then tries to read every
    file in it (including step2_audit.csv) as Parquet.
    """
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
    log(f"[step5] load firm table: {path} rows={len(df)}")
    return df


def load_deals_clean(clean_dir: Path | None = None) -> pd.DataFrame:
    """Load the Step 1 deals_clean parquet (one row per deal); empty if absent."""
    clean_dir = Path(clean_dir or config.CLEAN_DIR)
    path = clean_dir / "deals_clean.parquet"
    if not path.exists():
        log(f"[step5] load deals_clean: {path} MISSING -> empty")
        return pd.DataFrame()
    df = pd.read_parquet(path)
    log(f"[step5] load deals_clean: {path} rows={len(df)}")
    return df
