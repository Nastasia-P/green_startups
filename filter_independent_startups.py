"""Filter Company_Europe.csv down to young startups.

A company is kept when all of the following hold:
  1. Universe (allowed-only): every comma-separated token in Universe is one of
     {Pre-venture, Venture Capital, Private Equity, Debt Financed}, and at least
     one token is present. Any row that also carries M&A, Publicly Listed or
     Other Private Companies (or is empty) is dropped.
  2. OwnershipStatus in OWNERSHIP_STATUSES (privately held, or in IPO
     registration).
  3. CompanyFinancingStatus in FINANCING_STATUSES (strict allow-set of backed /
     formerly-backed / corporation statuses; pending/failed transactions and
     "Potential Target" are dropped).
  4. Alive: BusinessStatus not in DEAD_BUSINESS_STATUSES (drops bankrupt/defunct
     firms). Empty BusinessStatus is kept (it is unknown, not dead).
  5. Young: YearFounded present AND 2026 - YearFounded <= 10 (missing year is
     dropped).

No employee or revenue cap, so scaleups are kept. The input is ~5.4 GB and is
streamed in chunks.
"""

import csv

import pandas as pd

INPUT_PATH = "Company_Europe.csv"
OUTPUT_PATH = "independent_startups.csv"

CURRENT_YEAR = 2026
MAX_AGE = 10  # at most 10 years old; missing YearFounded is dropped

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
OWNERSHIP_STATUSES = {
    "Privately Held (no backing)",
    "Privately Held (backing)",
    "In IPO Registration",
}

# Accepted CompanyFinancingStatus values (strict allow-set). Everything else,
# including pending/failed transactions and "Potential Target", is dropped.
FINANCING_STATUSES = {
    "Corporation",
    "Corporate Backed or Acquired",
    "Private Equity-Backed",
    "Venture Capital-Backed",
    "Formerly PE-Backed",
    "Formerly VC-backed",
    "Accelerator/Incubator Backed",
    "Formerly Accelerator/Incubator backed",
    "Private Debt Financed",
    "Formerly Angel backed",
    "Angel-Backed",
    "Formerly Private Debt Financed",
}

# Defunct/failed business states to exclude (empty BusinessStatus is kept: it is
# unknown, not dead).
DEAD_BUSINESS_STATUSES = {
    "Out of Business",
    "Bankruptcy: Liquidation",
    "Bankruptcy: Admin/Reorg",
}

CHUNKSIZE = 200_000


def universe_ok(value: str) -> bool:
    """True if Universe carries at least one token and all tokens are allowed."""
    tokens = [t.strip() for t in value.split(",")] if value else []
    return bool(tokens) and all(t in ALLOWED_UNIVERSE for t in tokens)


def main():
    scanned = 0
    kept = 0
    header_written = False
    status_counts = {}
    total_startup_status = 0  # BusinessStatus == "Startup" across whole set
    kept_startup_status = 0  # BusinessStatus == "Startup" within filtered set

    reader = pd.read_csv(
        INPUT_PATH,
        dtype=str,
        keep_default_na=False,
        chunksize=CHUNKSIZE,
    )

    with open(OUTPUT_PATH, "w", encoding="utf-8", newline="") as fout:
        for chunk in reader:
            scanned += len(chunk)

            year = pd.to_numeric(chunk["YearFounded"], errors="coerce")
            age = CURRENT_YEAR - year
            age_ok = year.notna() & (age <= MAX_AGE)

            total_startup_status += int((chunk["BusinessStatus"] == "Startup").sum())

            mask = (
                chunk["Universe"].map(universe_ok)
                & chunk["OwnershipStatus"].isin(OWNERSHIP_STATUSES)
                & chunk["CompanyFinancingStatus"].isin(FINANCING_STATUSES)
                & ~chunk["BusinessStatus"].isin(DEAD_BUSINESS_STATUSES)
                & age_ok
            )

            selected = chunk[mask].copy()
            if not selected.empty:
                selected["age_years"] = age[mask].astype("Int64")
                selected.to_csv(
                    fout,
                    index=False,
                    header=not header_written,
                    quoting=csv.QUOTE_MINIMAL,
                )
                header_written = True
                kept += len(selected)
                kept_startup_status += int((selected["BusinessStatus"] == "Startup").sum())

                for status, cnt in selected["CompanyFinancingStatus"].value_counts().items():
                    status_counts[status] = status_counts.get(status, 0) + int(cnt)

    pct = (kept / scanned) if scanned else 0
    print(f"Rows scanned: {scanned}")
    print(f"Independent startups kept: {kept} ({pct:.2%})")
    print(f"Output: {OUTPUT_PATH}")
    print("\nKept, by CompanyFinancingStatus:")
    for status, cnt in sorted(status_counts.items(), key=lambda kv: kv[1], reverse=True):
        print(f"  {cnt:>7}  {status}")

    cov = (kept_startup_status / total_startup_status) if total_startup_status else 0
    print("\nBusinessStatus == 'Startup' check:")
    print(f"  whole set:    {total_startup_status}")
    print(f"  filtered set: {kept_startup_status}")
    print(f"  coverage (filtered/whole): {cov:.1%}")


if __name__ == "__main__":
    main()
