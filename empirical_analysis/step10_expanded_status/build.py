"""Step 10 build logic: the expanded start-up-status population.

Starts from the raw European source, keeps the baseline's age criterion, drops
the ownership and operating-status restrictions, and broadens the Universe rule
(admit M&A / Publicly Listed; exclude only Other Private Companies). Every firm
gets a traceable reason for baseline membership/non-membership, and the existing
green methodology is applied for a green-vs-other comparison.

Read-only: it never writes the baseline population, company_analysis, or any
Step 1-8 output.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from . import config

# The classifier modules live at the repository root; make them importable.
if str(config.REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(config.REPO_ROOT))

from classify_startups_green_algorithmic import (  # noqa: E402
    build_trie,
    vertical_matches,
)
from classify_startups_green_strong_terms import (  # noqa: E402
    load_strong_phrases,
    load_strong_tokens,
    phrase_matches,
    token_matches,
)

# Mutually-exclusive baseline-exclusion group labels.
GROUPS_OUTSIDE = [
    "out_of_business_or_bankrupt",
    "acquired_or_merged",
    "public_or_exited",
    "universe_exit_marker_only",
    "multiple_exit_statuses",
    "other",
]


@dataclass
class Step10Result:
    expanded: pd.DataFrame = field(default_factory=pd.DataFrame)
    flow: pd.DataFrame = field(default_factory=pd.DataFrame)
    outcomes: pd.DataFrame = field(default_factory=pd.DataFrame)
    exclusion: pd.DataFrame = field(default_factory=pd.DataFrame)
    by_cohort: pd.DataFrame = field(default_factory=pd.DataFrame)
    universe_diag: pd.DataFrame = field(default_factory=pd.DataFrame)
    audit: pd.DataFrame = field(default_factory=pd.DataFrame)
    report_text: str = ""
    young: pd.DataFrame = field(default_factory=pd.DataFrame)  # kept for diagnostics


# --------------------------------------------------------------------------
# Loading (read-only)
# --------------------------------------------------------------------------
def load_source(source_path: Path) -> pd.DataFrame:
    """Read the needed columns from the raw European source (all strings)."""
    if not source_path.exists():
        raise FileNotFoundError(f"Raw source not found: {source_path}")
    import pyarrow as pa
    import pyarrow.csv as pacsv

    table = pacsv.read_csv(
        str(source_path),
        read_options=pacsv.ReadOptions(use_threads=True),
        convert_options=pacsv.ConvertOptions(
            include_columns=config.SOURCE_USECOLS,
            column_types={c: pa.string() for c in config.SOURCE_USECOLS},
            strings_can_be_null=False,
        ),
    )
    return table.to_pandas()


def load_baseline(population_path: Path) -> pd.DataFrame:
    """Canonical baseline labels; never modified."""
    if not population_path.exists():
        raise FileNotFoundError(f"Baseline population not found: {population_path}")
    pk = pd.read_parquet(population_path)
    required = {"company_id", "green", "green_stage"}
    missing = required.difference(pk.columns)
    if missing:
        raise ValueError(f"Baseline missing columns: {sorted(missing)}")
    pk = pk[["company_id", "green", "green_stage"]].copy()
    pk = pk.rename(columns={"green": "green_canon", "green_stage": "green_stage_canon"})
    pk["company_id"] = pk["company_id"].astype("string")
    return pk


# --------------------------------------------------------------------------
# Filtering
# --------------------------------------------------------------------------
def apply_age_filter(df: pd.DataFrame) -> pd.DataFrame:
    """Baseline Stage 1: valid YearFounded and age <= MAX_AGE."""
    year = pd.to_numeric(df["YearFounded"], errors="coerce")
    age = config.CURRENT_YEAR - year
    keep = year.notna() & (age <= config.MAX_AGE)
    out = df[keep].copy()
    out["year_founded"] = year[keep].astype("Int64")
    out["age_years"] = age[keep].astype("Int64")
    return out


def _universe_tokens(value: str) -> list[str]:
    return [t.strip() for t in value.split(",")] if value else []


def apply_step10_universe(young: pd.DataFrame) -> pd.DataFrame:
    """Step 10 Universe rule: non-empty and every token in the permitted 6-set
    (equivalently, does not contain Other Private Companies)."""
    perms = config.STEP10_UNIVERSE

    def ok(value: str) -> bool:
        toks = _universe_tokens(value)
        return bool(toks) and all(t in perms for t in toks)

    keep = young["Universe"].map(ok)
    return young[keep].copy()


# --------------------------------------------------------------------------
# Green classification (existing methodology)
# --------------------------------------------------------------------------
def _classify_stage(kw: str, desc: str, vert: str, tokens: frozenset[str], trie: dict) -> str:
    if vertical_matches(vert or ""):
        return "vertical"
    if token_matches(kw or "", desc or "", tokens):
        return "token"
    if phrase_matches(kw or "", desc or "", trie):
        return "phrase"
    return "none"


def classify_expanded(
    expanded: pd.DataFrame, tokens: frozenset[str], trie: dict
) -> pd.DataFrame:
    """Apply the sequential vertical->token->phrase cascade to every firm."""
    df = expanded
    stages = [
        _classify_stage(kw, desc, vert, tokens, trie)
        for kw, desc, vert in zip(
            df["Keywords"].tolist(), df["Description"].tolist(), df["Verticals"].tolist()
        )
    ]
    df["green_stage_applied"] = pd.array(stages, dtype="string")
    df["green_applied"] = (df["green_stage_applied"] != "none").astype("int64")
    return df


# --------------------------------------------------------------------------
# Flags, exclusion decomposition, hybrid green, cohort
# --------------------------------------------------------------------------
def _cohort(year: pd.Series) -> pd.Series:
    out = pd.Series(pd.NA, index=year.index, dtype="string")
    y = pd.to_numeric(year, errors="coerce")
    for lo, hi, label in config.COHORT_BINS:
        out = out.mask((y >= lo) & (y <= hi), label)
    return out


def derive_flags(expanded: pd.DataFrame, baseline: pd.DataFrame) -> pd.DataFrame:
    """Attach baseline membership, raw status flags, the exclusion decomposition,
    the grouped category, hybrid green labels, and cohort."""
    df = expanded.merge(baseline, on="company_id", how="left")

    os_ = df["OwnershipStatus"]
    bs = df["BusinessStatus"]
    toks = df["Universe"].map(_universe_tokens)

    df["has_ma_universe"] = toks.map(lambda t: "M&A" in t)
    df["has_publicly_listed_universe"] = toks.map(lambda t: "Publicly Listed" in t)
    df["is_acquired_or_merged"] = os_.isin(config.OWNERSHIP_ACQUIRED_MERGED)
    df["is_public_owner"] = os_ == config.OWNERSHIP_PUBLIC
    df["is_public"] = df["is_public_owner"] | df["has_publicly_listed_universe"]
    df["is_out_of_business"] = bs == config.BUSINESS_OUT_OF_BUSINESS
    df["is_out_of_business_owner"] = os_ == config.OWNERSHIP_OUT_OF_BUSINESS
    df["is_bankruptcy"] = bs.isin(config.BUSINESS_BANKRUPTCY)
    df["is_other_nonoperating"] = df["is_out_of_business_owner"] & ~(
        df["is_out_of_business"] | df["is_bankruptcy"]
    )

    # Baseline membership: authoritative from the canonical join.
    df["in_baseline_2026"] = df["green_canon"].notna()
    df["outside_baseline_2026"] = ~df["in_baseline_2026"]

    # Exclusion decomposition: which baseline filter(s) the firm fails.
    df["fails_ownership"] = ~os_.isin(config.BASELINE_OWNERSHIP)
    df["fails_universe"] = df["has_ma_universe"] | df["has_publicly_listed_universe"]
    df["fails_alive"] = bs.isin(config.DEAD_BUSINESS_STATUSES)

    def reasons(row) -> str:
        r = []
        if row["fails_ownership"]:
            r.append("ownership")
        if row["fails_universe"]:
            r.append("universe")
        if row["fails_alive"]:
            r.append("business_status")
        return " | ".join(r)

    df["exclusion_reasons"] = df.apply(reasons, axis=1)
    df["n_exclusion_reasons"] = (
        df["fails_ownership"].astype(int)
        + df["fails_universe"].astype(int)
        + df["fails_alive"].astype(int)
    )

    # Mutually-exclusive grouped category (raw flags remain primary).
    failure = df["is_out_of_business"] | df["is_bankruptcy"] | df["is_out_of_business_owner"]
    acq = df["is_acquired_or_merged"]
    pub = df["is_public"]
    count = failure.astype(int) + acq.astype(int) + pub.astype(int)
    df["baseline_exclusion_group"] = np.select(
        [
            df["in_baseline_2026"].to_numpy(),
            (count >= 2).to_numpy(),
            failure.to_numpy(),
            acq.to_numpy(),
            pub.to_numpy(),
            df["fails_universe"].to_numpy(),
        ],
        [
            "baseline_2026",
            "multiple_exit_statuses",
            "out_of_business_or_bankrupt",
            "acquired_or_merged",
            "public_or_exited",
            "universe_exit_marker_only",
        ],
        default="other",
    )

    # Hybrid green: canonical for baseline firms, applied for outside firms.
    in_base = df["in_baseline_2026"].to_numpy()
    df["green"] = np.where(
        in_base, df["green_canon"].fillna(0).to_numpy(), df["green_applied"].to_numpy()
    ).astype("int64")
    df["green_stage"] = pd.array(
        np.where(in_base, df["green_stage_canon"].to_numpy(), df["green_stage_applied"].to_numpy()),
        dtype="string",
    )

    df["cohort"] = _cohort(df["year_founded"])
    return df


# --------------------------------------------------------------------------
# Tables
# --------------------------------------------------------------------------
def _share(n: int, d: int) -> float:
    return round(100.0 * n / d, 1) if d else float("nan")


def build_flow(df: pd.DataFrame) -> pd.DataFrame:
    """Population -> baseline vs outside decomposition, with green/other split."""

    def row(label: str, sub: pd.DataFrame) -> dict:
        total = len(sub)
        g = int((sub["green"] == 1).sum())
        return {
            "population_status": label,
            "total_n": total,
            "green_n": g,
            "other_n": total - g,
            "green_share_pct": _share(g, total),
        }

    outside = df[df["outside_baseline_2026"]]
    rows = [
        row("expanded_step10", df),
        row("still_in_baseline_2026", df[df["in_baseline_2026"]]),
        row("outside_baseline", outside),
    ]
    for grp in GROUPS_OUTSIDE:
        rows.append(row(f"  {grp}", outside[outside["baseline_exclusion_group"] == grp]))
    return pd.DataFrame(rows)


def build_outcomes(df: pd.DataFrame) -> pd.DataFrame:
    """Membership + exit-group composition, green vs other columns (over expanded)."""
    green = df[df["green"] == 1]
    other = df[df["green"] == 0]
    ng, no = len(green), len(other)

    def line(label: str, gmask, omask) -> dict:
        gn = int(gmask.sum())
        on = int(omask.sum())
        return {
            "category": label,
            "green_n": gn,
            "green_pct": _share(gn, ng),
            "other_n": on,
            "other_pct": _share(on, no),
        }

    rows = [
        line("in_baseline_2026", green["in_baseline_2026"], other["in_baseline_2026"]),
        line("outside_baseline", green["outside_baseline_2026"], other["outside_baseline_2026"]),
    ]
    for grp in GROUPS_OUTSIDE:
        rows.append(
            line(
                grp,
                green["baseline_exclusion_group"] == grp,
                other["baseline_exclusion_group"] == grp,
            )
        )
    out = pd.DataFrame(rows)
    # Headline: share of each cohort still in the baseline (survivorship of the snapshot).
    out.attrs["green_share_in_baseline"] = _share(int((green["in_baseline_2026"]).sum()), ng)
    out.attrs["other_share_in_baseline"] = _share(int((other["in_baseline_2026"]).sum()), no)
    return out


def build_exclusion(df: pd.DataFrame) -> pd.DataFrame:
    """Green vs other across exclusion criteria, restricted to outside-baseline firms."""
    outside = df[df["outside_baseline_2026"]]
    g = outside[outside["green"] == 1]
    o = outside[outside["green"] == 0]
    n_all, n_g, n_o = len(outside), len(g), len(o)

    flag_rows = [
        "fails_ownership", "fails_universe", "fails_alive",
        "is_acquired_or_merged", "is_public", "is_out_of_business",
        "is_bankruptcy", "has_ma_universe", "has_publicly_listed_universe",
    ]
    rows = []
    for f in flag_rows:
        a = int(outside[f].sum())
        gg = int(g[f].sum())
        oo = int(o[f].sum())
        rows.append(
            {
                "criterion": f,
                "kind": "flag (non-exclusive)",
                "all_outside_n": a, "all_outside_pct": _share(a, n_all),
                "green_n": gg, "green_pct": _share(gg, n_g),
                "other_n": oo, "other_pct": _share(oo, n_o),
            }
        )
    for grp in GROUPS_OUTSIDE:
        a = int((outside["baseline_exclusion_group"] == grp).sum())
        gg = int((g["baseline_exclusion_group"] == grp).sum())
        oo = int((o["baseline_exclusion_group"] == grp).sum())
        rows.append(
            {
                "criterion": grp,
                "kind": "group (exclusive)",
                "all_outside_n": a, "all_outside_pct": _share(a, n_all),
                "green_n": gg, "green_pct": _share(gg, n_g),
                "other_n": oo, "other_pct": _share(oo, n_o),
            }
        )
    return pd.DataFrame(rows)


def build_by_cohort(df: pd.DataFrame) -> pd.DataFrame:
    """Status composition by founding cohort, green vs other."""
    rows = []
    cohorts = [label for _, _, label in config.COHORT_BINS]
    for cohort in cohorts:
        sub_c = df[df["cohort"] == cohort]
        for grp_label, sub in (("green", sub_c[sub_c["green"] == 1]), ("other", sub_c[sub_c["green"] == 0])):
            n = len(sub)
            n_base = int(sub["in_baseline_2026"].sum())
            n_out = n - n_base
            rec = {
                "cohort": cohort,
                "group": grp_label,
                "n_expanded": n,
                "n_in_baseline": n_base,
                "share_in_baseline_pct": _share(n_base, n),
                "n_outside": n_out,
            }
            for g in GROUPS_OUTSIDE:
                rec[f"n_{g}"] = int((sub["baseline_exclusion_group"] == g).sum())
            rows.append(rec)
    return pd.DataFrame(rows)


def build_universe_diag(young: pd.DataFrame) -> pd.DataFrame:
    """Raw Universe/Ownership/Business value counts on the age-filtered population."""
    rows = []
    perms = config.STEP10_UNIVERSE

    def norm_uni(v: str) -> str:
        toks = _universe_tokens(v)
        return ", ".join(sorted(toks)) if toks else "<empty>"

    uni = young["Universe"].map(norm_uni).value_counts()
    for value, cnt in uni.items():
        toks = [t.strip() for t in value.split(",")] if value != "<empty>" else []
        contains_opc = config.EXCLUDED_UNIVERSE in toks
        retained = bool(toks) and all(t in perms for t in toks)
        rows.append(
            {
                "field": "Universe",
                "value": value,
                "count": int(cnt),
                "contains_other_private_companies": contains_opc,
                "retained_by_step10": retained,
            }
        )
    for fld in ("OwnershipStatus", "BusinessStatus"):
        vc = young[fld].replace("", "<empty>").value_counts()
        for value, cnt in vc.items():
            rows.append(
                {
                    "field": fld,
                    "value": value,
                    "count": int(cnt),
                    "contains_other_private_companies": "",
                    "retained_by_step10": "",
                }
            )
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------
# Audit + report
# --------------------------------------------------------------------------
def build_audit(
    df: pd.DataFrame,
    young: pd.DataFrame,
    raw_rows: int,
    baseline: pd.DataFrame,
    tokens: frozenset[str],
    phrases: dict,
    paths: dict[str, Path],
) -> pd.DataFrame:
    in_base = df[df["in_baseline_2026"]]
    baseline_green = int((in_base["green"] == 1).sum())
    baseline_other = int((in_base["green"] == 0).sum())
    opc_in_expanded = int(df["Universe"].map(lambda v: config.EXCLUDED_UNIVERSE in _universe_tokens(v)).sum())
    ma_pub_retained = int((df["has_ma_universe"] | df["has_publicly_listed_universe"]).sum())
    nonop_retained = int((df["is_out_of_business"] | df["is_bankruptcy"]).sum())

    # Membership must equal "passes all three baseline filters".
    passes_all = ~df["fails_ownership"] & ~df["fails_universe"] & ~df["fails_alive"]
    membership_mismatch = int((df["in_baseline_2026"] != passes_all).sum())

    # All canonical baseline ids present in the expanded population.
    expanded_ids = set(df["company_id"].tolist())
    baseline_ids = set(baseline["company_id"].tolist())
    baseline_present = len(baseline_ids & expanded_ids)

    # Canonical-vs-applied green drift on the baseline (QA of the hybrid choice).
    applied_agree = int((in_base["green_applied"] == in_base["green"]).sum())

    dup = int(df["company_id"].duplicated().sum())

    rows = [
        ("raw_rows", config.RAW_ROWS, raw_rows),
        ("age_filtered", config.AGE_FILTERED, len(young)),
        ("expanded_step10", config.EXPANDED, len(df)),
        ("baseline_in_expanded", config.BASELINE, int(df["in_baseline_2026"].sum())),
        ("outside_baseline", config.OUTSIDE, int(df["outside_baseline_2026"].sum())),
        ("baseline_green", config.GREEN_TOTAL, baseline_green),
        ("baseline_other", config.OTHER_TOTAL, baseline_other),
        ("all_baseline_ids_present", config.BASELINE, baseline_present),
        ("other_private_companies_in_expanded", 0, opc_in_expanded),
        ("membership_matches_filters", 0, membership_mismatch),
        ("duplicate_company_ids", 0, dup),
        ("ma_or_publicly_listed_retained", ">0", ma_pub_retained),
        ("nonoperating_retained", ">0", nonop_retained),
        ("baseline_applied_equals_canonical", config.BASELINE, applied_agree),
        ("labels_modified", "False", "False"),
        ("vocab_standalone_used", 68, len(tokens)),
        ("vocab_standalone_thesis_ref", config.THESIS_STANDALONE, config.THESIS_STANDALONE),
        ("vocab_mwe_used", 456, len(phrases)),
        ("vocab_mwe_thesis_ref", config.THESIS_MWE, config.THESIS_MWE),
        ("source_path", "", str(paths["source"])),
        ("population_path", "", str(paths["population"])),
        ("standalone_path", "", str(paths["standalone"])),
        ("phrases_path", "", str(paths["phrases"])),
        ("out_dir", "", str(paths["out_dir"])),
    ]
    return pd.DataFrame(rows, columns=["key", "expected", "observed"])


def build_report(result: Step10Result, paths: dict[str, Path]) -> str:
    df = result.expanded
    flow = result.flow.set_index("population_status")
    exp_n = len(df)
    base_n = int(df["in_baseline_2026"].sum())
    out_n = int(df["outside_baseline_2026"].sum())
    g_in = result.outcomes.attrs.get("green_share_in_baseline")
    o_in = result.outcomes.attrs.get("other_share_in_baseline")

    lines = [
        "STEP 10 - EXPANDED START-UP-STATUS POPULATION (supplementary sensitivity)",
        "=" * 72,
        "Read-only exercise: it modifies no existing classification or output.",
        "Keeps Europe + valid founding year + age<=10; drops the current-ownership",
        "and operating-status restrictions; Universe excludes only Other Private",
        "Companies (admits M&A / Publicly Listed).",
        "",
        "INPUTS",
        f"  source     : {paths['source']}",
        f"  population : {paths['population']}",
        f"  standalone : {paths['standalone']}",
        f"  phrases    : {paths['phrases']}",
        "",
        "POPULATION FLOW",
        f"  age-filtered (last 10 years) : {len(result.young):,}  (expect {config.AGE_FILTERED:,})",
        f"  expanded Step 10 population  : {exp_n:,}  (expect {config.EXPANDED:,})",
        f"    still in 2026 baseline     : {base_n:,}  "
        f"(green {int((df[df['in_baseline_2026']]['green']==1).sum()):,})",
        f"    outside baseline           : {out_n:,}  "
        f"(green {int((df[df['outside_baseline_2026']]['green']==1).sum()):,})",
        "",
        "OUTSIDE-BASELINE BY GROUP (exclusive)",
    ]
    for grp in GROUPS_OUTSIDE:
        key = f"  {grp}"
        if key in flow.index:
            r = flow.loc[key]
            lines.append(
                f"    {grp:<28} n={int(r['total_n']):>6,}  "
                f"green={int(r['green_n']):>5,}  other={int(r['other_n']):>6,}"
            )
    lines += [
        "",
        "SURVIVORSHIP OF THE SNAPSHOT (share of the expanded cohort still in baseline)",
        f"    green start-ups : {g_in}%",
        f"    other firms     : {o_in}%",
        "",
        "INTERPRETATION BOUNDARY",
        "    This is a current-snapshot (7 Jul 2026 extract) status composition, not a",
        "    survival panel. It shows observable firms outside the 2026 baseline via",
        "    current exit/non-operation status; it is not a historical start-up",
        "    population, not a longitudinal survival/failure rate, and implies no causal",
        "    claim about green vs other survival.",
        "",
        f"OUTPUT DIR: {paths['out_dir']}",
    ]
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------
# Orchestration
# --------------------------------------------------------------------------
def run_diagnostic(
    source_path: Path,
    population_path: Path,
    standalone_path: Path,
    phrases_path: Path,
    out_dir: Path,
) -> Step10Result:
    src = load_source(source_path)
    raw_rows = len(src)
    young = apply_age_filter(src)
    expanded = apply_step10_universe(young)
    expanded["company_id"] = expanded["CompanyID"].astype("string")

    baseline = load_baseline(population_path)
    tokens = load_strong_tokens(standalone_path)
    phrases = load_strong_phrases(phrases_path)
    trie = build_trie({norm: norm for norm in phrases})

    expanded = classify_expanded(expanded, tokens, trie)
    expanded = derive_flags(expanded, baseline)

    paths = {
        "source": source_path,
        "population": population_path,
        "standalone": standalone_path,
        "phrases": phrases_path,
        "out_dir": out_dir,
    }
    result = Step10Result(
        expanded=expanded,
        flow=build_flow(expanded),
        outcomes=build_outcomes(expanded),
        exclusion=build_exclusion(expanded),
        by_cohort=build_by_cohort(expanded),
        universe_diag=build_universe_diag(young),
        audit=build_audit(expanded, young, raw_rows, baseline, tokens, phrases, paths),
        young=young,
    )
    result.report_text = build_report(result, paths)
    return result


# Columns written to the firm-level parquet (raw fields + diagnostics).
_OUTPUT_COLUMNS = [
    "company_id", "CompanyName", "year_founded", "age_years", "cohort",
    "OwnershipStatus", "BusinessStatus", "Universe", "HQCountry",
    "in_baseline_2026", "outside_baseline_2026", "baseline_exclusion_group",
    "fails_ownership", "fails_universe", "fails_alive",
    "exclusion_reasons", "n_exclusion_reasons",
    "has_ma_universe", "has_publicly_listed_universe",
    "is_acquired_or_merged", "is_public_owner", "is_public",
    "is_out_of_business", "is_out_of_business_owner", "is_bankruptcy", "is_other_nonoperating",
    "green", "green_stage", "green_applied", "green_stage_applied",
]


def write_outputs(result: Step10Result, out_dir: Path) -> Path:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    cols = [c for c in _OUTPUT_COLUMNS if c in result.expanded.columns]
    firm = result.expanded[cols].copy()
    firm_path = out / config.POPULATION_TABLE
    firm.to_parquet(firm_path, engine="pyarrow", index=False)

    result.flow.to_csv(out / config.FLOW_TABLE, index=False)
    result.outcomes.to_csv(out / config.OUTCOMES_TABLE, index=False)
    result.exclusion.to_csv(out / config.EXCLUSION_TABLE, index=False)
    result.by_cohort.to_csv(out / config.COHORT_TABLE, index=False)
    result.universe_diag.to_csv(out / config.UNIVERSE_DIAG_TABLE, index=False)
    result.audit.to_csv(out / config.AUDIT_TABLE, index=False)
    (out / config.REPORT_FILE).write_text(result.report_text, encoding="utf-8")

    print(f"[step10] wrote {firm_path}  ({len(firm):,} rows)")
    for name in (
        config.FLOW_TABLE, config.OUTCOMES_TABLE, config.EXCLUSION_TABLE,
        config.COHORT_TABLE, config.UNIVERSE_DIAG_TABLE, config.AUDIT_TABLE, config.REPORT_FILE,
    ):
        print(f"[step10] wrote {out / name}")
    return out


def acceptance_report(result: Step10Result) -> list[str]:
    recon = result.audit.set_index("key")
    lines: list[str] = []
    checks = [
        "age_filtered", "expanded_step10", "baseline_in_expanded", "outside_baseline",
        "baseline_green", "baseline_other", "all_baseline_ids_present",
        "other_private_companies_in_expanded", "membership_matches_filters",
        "duplicate_company_ids",
    ]
    for key in checks:
        exp = recon.loc[key, "expected"]
        obs = recon.loc[key, "observed"]
        flag = "" if str(exp) == str(obs) else "  WARN: mismatch"
        lines.append(f"{key}: expected {exp}, observed {obs}{flag}")
    for key in ("ma_or_publicly_listed_retained", "nonoperating_retained", "baseline_applied_equals_canonical"):
        lines.append(f"{key}: {recon.loc[key, 'observed']}")
    return lines


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        description="Step 10: expanded start-up-status population (read-only)"
    )
    parser.add_argument("--source", type=Path, default=config.SOURCE,
                        help="Raw European source CSV (Company_Europe.csv)")
    parser.add_argument("--population", type=Path, default=config.POPULATION,
                        help="Baseline population_key.parquet (green labels; read-only)")
    parser.add_argument("--standalone", type=Path, default=config.STANDALONE,
                        help="Standalone tokens CSV (strong_terms_active.csv)")
    parser.add_argument("--phrases", type=Path, default=config.PHRASES,
                        help="Multi-word phrases CSV (strong_term_phrases.csv)")
    parser.add_argument("--out-dir", type=Path, default=config.OUT_DIR,
                        help="Where to write the Step 10 outputs and report")
    args = parser.parse_args(argv)

    print("[step10] mode=diagnostic (read-only)")
    print(f"[step10] source     : {args.source}")
    print(f"[step10] population : {args.population}")
    print(f"[step10] out dir    : {args.out_dir}")

    result = run_diagnostic(
        args.source, args.population, args.standalone, args.phrases, args.out_dir
    )
    write_outputs(result, args.out_dir)

    print("\n=== Acceptance checks ===")
    for line in acceptance_report(result):
        print(line)
    print("\n" + result.report_text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
