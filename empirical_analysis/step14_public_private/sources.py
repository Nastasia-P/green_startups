"""Input access for Step 14 (public/private investor participation).

Loads the Step 5b firm panel (`first5_analysis.parquet`, controls + eligible
set), the Step 2 firm table (`company_analysis.parquet`, needed by
`prepare_window()` for the firm-relative window) and the Step 1 clean tables
(`deals_clean`, `deal_investors_clean`, `investors_clean`). No transformation
happens here; missing clean tables return empty frames so the module degrades
gracefully rather than crashing.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from . import config


def log(msg: str) -> None:
    if config.VERBOSE:
        print(msg)


def resolve_firm_panel(firm_panel_path: Path | None = None) -> Path:
    """Accept either the parquet file or the Step 5b output directory."""
    path = Path(firm_panel_path or config.FIRM_PANEL)
    if path.is_dir():
        candidate = path / "first5_analysis.parquet"
        if not candidate.exists():
            raise FileNotFoundError(
                f"--firm-panel is a directory but {candidate} is missing. "
                "Run step5b_fixed_horizon first to produce first5_analysis.parquet."
            )
        return candidate
    return path


def load_firm_panel(firm_panel_path: Path | None = None) -> pd.DataFrame:
    """Load first5_analysis.parquet (one row per common-horizon eligible firm)."""
    path = resolve_firm_panel(firm_panel_path)
    if not path.exists():
        raise FileNotFoundError(
            f"{path} does not exist. Run "
            "`python -m empirical_analysis.step5b_fixed_horizon.run` first."
        )
    df = pd.read_parquet(path)
    log(f"[step14] load firm panel: {path} rows={len(df)}")
    return df


def resolve_firm_table(firm_table_path: Path | None = None) -> Path:
    path = Path(firm_table_path or config.FIRM_TABLE)
    if path.is_dir():
        candidate = path / "company_analysis.parquet"
        if not candidate.exists():
            raise FileNotFoundError(
                f"--firm-table is a directory but {candidate} is missing."
            )
        return candidate
    return path


def load_firm_table(firm_table_path: Path | None = None) -> pd.DataFrame:
    """Load company_analysis.parquet (one row per firm)."""
    path = resolve_firm_table(firm_table_path)
    df = pd.read_parquet(path)
    log(f"[step14] load firm table: {path} rows={len(df)}")
    return df


def _load_clean(name: str, clean_dir: Path | None = None) -> pd.DataFrame:
    clean_dir = Path(clean_dir or config.CLEAN_DIR)
    path = clean_dir / f"{name}.parquet"
    if not path.exists():
        log(f"[step14] load {name}: {path} MISSING -> empty")
        return pd.DataFrame()
    df = pd.read_parquet(path)
    log(f"[step14] load {name}: {path} rows={len(df)}")
    return df


def load_deals_clean(clean_dir: Path | None = None) -> pd.DataFrame:
    return _load_clean("deals_clean", clean_dir)


def load_deal_investors(clean_dir: Path | None = None) -> pd.DataFrame:
    return _load_clean("deal_investors_clean", clean_dir)


def load_investors(clean_dir: Path | None = None) -> pd.DataFrame:
    return _load_clean("investors_clean", clean_dir)
