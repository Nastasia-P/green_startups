"""Input access for Step 2.

Step 2 reads the Step 1 Parquet outputs plus the company spine CSV. Nothing here
transforms data; the loaders return frames as written, and `build.py` does the
firm-level collapse.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from . import config


def log(msg: str) -> None:
    """Print a diagnostic line when config.VERBOSE is set."""
    if config.VERBOSE:
        print(msg)


def nonnull_mask(series: pd.Series) -> pd.Series:
    """True where a value is present. Empty/whitespace strings and NaN are missing."""
    if series.dtype == object or str(series.dtype) == "string":
        stripped = series.astype("string").str.strip()
        return (stripped.notna() & (stripped != "")).fillna(False).astype(bool)
    return series.notna()


def load_clean_tables(clean_dir: Path | None = None) -> dict[str, pd.DataFrame]:
    """Load the five Step 1 clean tables Step 2 needs, keyed by name.

    A missing file yields an empty frame rather than an error, so the fixture and
    partial runs degrade gracefully; the audit surfaces any empty input.
    """
    clean_dir = Path(clean_dir or config.CLEAN_DIR)
    tables: dict[str, pd.DataFrame] = {}
    for name in config.CLEAN_TABLES:
        path = clean_dir / f"{name}.parquet"
        if path.exists():
            tables[name] = pd.read_parquet(path)
            log(f"[step2] load {name}: {path} rows={len(tables[name])}")
        else:
            tables[name] = pd.DataFrame()
            log(f"[step2] load {name}: {path} MISSING -> empty")
    return tables


def load_spine(
    population_key: pd.DataFrame, spine_path: Path | None = None
) -> pd.DataFrame:
    """Load the spine scalar columns for the population, joined onto population_key.

    A left join keeps every population firm even if the spine lacks a row for it,
    so the output always has exactly one row per firm in population_key.
    """
    spine_path = Path(spine_path or config.SPINE)
    header = pd.read_csv(spine_path, nrows=0).columns
    usecols = [c for c in config.SPINE_USECOLS if c in header]
    df = pd.read_csv(spine_path, usecols=usecols, dtype={"CompanyID": "string"})
    df = df.rename(
        columns={
            "CompanyID": "company_id",
            "YearFounded": "year_founded",
            "HQCountry": "hq_country",
            "HQCity": "hq_city",
            "Employees": "employees",
            "BusinessStatus": "business_status",
            "PrimaryIndustrySector": "primary_sector",
            "PrimaryIndustryGroup": "primary_industry_group",
            "PrimaryIndustryCode": "primary_industry_code",
            "TotalRaised": "total_raised",
        }
    )
    df = df.drop_duplicates(subset="company_id")
    log(f"[step2] load spine: {spine_path} rows={len(df)} cols={usecols}")
    return population_key.merge(df, on="company_id", how="left")
