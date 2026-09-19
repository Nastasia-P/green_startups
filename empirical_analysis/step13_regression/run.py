"""Step 13 CLI: build the common-horizon financing regression tables.

Examples
--------
    python -m empirical_analysis.step13_regression.run --verbose
    python -m empirical_analysis.step13_regression.run \
        --firm-panel data/outputs/chapter4/first5_analysis.parquet \
        --output-dir data/outputs/chapter4 \
        --industry group

Requires `first5_analysis.parquet`, produced by:
    python -m empirical_analysis.step5b_fixed_horizon.run
"""

from __future__ import annotations

import argparse
from pathlib import Path

from . import config
from . import sources
from .build import HAVE_STATSMODELS, acceptance_report, build_all, write_outputs


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Step 13: common-horizon financing regressions "
                    "(five-year window; access, timing, capital)."
    )
    p.add_argument("--firm-panel", type=Path, default=None,
                   help="Path to first5_analysis.parquet (Step 5b output), or "
                        "the Step 5b output directory that contains it.")
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

    firm_panel_path = sources.resolve_firm_panel(args.firm_panel or config.FIRM_PANEL)
    output_dir = args.output_dir or config.OUTPUT_DIR

    print("[step13] firm panel :", firm_panel_path)
    print("[step13] output dir :", output_dir)
    print("[step13] industry FE:", industry_col)

    panel = sources.load_firm_panel(firm_panel_path)
    if industry_col not in panel.columns:
        print(f"[step13] ERROR: {industry_col!r} not found in {firm_panel_path}. "
              "Re-run step5b_fixed_horizon, or pass --industry group.")
        return 1

    result = build_all(panel, industry_col=industry_col)
    write_outputs(result, output_dir)

    diag = result.diagnostics
    print("\n[step13] sample summary (common horizon)")
    print(f"  eligible firms            : {diag.get('n_eligible')} "
          f"(green={diag.get('n_eligible_green')}, other={diag.get('n_eligible_other')})")
    print(f"  timing observed           : {diag.get('timing_observed')}")
    print(f"  capital observed/eligible : "
          f"{diag.get('capital_observed')} / {diag.get('n_eligible')}")

    print("\n[step13] green coefficient path (1) -> (4)")
    for name in (config.OUT_ACCESS, config.OUT_TIMING, config.OUT_CAPITAL):
        df = result.tables.get(name)
        if df is None or not len(df):
            continue
        for outcome, grp in df.groupby("outcome"):
            path = ", ".join(
                f"{config.SPEC_COLUMN_LABEL[s]}="
                f"{grp[grp['spec'] == s]['coef'].iloc[0]:+.4f}"
                f"{grp[grp['spec'] == s]['stars'].iloc[0]}"
                for s, _ in config.SPECS if (grp["spec"] == s).any()
            )
            print(f"  {outcome:<32} {path}")

    print("\n[step13] acceptance report")
    for line in acceptance_report(result):
        print("  " + line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
