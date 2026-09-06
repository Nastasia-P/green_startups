"""Step 13 CLI: build the exploratory regression tables.

Examples
--------
    python -m empirical_analysis.step13_regression.run --verbose
    python -m empirical_analysis.step13_regression.run \
        --firm-table data/outputs/company_analysis.parquet \
        --clean-dir data/outputs/clean_tables \
        --output-dir data/outputs/chapter4 \
        --industry group
"""

from __future__ import annotations

import argparse
from pathlib import Path

from . import config
from . import sources
from .build import HAVE_STATSMODELS, acceptance_report, build_all, write_outputs


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Step 13: exploratory composition-adjusted regressions."
    )
    p.add_argument("--firm-table", type=Path, default=None,
                   help="Path to company_analysis.parquet, or the Step 2 output "
                        "directory that contains it.")
    p.add_argument("--clean-dir", type=Path, default=None,
                   help="Directory with Step 1 clean parquet tables (deals_clean, "
                        "for the family-3 fixed-horizon capital).")
    p.add_argument("--output-dir", type=Path, default=None,
                   help="Directory to write CSV outputs.")
    p.add_argument("--industry", choices=["group", "code"], default="group",
                   help="Firm-level industry FE column: primary_industry_group "
                        "(default) or primary_industry_code.")
    p.add_argument("--verbose", action="store_true", help="Verbose logging.")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    config.VERBOSE = args.verbose

    if not HAVE_STATSMODELS:
        print("[step13] ERROR: statsmodels is not installed.")
        print("[step13] install it with: python -m pip install --user statsmodels")
        return 1

    industry_col = (
        config.INDUSTRY_COL_GROUP if args.industry == "group"
        else config.INDUSTRY_COL_CODE
    )

    firm_table = sources.resolve_firm_table(args.firm_table or config.FIRM_TABLE)
    clean_dir = args.clean_dir or config.CLEAN_DIR
    output_dir = args.output_dir or config.OUTPUT_DIR

    print("[step13] firm table :", firm_table)
    print("[step13] clean dir  :", clean_dir)
    print("[step13] output dir :", output_dir)
    print("[step13] industry FE:", industry_col)

    firm = sources.load_firm_table(firm_table)
    deals = sources.load_deals_clean(clean_dir)

    result = build_all(firm, deals, industry_col=industry_col)
    write_outputs(result, output_dir)

    diag = result.diagnostics
    print("\n[step13] sample summary")
    print(f"  firms total              : {int(diag.get('n_firms_total', 0))}")
    print(f"  timing observed          : {diag.get('timing_observed')}")
    print(f"  capital eligible/observed: "
          f"{int(diag.get('capital_eligible', 0))} / "
          f"{int(diag.get('capital_observed', 0))}")

    print("\n[step13] green coefficient path (M0 -> M3)")
    for name in (config.OUT_ACCESS, config.OUT_TIMING, config.OUT_CAPITAL):
        df = result.tables.get(name)
        if df is None or not len(df):
            continue
        for outcome, grp in df.groupby("outcome"):
            path = ", ".join(
                f"{m}={grp[grp['model'] == m]['green_coef'].iloc[0]:+.4f}"
                for m in ("M0", "M1", "M2", "M3") if (grp["model"] == m).any()
            )
            print(f"  {outcome:<32} {path}")

    print("\n[step13] acceptance report")
    for line in acceptance_report(result):
        print("  " + line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
