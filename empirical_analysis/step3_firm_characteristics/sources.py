"""Input access for Step 3.

Loads the Step 2 firm table and, on demand, the Step 1 clean relational tables
used for the industry and vertical cuts. No transformation happens here.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from . import config


def log(msg: str) -> None:
    if config.VERBOSE:
        print(msg)


def load_firm_table(firm_table_path: Path | None = None) -> pd.DataFrame:
    """Load company_analysis.parquet (one row per firm)."""
    path = Path(firm_table_path or config.FIRM_TABLE)
    df = pd.read_parquet(path)
    log(f"[step3] load firm table: {path} rows={len(df)}")
    return df


def load_clean_table(name: str, clean_dir: Path | None = None) -> pd.DataFrame:
    """Load a Step 1 clean parquet table by name; empty frame if absent."""
    clean_dir = Path(clean_dir or config.CLEAN_DIR)
    path = clean_dir / f"{name}.parquet"
    if not path.exists():
        log(f"[step3] load {name}: {path} MISSING -> empty")
        return pd.DataFrame()
    df = pd.read_parquet(path)
    log(f"[step3] load {name}: {path} rows={len(df)}")
    return df
