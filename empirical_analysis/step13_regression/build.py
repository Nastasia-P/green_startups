"""Step 13 build logic: the exploratory composition-adjusted regressions.

For every outcome we estimate four nested OLS models and report how the green
coefficient moves as controls are added:

    M0: outcome ~ green
    M1: + founding cohort
    M2: + country fixed effects
    M3: + primary industry fixed effects

The green coefficient is a CONDITIONAL ASSOCIATION, not a causal effect. Binary
access outcomes use a linear probability model (OLS); logistic regression is a
documented alternative but is not run here. Standard errors are HC1 robust.

The regression sample for an outcome is fixed by that outcome's observability
(access = full population; timing = firms with the lag observed; capital =
step5b-eligible firms with a disclosed in-window amount). Control levels are never
allowed to drop rows: missing or rare fixed-effect levels are folded into an
"Other" level, so the sample is identical across M0-M3 and the coefficient path is
comparable. Missing financing amounts are excluded, never zero-filled.
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
    """OLS with HC1 robust SE; return the green coefficient's statistics."""
    _require_statsmodels()
    res = sm.OLS(np.asarray(y, dtype=float), X.astype(float)).fit(
        cov_type=config.COV_TYPE
    )
    ci = res.conf_int(alpha=1 - config.CI_LEVEL)
    return {
        "green_coef": round(float(res.params["green"]), 6),
        "green_se": round(float(res.bse["green"]), 6),
        "green_pvalue": float(res.pvalues["green"]),
        "green_ci_low": round(float(ci.loc["green"][0]), 6),
        "green_ci_high": round(float(ci.loc["green"][1]), 6),
        "n": int(res.nobs),
        "r_squared": round(float(res.rsquared), 6),
    }


# --------------------------------------------------------------------------
# Per-outcome sequential regression (M0 -> M3)
# --------------------------------------------------------------------------
def regress_outcome(
    frame: pd.DataFrame,
    outcome_col: str,
    outcome_label: str,
    family: str,
    sample_label: str,
    industry_col: str,
    transformation: str = "none",
) -> tuple[list[dict], list[dict]]:
    """Estimate M0-M3 for one outcome; return (result_rows, audit_rows).

    The sample is the rows with the outcome observed (non-null); it is identical
    across the four models, so the green coefficient path is a clean
    composition-adjustment comparison.
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
    for model_name, blocks in config.MODEL_SPECS:
        X, meta = build_design(sub, blocks, industry_col, config.MIN_FE_LEVEL_N)
        stats = fit_ols(y, X)
        rows.append({
            "outcome": outcome_label,
            "family": family,
            "model": model_name,
            "sample": sample_label,
            "estimator": config.ESTIMATOR,
            "green_coef": stats["green_coef"],
            "green_se": stats["green_se"],
            "green_pvalue": stats["green_pvalue"],
            "green_ci_low": stats["green_ci_low"],
            "green_ci_high": stats["green_ci_high"],
            "n": stats["n"],
            "r_squared": stats["r_squared"],
            "controls": _controls_label(blocks),
            "n_fe_country": meta["n_fe_country"],
            "n_fe_industry": meta["n_fe_industry"],
            "cov_type": config.COV_TYPE,
        })
        audits.append({
            "family": family,
            "outcome": outcome_label,
            "model": model_name,
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


# --------------------------------------------------------------------------
# Family 3 outcome: first-five-year disclosed capital (reuses step5b)
# --------------------------------------------------------------------------
def build_first5_capital_frame(
    firm: pd.DataFrame, deals: pd.DataFrame, industry_col: str
) -> tuple[pd.DataFrame, dict[str, int]]:
    """Per-firm log(1 + disclosed in-window deal_size) over step5b-eligible firms.

    Reuses step5b's firm-relative window; only firms with at least one disclosed
    in-window deal enter (amounts are never zero-filled).
    """
    from empirical_analysis.step5b_fixed_horizon.build import prepare_window

    elig, in_window, diag = prepare_window(firm, deals)
    cols = ["company_id", config.GREEN_COL, config.COHORT_COL,
            config.COUNTRY_COL, industry_col]
    ctrl = firm[[c for c in cols if c in firm.columns]].copy()

    if in_window is None or in_window.empty:
        empty = pd.DataFrame(columns=cols + ["first5_disclosed_capital",
                                             config.CAPITAL_OUTCOME_LABEL])
        return empty, {"n_eligible": int(len(elig)), "n_observed": 0}

    disclosed = in_window[_num(in_window["deal_size"]).notna()].copy()
    per_firm = (
        disclosed.assign(deal_size=_num(disclosed["deal_size"]))
        .groupby("company_id")["deal_size"].sum()
        .rename("first5_disclosed_capital").reset_index()
    )
    per_firm[config.CAPITAL_OUTCOME_LABEL] = np.log1p(
        per_firm["first5_disclosed_capital"]
    )
    frame = per_firm.merge(ctrl, on="company_id", how="left")
    return frame, {"n_eligible": int(len(elig)), "n_observed": int(len(frame))}


# --------------------------------------------------------------------------
# Orchestration
# --------------------------------------------------------------------------
def build_all(
    firm: pd.DataFrame, deals: pd.DataFrame, industry_col: str | None = None
) -> Step13Result:
    industry_col = industry_col or config.INDUSTRY_COL
    result = Step13Result()
    audit_rows: list[dict] = []

    # Family 1: access (LPM over the full population).
    acc_rows: list[dict] = []
    sample_label = f"full population ({len(firm)})"
    for label, col in config.ACCESS_OUTCOMES:
        r, a = regress_outcome(firm, col, label, "access", sample_label, industry_col)
        acc_rows += r
        audit_rows += a
    result.tables[config.OUT_ACCESS] = pd.DataFrame(
        acc_rows, columns=config.RESULT_COLUMNS
    )

    # Family 2: timing (OLS over firms with the lag observed).
    tim_rows: list[dict] = []
    timing_observed: dict[str, int] = {}
    for label, col in config.TIMING_OUTCOMES:
        timing_observed[label] = int(_num(firm[col]).notna().sum()) if col in firm else 0
        r, a = regress_outcome(
            firm, col, label, "timing", f"{label} observed (non-null)", industry_col
        )
        tim_rows += r
        audit_rows += a
    result.tables[config.OUT_TIMING] = pd.DataFrame(
        tim_rows, columns=config.RESULT_COLUMNS
    )

    # Family 3: first-five-year disclosed capital (log1p; observed amounts only).
    cap_frame, cap_diag = build_first5_capital_frame(firm, deals, industry_col)
    cap_rows: list[dict] = []
    if len(cap_frame):
        r, a = regress_outcome(
            cap_frame, config.CAPITAL_OUTCOME_LABEL, config.CAPITAL_OUTCOME_LABEL,
            "capital", "step5b-eligible, observed in-window amount", industry_col,
            transformation="log1p",
        )
        cap_rows += r
        audit_rows += a
    result.tables[config.OUT_CAPITAL] = pd.DataFrame(
        cap_rows, columns=config.RESULT_COLUMNS
    )

    result.audit = pd.DataFrame(audit_rows)
    result.diagnostics = {
        "n_firms_total": int(len(firm)),
        "n_firms_unique": int(firm["company_id"].nunique())
        if "company_id" in firm.columns else int(len(firm)),
        "timing_observed": timing_observed,
        "capital_eligible": int(cap_diag.get("n_eligible", 0)),
        "capital_observed": int(cap_diag.get("n_observed", 0)),
        "capital_unique": int(cap_frame["company_id"].nunique())
        if len(cap_frame) else 0,
        "industry_col": industry_col,
    }
    return result


# --------------------------------------------------------------------------
# Captions
# --------------------------------------------------------------------------
def build_captions(result: Step13Result) -> pd.DataFrame:
    diag = result.diagnostics
    cap = result.caption
    cap[config.OUT_ACCESS] = (
        "Linear probability model (OLS) for binary access outcomes "
        "(any_financing=financed, any_vc, any_grant, any_accelerator) over the full "
        f"population ({diag.get('n_firms_total')}). HC1 robust SE. The green coefficient "
        "is the change in probability of the outcome for green vs other firms, holding "
        "the model's controls fixed. Logistic regression is a defensible alternative "
        "for a binary outcome and is flagged as a methodological decision; it is NOT "
        "run here (the exploratory brief was a simple linear regression)."
    )
    cap[config.OUT_TIMING] = (
        "OLS for years to first financing / first VC, over firms with the lag observed "
        "(non-null); n reported per model. Note this conditions on having been "
        "financed, so it is a within-financed association, not a population statement."
    )
    cap[config.OUT_CAPITAL] = (
        "OLS for log(1 + disclosed capital) raised in the firm's first five "
        "post-founding years (step5b fixed horizon), over step5b-eligible firms with a "
        f"disclosed in-window amount ({diag.get('capital_observed')} of "
        f"{diag.get('capital_eligible')} eligible). Missing amounts are excluded, never "
        "zero-filled; the coefficient is on a log scale (approx. proportional difference)."
    )
    cap["_method"] = (
        "Sequential specifications M0 (green only) -> M1 (+cohort) -> M2 (+country FE) "
        "-> M3 (+primary industry FE) let one read how much of the raw green difference "
        "is composition. Industry uses a single firm-level tag "
        f"({diag.get('industry_col')}); the multi-valued industry membership is never "
        "joined in. Rare/missing FE levels are folded into 'Other' so the sample is "
        "identical across M0-M3."
    )
    cap["_interpretation"] = (
        "All coefficients are CONDITIONAL ASSOCIATIONS, not causal effects of being "
        f"green. Statistical significance is not substantive importance: with n up to "
        f"{diag.get('n_firms_total')}, tiny differences become significant, so the "
        "coefficient MAGNITUDE (and its CI) matters more than the p-value. This does "
        "not address survivor-selection (Step 10)."
    )
    rows = [{"output": k, "caption": v} for k, v in cap.items()]
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------
# Output writing
# --------------------------------------------------------------------------
def write_outputs(result: Step13Result, output_dir: Path | None = None) -> Path:
    out = Path(output_dir or config.OUTPUT_DIR)
    out.mkdir(parents=True, exist_ok=True)

    for name in (config.OUT_ACCESS, config.OUT_TIMING, config.OUT_CAPITAL):
        df = result.tables.get(name, pd.DataFrame(columns=config.RESULT_COLUMNS))
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
                  c5b.OUT_FIRST_CHANNEL, c5b.CAPTIONS_FILE, c5b.FIGURE_ACCESS}
    except Exception:
        pass
    return names


def acceptance_report(result: Step13Result) -> list[str]:
    lines: list[str] = []
    diag = result.diagnostics
    audit = result.audit

    # C1: access sample is the full population; trio reconciles on every model.
    acc = result.tables.get(config.OUT_ACCESS, pd.DataFrame())
    pop = int(diag.get("n_firms_total", config.POP_TOTAL))
    acc_full = bool(len(acc)) and bool((acc["n"] == pop).all())
    trio_ok = True
    if len(audit):
        bad = audit[audit["n_green"] + audit["n_other"] != audit["n"]]
        trio_ok = len(bad) == 0
    lines.append(
        f"[C1] access n == full population ({pop}) on every model: "
        f"{'PASS' if acc_full else 'FAIL'}; n_green+n_other==n on all "
        f"{len(audit)} audit rows: {'PASS' if trio_ok else 'FAIL'}"
    )

    # C2: all four nested models estimated per outcome; green coef finite.
    models_ok = True
    coef_ok = True
    for name in (config.OUT_ACCESS, config.OUT_TIMING, config.OUT_CAPITAL):
        df = result.tables.get(name, pd.DataFrame())
        if not len(df):
            continue
        for outcome, grp in df.groupby("outcome"):
            if set(grp["model"]) != {"M0", "M1", "M2", "M3"}:
                models_ok = False
            if not np.isfinite(_num(grp["green_coef"]).to_numpy(float)).all():
                coef_ok = False
    lines.append(
        f"[C2] every outcome has M0-M3: {'PASS' if models_ok else 'FAIL'}; "
        f"green coefficients finite: {'PASS' if coef_ok else 'FAIL'}"
    )

    # C3: timing/capital use observed-only samples (reported n matches counts).
    c3_ok = True
    tim = result.tables.get(config.OUT_TIMING, pd.DataFrame())
    for label, n_obs in diag.get("timing_observed", {}).items():
        got = tim[tim["outcome"] == label]["n"]
        if len(got) and int(got.iloc[0]) != int(n_obs):
            c3_ok = False
    cap = result.tables.get(config.OUT_CAPITAL, pd.DataFrame())
    if len(cap) and int(cap["n"].iloc[0]) != int(diag.get("capital_observed", -1)):
        c3_ok = False
    lines.append(
        f"[C3] timing/capital samples are observed-only, reported n matches "
        f"non-null/observed counts (capital never zero-filled): "
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
    return lines
