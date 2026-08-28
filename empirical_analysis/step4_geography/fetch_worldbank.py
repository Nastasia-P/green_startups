"""One-shot fetch of World Bank population for T4.7.

Downloads indicator `SP.POP.TOTL` (total population) through the public World Bank v2
API for every start-up country and writes `data/sources/worldbank_population.csv` with
columns:
    iso2, country, year, population

World Bank covers all 46 start-up countries (including the UK, Russia, Gibraltar and
the micro-states) and returns a single, uniform latest year, so the per-capita
cross-check uses one consistent vintage and one source for every country. The
committed CSV is the runtime input for Step 4, so the analysis machine needs no network.
Re-run this only to refresh the reference year.

    python -m empirical_analysis.step4_geography.fetch_worldbank
    python -m empirical_analysis.step4_geography.fetch_worldbank --out data/sources/worldbank_population.csv
"""

from __future__ import annotations

import argparse
import json
import urllib.parse
import urllib.request
from pathlib import Path

import pandas as pd

from . import config


def _fetch_json(url: str, timeout: int = 60) -> list:
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
        return json.loads(resp.read().decode("utf-8"))


def fetch(country_to_iso2: dict[str, str] | None = None) -> pd.DataFrame:
    """Fetch the most recent SP.POP.TOTL value for each mapped country.

    One call covers all countries (semicolon-separated codes); `mrnev=1` asks the API
    for the most recent non-empty value per country. The World Bank returns the same
    latest year for every country, giving a consistent single vintage.
    """
    mapping = country_to_iso2 or config.COUNTRY_TO_ISO2
    iso_to_country = {v: k for k, v in mapping.items()}
    codes = ";".join(mapping.values())
    params = {"format": "JSON", "per_page": str(len(mapping) + 10), "mrnev": "1"}
    url = (f"{config.WORLDBANK_BASE_URL}/country/{codes}/indicator/"
           f"{config.WORLDBANK_INDICATOR}?{urllib.parse.urlencode(params)}")

    payload = _fetch_json(url)
    if not isinstance(payload, list) or len(payload) < 2 or payload[1] is None:
        raise RuntimeError(f"Unexpected World Bank response: {str(payload)[:200]}")

    rows = []
    for rec in payload[1]:
        value = rec.get("value")
        iso2 = ((rec.get("country") or {}).get("id") or "").upper()
        if value is None or iso2 not in iso_to_country:
            continue
        rows.append({
            "iso2": iso2,
            "country": iso_to_country[iso2],
            "year": int(rec["date"]),
            "population": int(value),
        })
    df = pd.DataFrame(rows).sort_values("country").reset_index(drop=True)

    missing = sorted(set(mapping) - set(df["country"]))
    years = sorted(df["year"].unique())
    print(f"[fetch_worldbank] {len(df)}/{len(mapping)} countries, year(s) {years}")
    if missing:
        print(f"[fetch_worldbank] no data for: {', '.join(missing)}")
    return df


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Fetch World Bank SP.POP.TOTL population.")
    p.add_argument("--out", type=Path, default=None,
                   help="Output CSV (default: data/sources/worldbank_population.csv).")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    out = args.out or config.POPULATION_FILE

    df = fetch()
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out, index=False)
    print(f"[fetch_worldbank] wrote {out}  ({len(df)} rows, year "
          f"{sorted(df['year'].unique())})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
