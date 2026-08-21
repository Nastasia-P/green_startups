"""Data sources for Chapter 4.

Provides:
- `load_population_key`  : one row per firm with green / green_stage.
- `load_company_frame`   : company-level scalar fields for the population.
- `RelationalSource`     : per-table access, with a fixture (preview_summary)
                           and a full-extract implementation.

Grain discipline (spec Part II.A3): relational tables are returned as-is; the
audit aggregates each to firm grain before use. Nothing is merged wholesale.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

import pandas as pd

from . import config


def _log(msg: str) -> None:
    """Print a diagnostic line when config.VERBOSE is set."""
    if config.VERBOSE:
        print(msg)


# --------------------------------------------------------------------------
# Missing-value helper (spec §3.6 / decision D-T4.0-6)
# --------------------------------------------------------------------------
def nonnull_mask(series: pd.Series) -> pd.Series:
    """True where a value is present. Empty/whitespace strings and NaN are missing."""
    if series.dtype == object:
        stripped = series.astype("string").str.strip()
        return stripped.notna() & (stripped != "")
    return series.notna()


# --------------------------------------------------------------------------
# Population key
# --------------------------------------------------------------------------
def load_population_key(ledger_path: Path | None = None) -> pd.DataFrame:
    """Return [company_id, green, green_stage, green_signal_group], one row per firm.

    `green_stage` is one of {vertical, token, phrase, none}; `green_signal_group`
    collapses it into the R1 robustness split (Stage 1 vs Stage 2+3).
    """
    ledger_path = Path(ledger_path or config.LEDGER)
    df = pd.read_csv(
        ledger_path,
        usecols=["CompanyID", "Green", "GreenStage"],
        dtype={"CompanyID": "string"},
    )
    df = df.rename(
        columns={"CompanyID": "company_id", "Green": "green", "GreenStage": "green_stage"}
    )
    df["green"] = pd.to_numeric(df["green"], errors="coerce").fillna(0).astype(int).clip(0, 1)
    df["green_stage"] = df["green_stage"].fillna("none").astype("string")

    def signal_group(stage: str) -> str:
        if stage == "vertical":
            return "Stage 1"
        if stage in ("token", "phrase"):
            return "Stage 2+3"
        return "none"

    df["green_signal_group"] = df["green_stage"].map(signal_group).astype("string")
    return df.drop_duplicates(subset="company_id").reset_index(drop=True)


# --------------------------------------------------------------------------
# Company-level frame
# --------------------------------------------------------------------------
_COMPANY_USECOLS = [
    "CompanyID",
    "YearFounded",
    "HQCountry",
    "HQCity",
    "Employees",
    "BusinessStatus",
    "PrimaryIndustrySector",
    "TotalRaised",
    "Verticals",
    "ActiveInvestors",
    "Revenue",
    "EBITDA",
    "FirstFinancingDealID",
    "FirstFinancingDate",
    "FirstFinancingDealType",
]


def load_company_frame(
    population_key: pd.DataFrame, company_path: Path | None = None
) -> pd.DataFrame:
    """Load company-level scalar fields for the population, joined to green flags.

    Only columns needed by T4.0 are read. Rows are restricted to the population
    (inner join on the ledger).
    """
    company_path = Path(company_path or config.COMPANY_MERGED)
    header = pd.read_csv(company_path, nrows=0).columns
    usecols = [c for c in _COMPANY_USECOLS if c in header]
    df = pd.read_csv(company_path, usecols=usecols, dtype={"CompanyID": "string"})
    df = df.rename(columns={"CompanyID": "company_id"})
    return population_key.merge(df, on="company_id", how="inner")


# --------------------------------------------------------------------------
# Relational sources
# --------------------------------------------------------------------------
class RelationalSource(ABC):
    """Access to the raw relational PitchBook tables needed by T4.0."""

    @abstractmethod
    def table(self, name: str) -> pd.DataFrame:
        """Return the named table (e.g. 'Deal', 'Investor'). Empty frame if absent."""


class FixtureRelationalSource(RelationalSource):
    """Reads tables from the wide `preview_summary.csv` fixture.

    Splits by the `source_file` column and drops union columns that are entirely
    empty for that subset. Smoke-test use only (spec §3.11).
    """

    def __init__(self, fixture_path: Path | None = None):
        self.fixture_path = Path(fixture_path or config.FIXTURE)
        self._raw = pd.read_csv(self.fixture_path, dtype=str, low_memory=False)

    def table(self, name: str) -> pd.DataFrame:
        source_file = f"{name}.csv"
        subset = self._raw[self._raw["source_file"] == source_file].copy()
        if subset.empty:
            return subset.drop(columns=["source_file"], errors="ignore")
        subset = subset.drop(columns=["source_file"])
        return subset.dropna(axis=1, how="all")


class FullExtractRelationalSource(RelationalSource):
    """Reads tables from a directory of raw 43-table CSVs, in chunks.

    Each table is filtered to the population on its own key (spec §A2):
    company-keyed tables on CompanyID; `Investor` on InvestorID via a two-pass
    load (first collect the InvestorIDs referenced by the population's
    CompanyInvestorRelation rows, then read only those investors). Results are
    cached, and only the columns T4.0 needs are read.
    """

    def __init__(
        self,
        extract_dir: Path | None = None,
        population_ids: set[str] | None = None,
        chunksize: int = config.CHUNKSIZE,
    ):
        extract_dir = extract_dir or config.FULL_EXTRACT_DIR
        if extract_dir is None:
            raise ValueError(
                "FULL_EXTRACT_DIR is not set. Point config.FULL_EXTRACT_DIR at the "
                "directory holding the raw PitchBook tables, or use --mode fixture."
            )
        self.extract_dir = Path(extract_dir)
        self.population_ids = population_ids
        self.chunksize = chunksize
        self._cache: dict[str, pd.DataFrame] = {}

    def _read_filtered(
        self, path: Path, filter_col: str | None, filter_set: set[str] | None, usecols: list[str]
    ) -> pd.DataFrame:
        header = pd.read_csv(path, nrows=0).columns
        cols = [c for c in usecols if c in header]
        if filter_col and filter_col in header and filter_col not in cols:
            cols.append(filter_col)
        read_kwargs = {"dtype": str, "chunksize": self.chunksize, "low_memory": False}
        if cols:
            read_kwargs["usecols"] = cols
        frames: list[pd.DataFrame] = []
        raw_rows = 0
        for chunk in pd.read_csv(path, **read_kwargs):
            raw_rows += len(chunk)
            if filter_col and filter_set is not None and filter_col in chunk.columns:
                chunk = chunk[chunk[filter_col].isin(filter_set)]
            if not chunk.empty:
                frames.append(chunk)
        result = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=cols)
        _log(
            f"    header cols={list(header)[:8]}{'...' if len(header) > 8 else ''}"
        )
        _log(
            f"    filter_col={filter_col!r} present={filter_col in header if filter_col else 'n/a'} "
            f"raw_rows={raw_rows} kept_rows={len(result)}"
        )
        return result

    def _needed_investor_ids(self) -> set[str]:
        cir = self.table("CompanyInvestorRelation")
        if cir.empty or "InvestorID" not in cir.columns:
            return set()
        return set(cir["InvestorID"].astype("string").dropna())

    def table(self, name: str) -> pd.DataFrame:
        if name in self._cache:
            return self._cache[name]

        path = self.extract_dir / f"{name}.csv"
        _log(f"[T4.0] load table {name}: {path} exists={path.exists()}")
        if not path.exists():
            self._cache[name] = pd.DataFrame()
            return self._cache[name]

        usecols = config.FULL_EXTRACT_USECOLS.get(name, [])
        filter_col = config.FULL_EXTRACT_FILTER_COL.get(name, "CompanyID")

        if name == "Investor":
            filter_set: set[str] | None = self._needed_investor_ids()
        elif filter_col is None:
            filter_set = None
        else:
            filter_set = self.population_ids

        result = self._read_filtered(path, filter_col, filter_set, usecols)
        self._cache[name] = result
        return result


def make_relational_source(
    mode: str, population_ids: set[str] | None = None
) -> RelationalSource:
    """Factory: 'fixture' -> preview_summary; 'full' -> extract directory."""
    if mode == "fixture":
        return FixtureRelationalSource()
    if mode == "full":
        return FullExtractRelationalSource(population_ids=population_ids)
    raise ValueError(f"Unknown mode: {mode!r} (expected 'fixture' or 'full')")
