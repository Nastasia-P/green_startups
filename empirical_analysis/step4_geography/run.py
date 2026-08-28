"""Step 4 CLI: build the geography outputs (T4.6-T4.8, AP2, F4.2, F4.3).

Examples
--------
    python -m empirical_analysis.step4_geography.run --verbose
    python -m empirical_analysis.step4_geography.run \
        --firm-table data/outputs/company_analysis.parquet \
        --population data/sources/worldbank_population.csv \
        --output-dir data/outputs/chapter4
"""

from __future__ import annotations

import argparse
from pathlib import Path

from . import config
from . import sources
from .build import acceptance_report, build_all, write_outputs


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Step 4: geography (T4.6-T4.8, AP2, F4.2, F4.3).")
    p.add_argument("--firm-table", type=Path, default=None,
                   help="Path to company_analysis.parquet, or the Step 2 output "
                        "directory that contains it.")
    p.add_argument("--population", type=Path, default=None,
                   help="World Bank population CSV (default: data/sources/"
                        "worldbank_population.csv).")
    p.add_argument("--output-dir", type=Path, default=None,
                   help="Directory to write CSV outputs.")
    p.add_argument("--min-country-n", type=int, default=None,
                   help=f"Minimum start-ups per country (default {config.MIN_COUNTRY_N}).")
    p.add_argument("--min-city-n", type=int, default=None,
                   help=f"Minimum start-ups per city (default {config.MIN_CITY_N}).")
    p.add_argument("--verbose", action="store_true", help="Verbose logging.")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    config.VERBOSE = args.verbose

    firm_table = sources.resolve_firm_table(args.firm_table or config.FIRM_TABLE)
    population_path = args.population or config.POPULATION_FILE
    output_dir = args.output_dir or config.OUTPUT_DIR

    print("[step4] firm table :", firm_table)
    print("[step4] population :", population_path)
    print("[step4] output dir :", output_dir)

    firm = sources.load_firm_table(firm_table)
    population = sources.load_population(population_path)

    result = build_all(
        firm, population,
        min_country_n=args.min_country_n, min_city_n=args.min_city_n,
    )
    write_outputs(result, output_dir)

    print("\n[step4] acceptance report")
    for line in acceptance_report(result):
        print("  " + line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
