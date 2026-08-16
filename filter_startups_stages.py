"""Filter Company_Europe.csv through four sequential stages.

Stages are applied in order; a row must pass stage *n* to be considered for
stage *n+1*. Only rows that survive all four stages are written to the output.

  1. Young      -- YearFounded present AND 2026 - YearFounded <= 10 (missing or
                   invalid year is dropped).
  2. Ownership  -- OwnershipStatus in OWNERSHIP_STATUSES only (privately held, or
                   in IPO registration). OwnershipStatus "Out of Business" is
                   dropped here (not deferred to Stage 4).
  3. Universe   -- allowed-only: every comma-separated token in Universe is one
                   of {Pre-venture, Venture Capital, Private Equity,
                   Debt Financed}, and at least one token is present. Any row
                   that also carries M&A, Publicly Listed or Other Private
                   Companies (or is empty) is dropped.
  4. Alive      -- BusinessStatus not in DEAD_BUSINESS_STATUSES (drops
                   bankrupt/defunct firms). Empty BusinessStatus is kept (it is
                   unknown, not dead).

Each stage reports why companies were filtered out (kept/dropped counts plus a
value-count breakdown of the failing field).

Reading is parallelised: if pyarrow is available the CSV is parsed with its
multithreaded reader; otherwise the script falls back to streaming the file in
chunks with pandas.
"""

import csv
from collections import Counter

import pandas as pd

INPUT_PATH = "Company_Europe.csv"
OUTPUT_PATH = "startups_stages_filtered.csv"
REPORT_PATH = "startups_stages_report.txt"

CURRENT_YEAR = 2026
MAX_AGE = 10  # at most 10 years old; missing/invalid YearFounded is dropped

# Universe tokens allowed; a row qualifies only if every token it carries is in
# this set (so combinations with M&A / Publicly Listed / Other Private Companies
# are excluded).
ALLOWED_UNIVERSE = {
    "Pre-venture",
    "Venture Capital",
    "Private Equity",
    "Debt Financed",
}

# Accepted ownership states (independent private firms, plus pre-IPO).
# OwnershipStatus "Out of Business" is not allowed (dropped at Stage 2).
OWNERSHIP_STATUSES = {
    "Privately Held (no backing)",
    "Privately Held (backing)",
    "In IPO Registration",
}

# Defunct/failed business states to exclude (empty BusinessStatus is kept: it is
# unknown, not dead).
DEAD_BUSINESS_STATUSES = {
    "Out of Business",
    "Bankruptcy: Liquidation",
    "Bankruptcy: Admin/Reorg",
}

CHUNKSIZE = 200_000  # only used by the pandas fallback

# How many distinct rejection values to show per stage in the final report.
TOP_REASONS = 15


def universe_ok(value: str) -> bool:
    """True if Universe carries at least one token and all tokens are allowed."""
    tokens = [t.strip() for t in value.split(",")] if value else []
    return bool(tokens) and all(t in ALLOWED_UNIVERSE for t in tokens)


class StageStats:
    """Accumulates per-stage counts and rejection reasons across frames."""

    def __init__(self):
        self.entered = {"young": 0, "ownership": 0, "universe": 0, "alive": 0}
        self.kept = {"young": 0, "ownership": 0, "universe": 0, "alive": 0}
        self.reasons = {
            "young": Counter(),
            "ownership": Counter(),
            "universe": Counter(),
            "alive": Counter(),
        }


def filter_frame(chunk: pd.DataFrame, stats: StageStats) -> pd.DataFrame:
    """Apply the four sequential stages to one frame, updating ``stats``.

    Returns the survivors (with an ``age_years`` column added).
    """
    remaining = chunk

    # Stage 1: Young
    stats.entered["young"] += len(remaining)
    year = pd.to_numeric(remaining["YearFounded"], errors="coerce")
    age = CURRENT_YEAR - year
    young_ok = year.notna() & (age <= MAX_AGE)
    dropped_mask = ~young_ok
    if dropped_mask.any():
        bad_year = year[dropped_mask].isna()
        stats.reasons["young"]["missing_or_invalid_year"] += int(bad_year.sum())
        stats.reasons["young"]["too_old"] += int((~bad_year).sum())
    remaining = remaining[young_ok]
    age_years = age[young_ok]
    stats.kept["young"] += len(remaining)

    # Stage 2: Ownership (allow-list only; Out of Business is dropped here)
    stats.entered["ownership"] += len(remaining)
    own_ok = remaining["OwnershipStatus"].isin(OWNERSHIP_STATUSES)
    stats.reasons["ownership"].update(remaining.loc[~own_ok, "OwnershipStatus"])
    remaining = remaining[own_ok]
    age_years = age_years[own_ok]
    stats.kept["ownership"] += len(remaining)

    # Stage 3: Universe
    stats.entered["universe"] += len(remaining)
    uni_ok = remaining["Universe"].map(universe_ok)
    stats.reasons["universe"].update(remaining.loc[~uni_ok, "Universe"])
    remaining = remaining[uni_ok]
    age_years = age_years[uni_ok]
    stats.kept["universe"] += len(remaining)

    # Stage 4: Alive
    stats.entered["alive"] += len(remaining)
    alive_ok = ~remaining["BusinessStatus"].isin(DEAD_BUSINESS_STATUSES)
    stats.reasons["alive"].update(remaining.loc[~alive_ok, "BusinessStatus"])
    remaining = remaining[alive_ok]
    age_years = age_years[alive_ok]
    stats.kept["alive"] += len(remaining)

    survivors = remaining.copy()
    survivors["age_years"] = age_years.astype("Int64")
    return survivors


def format_stage(name, entered, kept, reasons):
    """Return the report lines for one stage."""
    dropped = entered - kept
    lines = [f"\nStage {name}: entered={entered} dropped={dropped} kept={kept}"]
    if dropped and reasons:
        lines.append("  dropped, by reason:")
        for reason, cnt in reasons.most_common(TOP_REASONS):
            label = reason if reason != "" else "<empty>"
            lines.append(f"    {cnt:>9}  {label}")
        extra = len(reasons) - TOP_REASONS
        if extra > 0:
            lines.append(f"    ... and {extra} more distinct values")
    return lines


def iter_frames():
    """Yield the data as one or more all-string DataFrames.

    Uses pyarrow's multithreaded CSV reader when available (a single frame),
    otherwise streams with pandas in chunks.
    """
    try:
        import pyarrow as pa
        import pyarrow.csv as pacsv
    except ImportError:
        print("pyarrow not found; falling back to chunked pandas reader.")
        reader = pd.read_csv(
            INPUT_PATH,
            dtype=str,
            keep_default_na=False,
            chunksize=CHUNKSIZE,
        )
        yield from reader
        return

    with open(INPUT_PATH, newline="") as f:
        header = next(csv.reader(f))
    column_types = {name: pa.string() for name in header}

    print(f"Reading with pyarrow (threads={pa.cpu_count()}) ...")
    table = pacsv.read_csv(
        INPUT_PATH,
        read_options=pacsv.ReadOptions(use_threads=True),
        convert_options=pacsv.ConvertOptions(
            column_types=column_types,
            strings_can_be_null=False,
        ),
    )
    yield table.to_pandas()


def main():
    scanned = 0
    stats = StageStats()
    header_written = False

    with open(OUTPUT_PATH, "w", encoding="utf-8", newline="") as fout:
        for chunk in iter_frames():
            scanned += len(chunk)
            survivors = filter_frame(chunk, stats)
            if not survivors.empty:
                survivors.to_csv(
                    fout,
                    index=False,
                    header=not header_written,
                    quoting=csv.QUOTE_MINIMAL,
                )
                header_written = True

    survivors_total = stats.kept["alive"]
    pct = (survivors_total / scanned) if scanned else 0

    lines = [f"Rows scanned: {scanned}"]
    lines += format_stage("1 Young", stats.entered["young"], stats.kept["young"], stats.reasons["young"])
    lines += format_stage("2 Ownership", stats.entered["ownership"], stats.kept["ownership"], stats.reasons["ownership"])
    lines += format_stage("3 Universe", stats.entered["universe"], stats.kept["universe"], stats.reasons["universe"])
    lines += format_stage("4 Alive", stats.entered["alive"], stats.kept["alive"], stats.reasons["alive"])
    lines.append(f"\nSurvivors (all stages): {survivors_total} ({pct:.2%})")
    lines.append(f"Output: {OUTPUT_PATH}")

    report = "\n".join(lines)
    print(report)
    with open(REPORT_PATH, "w", encoding="utf-8") as rep:
        rep.write(report + "\n")
    print(f"Stage report: {REPORT_PATH}")


if __name__ == "__main__":
    main()
