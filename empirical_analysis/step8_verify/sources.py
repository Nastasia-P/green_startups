"""Input access for Step 8.

Loads the Step 2 firm table, the Step 1 clean tables, the World Bank population file,
and (for the stale-file guard) the on-disk output CSVs. No transformation here.
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
    log(f"[step8] load firm table: {path} rows={len(df)}")
    return df


def _load_clean(name: str, clean_dir: Path | None = None) -> pd.DataFrame:
    clean_dir = Path(clean_dir or config.CLEAN_DIR)
    path = clean_dir / f"{name}.parquet"
    if not path.exists():
        log(f"[step8] load {name}: {path} MISSING -> empty")
        return pd.DataFrame()
    df = pd.read_parquet(path)
    log(f"[step8] load {name}: {path} rows={len(df)}")
    return df


def load_deals_clean(clean_dir: Path | None = None) -> pd.DataFrame:
    return _load_clean("deals_clean", clean_dir)


def load_company_investors(clean_dir: Path | None = None) -> pd.DataFrame:
    return _load_clean("company_investors_clean", clean_dir)


def load_investors(clean_dir: Path | None = None) -> pd.DataFrame:
    return _load_clean("investors_clean", clean_dir)


def load_deal_investors(clean_dir: Path | None = None) -> pd.DataFrame:
    return _load_clean("deal_investors_clean", clean_dir)


def load_industries(clean_dir: Path | None = None) -> pd.DataFrame:
    return _load_clean("industries_clean", clean_dir)


def load_verticals(clean_dir: Path | None = None) -> pd.DataFrame:
    return _load_clean("verticals_clean", clean_dir)


def load_population(population_path: Path | None = None) -> pd.DataFrame:
    """Load the committed World Bank population file; empty frame if absent."""
    path = Path(population_path or config.POPULATION_FILE)
    if not path.exists():
        log(f"[step8] load population: {path} MISSING -> empty")
        return pd.DataFrame(columns=["iso2", "country", "year", "population"])
    df = pd.read_csv(path)
    log(f"[step8] load population: {path} rows={len(df)}")
    return df


def read_output_csv(name: str, output_dir: Path | None = None) -> pd.DataFrame | None:
    """Read `<name>.csv` from the output dir, or None if it is absent."""
    if output_dir is None:
        return None
    path = Path(output_dir) / f"{name}.csv"
    if not path.exists():
        return None
    return pd.read_csv(path)
