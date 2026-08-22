"""Raw-table access for Step 1.

Two interchangeable sources:
- `FullExtractSource` reads the real extract directory in chunks, filtering each
  table on its own key so nothing large is ever held in memory.
- `FixtureSource` splits the committed `preview_summary.csv` sample, used by the
  smoke test.

Each table is returned at its own grain. Nothing is merged here.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

import pandas as pd

from . import config


def log(msg: str) -> None:
    """Print a diagnostic line when config.VERBOSE is set."""
    if config.VERBOSE:
        print(msg)


def nonnull_mask(series: pd.Series) -> pd.Series:
    """True where a value is present. Empty/whitespace strings and NaN are missing."""
    if series.dtype == object:
        stripped = series.astype("string").str.strip()
        return stripped.notna() & (stripped != "")
    return series.notna()


def parse_deal_dates(raw: pd.Series) -> pd.Series:
    """Parse deal dates robustly.

    Try the configured format first, then fall back to inference for values it
    could not parse. Without the fallback a differently formatted Deal.csv would
    silently lose every row at the date filter.
    """
    s = raw.astype("string")
    parsed = pd.to_datetime(s, format=config.DEAL_DATE_FORMAT, errors="coerce")
    unparsed = (parsed.isna() & nonnull_mask(s)).fillna(False).astype(bool)
    if unparsed.any():
        parsed.loc[unparsed] = pd.to_datetime(s[unparsed], errors="coerce")
    return parsed


class RawSource(ABC):
    """Access to the raw PitchBook tables Step 1 consumes."""

    @abstractmethod
    def table(self, name: str, keep_ids: set[str] | None = None) -> pd.DataFrame:
        """Return the named table, optionally restricted to `keep_ids` on its filter key."""

    @abstractmethod
    def raw_row_count(self, name: str) -> int:
        """Rows present in the source before filtering (for the audit)."""


class FixtureSource(RawSource):
    """Reads tables from the wide `preview_summary.csv` sample (smoke test only)."""

    def __init__(self, fixture_path: Path | None = None):
        self.fixture_path = Path(fixture_path or config.FIXTURE)
        self._raw = pd.read_csv(self.fixture_path, dtype=str, low_memory=False)
        self._raw_counts: dict[str, int] = {}

    def table(self, name: str, keep_ids: set[str] | None = None) -> pd.DataFrame:
        subset = self._raw[self._raw["source_file"] == f"{name}.csv"].copy()
        self._raw_counts[name] = len(subset)
        if subset.empty:
            return pd.DataFrame(columns=config.USECOLS.get(name, []))
        subset = subset.drop(columns=["source_file"]).dropna(axis=1, how="all")
        cols = [c for c in config.USECOLS.get(name, []) if c in subset.columns]
        if cols:
            subset = subset[cols]
        filter_col = config.FILTER_COL.get(name)
        if keep_ids is not None and filter_col and filter_col in subset.columns:
            subset = subset[subset[filter_col].isin(keep_ids)]
        log(f"[step1] fixture table {name}: kept_rows={len(subset)}")
        return subset.reset_index(drop=True)

    def raw_row_count(self, name: str) -> int:
        return self._raw_counts.get(name, 0)


class FullExtractSource(RawSource):
    """Reads tables from a directory of raw PitchBook CSVs, in chunks."""

    def __init__(self, extract_dir: Path | None = None, chunksize: int = config.CHUNKSIZE):
        self.extract_dir = Path(extract_dir or config.EXTRACT_DIR)
        self.chunksize = chunksize
        self._raw_counts: dict[str, int] = {}

    def path_for(self, name: str) -> Path:
        return self.extract_dir / f"{name}.csv"

    def table(self, name: str, keep_ids: set[str] | None = None) -> pd.DataFrame:
        path = self.path_for(name)
        log(f"[step1] load {name}: {path} exists={path.exists()}")
        if not path.exists():
            self._raw_counts[name] = 0
            return pd.DataFrame(columns=config.USECOLS.get(name, []))

        header = pd.read_csv(path, nrows=0).columns
        usecols = config.USECOLS.get(name, [])
        cols = [c for c in usecols if c in header]
        filter_col = config.FILTER_COL.get(name)
        if filter_col and filter_col in header and filter_col not in cols:
            cols.append(filter_col)

        read_kwargs: dict = {"dtype": str, "chunksize": self.chunksize, "low_memory": False}
        if cols:
            read_kwargs["usecols"] = cols

        frames: list[pd.DataFrame] = []
        raw_rows = 0
        for chunk in pd.read_csv(path, **read_kwargs):
            raw_rows += len(chunk)
            if keep_ids is not None and filter_col and filter_col in chunk.columns:
                chunk = chunk[chunk[filter_col].isin(keep_ids)]
            if not chunk.empty:
                frames.append(chunk)

        self._raw_counts[name] = raw_rows
        result = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=cols)
        log(f"    filter_col={filter_col!r} raw_rows={raw_rows} kept_rows={len(result)}")
        return result

    def raw_row_count(self, name: str) -> int:
        return self._raw_counts.get(name, 0)


def make_source(mode: str, extract_dir: Path | None = None) -> RawSource:
    """Factory: 'fixture' -> preview_summary sample; 'full' -> extract directory."""
    if mode == "fixture":
        return FixtureSource()
    if mode == "full":
        return FullExtractSource(extract_dir=extract_dir)
    raise ValueError(f"Unknown mode: {mode!r} (expected 'fixture' or 'full')")


def load_population_key(ledger_path: Path | None = None) -> pd.DataFrame:
    """Return [company_id, green, green_stage, green_signal_group], one row per firm."""
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
