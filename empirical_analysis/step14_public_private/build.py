"""Step 14 build logic: public/private investor participation (common horizon).

Everything is firm-relative to each eligible firm's first five post-founding
years (reusing Step 5b's `prepare_window`). The public/private split is fixed by
an explicit, audited classification (`config.ANALYTICAL_GROUP`), never decided
silently here. Investor-level contributed amounts do not exist in the data, so
capital is reported as disclosed deal size by investor composition, never as
per-investor "public/private capital".

Outputs (all machine-readable CSV + one Parquet panel):
- investor_type_mapping: the classification + relationship/firm counts per type;
- investor_amount_audit: evidence that no investor-level amount column exists;
- pubpriv_analysis_5yr: one row per eligible firm with the participation flags;
- T14_pubpriv_participation: green vs other under two denominators;
- T14_pubpriv_regression: LPM (1)-(5) for the four participation outcomes;
- T14_grant_vc_sequencing_5yr / T14_pubpriv_sequencing_5yr: in-window ordering;
- T14_pubpriv_ordering_regression: supplementary public_precedes_private model;
- T14_deal_size_by_investor_composition_5yr: deal size by composition.
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
class Step14Result:
    tables: dict[str, pd.DataFrame] = field(default_factory=dict)
    firm_panel: pd.DataFrame = field(default_factory=pd.DataFrame)
    caption: dict[str, str] = field(default_factory=dict)
    diagnostics: dict[str, object] = field(default_factory=dict)


# --------------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------------
def _require_statsmodels() -> None:
    if not HAVE_STATSMODELS:
        raise RuntimeError(
            "statsmodels is required for Step 14. Install it with "
            "`python -m pip install --user statsmodels` and re-run."
        )


def _num(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def _split(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    green = df[df[config.GREEN_COL] == 1]
    other = df[df[config.GREEN_COL] != 1]
    return green, other


def _share(mask: pd.Series, frame: pd.DataFrame) -> float:
    return round(float(mask.sum()) / len(frame), config.DECIMALS) if len(frame) else float("nan")


def _pp(green_share: float, other_share: float) -> float:
    if pd.isna(green_share) or pd.isna(other_share):
        return float("nan")
    return round((green_share - other_share) * 100, config.DECIMALS_PP)


def _median(series: pd.Series) -> float:
    s = _num(series).dropna()
    return round(float(s.median()), config.DECIMALS) if len(s) else float("nan")


def _diff(g: float, o: float) -> float:
    if pd.isna(g) or pd.isna(o):
        return float("nan")
    return round(g - o, config.DECIMALS)


def _stars(p: float) -> str:
    if p is None or (isinstance(p, float) and np.isnan(p)):
        return ""
    for threshold in sorted(config.STAR_RULE):
        if p < threshold:
            return config.STAR_RULE[threshold]
    return ""


def _p_display(p: float) -> str:
    if p is None or (isinstance(p, float) and np.isnan(p)):
        return ""
    threshold = 10 ** (-config.DECIMALS)
    if p < threshold:
        return f"<{threshold:.{config.DECIMALS}f}"
    return f"{round(float(p), config.DECIMALS):.{config.DECIMALS}f}"


def _round_cols(df: pd.DataFrame) -> pd.DataFrame:
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
# Investor classification + relationships
# --------------------------------------------------------------------------
def classify_investors(investors: pd.DataFrame) -> pd.DataFrame:
    """investor_id -> analytical_group / is_public / is_private (0/1)."""
    if investors is None or investors.empty:
        return pd.DataFrame(columns=["investor_id", "investor_type_grp",
                                     "analytical_group", "is_public", "is_private"])
    inv = investors[["investor_id", "investor_type_grp"]].copy()
    inv["analytical_group"] = inv["investor_type_grp"].map(config.ANALYTICAL_GROUP)
    inv["is_public"] = (inv["analytical_group"] == config.PUBLIC_LABEL).astype(int)
    inv["is_private"] = (inv["analytical_group"] == config.PRIVATE_LABEL).astype(int)
    return inv


def build_investor_mapping(
    investors: pd.DataFrame, deal_investors: pd.DataFrame, deals: pd.DataFrame
) -> pd.DataFrame:
    """Classification audit: one row per investor_type_grp with counts.

    n_investors from investors_clean; n_relationships from deal_investors_clean;
    n_firms = distinct companies reached (deal_investors -> deals). Covers 100%
    of observed types; any type absent from config.ANALYTICAL_GROUP is surfaced
    with analytical_group == "UNMAPPED".
    """
    cols = ["investor_type_grp", "analytical_group", "n_investors",
            "n_relationships", "n_firms"]
    if investors is None or investors.empty:
        return pd.DataFrame(columns=cols)

    n_investors = investors["investor_type_grp"].value_counts(dropna=False)

    # relationships + firms need investor_type_grp joined onto deal_investors
    rel_counts = pd.Series(dtype="int64")
    firm_counts = pd.Series(dtype="int64")
    if deal_investors is not None and not deal_investors.empty:
        di = deal_investors[["deal_id", "investor_id"]].copy()
        di = di.merge(
            investors[["investor_id", "investor_type_grp"]], on="investor_id", how="left"
        )
        rel_counts = di["investor_type_grp"].value_counts(dropna=False)
        if deals is not None and not deals.empty:
            di = di.merge(deals[["deal_id", "company_id"]], on="deal_id", how="left")
            firm_counts = (
                di.dropna(subset=["company_id"])
                .groupby("investor_type_grp")["company_id"].nunique()
            )

    rows = []
    for grp in n_investors.index:
        grp_key = grp if pd.notna(grp) else None
        rows.append({
            "investor_type_grp": grp if pd.notna(grp) else "(missing)",
            "analytical_group": config.ANALYTICAL_GROUP.get(grp_key, "UNMAPPED"),
            "n_investors": int(n_investors.get(grp, 0)),
            "n_relationships": int(rel_counts.get(grp, 0)) if len(rel_counts) else 0,
            "n_firms": int(firm_counts.get(grp, 0)) if len(firm_counts) else 0,
        })
    out = pd.DataFrame(rows, columns=cols)
    # public first, then private, then exclude/unmapped; stable within group
    order = {config.PUBLIC_LABEL: 0, config.PRIVATE_LABEL: 1,
             config.EXCLUDE_LABEL: 2, "UNMAPPED": 3}
    out["_o"] = out["analytical_group"].map(order).fillna(4)
    out = out.sort_values(["_o", "n_investors"], ascending=[True, False]).drop(columns="_o")
    return out.reset_index(drop=True)


def build_amount_audit(deal_investors: pd.DataFrame) -> pd.DataFrame:
    """Evidence for whether an investor-level contributed amount exists.

    Searches deal_investors_clean columns for an amount-like field. If none
    exists we fall back to deal-level composition (never splitting a deal
    amount across investors).
    """
    cols = list(deal_investors.columns) if deal_investors is not None else []
    keywords = ("amount", "amt", "invest_size", "capital", "contribut",
                "usd", "eur", "stake", "ticket")
    id_like = {"investor_id", "investor_name", "deal_id"}
    amount_like = [
        c for c in cols
        if c not in id_like and any(k in c.lower() for k in keywords)
    ]
    has_amount = len(amount_like) > 0
    row = {
        "deal_investors_columns": ", ".join(cols),
        "amount_like_columns_found": ", ".join(amount_like) if amount_like else "(none)",
        "has_investor_level_amount": int(has_amount),
        "decision": (
            "Investor-level contributed amounts ARE available; compute public/"
            "private capital per investor within the window."
            if has_amount else
            "No investor-level contributed amount exists in deal_investors_clean. "
            "Do NOT split or duplicate a deal amount across investors. Fall back "
            "to deal-level 'deal size by investor composition' "
            f"({config.OUT_CAPITAL_COMPOSITION}.csv)."
        ),
    }
    return pd.DataFrame([row])


def build_relations(
    in_window: pd.DataFrame, deal_investors: pd.DataFrame, investors: pd.DataFrame
) -> pd.DataFrame:
    """One row per (eligible firm, in-window deal, investor) with class flags."""
    base_cols = ["company_id", "deal_id", "deal_date", "rel", "green",
                 "deal_size", "stage_group", "investor_id",
                 "analytical_group", "is_public", "is_private"]
    if in_window is None or in_window.empty or deal_investors is None or deal_investors.empty:
        return pd.DataFrame(columns=base_cols)
    iw = in_window[["company_id", "deal_id", "deal_date", "rel", "green",
                    "deal_size", "stage_group"]].copy()
    di = deal_investors[["deal_id", "investor_id"]].copy()
    inv = classify_investors(investors)
    rel = iw.merge(di, on="deal_id", how="inner")
    rel = rel.merge(
        inv[["investor_id", "analytical_group", "is_public", "is_private"]],
        on="investor_id", how="left",
    )
    rel["is_public"] = _num(rel["is_public"]).fillna(0).astype(int)
    rel["is_private"] = _num(rel["is_private"]).fillna(0).astype(int)
    return rel[base_cols]


# --------------------------------------------------------------------------
# Firm-level participation panel (one row per eligible firm)
# --------------------------------------------------------------------------
def build_firm_panel(
    elig_controls: pd.DataFrame, relations: pd.DataFrame
) -> pd.DataFrame:
    """One row per eligible firm with the common-horizon participation flags.

    `elig_controls` is the Step 5b panel restricted to controls + eligibility
    (company_id, green, cohort, hq_country, primary_industry_group,
    n_deals_5yr). Firms with no in-window investor relationship get 0/0 flags
    and n_investors_5yr = 0 (an observed zero, not missing).
    """
    panel = elig_controls.copy()

    if relations is None or relations.empty:
        panel["has_investor_record_5yr"] = 0
        panel["any_public_5yr"] = 0
        panel["any_private_5yr"] = 0
        panel["both_public_private_5yr"] = 0
        panel["same_deal_public_private_5yr"] = 0
        panel["n_investors_5yr"] = 0
        return panel

    rel = relations
    firm_pub = rel.groupby("company_id")["is_public"].max().rename("any_public_5yr")
    firm_priv = rel.groupby("company_id")["is_private"].max().rename("any_private_5yr")
    n_inv = rel.groupby("company_id")["investor_id"].nunique().rename("n_investors_5yr")

    # same-deal co-investment: a single in-window deal carrying both types
    per_deal = rel.groupby(["company_id", "deal_id"]).agg(
        has_pub=("is_public", "max"), has_priv=("is_private", "max")
    )
    per_deal["deal_both"] = ((per_deal["has_pub"] == 1) & (per_deal["has_priv"] == 1)).astype(int)
    same_deal = per_deal.groupby("company_id")["deal_both"].max().rename(
        "same_deal_public_private_5yr"
    )
    has_record = rel.groupby("company_id").size().rename("_n_rel")

    panel = panel.join(firm_pub, on="company_id").join(firm_priv, on="company_id")
    panel = panel.join(n_inv, on="company_id").join(same_deal, on="company_id")
    panel = panel.join(has_record, on="company_id")

    panel["has_investor_record_5yr"] = (_num(panel["_n_rel"]).fillna(0) > 0).astype(int)
    for col in ("any_public_5yr", "any_private_5yr",
                "same_deal_public_private_5yr", "n_investors_5yr"):
        panel[col] = _num(panel[col]).fillna(0).astype(int)
    panel["both_public_private_5yr"] = (
        (panel["any_public_5yr"] == 1) & (panel["any_private_5yr"] == 1)
    ).astype(int)
    panel = panel.drop(columns=["_n_rel"])
    return panel.reset_index(drop=True)


# --------------------------------------------------------------------------
# Participation table (two denominators)
# --------------------------------------------------------------------------
PARTICIPATION_OUTCOMES = [
    "has_investor_record_5yr",
    "any_public_5yr",
    "any_private_5yr",
    "both_public_private_5yr",
    "same_deal_public_private_5yr",
]


def build_participation(firm_panel: pd.DataFrame) -> pd.DataFrame:
    invested = firm_panel[firm_panel["has_investor_record_5yr"] == 1]
    rows = []
    for outcome in PARTICIPATION_OUTCOMES:
        row = {"outcome": outcome}
        for label, sample in (("invested", invested), ("eligible", firm_panel)):
            g, o = _split(sample)
            gs = _share(_num(g[outcome]) == 1, g)
            os_ = _share(_num(o[outcome]) == 1, o)
            row[f"green_pct_{label}"] = gs
            row[f"other_pct_{label}"] = os_
            row[f"pp_difference_{label}"] = _pp(gs, os_)
            row[f"n_green_{label}"] = int(len(g))
            row[f"n_others_{label}"] = int(len(o))
            row[f"n_startups_{label}"] = int(len(g) + len(o))
        rows.append(row)
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------
# Regression machinery (mirrors step13; adds the deal-count block)
# --------------------------------------------------------------------------
def _clean_control(series: pd.Series, min_n: int) -> pd.Series:
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


def _controls_label(blocks: list[str]) -> str:
    if not blocks:
        return "green"
    names = {"cohort": "cohort", "country": "country_FE",
             "industry": "industry_FE", "dealcount": "deal_count"}
    return "green+" + "+".join(names[b] for b in blocks)


def build_design(
    sample: pd.DataFrame, blocks: list[str], industry_col: str, min_n: int
) -> tuple[pd.DataFrame, dict[str, int]]:
    _require_statsmodels()
    X = pd.DataFrame(index=sample.index)
    X["green"] = _num(sample[config.GREEN_COL]).fillna(0).astype(float)
    meta = {"n_fe_country": 0, "n_fe_industry": 0, "deal_count": 0}

    if "cohort" in blocks:
        X = pd.concat([X, _dummies(_clean_control(sample[config.COHORT_COL], min_n), "cohort")], axis=1)
    if "country" in blocks:
        s = _clean_control(sample[config.COUNTRY_COL], min_n)
        meta["n_fe_country"] = int(s.nunique())
        X = pd.concat([X, _dummies(s, "country")], axis=1)
    if "industry" in blocks:
        s = _clean_control(sample[industry_col], min_n)
        meta["n_fe_industry"] = int(s.nunique())
        X = pd.concat([X, _dummies(s, "industry")], axis=1)
    if "dealcount" in blocks:
        meta["deal_count"] = 1
        X[config.DEALCOUNT_DESIGN_COL] = _num(sample[config.DEALCOUNT_DESIGN_COL]).fillna(0.0).astype(float)

    X = sm.add_constant(X, has_constant="add")
    return X, meta


def fit_ols(y: np.ndarray, X: pd.DataFrame) -> dict[str, float]:
    _require_statsmodels()
    res = sm.OLS(np.asarray(y, dtype=float), X.astype(float)).fit(cov_type=config.COV_TYPE)
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


def regress_outcome(
    frame: pd.DataFrame,
    outcome_col: str,
    outcome_label: str,
    family: str,
    sample_label: str,
    industry_col: str,
    pp_scale: bool = True,
) -> tuple[list[dict], list[dict]]:
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
            "deal_count_control": int("dealcount" in blocks),
            "n_fe_country": meta["n_fe_country"],
            "n_fe_industry": meta["n_fe_industry"],
            "cov_type": config.COV_TYPE,
        })
        audits.append({
            "family": family, "outcome": outcome_label, "spec": spec_name,
            "column": config.SPEC_COLUMN_LABEL[spec_name], "sample": sample_label,
            "n": stats["n"], "n_green": g, "n_other": o,
            "n_unique_firms": n_unique, "n_missing_outcome": n_missing,
            "deal_count_control": int("dealcount" in blocks),
            "n_fe_country": meta["n_fe_country"], "n_fe_industry": meta["n_fe_industry"],
            "cov_type": config.COV_TYPE,
        })
    return rows, audits


def _finalize_table(rows: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(rows, columns=config.RESULT_COLUMNS)
    return _round_cols(df)


REGRESSION_OUTCOMES = [
    ("any_public", "any_public_5yr"),
    ("any_private", "any_private_5yr"),
    ("both_public_private", "both_public_private_5yr"),
    ("same_deal_public_private", "same_deal_public_private_5yr"),
]


def build_regressions(
    firm_panel: pd.DataFrame, industry_col: str
) -> tuple[pd.DataFrame, list[dict]]:
    """LPM (1)-(5) for the four participation outcomes, on the invested sample."""
    invested = firm_panel[firm_panel["has_investor_record_5yr"] == 1].copy()
    invested[config.DEALCOUNT_DESIGN_COL] = np.log1p(_num(invested[config.DEALCOUNT_COL]))
    sample_label = f"in-window investor record ({len(invested)})"
    rows: list[dict] = []
    audits: list[dict] = []
    for label, col in REGRESSION_OUTCOMES:
        r, a = regress_outcome(
            invested, col, label, "participation", sample_label, industry_col,
            pp_scale=True,
        )
        rows += r
        audits += a
    return _finalize_table(rows), audits


# --------------------------------------------------------------------------
# Sequencing: grant -> VC (in-window)
# --------------------------------------------------------------------------
def _gv_row(measure, g_stat, o_stat, n_g, n_o) -> dict:
    return {
        "measure": measure,
        "green_stat": g_stat,
        "other_stat": o_stat,
        "difference": _diff(g_stat, o_stat),
        "n_green": int(n_g),
        "n_others": int(n_o),
        "n_startups": int(n_g) + int(n_o),
    }


def build_grant_vc_sequencing(in_window: pd.DataFrame) -> pd.DataFrame:
    cols = ["measure", "green_stat", "other_stat", "difference",
            "n_green", "n_others", "n_startups"]
    if in_window is None or in_window.empty:
        return pd.DataFrame(columns=cols)
    d = in_window[["company_id", "green", "deal_date", "stage_group"]].copy()
    d["deal_date"] = pd.to_datetime(d["deal_date"], errors="coerce")
    grant = (d[d["stage_group"] == config.GRANT_STAGE_GROUP]
             .groupby("company_id")["deal_date"].min().rename("grant_date"))
    vc = (d[d["stage_group"].isin(config.VC_STAGE_GROUPS)]
          .groupby("company_id")["deal_date"].min().rename("vc_date"))
    green_by = d.groupby("company_id")["green"].first()
    per = pd.concat([grant, vc, green_by], axis=1).reset_index()

    both = per[per["grant_date"].notna() & per["vc_date"].notna()].copy()
    both["grant_first"] = both["grant_date"] < both["vc_date"]
    both["vc_first"] = both["vc_date"] < both["grant_date"]
    both["same_date"] = both["grant_date"] == both["vc_date"]
    both["months"] = (both["vc_date"] - both["grant_date"]).dt.days / 30.44

    gb, ob = _split(both)
    rows = [
        _gv_row("n_firms_grant_and_vc", len(gb), len(ob), len(gb), len(ob)),
        _gv_row("pct_grant_first", _share(gb["grant_first"], gb),
                _share(ob["grant_first"], ob), len(gb), len(ob)),
        _gv_row("pct_vc_first", _share(gb["vc_first"], gb),
                _share(ob["vc_first"], ob), len(gb), len(ob)),
        _gv_row("pct_same_date", _share(gb["same_date"], gb),
                _share(ob["same_date"], ob), len(gb), len(ob)),
    ]
    g_pre, o_pre = gb[gb["grant_first"]], ob[ob["grant_first"]]
    rows.append(_gv_row("median_months_grant_to_vc",
                        _median(g_pre["months"]), _median(o_pre["months"]),
                        len(g_pre), len(o_pre)))
    return pd.DataFrame(rows, columns=cols)


# --------------------------------------------------------------------------
# Sequencing: public -> private ordering (in-window)
# --------------------------------------------------------------------------
def _first_dates(relations: pd.DataFrame) -> pd.DataFrame:
    """Per firm: earliest public-bearing and private-bearing in-window deal date,
    same-deal flag, and green."""
    rel = relations.copy()
    rel["deal_date"] = pd.to_datetime(rel["deal_date"], errors="coerce")
    pub = (rel[rel["is_public"] == 1].groupby("company_id")["deal_date"].min()
           .rename("public_date"))
    priv = (rel[rel["is_private"] == 1].groupby("company_id")["deal_date"].min()
            .rename("private_date"))
    green_by = rel.groupby("company_id")["green"].first()
    per_deal = rel.groupby(["company_id", "deal_id"]).agg(
        has_pub=("is_public", "max"), has_priv=("is_private", "max"))
    per_deal["both"] = ((per_deal["has_pub"] == 1) & (per_deal["has_priv"] == 1)).astype(int)
    same_deal = per_deal.groupby("company_id")["both"].max().rename("same_deal")
    per = pd.concat([pub, priv, same_deal, green_by], axis=1).reset_index()
    return per


def build_pubpriv_sequencing(relations: pd.DataFrame) -> pd.DataFrame:
    cols = ["measure", "green_stat", "other_stat", "difference",
            "n_green", "n_others", "n_startups"]
    if relations is None or relations.empty:
        return pd.DataFrame(columns=cols)
    per = _first_dates(relations)
    both = per[per["public_date"].notna() & per["private_date"].notna()].copy()
    if both.empty:
        return pd.DataFrame(columns=cols)
    both["public_first"] = both["public_date"] < both["private_date"]
    both["private_first"] = both["private_date"] < both["public_date"]
    both["same_date"] = both["public_date"] == both["private_date"]
    both["same_deal"] = _num(both["same_deal"]).fillna(0).astype(int) == 1
    both["months"] = (both["private_date"] - both["public_date"]).dt.days / 30.44

    gb, ob = _split(both)
    rows = [
        _gv_row("n_firms_public_and_private", len(gb), len(ob), len(gb), len(ob)),
        _gv_row("pct_public_first", _share(gb["public_first"], gb),
                _share(ob["public_first"], ob), len(gb), len(ob)),
        _gv_row("pct_private_first", _share(gb["private_first"], gb),
                _share(ob["private_first"], ob), len(gb), len(ob)),
        _gv_row("pct_same_date", _share(gb["same_date"], gb),
                _share(ob["same_date"], ob), len(gb), len(ob)),
        _gv_row("pct_same_deal", _share(gb["same_deal"], gb),
                _share(ob["same_deal"], ob), len(gb), len(ob)),
    ]
    g_pre, o_pre = gb[gb["public_first"]], ob[ob["public_first"]]
    rows.append(_gv_row("median_months_public_to_private",
                        _median(g_pre["months"]), _median(o_pre["months"]),
                        len(g_pre), len(o_pre)))
    return pd.DataFrame(rows, columns=cols)


def build_ordering_regression(
    relations: pd.DataFrame, firm_panel: pd.DataFrame, industry_col: str
) -> tuple[pd.DataFrame, list[dict]]:
    """Supplementary LPM for public_precedes_private among firms with both.

    Selected sample: firms that have BOTH an in-window public and private
    investor (a conditional, not a population, statement).
    """
    empty = pd.DataFrame(columns=config.RESULT_COLUMNS)
    if relations is None or relations.empty:
        return empty, []
    per = _first_dates(relations)
    both = per[per["public_date"].notna() & per["private_date"].notna()].copy()
    if both.empty:
        return empty, []
    both["public_precedes_private"] = (both["public_date"] < both["private_date"]).astype(int)

    ctrl_cols = ["company_id", config.GREEN_COL, config.COHORT_COL,
                 config.COUNTRY_COL, industry_col, config.DEALCOUNT_COL]
    ctrl = firm_panel[[c for c in ctrl_cols if c in firm_panel.columns]].copy()
    frame = both[["company_id", "public_precedes_private"]].merge(
        ctrl, on="company_id", how="left")
    frame[config.DEALCOUNT_DESIGN_COL] = np.log1p(_num(frame[config.DEALCOUNT_COL]))
    sample_label = f"firms with both public and private in-window ({len(frame)})"
    rows, audits = regress_outcome(
        frame, "public_precedes_private", "public_precedes_private",
        "ordering", sample_label, industry_col, pp_scale=True,
    )
    return _finalize_table(rows), audits


# --------------------------------------------------------------------------
# Capital by investor composition (deal-level; disclosed only, never zeroed)
# --------------------------------------------------------------------------
def _deal_composition(in_window: pd.DataFrame, relations: pd.DataFrame) -> pd.DataFrame:
    """Per in-window deal: green, deal_size, and public/private composition."""
    deals = in_window[["company_id", "deal_id", "green", "deal_size"]].drop_duplicates(
        subset=["company_id", "deal_id"]
    ).copy()
    if relations is None or relations.empty:
        deals["has_pub"] = 0
        deals["has_priv"] = 0
    else:
        per_deal = relations.groupby(["company_id", "deal_id"]).agg(
            has_pub=("is_public", "max"), has_priv=("is_private", "max")
        ).reset_index()
        deals = deals.merge(per_deal, on=["company_id", "deal_id"], how="left")
        deals["has_pub"] = _num(deals["has_pub"]).fillna(0).astype(int)
        deals["has_priv"] = _num(deals["has_priv"]).fillna(0).astype(int)

    def _comp(row) -> str:
        p, v = row["has_pub"] == 1, row["has_priv"] == 1
        if p and v:
            return "mixed_public_private"
        if p:
            return "public_only"
        if v:
            return "private_only"
        return "other_or_neither"

    deals["composition"] = deals.apply(_comp, axis=1)
    return deals


def build_capital_composition(
    in_window: pd.DataFrame, relations: pd.DataFrame
) -> pd.DataFrame:
    """Disclosed in-window deal size by investor composition (NOT capital amount).

    Only deals with a disclosed deal_size enter; missing sizes are never
    zero-filled. This is deal size grouped by the public/private composition of
    the investors on the deal, not a per-investor capital allocation.
    """
    cols = ["composition", "group", "median_deal_size", "sum_deal_size",
            "n_deals_disclosed", "n_firms", "n_green", "n_others", "n_startups"]
    if in_window is None or in_window.empty:
        return pd.DataFrame(columns=cols)
    deals = _deal_composition(in_window, relations)
    disclosed = deals[_num(deals["deal_size"]).notna()].copy()
    disclosed["deal_size"] = _num(disclosed["deal_size"])

    order = ["public_only", "private_only", "mixed_public_private", "other_or_neither"]
    rows = []
    for comp in order:
        sub = disclosed[disclosed["composition"] == comp]
        g, o = _split(sub)
        n_fg = int(g["company_id"].nunique())
        n_fo = int(o["company_id"].nunique())
        for label, part, n_firms in ((config.GREEN_LABEL, g, n_fg),
                                     (config.OTHER_LABEL, o, n_fo)):
            rows.append({
                "composition": comp,
                "group": label,
                "median_deal_size": _median(part["deal_size"]),
                "sum_deal_size": round(float(_num(part["deal_size"]).sum()), config.DECIMALS)
                if len(part) else float("nan"),
                "n_deals_disclosed": int(len(part)),
                "n_firms": n_firms,
                "n_green": n_fg,
                "n_others": n_fo,
                "n_startups": n_fg + n_fo,
            })
    return pd.DataFrame(rows, columns=cols)


# --------------------------------------------------------------------------
# Orchestration
# --------------------------------------------------------------------------
def build_all(
    firm_panel_5b: pd.DataFrame,
    firm: pd.DataFrame,
    deals: pd.DataFrame,
    deal_investors: pd.DataFrame,
    investors: pd.DataFrame,
    industry_col: str | None = None,
) -> Step14Result:
    from empirical_analysis.step5b_fixed_horizon.build import prepare_window

    industry_col = industry_col or config.INDUSTRY_COL
    result = Step14Result()

    elig, in_window, win_diag = prepare_window(firm, deals)

    # controls come from the Step 5b canonical panel (restricted to eligible)
    ctrl_cols = ["company_id", config.GREEN_COL, config.COHORT_COL,
                 config.COUNTRY_COL, config.INDUSTRY_COL_GROUP, config.DEALCOUNT_COL]
    ctrl = firm_panel_5b[[c for c in ctrl_cols if c in firm_panel_5b.columns]].copy()

    relations = build_relations(in_window, deal_investors, investors)

    # 1. classification audit
    result.tables[config.OUT_MAPPING] = build_investor_mapping(investors, deal_investors, deals)
    result.tables[config.OUT_AMOUNT_AUDIT] = build_amount_audit(deal_investors)

    # 2. firm-level participation panel + table
    firm_panel = build_firm_panel(ctrl, relations)
    result.firm_panel = firm_panel
    result.tables[config.OUT_PARTICIPATION] = build_participation(firm_panel)

    # 3. adjusted regressions
    reg_table, reg_audit = build_regressions(firm_panel, industry_col)
    result.tables[config.OUT_REGRESSION] = reg_table

    # 4. sequencing
    result.tables[config.OUT_GRANT_VC] = build_grant_vc_sequencing(in_window)
    result.tables[config.OUT_SEQUENCING] = build_pubpriv_sequencing(relations)
    ord_table, ord_audit = build_ordering_regression(relations, firm_panel, industry_col)
    result.tables[config.OUT_ORDERING_REG] = ord_table

    # 5. capital by composition
    result.tables[config.OUT_CAPITAL_COMPOSITION] = build_capital_composition(in_window, relations)

    invested = firm_panel[firm_panel["has_investor_record_5yr"] == 1]
    both_n = int((firm_panel["both_public_private_5yr"] == 1).sum())
    result.diagnostics = {
        "n_eligible": int(len(firm_panel)),
        "n_eligible_green": int((firm_panel[config.GREEN_COL] == 1).sum()),
        "n_eligible_other": int((firm_panel[config.GREEN_COL] != 1).sum()),
        "n_invested": int(len(invested)),
        "n_invested_green": int((invested[config.GREEN_COL] == 1).sum()),
        "n_invested_other": int((invested[config.GREEN_COL] != 1).sum()),
        "n_both_public_private": both_n,
        "industry_col": industry_col,
        "reg_audit": reg_audit,
        "ordering_audit": ord_audit,
        "observed_investor_types": sorted(
            [t for t in investors["investor_type_grp"].dropna().unique()]
        ) if investors is not None and not investors.empty else [],
        "win_diag": {k: v for k, v in win_diag.items() if not str(k).startswith("_")},
    }
    return result


# --------------------------------------------------------------------------
# Captions
# --------------------------------------------------------------------------
def build_captions(result: Step14Result) -> pd.DataFrame:
    diag = result.diagnostics
    cap = result.caption
    n_elig = diag.get("n_eligible")
    n_inv = diag.get("n_invested")

    pub = sorted([k for k, v in config.ANALYTICAL_GROUP.items() if v == config.PUBLIC_LABEL])
    priv = sorted([k for k, v in config.ANALYTICAL_GROUP.items() if v == config.PRIVATE_LABEL])
    exc = sorted([k for k, v in config.ANALYTICAL_GROUP.items() if v == config.EXCLUDE_LABEL])

    cap[config.OUT_MAPPING] = (
        f"Explicit investor classification (defines exactly which categories "
        f"count as public and private). PUBLIC={pub}; PRIVATE={priv}; "
        f"EXCLUDE={exc}. Covers 100% of observed investor_type_grp values. "
        "n_investors from investors_clean; n_relationships from "
        "deal_investors_clean; n_firms = distinct companies reached."
    )
    cap[config.OUT_AMOUNT_AUDIT] = (
        "Audit of whether an investor-level contributed amount exists. It does "
        "not, so public/private capital cannot be measured per investor; we fall "
        "back to disclosed deal size by investor composition and never split or "
        "duplicate a deal amount across investors."
    )
    cap[config.OUT_FIRM_PANEL] = (
        f"One row per common-horizon eligible firm (n={n_elig}) with in-window "
        "investor participation flags: has_investor_record_5yr, any_public_5yr, "
        "any_private_5yr, both_public_private_5yr, same_deal_public_private_5yr "
        "(a single in-window deal carrying both types; a subset of "
        "both_public_private_5yr), and n_investors_5yr. Firms with no in-window "
        "investor relationship have 0 flags and n_investors_5yr=0 (observed zero)."
    )
    cap[config.OUT_PARTICIPATION] = (
        f"Public/private participation within each firm's first five post-founding "
        f"years, green vs other, under two denominators: primary = firms with >=1 "
        f"in-window investor relationship (n={n_inv}, matching Step 6's INVESTED "
        f"logic); sensitivity = all {n_elig} eligible firms. Reporting both makes "
        "investor-record coverage transparent rather than treating 'no recorded "
        "investor' as substantive non-participation."
    )
    cap[config.OUT_REGRESSION] = (
        f"Linear probability models (HC1 SE) for four participation outcomes "
        "(any_public, any_private, both_public_private, same_deal_public_private) "
        f"on the investor-record sample (n={n_inv}). Columns (1) green; (2) "
        "+cohort; (3) +country FE; (4) +industry FE are the MAIN specifications; "
        "column (5) '+ deal count' additionally controls for log(1+n_deals_5yr) "
        "and is an Enrico-requested SENSITIVITY, not the baseline (deal count is "
        "part of financing history and may sit downstream of green status). "
        "Coefficients stored raw (0-1) and as percentage points (coef_pp/se_pp); "
        "stars from the stored p-value (* p<.10, ** p<.05, *** p<.01)."
    )
    cap[config.OUT_GRANT_VC] = (
        "Descriptive grant->VC sequencing within the five-year window, among "
        "eligible firms with BOTH an in-window grant and in-window VC event: "
        "grant first / VC first / same date, and median months grant-to-VC "
        "(grant-first firms). Descriptive ordering only -- not evidence the grant "
        "caused later VC."
    )
    cap[config.OUT_SEQUENCING] = (
        "Descriptive public/private ordering within the five-year window, among "
        "eligible firms with BOTH an in-window public and in-window private "
        "investor: public first / private first / same date / same deal, and "
        "median months public-to-private. Descriptive; not a crowding-in claim."
    )
    cap[config.OUT_ORDERING_REG] = (
        "SUPPLEMENTARY adjusted LPM for public_precedes_private, estimated only on "
        "firms that have BOTH an in-window public and private investor. This "
        "sample is selected on receiving both types of capital, so it is a "
        "conditional, not a population, statement. Columns (1)-(5) as above."
    )
    cap[config.OUT_CAPITAL_COMPOSITION] = (
        "DEAL SIZE BY INVESTOR COMPOSITION (not 'public/private capital amount'): "
        "no investor-level contributed amount exists, so disclosed in-window deals "
        "are classified as public-only / private-only / mixed public-private / "
        "other-or-neither by the investor types present, and their disclosed deal "
        "sizes compared. Only disclosed deals enter; missing sizes are never "
        "zero-filled. A deal amount is never allocated across its investors."
    )
    cap["_interpretation"] = (
        "All associations are conditional, not causal. same_deal co-investment is "
        "logically a subset of ever-both. Participation depends on investor-record "
        "coverage (hence two denominators). This does not address survivor-"
        "selection (Step 10)."
    )
    rows = [{"output": k, "caption": v} for k, v in cap.items()]
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------
# Output writing
# --------------------------------------------------------------------------
def write_outputs(result: Step14Result, output_dir: Path | None = None) -> Path:
    out = Path(output_dir or config.OUTPUT_DIR)
    out.mkdir(parents=True, exist_ok=True)

    csv_names = [
        config.OUT_MAPPING, config.OUT_AMOUNT_AUDIT, config.OUT_PARTICIPATION,
        config.OUT_REGRESSION, config.OUT_GRANT_VC, config.OUT_SEQUENCING,
        config.OUT_ORDERING_REG, config.OUT_CAPITAL_COMPOSITION,
    ]
    for name in csv_names:
        df = result.tables.get(name, pd.DataFrame())
        path = out / f"{name}.csv"
        df.to_csv(path, index=False)
        print(f"[step14] wrote {path}  ({len(df)} rows)")

    if len(result.firm_panel):
        panel_path = out / f"{config.OUT_FIRM_PANEL}.parquet"
        result.firm_panel.to_parquet(panel_path, index=False)
        print(f"[step14] wrote {panel_path}  ({len(result.firm_panel)} rows)")

    audit = pd.DataFrame(result.diagnostics.get("reg_audit", []) +
                         result.diagnostics.get("ordering_audit", []))
    audit_path = out / f"{config.SAMPLE_AUDIT}.csv"
    audit.to_csv(audit_path, index=False)
    print(f"[step14] wrote {audit_path}  ({len(audit)} rows)")

    cap_df = build_captions(result)
    cap_path = out / f"{config.CAPTIONS_FILE}.csv"
    cap_df.to_csv(cap_path, index=False)
    print(f"[step14] wrote {cap_path}  ({len(cap_df)} rows)")
    return out


# --------------------------------------------------------------------------
# Acceptance report (printed by run.py)
# --------------------------------------------------------------------------
def _protected_names() -> set[str]:
    names: set[str] = set()
    try:
        from empirical_analysis.step5b_fixed_horizon import config as c5b
        names |= set(c5b.STEP5_PROTECTED_NAMES)
        names |= {c5b.OUT_ACCESS, c5b.OUT_TIMING, c5b.OUT_CAPITAL,
                  c5b.OUT_FIRST_CHANNEL, c5b.CAPTIONS_FILE, c5b.FIGURE_ACCESS,
                  c5b.FIRM_PANEL, c5b.FIRM_AUDIT}
    except Exception:
        pass
    try:
        from empirical_analysis.step13_regression import config as c13
        names |= set(c13.STEP13_OUTPUT_NAMES)
    except Exception:
        pass
    return names


def acceptance_report(result: Step14Result) -> list[str]:
    lines: list[str] = []
    diag = result.diagnostics
    panel = result.firm_panel

    # C1: classification covers 100% of observed investor_type_grp values.
    observed = set(diag.get("observed_investor_types", []))
    unmapped = sorted(observed - set(config.ANALYTICAL_GROUP))
    mapping = result.tables.get(config.OUT_MAPPING, pd.DataFrame())
    mapping_unmapped = []
    if len(mapping):
        mapping_unmapped = mapping.loc[
            mapping["analytical_group"] == "UNMAPPED", "investor_type_grp"
        ].tolist()
    c1 = (not unmapped) and (not mapping_unmapped)
    lines.append(
        f"[C1] investor classification covers 100% of observed investor_type_grp "
        f"({len(observed)} types): {'PASS' if c1 else 'FAIL'}"
        + (f"  UNMAPPED={unmapped or mapping_unmapped}" if not c1 else "")
    )

    # C2: same-deal co-investment is a subset of ever-both.
    c2 = True
    if len(panel):
        viol = panel[(panel["same_deal_public_private_5yr"] == 1)
                     & (panel["both_public_private_5yr"] != 1)]
        c2 = len(viol) == 0
    lines.append(
        f"[C2] same_deal_public_private_5yr subset of both_public_private_5yr: "
        f"{'PASS' if c2 else 'FAIL'}"
    )

    # C3: two denominators reported; invested <= eligible.
    n_elig = int(diag.get("n_eligible", 0))
    n_inv = int(diag.get("n_invested", 0))
    part = result.tables.get(config.OUT_PARTICIPATION, pd.DataFrame())
    has_both = bool(len(part)) and {
        "green_pct_invested", "green_pct_eligible"
    } <= set(part.columns)
    c3 = has_both and (n_inv <= n_elig)
    lines.append(
        f"[C3] participation reports invested + eligible denominators and "
        f"invested ({n_inv}) <= eligible ({n_elig}): {'PASS' if c3 else 'FAIL'}"
    )

    # C4: regressions -- specs (1)-(5), n == invested sample, one row per firm,
    # (n) labels only (never M0-M3).
    reg = result.tables.get(config.OUT_REGRESSION, pd.DataFrame())
    audit = pd.DataFrame(diag.get("reg_audit", []))
    specs_ok = labels_ok = n_ok = unique_ok = True
    expected_specs = {name for name, _ in config.SPECS}
    expected_cols = set(config.SPEC_COLUMN_LABEL.values())
    if len(reg):
        for outcome, grp in reg.groupby("outcome"):
            if set(grp["spec"]) != expected_specs:
                specs_ok = False
            if not set(grp["column"]) <= expected_cols:
                labels_ok = False
            if not (grp["n"] == n_inv).all():
                n_ok = False
    if len(audit):
        if not (audit["n"] == audit["n_unique_firms"]).all():
            unique_ok = False
    lines.append(
        f"[C4] regressions have specs (1)-(5) with (n) labels only: "
        f"{'PASS' if specs_ok and labels_ok else 'FAIL'}; n == invested sample "
        f"({n_inv}) on every spec: {'PASS' if n_ok else 'FAIL'}; one row per firm: "
        f"{'PASS' if unique_ok else 'FAIL'}"
    )

    # C5: column (5) carries the deal-count control; (1)-(4) do not.
    c5 = True
    if len(reg):
        c5 = (
            (reg.loc[reg["column"] == "(5)", "deal_count_control"] == 1).all()
            and (reg.loc[reg["column"] != "(5)", "deal_count_control"] == 0).all()
        )
    lines.append(
        f"[C5] deal-count control present only in column (5): "
        f"{'PASS' if c5 else 'FAIL'}"
    )

    # C6: pp columns scale coef/std_error; stars match config.STAR_RULE.
    pp_ok = stars_ok = True
    for tbl in (reg, result.tables.get(config.OUT_ORDERING_REG, pd.DataFrame())):
        if not len(tbl):
            continue
        expect_pp = (_num(tbl["coef"]) * 100).round(config.DECIMALS_PP)
        if not np.allclose(expect_pp.to_numpy(float),
                           _num(tbl["coef_pp"]).to_numpy(float),
                           atol=10 ** (-config.DECIMALS_PP), equal_nan=True):
            pp_ok = False
        if not (tbl["p_value"].apply(_stars) == tbl["stars"]).all():
            stars_ok = False
    lines.append(
        f"[C6] pp display columns scale coef by 100: {'PASS' if pp_ok else 'FAIL'}; "
        f"stars match stored p-values: {'PASS' if stars_ok else 'FAIL'}"
    )

    # C7: deal-size-by-composition uses disclosed deals only (never zero-filled).
    comp = result.tables.get(config.OUT_CAPITAL_COMPOSITION, pd.DataFrame())
    c7 = True
    if len(comp):
        # median must be NaN exactly when there are no disclosed deals in a cell
        bad = comp[(comp["n_deals_disclosed"] == 0) & comp["median_deal_size"].notna()]
        c7 = len(bad) == 0
    lines.append(
        f"[C7] deal-size-by-composition uses disclosed deals only, missing sizes "
        f"never zero-filled: {'PASS' if c7 else 'FAIL'}"
    )

    # C8: output names disjoint from Step 5/5b/6/13 and self-scoped.
    produced = set(config.STEP14_OUTPUT_NAMES)
    collision = produced & _protected_names()
    lines.append(
        f"[C8] outputs disjoint from earlier steps and self-scoped: "
        f"{'PASS' if not collision else 'FAIL'}"
        + (f"  COLLISION={sorted(collision)}" if collision else "")
    )
    return lines
