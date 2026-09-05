"""Step 9 build logic: independent keyword-recovery of the Stage-1 firms.

The matching rules are imported unchanged from the live classifier
(``classify_startups_green_strong_terms`` + ``classify_startups_green_algorithmic``)
so behaviour is identical to the production green classification. Only the token
and phrase stages are applied, to Keywords + Description; the vertical stage is
NEVER used as a search signal (it is used only to split the Stage-1 firms into
CleanTech-only / Climate-Tech-only / both cohorts).

Pipeline::

    population_key.parquet (116,005 firms, read-only)
      + Keywords/Description/Verticals from the spine
      -> apply 68 standalone tokens + 456 phrases (existing rules)
      -> per-firm diagnostics (text_match_standalone / _mwe / _any, matches)
      -> restrict to green_stage == "vertical" (6,636) and measure recovery
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from . import config

# The classifier modules live at the repository root; make them importable when
# this package is run from anywhere.
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

MATCH_SEP = " | "


@dataclass
class Step9Result:
    firm_level: pd.DataFrame = field(default_factory=pd.DataFrame)
    stage1_headline: pd.DataFrame = field(default_factory=pd.DataFrame)
    by_vertical: pd.DataFrame = field(default_factory=pd.DataFrame)
    reconciliation: pd.DataFrame = field(default_factory=pd.DataFrame)
    report_text: str = ""


# --------------------------------------------------------------------------
# Loading (read-only)
# --------------------------------------------------------------------------
def load_baseline(population_path: Path) -> pd.DataFrame:
    """Load the canonical green labels; never modified."""
    if not population_path.exists():
        raise FileNotFoundError(f"Baseline population not found: {population_path}")
    pk = pd.read_parquet(population_path)
    required = {"company_id", "green", "green_stage", "green_signal_group"}
    missing = required.difference(pk.columns)
    if missing:
        raise ValueError(f"Baseline missing columns: {sorted(missing)}")
    pk = pk[["company_id", "green", "green_stage", "green_signal_group"]].copy()
    pk["company_id"] = pk["company_id"].astype("string")
    return pk


def load_text(spine_path: Path) -> pd.DataFrame:
    """Load Keywords / Description / Verticals text, keyed by company_id."""
    if not spine_path.exists():
        raise FileNotFoundError(f"Text spine not found: {spine_path}")
    df = pd.read_csv(
        spine_path,
        usecols=config.SPINE_USECOLS,
        dtype=str,
        keep_default_na=False,
    )
    df = df.rename(columns={"CompanyID": "company_id"})
    df["company_id"] = df["company_id"].astype("string")
    return df


# --------------------------------------------------------------------------
# Diagnostics
# --------------------------------------------------------------------------
def _vertical_cohort(verticals: str) -> str:
    """Map the Verticals tag string to a Stage-1 cohort label.

    Stage-1 firms carry at least one green vertical; non-Stage-1 firms return
    "NA" (no green vertical present).
    """
    verts = set(vertical_matches(verticals or ""))
    has_clean = "CleanTech" in verts
    has_climate = "Climate Tech" in verts
    if has_clean and has_climate:
        return "both"
    if has_clean:
        return "cleantech_only"
    if has_climate:
        return "climate_only"
    return "NA"


def compute_diagnostics(
    baseline: pd.DataFrame,
    text: pd.DataFrame,
    tokens: frozenset[str],
    trie: dict,
) -> pd.DataFrame:
    """Apply the token + phrase rules to every firm and attach diagnostics.

    Left-join keeps all baseline firms; firms without text simply match nothing.
    """
    df = baseline.merge(text, on="company_id", how="left")
    for col in ("Keywords", "Description", "Verticals"):
        df[col] = df[col].fillna("").astype("string")

    standalone_hits: list[str] = []
    mwe_hits: list[str] = []
    n_standalone: list[int] = []
    n_mwe: list[int] = []
    cohorts: list[str] = []

    keywords = df["Keywords"].tolist()
    descriptions = df["Description"].tolist()
    verticals = df["Verticals"].tolist()

    for kw, desc, vert in zip(keywords, descriptions, verticals):
        toks = token_matches(kw, desc, tokens)
        phrs = phrase_matches(kw, desc, trie)
        standalone_hits.append(MATCH_SEP.join(toks))
        mwe_hits.append(MATCH_SEP.join(phrs))
        n_standalone.append(len(toks))
        n_mwe.append(len(phrs))
        cohorts.append(_vertical_cohort(vert))

    df["is_stage1"] = (df["green_stage"] == "vertical").astype(bool)
    df["vertical_cohort"] = pd.array(cohorts, dtype="string")
    df["n_standalone"] = n_standalone
    df["n_mwe"] = n_mwe
    df["matched_standalone_terms"] = pd.array(standalone_hits, dtype="string")
    df["matched_mwes"] = pd.array(mwe_hits, dtype="string")
    df["text_match_standalone"] = df["n_standalone"] > 0
    df["text_match_mwe"] = df["n_mwe"] > 0
    df["text_match_any"] = df["text_match_standalone"] | df["text_match_mwe"]

    # Drop the raw text; only the diagnostics travel into the firm-level output.
    df = df.drop(columns=["Keywords", "Description", "Verticals"])
    return df


# --------------------------------------------------------------------------
# Tables
# --------------------------------------------------------------------------
def _pct(n: int, denom: int) -> float:
    return round(100.0 * n / denom, 1) if denom else float("nan")


def _recovery_counts(sub: pd.DataFrame) -> dict[str, int]:
    standalone = bool_sum(sub["text_match_standalone"])
    mwe = bool_sum(sub["text_match_mwe"])
    any_ = bool_sum(sub["text_match_any"])
    both = bool_sum(sub["text_match_standalone"] & sub["text_match_mwe"])
    return {
        "n_firms": len(sub),
        "recovered_standalone": standalone,
        "recovered_mwe": mwe,
        "recovered_any": any_,
        "recovered_both": both,
        "standalone_only": bool_sum(sub["text_match_standalone"] & ~sub["text_match_mwe"]),
        "mwe_only": bool_sum(~sub["text_match_standalone"] & sub["text_match_mwe"]),
        "not_recovered": len(sub) - any_,
    }


def bool_sum(mask: pd.Series) -> int:
    return int(mask.fillna(False).astype(bool).sum())


def build_stage1_headline(firm_level: pd.DataFrame) -> pd.DataFrame:
    """Headline recovery for the Stage-1 (vertical) firms: metric, n, pct."""
    stage1 = firm_level[firm_level["is_stage1"]]
    c = _recovery_counts(stage1)
    denom = c["n_firms"]
    order = [
        ("stage1_n", c["n_firms"]),
        ("recovered_any", c["recovered_any"]),
        ("recovered_standalone", c["recovered_standalone"]),
        ("recovered_mwe", c["recovered_mwe"]),
        ("recovered_both", c["recovered_both"]),
        ("standalone_only", c["standalone_only"]),
        ("mwe_only", c["mwe_only"]),
        ("not_recovered", c["not_recovered"]),
    ]
    rows = [{"metric": m, "n": n, "pct_of_stage1": _pct(n, denom)} for m, n in order]
    return pd.DataFrame(rows)


def build_by_vertical(firm_level: pd.DataFrame) -> pd.DataFrame:
    """Recovery split by Stage-1 vertical cohort; cohorts sum to stage1_n."""
    stage1 = firm_level[firm_level["is_stage1"]]
    cohorts = ["cleantech_only", "climate_only", "both", "all_stage1"]
    rows = []
    for cohort in cohorts:
        sub = stage1 if cohort == "all_stage1" else stage1[stage1["vertical_cohort"] == cohort]
        c = _recovery_counts(sub)
        denom = c["n_firms"]
        rows.append(
            {
                "cohort": cohort,
                "n_firms": c["n_firms"],
                "recovered_any_n": c["recovered_any"],
                "recovered_any_pct": _pct(c["recovered_any"], denom),
                "recovered_standalone_n": c["recovered_standalone"],
                "recovered_standalone_pct": _pct(c["recovered_standalone"], denom),
                "recovered_mwe_n": c["recovered_mwe"],
                "recovered_mwe_pct": _pct(c["recovered_mwe"], denom),
                "not_recovered_n": c["not_recovered"],
                "not_recovered_pct": _pct(c["not_recovered"], denom),
            }
        )
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------
# Reconciliation + report
# --------------------------------------------------------------------------
def _standalone_recovery_excl_dualuse(
    text: pd.DataFrame, tokens: frozenset[str], stage1_ids: pd.Series
) -> int:
    """Stage-1 standalone recovery using the 64-token variant (drop dual-use)."""
    slim = frozenset(tokens - config.DUAL_USE_TOKENS)
    ids = set(stage1_ids.tolist())
    sub = text[text["company_id"].isin(ids)]
    hits = 0
    for kw, desc in zip(sub["Keywords"].tolist(), sub["Description"].tolist()):
        if token_matches(kw, desc, slim):
            hits += 1
    return hits


def build_reconciliation(
    firm_level: pd.DataFrame,
    text: pd.DataFrame,
    tokens: frozenset[str],
    phrases: dict[str, str],
    paths: dict[str, Path],
) -> pd.DataFrame:
    """Audit rows: population/stage counts, vocab sizes, guards, resolved paths."""
    stage_counts = firm_level["green_stage"].value_counts().to_dict()
    green_total = int((firm_level["green"] == 1).sum())
    text_matched = int(firm_level["company_id"].isin(set(text["company_id"].tolist())).sum())

    # Guard: no vertical-name surfaces leaked into the vocabulary.
    token_leak = sorted(t for t in tokens if t in config.VERTICAL_NAME_TERMS)
    phrase_leak = sorted(p for p in phrases if p in config.VERTICAL_NAME_TERMS)
    guard_ok = not token_leak and not phrase_leak

    stage1 = firm_level[firm_level["is_stage1"]]
    stage1_ids = stage1["company_id"]
    standalone_excl = _standalone_recovery_excl_dualuse(text, tokens, stage1_ids)

    rows = [
        ("baseline_population", config.POP_TOTAL, len(firm_level)),
        ("green_total", config.GREEN_TOTAL, green_total),
        ("stage1_vertical", config.STAGE1_N, int(stage_counts.get("vertical", 0))),
        ("token", config.TOKEN_N, int(stage_counts.get("token", 0))),
        ("phrase", config.PHRASE_N, int(stage_counts.get("phrase", 0))),
        ("none", config.NONE_N, int(stage_counts.get("none", 0))),
        ("labels_modified", "False", "False"),
        ("vocab_standalone_used", 68, len(tokens)),
        ("vocab_standalone_thesis_ref", config.THESIS_STANDALONE, config.THESIS_STANDALONE),
        ("vocab_mwe_used", 456, len(phrases)),
        ("vocab_mwe_thesis_ref", config.THESIS_MWE, config.THESIS_MWE),
        ("text_join_coverage", config.POP_TOTAL, text_matched),
        ("guard_no_vertical_terms_in_vocab", "True", str(guard_ok)),
        ("vertical_terms_found_in_tokens", "", MATCH_SEP.join(token_leak)),
        ("vertical_terms_found_in_phrases", "", MATCH_SEP.join(phrase_leak)),
        (
            "stage1_recovered_standalone_excl_dualuse",
            "",
            f"{standalone_excl} ({_pct(standalone_excl, len(stage1))}%)",
        ),
        ("population_path", "", str(paths["population"])),
        ("spine_path", "", str(paths["spine"])),
        ("standalone_path", "", str(paths["standalone"])),
        ("phrases_path", "", str(paths["phrases"])),
        ("out_dir", "", str(paths["out_dir"])),
    ]
    return pd.DataFrame(rows, columns=["key", "expected", "observed"])


def build_report(
    headline: pd.DataFrame,
    by_vertical: pd.DataFrame,
    reconciliation: pd.DataFrame,
    tokens: frozenset[str],
    phrases: dict[str, str],
    paths: dict[str, Path],
) -> str:
    """The module's own separate, human-readable report."""
    h = headline.set_index("metric")
    stage1_n = int(h.loc["stage1_n", "n"])

    def line(metric: str) -> str:
        n = int(h.loc[metric, "n"])
        pct = h.loc[metric, "pct_of_stage1"]
        return f"    {metric:<24} {n:>7,}  ({pct}%)"

    lines = [
        "STEP 9 - KEYWORD-RECOVERY ROBUSTNESS DIAGNOSTIC",
        "=" * 64,
        "Read-only exercise: it modifies no existing classification or output.",
        "Question: of the Stage-1 firms flagged green ONLY via the CleanTech /",
        "Climate Tech verticals, how many does the thesis's environmental",
        "vocabulary independently recover from Keywords + Description alone?",
        "",
        "INPUTS",
        f"  population : {paths['population']}",
        f"  spine      : {paths['spine']}",
        f"  standalone : {paths['standalone']}",
        f"  phrases    : {paths['phrases']}",
        "",
        "VOCABULARY (applied to text only; no vertical names used as search terms)",
        f"  standalone tokens used : {len(tokens)}  (thesis reference {config.THESIS_STANDALONE})",
        f"  multi-word phrases used: {len(phrases)}  (thesis reference {config.THESIS_MWE})",
        "",
        f"STAGE-1 RECOVERY (denominator = {stage1_n:,} vertical-only green firms)",
        line("recovered_any"),
        line("recovered_standalone"),
        line("recovered_mwe"),
        line("recovered_both"),
        line("standalone_only"),
        line("mwe_only"),
        line("not_recovered"),
        "",
        "BY VERTICAL COHORT (cohorts sum to Stage-1 total)",
    ]
    for _, r in by_vertical.iterrows():
        lines.append(
            f"    {r['cohort']:<16} n={int(r['n_firms']):>6,}  "
            f"recovered_any={int(r['recovered_any_n']):>6,} ({r['recovered_any_pct']}%)"
        )

    recon = reconciliation.set_index("key")
    guard = recon.loc["guard_no_vertical_terms_in_vocab", "observed"]
    excl = recon.loc["stage1_recovered_standalone_excl_dualuse", "observed"]
    lines.extend(
        [
            "",
            "GUARDS / SENSITIVITY",
            f"    no vertical-name terms in vocabulary : {guard}",
            f"    standalone recovery, 64-token variant (excl. nuclear/biological): {excl}",
            "",
            "INTERPRETATION BOUNDARY",
            "    Not an estimate of classifier recall; PitchBook verticals are not",
            "    assumed to be complete ground truth; not a new green definition.",
            f"    Vocabulary applied: {len(tokens)}/{len(phrases)} vs thesis "
            f"{config.THESIS_STANDALONE}/{config.THESIS_MWE}.",
            "",
            f"OUTPUT DIR: {paths['out_dir']}",
        ]
    )
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------
# Orchestration
# --------------------------------------------------------------------------
def run_diagnostic(
    population_path: Path,
    spine_path: Path,
    standalone_path: Path,
    phrases_path: Path,
    out_dir: Path,
) -> Step9Result:
    """Compute every table + the report. Pure of side effects except reading."""
    baseline = load_baseline(population_path)
    text = load_text(spine_path)
    tokens = load_strong_tokens(standalone_path)
    phrases = load_strong_phrases(phrases_path)
    trie = build_trie({norm: norm for norm in phrases})

    firm_level = compute_diagnostics(baseline, text, tokens, trie)
    headline = build_stage1_headline(firm_level)
    by_vertical = build_by_vertical(firm_level)

    paths = {
        "population": population_path,
        "spine": spine_path,
        "standalone": standalone_path,
        "phrases": phrases_path,
        "out_dir": out_dir,
    }
    reconciliation = build_reconciliation(firm_level, text, tokens, phrases, paths)
    report_text = build_report(headline, by_vertical, reconciliation, tokens, phrases, paths)

    return Step9Result(
        firm_level=firm_level,
        stage1_headline=headline,
        by_vertical=by_vertical,
        reconciliation=reconciliation,
        report_text=report_text,
    )


def write_outputs(result: Step9Result, out_dir: Path) -> Path:
    """Write the firm-level parquet, the three CSVs, and the separate report."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    firm_path = out / config.FIRM_LEVEL_TABLE
    result.firm_level.to_parquet(firm_path, engine="pyarrow", index=False)
    result.stage1_headline.to_csv(out / config.STAGE1_TABLE, index=False)
    result.by_vertical.to_csv(out / config.BY_VERTICAL_TABLE, index=False)
    result.reconciliation.to_csv(out / config.RECONCILIATION_TABLE, index=False)
    (out / config.REPORT_FILE).write_text(result.report_text, encoding="utf-8")

    print(f"[step9] wrote {firm_path}  ({len(result.firm_level):,} rows)")
    print(f"[step9] wrote {out / config.STAGE1_TABLE}")
    print(f"[step9] wrote {out / config.BY_VERTICAL_TABLE}")
    print(f"[step9] wrote {out / config.RECONCILIATION_TABLE}")
    print(f"[step9] wrote {out / config.REPORT_FILE}")
    return out


def acceptance_report(result: Step9Result) -> list[str]:
    """Checks that say whether Step 9 succeeded. Warns, never raises."""
    recon = result.reconciliation.set_index("key")
    lines: list[str] = []
    for key in ("baseline_population", "green_total", "stage1_vertical", "token", "phrase", "none"):
        exp = recon.loc[key, "expected"]
        obs = recon.loc[key, "observed"]
        flag = "" if str(exp) == str(obs) else "  WARN: mismatch"
        lines.append(f"{key}: expected {exp}, observed {obs}{flag}")
    guard = recon.loc["guard_no_vertical_terms_in_vocab", "observed"]
    lines.append(f"guard_no_vertical_terms_in_vocab: {guard}")
    if guard != "True":
        lines.append("  WARN: a vertical-name term leaked into the vocabulary")
    # Cohort sum invariant.
    bv = result.by_vertical.set_index("cohort")["n_firms"]
    cohort_sum = int(bv[["cleantech_only", "climate_only", "both"]].sum())
    lines.append(f"cohort_sum: {cohort_sum} (expected {int(bv['all_stage1'])})")
    return lines


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        description="Step 9: keyword-recovery robustness diagnostic (read-only)"
    )
    parser.add_argument("--population", type=Path, default=config.POPULATION,
                        help="Baseline population_key.parquet (green labels; read-only)")
    parser.add_argument("--spine", type=Path, default=config.SPINE,
                        help="Text spine CSV (Keywords/Description/Verticals)")
    parser.add_argument("--standalone", type=Path, default=config.STANDALONE,
                        help="Standalone tokens CSV (strong_terms_active.csv)")
    parser.add_argument("--phrases", type=Path, default=config.PHRASES,
                        help="Multi-word phrases CSV (strong_term_phrases.csv)")
    parser.add_argument("--out-dir", type=Path, default=config.OUT_DIR,
                        help="Where to write the Step 9 outputs and report")
    args = parser.parse_args(argv)

    print("[step9] mode=diagnostic (read-only)")
    print(f"[step9] population : {args.population}")
    print(f"[step9] spine      : {args.spine}")
    print(f"[step9] standalone : {args.standalone}")
    print(f"[step9] phrases    : {args.phrases}")
    print(f"[step9] out dir    : {args.out_dir}")

    result = run_diagnostic(
        args.population, args.spine, args.standalone, args.phrases, args.out_dir
    )
    write_outputs(result, args.out_dir)

    print("\n=== Acceptance checks ===")
    for line in acceptance_report(result):
        print(line)
    print("\n" + result.report_text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
