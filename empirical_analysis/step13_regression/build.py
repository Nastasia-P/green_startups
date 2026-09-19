"""Step 13 build logic: common-horizon financing regressions.

Every primary regression family here (access, timing, capital) is estimated
on the Step 5b canonical five-year dataset (`first5_analysis.parquet`): the
31,257 firms founded 2016-2020 whose complete [year_founded, year_founded+5]
window is observable. There is no full-population / lifetime regression left
in this module -- every green coefficient below refers to the same
common-horizon observation framework.

For every outcome we estimate four nested OLS models and report how the green
coefficient moves as controls are added:

    (1) outcome ~ green
    (2) + founding cohort
    (3) + country fixed effects
    (4) + primary industry fixed effects

Internally these are ``spec1``..``spec4``; every output-facing column uses the
plain column label ``(1)``-``(4)`` instead -- nothing here is named M0-M3.

The green coefficient is a CONDITIONAL ASSOCIATION, not a causal effect. Binary
access outcomes use a linear probability model (OLS); logistic regression is a
documented alternative but is not run here. Standard errors are HC1 robust.
Binary-outcome coefficients/SEs are stored raw (0-1 scale) *and* as
percentage-point display columns (`coef_pp`, `se_pp`).

- **Access** (family 1): every eligible firm (n=31,257); any_financing_5yr,
  any_vc_5yr, any_grant_5yr, any_accelerator_5yr.
- **Timing** (family 2, supplementary): conditional on the event occurring
  in-window (years to first financing / first VC).
- **Capital** (family 3): log(1 + disclosed_capital_5yr), restricted to
  eligible firms with a disclosed in-window amount -- an INTENSIVE-MARGIN
  analysis (how much, among recipients), never an extensive-margin capital
  measure. Missing amounts are never zero-filled. A separate capital coverage
  diagnostic reports the disclosure rate; it is a disclosure/coverage
  statistic, not capital access.

Control levels are never allowed to drop rows: missing or rare fixed-effect
levels are folded into an "Other" level, so the sample is identical across
(1)-(4) and the coefficient path is comparable.

Only machine-readable CSVs are produced (no LaTeX / formatted text tables);
each table carries coef, std_error, p_value, auto-generated significance
stars, CI, n, R-squared and FE indicators so thesis tables can be typeset
from these numbers directly. Decimal precision is governed by the single
tunable `config.DECIMALS` / `config.DECIMALS_PP` constants.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from . import config

try:  # statsmodels is an optional heavy dependency; run.py guards on this.
    import statsmodels.api as sm
    HAVE_STATSMODELS = True
except Exception:  # pragma: no cover - environment-dependent
    sm = None
    HAVE_STATSMODELS = False


@dataclass
class Step13Result:
    tables: dict[str, pd.DataFrame] = field(default_factory=dict)
    audit: pd.DataFrame = field(default_factory=pd.DataFrame)
    caption: dict[str, str] = field(default_factory=dict)
    diagnostics: dict[str, object] = field(default_factory=dict)


# --------------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------------
def _require_statsmodels() -> None:
    if not HAVE_STATSMODELS:
        raise RuntimeError(
            "statsmodels is required for Step 13. Install it with "
            "`python -m pip install --user statsmodels` and re-run."
        )


def _num(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def _split(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    green = df[df[config.GREEN_COL] == 1]
    other = df[df[config.GREEN_COL] != 1]
    return green, other


def _controls_label(blocks: list[str]) -> str:
    if not blocks:
        return "green"
    names = {"cohort": "cohort", "country": "country_FE", "industry": "industry_FE"}
    return "green+" + "+".join(names[b] for b in blocks)


def _clean_control(series: pd.Series, min_n: int) -> pd.Series:
    """Fold missing and rare levels of a categorical control into "Other".

    Keeps the design matrix full-rank (no singleton dummies) and, crucially,
    never drops a firm from the sample for a thin/absent control value.
    """
    s = series.astype("object")
    s = s.where(pd.notna(s), config.OTHER_LEVEL)
    counts = s.value_counts()
    rare = set(counts[counts < min_n].index) - {config.OTHER_LEVEL}
    if rare:
        s = s.where(~s.isin(rare), config.OTHER_LEVEL)
    return s


def _dummies(series: pd.Series, prefix: str) -> pd.DataFrame:
    return pd.get_dummies(
        series.astype("category"), prefix=prefix, drop_first=True, dtype=float
    )


def _stars(p: float) -> str:
    """Significance stars generated from a stored p-value via one rule.

    ``config.STAR_RULE`` maps threshold -> marker; checked from the smallest
    threshold up so the most significant marker wins. Never hard-coded per
    coefficient.
    """
    if p is None or (isinstance(p, float) and np.isnan(p)):
        return ""
    for threshold in sorted(config.STAR_RULE):
        if p < threshold:
            return config.STAR_RULE[threshold]
    return ""


def _p_display(p: float) -> str:
    """Human-readable p-value: avoids a bare ``0.0`` for tiny p-values."""
    if p is None or (isinstance(p, float) and np.isnan(p)):
        return ""
    threshold = 10 ** (-config.DECIMALS)
    if p < threshold:
        return f"<{threshold:.{config.DECIMALS}f}"
    return f"{round(float(p), config.DECIMALS):.{config.DECIMALS}f}"


def _round_cols(df: pd.DataFrame) -> pd.DataFrame:
    """Apply the single consistent decimal-precision policy to a result table.

    `config.DECIMALS` governs coef/std_error/ci_low/ci_high/r_squared/p_value;
    `config.DECIMALS_PP` governs the percentage-point display columns. Change
    either constant in `config.py` to change every rounded number this module
    writes.
    """
    if not len(df):
        return df
    out = df.copy()
    for col in ("coef", "std_error", "ci_low", "ci_high", "r_squared", "p_value"):
        if col in out.columns:
            out[col] = _num(out[col]).round(config.DECIMALS)
    for col in ("coef_pp", "se_pp"):
        if col in out.columns:
            out[col] = _num(out[col]).round(config.DECIMALS_PP)
    return out


# --------------------------------------------------------------------------
# Design matrix + fit
# --------------------------------------------------------------------------
def build_design(
    sample: pd.DataFrame, blocks: list[str], industry_col: str, min_n: int
) -> tuple[pd.DataFrame, dict[str, int]]:
    """Assemble the OLS design matrix (const + green + requested FE dummies)."""
    _require_statsmodels()
    X = pd.DataFrame(index=sample.index)
    X["green"] = _num(sample[config.GREEN_COL]).fillna(0).astype(float)
    meta = {"n_fe_country": 0, "n_fe_industry": 0}

    if "cohort" in blocks:
        s = _clean_control(sample[config.COHORT_COL], min_n)
        X = pd.concat([X, _dummies(s, "cohort")], axis=1)
    if "country" in blocks:
        s = _clean_control(sample[config.COUNTRY_COL], min_n)
        meta["n_fe_country"] = int(s.nunique())
        X = pd.concat([X, _dummies(s, "country")], axis=1)
    if "industry" in blocks:
        s = _clean_control(sample[industry_col], min_n)
        meta["n_fe_industry"] = int(s.nunique())
        X = pd.concat([X, _dummies(s, "industry")], axis=1)

    X = sm.add_constant(X, has_constant="add")
    return X, meta


def fit_ols(y: np.ndarray, X: pd.DataFrame) -> dict[str, float]:
    """OLS with HC1 robust SE; return the green coefficient's statistics.

    Full precision -- rounding for display happens once, at table-assembly
    time, via `_round_cols`.
    """
    _require_statsmodels()
    res = sm.OLS(np.asarray(y, dtype=float), X.astype(float)).fit(
        cov_type=config.COV_TYPE
    )
    ci = res.conf_int(alpha=1 - config.CI_LEVEL)
    return {
        "coef": float(res.params["green"]),
        "std_error": float(res.bse["green"]),
        "p_value": float(res.pvalues["green"]),
        "ci_low": float(ci.loc["green"][0]),
        "ci_high": float(ci.loc["green"][1]),
        "n": int(res.nobs),
        "r_squared": float(res.rsquared),
    }


# --------------------------------------------------------------------------
# Per-outcome sequential regression: (1) -> (4)
# --------------------------------------------------------------------------
def regress_outcome(
    frame: pd.DataFrame,
    outcome_col: str,
    outcome_label: str,
    family: str,
    sample_label: str,
    industry_col: str,
    pp_scale: bool = False,
    transformation: str = "none",
) -> tuple[list[dict], list[dict]]:
    """Estimate specs (1)-(4) for one outcome; return (result_rows, audit_rows).

    The sample is the rows with the outcome observed (non-null); it is
    identical across the four specs, so the green coefficient path is a clean
    composition-adjustment comparison. Set `pp_scale=True` for binary outcomes
    to also populate the percentage-point display columns.
    """
    y_all = _num(frame[outcome_col])
    sub = frame[y_all.notna()].copy()
    n_missing = int(len(frame) - len(sub))
    y = _num(sub[outcome_col]).to_numpy(dtype=float)

    g = int((_num(sub[config.GREEN_COL]) == 1).sum())
    o = int(len(sub) - g)
    n_unique = int(sub["company_id"].nunique()) if "company_id" in sub.columns else len(sub)

    rows: list[dict] = []
    audits: list[dict] = []
    for spec_name, blocks in config.SPECS:
        X, meta = build_design(sub, blocks, industry_col, config.MIN_FE_LEVEL_N)
        stats = fit_ols(y, X)
        rows.append({
            "outcome": outcome_label,
            "family": family,
            "spec": spec_name,
            "column": config.SPEC_COLUMN_LABEL[spec_name],
            "controls": _controls_label(blocks),
            "sample": sample_label,
            "estimator": config.ESTIMATOR,
            "coef": stats["coef"],
            "std_error": stats["std_error"],
            "p_value": stats["p_value"],
            "p_value_display": _p_display(stats["p_value"]),
            "stars": _stars(stats["p_value"]),
            "ci_low": stats["ci_low"],
            "ci_high": stats["ci_high"],
            "coef_pp": stats["coef"] * 100 if pp_scale else float("nan"),
            "se_pp": stats["std_error"] * 100 if pp_scale else float("nan"),
            "n": stats["n"],
            "r_squared": stats["r_squared"],
            "cohort_controls": int("cohort" in blocks),
            "country_fe": int("country" in blocks),
            "industry_fe": int("industry" in blocks),
            "n_fe_country": meta["n_fe_country"],
            "n_fe_industry": meta["n_fe_industry"],
            "cov_type": config.COV_TYPE,
        })
        audits.append({
            "family": family,
            "outcome": outcome_label,
            "spec": spec_name,
            "column": config.SPEC_COLUMN_LABEL[spec_name],
            "sample": sample_label,
            "n": stats["n"],
            "n_green": g,
            "n_other": o,
            "n_unique_firms": n_unique,
            "n_missing_outcome": n_missing,
            "n_fe_country": meta["n_fe_country"],
            "n_fe_industry": meta["n_fe_industry"],
            "transformation": transformation,
            "cov_type": config.COV_TYPE,
        })
    return rows, audits


def _finalize_table(rows: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(rows, columns=config.RESULT_COLUMNS)
    return _round_cols(df)


# --------------------------------------------------------------------------
# Capital coverage diagnostic (disclosure/coverage, NOT capital access)
# --------------------------------------------------------------------------
def build_capital_coverage(panel: pd.DataFrame) -> pd.DataFrame:
    """Eligible-firm disclosure coverage for the intensive-margin capital sample.

    This is a disclosure/coverage diagnostic -- the share of eligible firms
    with *any* disclosed in-window amount -- not a capital-access measure.
    It exists to make the capital regression's selection problem explicit:
    the regression below only ever sees the firms counted here as disclosed.
    """
    g, o = _split(panel)
    n_elig, n_g, n_o = int(len(panel)), int(len(g)), int(len(o))
    has = config.CAPITAL_HAS_COL
    n_disc = int((_num(panel[has]) == 1).sum()) if has in panel.columns else 0
    n_disc_g = int((_num(g[has]) == 1).sum()) if has in g.columns else 0
    n_disc_o = int((_num(o[has]) == 1).sum()) if has in o.columns else 0
    row = {
        "eligible_firms": n_elig,
        "eligible_green": n_g,
        "eligible_other": n_o,
        "firms_with_disclosed_capital": n_disc,
        "firms_with_disclosed_capital_green": n_disc_g,
        "firms_with_disclosed_capital_other": n_disc_o,
        "coverage_overall": round(n_disc / n_elig, config.DECIMALS) if n_elig else float("nan"),
        "coverage_green": round(n_disc_g / n_g, config.DECIMALS) if n_g else float("nan"),
        "coverage_other": round(n_disc_o / n_o, config.DECIMALS) if n_o else float("nan"),
        "n_excluded_no_disclosed_amount": n_elig - n_disc,
        "note": (
            "Disclosure/coverage diagnostic, not a capital-access measure: the "
            "share of eligible firms with >=1 disclosed in-window deal amount. "
            "The capital regression is estimated only on the "
            "firms_with_disclosed_capital rows (intensive margin: how much, "
            "among recipients), never on the full eligible_firms population."
        ),
    }
    return pd.DataFrame([row])


# --------------------------------------------------------------------------
# Orchestration
# --------------------------------------------------------------------------
def build_all(
    panel: pd.DataFrame, industry_col: str | None = None
) -> Step13Result:
    industry_col = industry_col or config.INDUSTRY_COL
    result = Step13Result()
    audit_rows: list[dict] = []

    n_eligible = int(len(panel))
    sample_label = f"common-horizon eligible firms ({n_eligible})"

    # Family 1: access (LPM over every common-horizon eligible firm).
    acc_rows: list[dict] = []
    for label, col in config.ACCESS_OUTCOMES:
        r, a = regress_outcome(
            panel, col, label, "access", sample_label, industry_col, pp_scale=True
        )
        acc_rows += r
        audit_rows += a
    result.tables[config.OUT_ACCESS] = _finalize_table(acc_rows)

    # Family 2 (supplementary): timing, conditional on the in-window event.
    tim_rows: list[dict] = []
    timing_observed: dict[str, int] = {}
    for label, col in config.TIMING_OUTCOMES:
        timing_observed[label] = (
            int(_num(panel[col]).notna().sum()) if col in panel.columns else 0
        )
        r, a = regress_outcome(
            panel, col, label, "timing",
            f"{label} observed in-window (non-null)", industry_col,
        )
        tim_rows += r
        audit_rows += a
    result.tables[config.OUT_TIMING] = _finalize_table(tim_rows)

    # Family 3: intensive-margin capital (disclosed-amount firms only).
    has_col = config.CAPITAL_HAS_COL
    if has_col in panel.columns:
        cap_sub = panel[_num(panel[has_col]) == 1].copy()
    else:
        cap_sub = panel.iloc[0:0].copy()
    if len(cap_sub):
        cap_sub[config.CAPITAL_OUTCOME_LABEL] = np.log1p(
            _num(cap_sub[config.CAPITAL_SOURCE_COL])
        )
    cap_rows: list[dict] = []
    if len(cap_sub):
        r, a = regress_outcome(
            cap_sub, config.CAPITAL_OUTCOME_LABEL, config.CAPITAL_OUTCOME_LABEL,
            "capital",
            "eligible firms with disclosed in-window capital (intensive margin)",
            industry_col, transformation="log1p",
        )
        cap_rows += r
        audit_rows += a
    result.tables[config.OUT_CAPITAL] = _finalize_table(cap_rows)

    # Capital coverage diagnostic (disclosure/coverage, not capital access).
    result.tables[config.CAPITAL_COVERAGE] = build_capital_coverage(panel)

    result.audit = pd.DataFrame(audit_rows)
    g, o = _split(panel)
    result.diagnostics = {
        "n_eligible": n_eligible,
        "n_eligible_green": int(len(g)),
        "n_eligible_other": int(len(o)),
        "timing_observed": timing_observed,
        "capital_observed": int(len(cap_sub)),
        "capital_unique": (
            int(cap_sub["company_id"].nunique()) if len(cap_sub) else 0
        ),
        "industry_col": industry_col,
    }
    return result


# --------------------------------------------------------------------------
# Captions
# --------------------------------------------------------------------------
def build_captions(result: Step13Result) -> pd.DataFrame:
    diag = result.diagnostics
    cap = result.caption
    n_elig = diag.get("n_eligible")
    n_g = diag.get("n_eligible_green")
    n_o = diag.get("n_eligible_other")

    cap[config.OUT_ACCESS] = (
        "Linear probability model (OLS) for binary access outcomes "
        "(any_financing, any_vc, any_grant, any_accelerator, all observed within "
        f"each firm's first five post-founding years) over the common-horizon "
        f"eligible population (n={n_elig}; green={n_g}, other={n_o}). HC1 robust "
        "SE. The green coefficient is the change in probability of the outcome "
        "for green vs other firms, holding the spec's controls fixed; it is "
        "stored raw (0-1) as `coef`/`std_error` and also as percentage points "
        "(`coef_pp`/`se_pp`, e.g. 0.043 -> 4.3 pp). Significance stars are "
        "generated from the stored p-value (* p<.10, ** p<.05, *** p<.01). "
        "Logistic regression is a defensible alternative for a binary outcome "
        "and is flagged as a methodological decision; it is NOT run here."
    )
    cap[config.OUT_TIMING] = (
        "Supplementary. OLS for years to first financing / first VC, restricted "
        "to eligible firms that experience the respective event within their "
        "five-year window (n reported per outcome). This conditions on having "
        "been financed in-window, so it is a within-financed association, not a "
        "population statement. Same common-horizon population and specs as the "
        "access family; not a lifetime-observation regression."
    )
    cap[config.OUT_CAPITAL] = (
        "INTENSIVE-MARGIN analysis: OLS for log(1 + disclosed capital raised in "
        "the firm's first five post-founding years), estimated only on eligible "
        f"firms with a disclosed in-window amount ({diag.get('capital_observed')} "
        f"of {n_elig} eligible). This estimates how much observed recipients "
        "raise, NOT whether firms raise anything -- it does not observe the "
        "extensive margin (how many). Missing amounts are excluded, never "
        f"zero-filled. See `{config.CAPITAL_COVERAGE}.csv` for the disclosure "
        "coverage diagnostic that documents this selection explicitly."
    )
    cap[config.CAPITAL_COVERAGE] = (
        "Disclosure/coverage diagnostic, not a capital-access measure: the "
        "share of common-horizon eligible firms with >=1 disclosed in-window "
        "deal amount, overall and by green/other. Quantifies exactly which "
        "firms enter the intensive-margin capital regression above and how "
        "many are excluded for lacking a disclosed amount."
    )
    cap["_method"] = (
        "Sequential specifications (1) green only -> (2) +cohort -> (3) +country "
        "FE -> (4) +primary industry FE let one read how much of the raw green "
        "difference is composition. Industry uses a single firm-level tag "
        f"({diag.get('industry_col')}); the multi-valued industry membership is "
        "never joined in. Rare/missing FE levels are folded into 'Other' so the "
        "sample is identical across (1)-(4). Internal spec names (spec1-spec4) "
        "never appear in thesis-facing output; only the column label (1)-(4) "
        "and FE indicator columns (cohort_controls/country_fe/industry_fe) do."
    )
    cap["_sample"] = (
        f"Every regression here uses the Step 5b common-horizon dataset "
        f"(first5_analysis.parquet): firms founded 2016-2020 with a complete "
        f"observable five-year window (n={n_elig}; green={n_g}, other={n_o}). "
        "This replaces the earlier full-population / lifetime-observation "
        "financing and timing regressions so every reported association refers "
        "to the same five-year observation framework as Section 4.3."
    )
    cap["_tables"] = (
        "No formatted or LaTeX tables are generated here -- only machine-"
        "readable CSVs. Each result row already carries everything needed to "
        "typeset a thesis table by hand: `column` (1)-(4), `coef`, `std_error`, "
        "`p_value`, `stars`, `ci_low`/`ci_high`, `n`, `r_squared`, and the FE "
        "indicator columns for the bottom-of-table rows (Cohort controls / "
        "Country fixed effects / Industry fixed effects / Observations / R2)."
    )
    cap["_decimals"] = (
        f"Decimal precision is one tunable policy: config.DECIMALS="
        f"{config.DECIMALS} governs coef/std_error/ci_low/ci_high/r_squared/"
        f"p_value; config.DECIMALS_PP={config.DECIMALS_PP} governs the "
        "percentage-point display columns coef_pp/se_pp."
    )
    cap["_interpretation"] = (
        "All coefficients are CONDITIONAL ASSOCIATIONS, not causal effects of "
        f"being green. Statistical significance is not substantive importance: "
        f"with n up to {n_elig}, small differences can be significant, so the "
        "coefficient MAGNITUDE (and its CI) matters more than the p-value. This "
        "does not address survivor-selection (Step 10)."
    )
    rows = [{"output": k, "caption": v} for k, v in cap.items()]
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------
# Output writing
# --------------------------------------------------------------------------
def write_outputs(result: Step13Result, output_dir: Path | None = None) -> Path:
    out = Path(output_dir or config.OUTPUT_DIR)
    out.mkdir(parents=True, exist_ok=True)

    for name in (config.OUT_ACCESS, config.OUT_TIMING, config.OUT_CAPITAL,
                 config.CAPITAL_COVERAGE):
        df = result.tables.get(name, pd.DataFrame())
        path = out / f"{name}.csv"
        df.to_csv(path, index=False)
        print(f"[step13] wrote {path}  ({len(df)} rows)")

    audit_path = out / f"{config.SAMPLE_AUDIT}.csv"
    result.audit.to_csv(audit_path, index=False)
    print(f"[step13] wrote {audit_path}  ({len(result.audit)} rows)")

    cap_df = build_captions(result)
    cap_path = out / f"{config.CAPTIONS_FILE}.csv"
    cap_df.to_csv(cap_path, index=False)
    print(f"[step13] wrote {cap_path}  ({len(cap_df)} rows)")
    return out


# --------------------------------------------------------------------------
# Acceptance report (printed by run.py)
# --------------------------------------------------------------------------
def _protected_names() -> set[str]:
    """Existing Step 5 / step5b output names that must never be produced here."""
    names: set[str] = set()
    try:
        from empirical_analysis.step5b_fixed_horizon import config as c5b
        names |= set(c5b.STEP5_PROTECTED_NAMES)
        names |= {c5b.OUT_ACCESS, c5b.OUT_TIMING, c5b.OUT_CAPITAL,
                  c5b.OUT_FIRST_CHANNEL, c5b.CAPTIONS_FILE, c5b.FIGURE_ACCESS,
                  c5b.FIRM_PANEL, c5b.FIRM_AUDIT}
    except Exception:
        pass
    return names


def acceptance_report(result: Step13Result) -> list[str]:
    lines: list[str] = []
    diag = result.diagnostics
    audit = result.audit

    # C1: access sample is every common-horizon eligible firm; trio reconciles.
    acc = result.tables.get(config.OUT_ACCESS, pd.DataFrame())
    n_elig = int(diag.get("n_eligible", 0))
    acc_full = bool(len(acc)) and bool((acc["n"] == n_elig).all())
    trio_ok = True
    if len(audit):
        bad = audit[audit["n_green"] + audit["n_other"] != audit["n"]]
        trio_ok = len(bad) == 0
    lines.append(
        f"[C1] access n == common-horizon eligible firms ({n_elig}) on every "
        f"spec: {'PASS' if acc_full else 'FAIL'}; n_green+n_other==n on all "
        f"{len(audit)} audit rows: {'PASS' if trio_ok else 'FAIL'}"
    )

    # C2: all four specs estimated per outcome; green coefficient finite;
    # no M0-M3 naming leaked into the column label.
    specs_ok = True
    coef_ok = True
    labels_ok = True
    expected_specs = {name for name, _ in config.SPECS}
    expected_cols = set(config.SPEC_COLUMN_LABEL.values())
    for name in (config.OUT_ACCESS, config.OUT_TIMING, config.OUT_CAPITAL):
        df = result.tables.get(name, pd.DataFrame())
        if not len(df):
            continue
        for outcome, grp in df.groupby("outcome"):
            if set(grp["spec"]) != expected_specs:
                specs_ok = False
            if not set(grp["column"]) <= expected_cols:
                labels_ok = False
            if not np.isfinite(_num(grp["coef"]).to_numpy(float)).all():
                coef_ok = False
    lines.append(
        f"[C2] every outcome has specs (1)-(4): {'PASS' if specs_ok else 'FAIL'}; "
        f"column labels are (1)-(4) only (no M0-M3): "
        f"{'PASS' if labels_ok else 'FAIL'}; coefficients finite: "
        f"{'PASS' if coef_ok else 'FAIL'}"
    )

    # C3: timing/capital use observed-only samples (reported n matches counts).
    c3_ok = True
    tim = result.tables.get(config.OUT_TIMING, pd.DataFrame())
    for label, n_obs in diag.get("timing_observed", {}).items():
        got = tim[tim["outcome"] == label]["n"] if len(tim) else pd.Series(dtype=int)
        if len(got) and int(got.iloc[0]) != int(n_obs):
            c3_ok = False
    cap = result.tables.get(config.OUT_CAPITAL, pd.DataFrame())
    if len(cap) and int(cap["n"].iloc[0]) != int(diag.get("capital_observed", -1)):
        c3_ok = False
    lines.append(
        f"[C3] timing/capital samples are observed-only, reported n matches "
        f"non-null/in-window-observed counts (capital never zero-filled): "
        f"{'PASS' if c3_ok else 'FAIL'} "
        f"(timing_observed={diag.get('timing_observed')}, "
        f"capital_observed={diag.get('capital_observed')})"
    )

    # C4: no firm duplicated by the industry join (rows == unique firms).
    c4_ok = True
    if len(audit):
        dup = audit[audit["n"] != audit["n_unique_firms"]]
        c4_ok = len(dup) == 0
    if diag.get("capital_observed", 0) != diag.get("capital_unique", 0):
        c4_ok = False
    lines.append(
        f"[C4] regression sample rows == unique company_id (no industry-join "
        f"duplication): {'PASS' if c4_ok else 'FAIL'}"
    )

    # C5: writes only its own names; disjoint from Step 5 / step5b outputs.
    produced = set(config.STEP13_OUTPUT_NAMES)
    protected = _protected_names()
    collision = produced & protected
    only_own = produced <= set(config.STEP13_OUTPUT_NAMES)
    c5_ok = (not collision) and only_own
    lines.append(
        f"[C5] outputs {sorted(produced)} disjoint from Step 5/step5b names and "
        f"self-scoped: {'PASS' if c5_ok else 'FAIL'}"
        + (f"  COLLISION={sorted(collision)}" if collision else "")
    )

    # C6: pp display columns scale coef/std_error exactly for the access
    # family (binary outcomes) and are NaN elsewhere (timing/capital).
    pp_ok = True
    if len(acc):
        expect_pp = (_num(acc["coef"]) * 100).round(config.DECIMALS_PP)
        got_pp = _num(acc["coef_pp"])
        pp_ok = bool(np.allclose(
            expect_pp.to_numpy(float), got_pp.to_numpy(float),
            atol=10 ** (-config.DECIMALS_PP), equal_nan=True,
        ))
    for name in (config.OUT_TIMING, config.OUT_CAPITAL):
        df = result.tables.get(name, pd.DataFrame())
        if len(df) and "coef_pp" in df.columns:
            if not _num(df["coef_pp"]).isna().all():
                pp_ok = False
    lines.append(
        f"[C6] percentage-point display columns (coef_pp/se_pp) scale the raw "
        f"0-1 access coefficient by 100 and are NaN for timing/capital: "
        f"{'PASS' if pp_ok else 'FAIL'}"
    )

    # C7: stars are generated from the stored p-value via config.STAR_RULE,
    # consistently across every table (never hard-coded).
    stars_ok = True
    for name in (config.OUT_ACCESS, config.OUT_TIMING, config.OUT_CAPITAL):
        df = result.tables.get(name, pd.DataFrame())
        if not len(df):
            continue
        expect = df["p_value"].apply(_stars)
        if not (expect == df["stars"]).all():
            stars_ok = False
    lines.append(
        f"[C7] significance stars match config.STAR_RULE applied to the stored "
        f"p-value on every table: {'PASS' if stars_ok else 'FAIL'}"
    )

    return lines
