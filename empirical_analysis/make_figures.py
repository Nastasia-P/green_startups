"""Render the thesis figures as PNGs from the Chapter 4 output CSVs.

Five figures, each read from an existing CSV in ``data/outputs/chapter4`` and
written as a PNG to ``data/outputs/chapter4/figures``:

    Figure 1  founding-cohort composition        <- F4_01_green_share_by_cohort.csv
    Figure 4  first-5yr financing access          <- T_first5_access.csv
    Figure 5  first-5yr investor-type mix         <- T_first5_investor_type_participation.csv
    Figure 6  green share of firms vs capital     <- T4_26_green_share_firms_vs_capital.csv
    Figure S1 first-5yr public/private            <- T_first5_public_private.csv

Design rules (shared): green start-ups are drawn in GREEN and other European
start-ups in OTHER, consistently across every figure; percentage values are
printed on the bars; there are no figure titles and no source text on the plots
(only axis labels and a small legend).

The bar figures need ``matplotlib``. It is pinned in
``empirical_analysis/requirements.txt`` but is an optional heavy dependency, so
it is imported lazily inside the render functions -- the pure data-prep helpers
(``prep_*``) import only pandas and are unit-testable without it.

Usage
-----
    pip install -r empirical_analysis/requirements.txt   # matplotlib
    python -m empirical_analysis.make_figures            # all figures
    python -m empirical_analysis.make_figures --only 1 4 5
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

# --------------------------------------------------------------------------
# Paths + palette
# --------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parents[1]
INPUT_DIR = REPO_ROOT / "data" / "outputs" / "chapter4"
OUTPUT_DIR = INPUT_DIR / "figures"

# Consistent colours everywhere: green firms in green, others in grey;
# LIGHT_GREEN is the second green-firm measure in Figure 6 (share of capital).
GREEN = "#2e7d32"
OTHER = "#9e9e9e"
LIGHT_GREEN = "#a5d6a7"   # second green-firm measure in Figure 6 (share of capital)
GREEN_LABEL = "Green start-ups"
OTHER_LABEL = "Other European start-ups"

PNG_DPI = 200

# --- Fixed category orders / labels ---------------------------------------
FINANCING_ORDER = ["any_financing", "any_vc", "any_grant", "any_accelerator"]
FINANCING_LABELS = {
    "any_financing": "Any recorded financing",
    "any_vc": "Venture capital",
    "any_grant": "Grant",
    "any_accelerator": "Accelerator / incubator",
}
PUBPRIV_ORDER = ["any_public", "any_private",
                 "both_public_private", "same_deal_public_private"]
PUBPRIV_LABELS = {
    "any_public": "Any public investor",
    "any_private": "Any private investor",
    "both_public_private": "Both public and private",
    "same_deal_public_private": "Same-deal co-investment",
}
# The nine meaningful investor categories for Figure 5 (excludes Other/Unclassified).
INVESTOR_TYPES_9 = [
    "Accelerator/Incubator", "Independent VC", "Public/Government", "Corporate",
    "PE/Growth", "Angel", "Impact Investing", "Lender/Debt", "Family Office",
]
# Top-10 countries by green-start-up count (Figure 6), for reference/validation.
FIG6_N = 10


# ==========================================================================
# Pure data-prep helpers (no matplotlib) -- unit-testable
# ==========================================================================
def prep_cohort_composition(df: pd.DataFrame) -> pd.DataFrame:
    """Figure 1: cohort composition WITHIN each group (sums to 100% per group).

    Uses the n_green / n_others counts (NOT green_share, which is the within-
    cohort green share): green_pct = n_green / total green; other_pct =
    n_others / total other. Cohorts are kept in file (chronological) order.
    """
    out = df[["cohort", "n_green", "n_others"]].copy()
    tot_g = float(out["n_green"].sum())
    tot_o = float(out["n_others"].sum())
    out["green_pct"] = out["n_green"] / tot_g * 100.0
    out["other_pct"] = out["n_others"] / tot_o * 100.0
    return out.reset_index(drop=True)


def prep_financing_access(df: pd.DataFrame) -> pd.DataFrame:
    """Figure 4: four financing outcomes in fixed order, green vs other (%)."""
    d = df.set_index("financing_type")
    rows = []
    for key in FINANCING_ORDER:
        if key not in d.index:
            continue
        rows.append({
            "outcome": key,
            "label": FINANCING_LABELS[key],
            "green_pct": float(d.loc[key, "green_pct"]) * 100.0,
            "other_pct": float(d.loc[key, "other_pct"]) * 100.0,
        })
    return pd.DataFrame(rows)


def prep_public_private(df: pd.DataFrame) -> pd.DataFrame:
    """Figure S1: four public/private outcomes in fixed order, green vs other (%)."""
    d = df.set_index("outcome")
    rows = []
    for key in PUBPRIV_ORDER:
        if key not in d.index:
            continue
        rows.append({
            "outcome": key,
            "label": PUBPRIV_LABELS[key],
            "green_pct": float(d.loc[key, "green_share"]) * 100.0,
            "other_pct": float(d.loc[key, "other_share"]) * 100.0,
        })
    return pd.DataFrame(rows)


def prep_investor_type(df: pd.DataFrame) -> pd.DataFrame:
    """Figure 5: per investor type, green vs other (%), sorted by green desc.

    Restricted to the nine meaningful categories; the long-format input has one
    row per investor_type x group (green/other) with share_with_type.
    """
    wide = df.pivot_table(
        index="investor_type", columns="group", values="share_with_type",
        aggfunc="first",
    )
    rows = []
    for t in INVESTOR_TYPES_9:
        if t not in wide.index:
            continue
        rows.append({
            "investor_type": t,
            "green_pct": float(wide.loc[t].get("green", float("nan"))) * 100.0,
            "other_pct": float(wide.loc[t].get("other", float("nan"))) * 100.0,
        })
    out = pd.DataFrame(rows)
    return out.sort_values("green_pct", ascending=False).reset_index(drop=True)


def prep_firms_vs_capital(df: pd.DataFrame, n: int = FIG6_N) -> pd.DataFrame:
    """Figure 6: top-n countries by n_green, green share of firms vs of capital (%)."""
    top = df.sort_values("n_green", ascending=False).head(n).copy()
    top["firm_share_pct"] = top["green_firm_share"] * 100.0
    top["capital_share_pct"] = top["green_funding_share_total_raised"] * 100.0
    return top[["country", "n_green", "firm_share_pct", "capital_share_pct"]].reset_index(drop=True)


# ==========================================================================
# Rendering helpers (matplotlib imported lazily)
# ==========================================================================
def _plt():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    return plt


def _grouped_vbars(labels, green_vals, other_vals, ylabel, out_path):
    """Vertical grouped bars: green vs other, value labels above each bar."""
    plt = _plt()
    x = range(len(labels))
    w = 0.4
    fig, ax = plt.subplots(figsize=(max(6.0, 1.6 * len(labels)), 4.8))
    gb = ax.bar([i - w / 2 for i in x], green_vals, width=w,
                label=GREEN_LABEL, color=GREEN)
    ob = ax.bar([i + w / 2 for i in x], other_vals, width=w,
                label=OTHER_LABEL, color=OTHER)
    for bars in (gb, ob):
        for b in bars:
            h = b.get_height()
            ax.annotate(f"{h:.1f}", (b.get_x() + b.get_width() / 2, h),
                        xytext=(0, 3), textcoords="offset points",
                        ha="center", va="bottom", fontsize=8)
    ax.set_ylabel(ylabel)
    ax.set_xticks(list(x))
    ax.set_xticklabels(labels, rotation=15, ha="right")
    top = max(list(green_vals) + list(other_vals))
    ax.set_ylim(0, top * 1.15)
    ax.legend(frameon=False)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(out_path, dpi=PNG_DPI)
    plt.close(fig)
    return out_path


def _grouped_hbars(labels, series, xlabel, out_path, colors, legend_labels):
    """Horizontal grouped bars (2 series). First label ends up on top."""
    plt = _plt()
    y = list(range(len(labels)))[::-1]  # first row at the top
    h = 0.4
    fig, ax = plt.subplots(figsize=(8.0, max(4.5, 0.62 * len(labels) + 1.2)))
    offsets = (h / 2, -h / 2)
    all_vals = []
    for vals, off, color, lab in zip(series, offsets, colors, legend_labels):
        bars = ax.barh([yi + off for yi in y], vals, height=h, label=lab, color=color)
        all_vals += list(vals)
        for b in bars:
            wv = b.get_width()
            ax.annotate(f"{wv:.1f}", (wv, b.get_y() + b.get_height() / 2),
                        xytext=(3, 0), textcoords="offset points",
                        ha="left", va="center", fontsize=8)
    ax.set_yticks(y)
    ax.set_yticklabels(labels)
    ax.set_xlabel(xlabel)
    ax.set_xlim(0, max(all_vals) * 1.15)
    ax.legend(frameon=False, loc="lower right")
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(out_path, dpi=PNG_DPI)
    plt.close(fig)
    return out_path


# ==========================================================================
# Figures
# ==========================================================================
def figure1(input_dir: Path, output_dir: Path) -> Path:
    df = pd.read_csv(input_dir / "F4_01_green_share_by_cohort.csv")
    comp = prep_cohort_composition(df)
    return _grouped_vbars(
        comp["cohort"].tolist(), comp["green_pct"].tolist(), comp["other_pct"].tolist(),
        "Share of group (%)", output_dir / "fig1_founding_cohort_composition.png",
    )


def figure4(input_dir: Path, output_dir: Path) -> Path:
    df = pd.read_csv(input_dir / "T_first5_access.csv")
    acc = prep_financing_access(df)
    return _grouped_vbars(
        acc["label"].tolist(), acc["green_pct"].tolist(), acc["other_pct"].tolist(),
        "Share of eligible firms (%)", output_dir / "fig4_first5_financing_access.png",
    )


def figureS1(input_dir: Path, output_dir: Path) -> Path:
    df = pd.read_csv(input_dir / "T_first5_public_private.csv")
    pp = prep_public_private(df)
    return _grouped_vbars(
        pp["label"].tolist(), pp["green_pct"].tolist(), pp["other_pct"].tolist(),
        "Share of firms with recorded investors (%)",
        output_dir / "figS1_first5_public_private.png",
    )


def figure5(input_dir: Path, output_dir: Path) -> Path:
    df = pd.read_csv(input_dir / "T_first5_investor_type_participation.csv")
    it = prep_investor_type(df)
    return _grouped_hbars(
        it["investor_type"].tolist(), (it["green_pct"].tolist(), it["other_pct"].tolist()),
        "Share of firms with recorded investors (%)",
        output_dir / "fig5_first5_investor_type_participation.png",
        colors=(GREEN, OTHER), legend_labels=(GREEN_LABEL, OTHER_LABEL),
    )


def figure6(input_dir: Path, output_dir: Path) -> Path:
    df = pd.read_csv(input_dir / "T4_26_green_share_firms_vs_capital.csv")
    fc = prep_firms_vs_capital(df)
    return _grouped_hbars(
        fc["country"].tolist(),
        (fc["firm_share_pct"].tolist(), fc["capital_share_pct"].tolist()),
        "Share within country (%)",
        output_dir / "fig6_green_share_firms_vs_capital.png",
        colors=(GREEN, LIGHT_GREEN),
        legend_labels=("Green share of firms", "Green share of recorded capital"),
    )


# ==========================================================================
# Orchestration
# ==========================================================================
FIGURES = {
    "1": ("Figure 1 - founding-cohort composition", figure1),
    "4": ("Figure 4 - first-5yr financing access", figure4),
    "5": ("Figure 5 - first-5yr investor-type mix", figure5),
    "6": ("Figure 6 - green share of firms vs capital", figure6),
    "S1": ("Figure S1 - first-5yr public/private", figureS1),
}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Render the Chapter 4 thesis figures as PNGs. Needs matplotlib; "
                    "install via `pip install -r empirical_analysis/requirements.txt`."
    )
    p.add_argument("--input-dir", type=Path, default=None,
                   help="Directory with the source CSVs (default data/outputs/chapter4).")
    p.add_argument("--output-dir", type=Path, default=None,
                   help="Directory for the PNGs (default <input-dir>/figures).")
    p.add_argument("--only", nargs="+", choices=list(FIGURES),
                   help="Render only these figures (e.g. --only 1 4 5).")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    input_dir = args.input_dir or INPUT_DIR
    output_dir = args.output_dir or (input_dir / "figures")
    output_dir.mkdir(parents=True, exist_ok=True)

    selected = args.only or list(FIGURES)
    print(f"[figures] input : {input_dir}")
    print(f"[figures] output: {output_dir}")

    failures = 0
    for key in selected:
        label, fn = FIGURES[key]
        try:
            out = fn(input_dir, output_dir)
            print(f"[figures] {label}: wrote {out.name}")
        except ImportError as exc:
            failures += 1
            print(f"[figures] {label}: SKIPPED (missing dependency: {exc}). "
                  "Install matplotlib and re-run.")
        except Exception as exc:  # pragma: no cover - surfaced to the user
            failures += 1
            print(f"[figures] {label}: FAILED ({type(exc).__name__}: {exc})")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
