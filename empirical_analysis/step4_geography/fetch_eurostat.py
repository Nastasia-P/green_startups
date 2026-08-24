"""One-shot fetch of Eurostat population for T4.7.

Downloads table `demo_pjan` (population on 1 January) through the public JSON-stat
API, filtered to sex=T and age=TOTAL, and writes
`data/sources/eurostat_population.csv` with columns:
    geo_code, country_eurostat, year, population

The committed CSV is the runtime input for Step 4, so the analysis machine needs no
network. Re-run this only to refresh the reference year.

    python -m empirical_analysis.step4_geography.fetch_eurostat
    python -m empirical_analysis.step4_geography.fetch_eurostat --year 2023 --out data/sources/eurostat_population.csv
"""

from __future__ import annotations

import argparse
import json
import urllib.parse
import urllib.request
from pathlib import Path

import pandas as pd

from . import config


def _build_url(dataset: str, year: int) -> str:
    params = {
        "format": "JSON",
        "lang": "EN",
        "sex": "T",
        "age": "TOTAL",
        "time": str(year),
    }
    return f"{config.EUROSTAT_BASE_URL}/{dataset}?{urllib.parse.urlencode(params)}"


def _fetch_json(url: str, timeout: int = 60) -> dict:
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
        return json.loads(resp.read().decode("utf-8"))


def _parse_jsonstat(payload: dict, year: int) -> pd.DataFrame:
    """Turn a JSON-stat 2.0 demo_pjan response into a tidy geo/population frame."""
    dims = payload["dimension"]
    geo_dim = dims["geo"]
    geo_index = geo_dim["category"]["index"]        # geo_code -> position
    geo_labels = geo_dim["category"]["label"]       # geo_code -> country name
    values = payload["value"]                       # position (as str) -> population

    # demo_pjan sliced on one year/sex/age varies only along geo, so the flat index
    # into `value` is the geo position.
    rows = []
    for geo_code, pos in geo_index.items():
        pop = values.get(str(pos))
        if pop is None:
            continue
        rows.append(
            {
                "geo_code": geo_code,
                "country_eurostat": geo_labels.get(geo_code, geo_code),
                "year": year,
                "population": int(pop),
            }
        )
    return pd.DataFrame(rows).sort_values("geo_code").reset_index(drop=True)


def fetch(years: tuple[int, ...] | None = None) -> pd.DataFrame:
    """Fetch the most recent requested year that returns broad country coverage."""
    years = years or config.EUROSTAT_YEARS
    last_err: Exception | None = None
    for year in years:
        url = _build_url(config.EUROSTAT_DATASET, year)
        try:
            payload = _fetch_json(url)
            df = _parse_jsonstat(payload, year)
        except Exception as exc:  # noqa: BLE001 - report and try the next year
            last_err = exc
            print(f"[fetch_eurostat] {year}: {exc}")
            continue
        if len(df) >= 25:  # broad coverage: EU27-ish
            print(f"[fetch_eurostat] {year}: {len(df)} geographies")
            return df
        print(f"[fetch_eurostat] {year}: only {len(df)} geographies, trying older")
    if last_err:
        raise last_err
    raise RuntimeError("No Eurostat year returned broad coverage.")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Fetch Eurostat demo_pjan population.")
    p.add_argument("--year", type=int, default=None,
                   help="Reference year (default: try 2024, 2023, 2022).")
    p.add_argument("--out", type=Path, default=None,
                   help="Output CSV (default: data/sources/eurostat_population.csv).")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    years = (args.year,) if args.year else config.EUROSTAT_YEARS
    out = args.out or config.POPULATION_FILE

    df = fetch(years)
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out, index=False)
    print(f"[fetch_eurostat] wrote {out}  ({len(df)} rows, year "
          f"{sorted(df['year'].unique())})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
