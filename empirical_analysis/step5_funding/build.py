"""Step 5 build logic: the funding tables.

Everything is descriptive. Access is measured on the full population (rule N2);
amounts, sizes, valuations, lags and trajectories are measured only within the
financed subsample (rule N1) because green firms are far better documented and a
raw amount comparison would measure coverage, not capital. Lifetime amounts are
reported within founding cohort (rule N4); horizon and follow-on measures are
censored to firms with a full observation window (rule R4). Medians are primary
(rule N6). Every table ends with the uniform n_green / n_others / n_startups trio.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from . import config


@dataclass
class Step5Result:
    tables: dict[str, pd.DataFrame] = field(default_factory=dict)
    caption: dict[str, str] = field(default_factory=dict)
    diagnostics: dict[str, float] = field(default_factory=dict)


# --------------------------------------------------------------------------
# Small statistics helpers
# --------------------------------------------------------------------------
def _num(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def _split(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    green = df[df["green"] == 1]
    other = df[df["green"] != 1]
    return green, other


def _financed(firm: pd.DataFrame) -> pd.DataFrame:
    return firm[firm["financed"] == 1]


def _median(series: pd.Series) -> float:
    s = _num(series).dropna()
    return round(float(s.median()), 2) if len(s) else float("nan")


def _quantile(series: pd.Series, q: float) -> float:
    s = _num(series).dropna()
    return round(float(s.quantile(q)), 2) if len(s) else float("nan")


def _mean(series: pd.Series) -> float:
    s = _num(series).dropna()
    return round(float(s.mean()), 2) if len(s) else float("nan")


def _n_nonnull(series: pd.Series) -> int:
    return int(_num(series).notna().sum())


def _pp(green_share: float, other_share: float) -> float:
    if pd.isna(green_share) or pd.isna(other_share):
        return float("nan")
    return round((green_share - other_share) * 100, 1)


def _ratio(green: float, other: float) -> float:
    if pd.isna(green) or pd.isna(other) or other == 0:
        return float("nan")
    return round(green / other, 3)


def _stage_sort(values) -> list:
    """Order stage_group values by STAGE_GROUP_ORDER; unknowns appended after."""
    order = {name: i for i, name in enumerate(config.STAGE_GROUP_ORDER)}
    present = [v for v in values if pd.notna(v)]
    return sorted(set(present), key=lambda v: order.get(v, len(order)))


def _is_stage1(df: pd.DataFrame) -> pd.Series:
    return (df["green"] == 1) & (df["green_signal_group"] == config.STAGE1_LABEL)


def _is_stage23(df: pd.DataFrame) -> pd.Series:
    return (df["green"] == 1) & (df["green_signal_group"] == config.STAGE23_LABEL)


# --------------------------------------------------------------------------
# T4.9 access to finance (full population, rule N2)
# --------------------------------------------------------------------------
def build_funding_access(firm: pd.DataFrame) -> pd.DataFrame:
    g, o = _split(firm)
    s1 = firm[_is_stage1(firm)]
    s23 = firm[_is_stage23(firm)]
    rows = []
    for label, col in config.ACCESS_FLAGS:
        if col not in firm.columns:
            continue
        g_hit = (g[col] == 1)
        o_hit = (o[col] == 1)
        gs = float(g_hit.mean()) if len(g) else float("nan")
        os_ = float(o_hit.mean()) if len(o) else float("nan")
        s1s = float((s1[col] == 1).mean()) if len(s1) else float("nan")
        s23s = float((s23[col] == 1).mean()) if len(s23) else float("nan")
        gn = int(g_hit.sum())
        on = int(o_hit.sum())
        rows.append(
            {
                "financing_type": label,
                "green_pct": round(gs, 4),
                "other_pct": round(os_, 4),
                "pp_difference": _pp(gs, os_),
                "green_pct_stage1": round(s1s, 4),
                "green_pct_stage2plus3": round(s23s, 4),
                "n_green": gn,
                "n_others": on,
                "n_startups": gn + on,
            }
        )
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------
# T4.9b access to finance by founding cohort (full population, rules N2, N4)
# --------------------------------------------------------------------------
def build_funding_access_by_cohort(firm: pd.DataFrame) -> pd.DataFrame:
    """Cohort-adjusted access: each headline flag's green-vs-other reach within
    founding cohort. Access stays on the full population (rule N2, denominator is the
    cohort's green / other firms); reporting by cohort (rule N4) controls for the fact
    that older firms have had longer to raise. Shares use the cohort-group denominator,
    while the n_green / n_others trio counts firms carrying the flag (as in T4.9)."""
    rows = []
    for label, col in config.ACCESS_FLAGS_BY_COHORT:
        if col not in firm.columns:
            continue
        for cohort in config.COHORT_ORDER:
            sub = firm[firm["cohort"] == cohort]
            g, o = _split(sub)
            g_hit = (g[col] == 1)
            o_hit = (o[col] == 1)
            gs = float(g_hit.mean()) if len(g) else float("nan")
            os_ = float(o_hit.mean()) if len(o) else float("nan")
            gn = int(g_hit.sum())
            on = int(o_hit.sum())
            rows.append(
                {
                    "financing_type": label,
                    "cohort": cohort,
                    "green_pct": round(gs, 4),
                    "other_pct": round(os_, 4),
                    "pp_difference": _pp(gs, os_),
                    "green_n_cohort": len(g),
                    "other_n_cohort": len(o),
                    "low_n_flag": int(len(g) < config.LOW_N_FLAG),
                    "n_green": gn,
                    "n_others": on,
                    "n_startups": gn + on,
                }
            )
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------
# T4.10 total raised by cohort (financed subsample, rules N1, N4)
# --------------------------------------------------------------------------
def build_total_raised_by_cohort(firm: pd.DataFrame) -> pd.DataFrame:
    fin = _financed(firm)
    rows = []
    for field_name in config.AMOUNT_FIELDS:
        if field_name not in fin.columns:
            continue
        for cohort in config.COHORT_ORDER:
            sub = fin[fin["cohort"] == cohort]
            g, o = _split(sub)
            gv, ov = _num(g[field_name]), _num(o[field_name])
            g_med, o_med = _median(gv), _median(ov)
            s1 = sub[_is_stage1(sub)]
            s23 = sub[_is_stage23(sub)]
            rows.append(
                {
                    "amount_field": field_name,
                    "cohort": cohort,
                    "green_median": g_med,
                    "green_q25": _quantile(gv, 0.25),
                    "green_q75": _quantile(gv, 0.75),
                    "green_mean": _mean(gv),
                    "green_p90": _quantile(gv, config.P90),
                    "other_median": o_med,
                    "other_q25": _quantile(ov, 0.25),
                    "other_q75": _quantile(ov, 0.75),
                    "other_mean": _mean(ov),
                    "other_p90": _quantile(ov, config.P90),
                    "median_ratio": _ratio(g_med, o_med),
                    "green_median_stage1": _median(s1[field_name]),
                    "green_median_stage2plus3": _median(s23[field_name]),
                    "n_green": _n_nonnull(gv),
                    "n_others": _n_nonnull(ov),
                    "n_startups": _n_nonnull(gv) + _n_nonnull(ov),
                }
            )
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------
# First-deal helper (earliest deal per firm from deals_clean)
# --------------------------------------------------------------------------
def _first_deals(deals: pd.DataFrame) -> pd.DataFrame:
    """One row per firm: its earliest deal's stage_group, size, size actuality."""
    cols = ["company_id", "stage_group", "deal_size", "size_is_actual"]
    if deals.empty:
        return pd.DataFrame(columns=cols)
    d = deals.copy()
    d["deal_date"] = pd.to_datetime(d["deal_date"], errors="coerce")
    if "is_first_deal" in d.columns and int((d["is_first_deal"] == 1).sum()) > 0:
        first = d[d["is_first_deal"] == 1].copy()
    else:
        first = d.copy()
    # Guard against ties/duplicates: keep the earliest dated row per firm.
    first = first.sort_values(["company_id", "deal_date"], kind="stable")
    first = first.drop_duplicates("company_id", keep="first")
    for c in cols:
        if c not in first.columns:
            first[c] = pd.NA
    return first[cols].reset_index(drop=True)


# --------------------------------------------------------------------------
# T4.11 first financing size by stage (financed subsample)
# --------------------------------------------------------------------------
def build_first_size_by_stage(firm: pd.DataFrame, deals: pd.DataFrame) -> pd.DataFrame:
    cols = [
        "stage_group", "green_median", "green_q25", "green_q75",
        "other_median", "other_q25", "other_q75", "median_ratio",
        "share_size_actual", "n_green", "n_others", "n_startups",
    ]
    fd = _first_deals(deals)
    if fd.empty:
        return pd.DataFrame(columns=cols)
    green_by = firm.set_index(firm["company_id"].astype("string"))["green"]
    fd["company_id"] = fd["company_id"].astype("string")
    fd["green"] = fd["company_id"].map(green_by).fillna(0).astype(int)
    fd["deal_size"] = _num(fd["deal_size"])
    fd["size_is_actual"] = _num(fd["size_is_actual"])

    rows = []
    for stage in _stage_sort(fd["stage_group"].dropna().unique()):
        sub = fd[fd["stage_group"] == stage]
        with_size = sub[sub["deal_size"].notna()]
        g, o = _split(with_size)
        g_med, o_med = _median(g["deal_size"]), _median(o["deal_size"])
        rows.append(
            {
                "stage_group": stage,
                "green_median": g_med,
                "green_q25": _quantile(g["deal_size"], 0.25),
                "green_q75": _quantile(g["deal_size"], 0.75),
                "other_median": o_med,
                "other_q25": _quantile(o["deal_size"], 0.25),
                "other_q75": _quantile(o["deal_size"], 0.75),
                "median_ratio": _ratio(g_med, o_med),
                "share_size_actual": (
                    round(float(with_size["size_is_actual"].mean()), 4)
                    if len(with_size) else float("nan")
                ),
                "n_green": len(g),
                "n_others": len(o),
                "n_startups": len(with_size),
            }
        )
    return pd.DataFrame(rows, columns=cols)


# --------------------------------------------------------------------------
# T4.12 post-money valuation (financed subsample, low coverage)
# --------------------------------------------------------------------------
def build_post_valuation(firm: pd.DataFrame, deals: pd.DataFrame) -> pd.DataFrame:
    cols = ["group", "median", "q25", "q75", "n_green", "n_others", "n_startups"]
    if deals.empty or "post_valuation" not in deals.columns:
        return pd.DataFrame(columns=cols)
    d = deals[["company_id", "post_valuation"]].copy()
    d["company_id"] = d["company_id"].astype("string")
    d["post_valuation"] = _num(d["post_valuation"])
    d = d[d["post_valuation"].notna()]
    if d.empty:
        return pd.DataFrame(columns=cols)
    # One value per firm: the firm's median valuation across its valued deals.
    per_firm = d.groupby("company_id")["post_valuation"].median().reset_index()
    green_by = firm.set_index(firm["company_id"].astype("string"))["green"]
    per_firm["green"] = per_firm["company_id"].map(green_by).fillna(0).astype(int)
    g, o = _split(per_firm)

    n_g, n_o = len(g), len(o)
    rows = [
        {"group": config.GREEN_LABEL, "median": _median(g["post_valuation"]),
         "q25": _quantile(g["post_valuation"], 0.25),
         "q75": _quantile(g["post_valuation"], 0.75),
         "n_green": n_g, "n_others": 0, "n_startups": n_g},
        {"group": config.OTHER_LABEL, "median": _median(o["post_valuation"]),
         "q25": _quantile(o["post_valuation"], 0.25),
         "q75": _quantile(o["post_valuation"], 0.75),
         "n_green": 0, "n_others": n_o, "n_startups": n_o},
        {"group": "All financed", "median": _median(per_firm["post_valuation"]),
         "q25": _quantile(per_firm["post_valuation"], 0.25),
         "q75": _quantile(per_firm["post_valuation"], 0.75),
         "n_green": n_g, "n_others": n_o, "n_startups": n_g + n_o},
    ]
    return pd.DataFrame(rows, columns=cols)


# --------------------------------------------------------------------------
# T4.13 time to first financing (financed subsample)
# --------------------------------------------------------------------------
def _lag_row(sub: pd.DataFrame, measure: str, cohort: str, with_stage: bool) -> dict:
    g, o = _split(sub)
    gv, ov = _num(g[measure]), _num(o[measure])
    g_med, o_med = _median(gv), _median(ov)
    return {
        "measure": measure,
        "cohort": cohort,
        "green_median": g_med,
        "green_q25": _quantile(gv, 0.25),
        "green_q75": _quantile(gv, 0.75),
        "other_median": o_med,
        "other_q25": _quantile(ov, 0.25),
        "other_q75": _quantile(ov, 0.75),
        "difference": (round(g_med - o_med, 2)
                       if pd.notna(g_med) and pd.notna(o_med) else float("nan")),
        "green_median_stage1": (_median(sub[_is_stage1(sub)][measure])
                                if with_stage else float("nan")),
        "green_median_stage2plus3": (_median(sub[_is_stage23(sub)][measure])
                                     if with_stage else float("nan")),
        "n_green": _n_nonnull(gv),
        "n_others": _n_nonnull(ov),
        "n_startups": _n_nonnull(gv) + _n_nonnull(ov),
    }


def build_time_to_financing(firm: pd.DataFrame) -> pd.DataFrame:
    fin = _financed(firm)
    rows = []
    for measure in ("first_funding_lag", "first_vc_lag"):
        if measure not in fin.columns:
            continue
        rows.append(_lag_row(fin, measure, "all", with_stage=True))
        for cohort in config.COHORT_ORDER:
            rows.append(_lag_row(fin[fin["cohort"] == cohort], measure, cohort,
                                 with_stage=False))
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------
# T4.14 first financing type composition (financed subsample)
# --------------------------------------------------------------------------
def build_first_financing_type(firm: pd.DataFrame, deals: pd.DataFrame) -> pd.DataFrame:
    cols = [
        "stage_group", "green_pct", "other_pct", "pp_difference",
        "green_pct_stage1", "green_pct_stage2plus3",
        "n_green", "n_others", "n_startups",
    ]
    fd = _first_deals(deals)
    if fd.empty:
        return pd.DataFrame(columns=cols)
    attrs = firm.set_index(firm["company_id"].astype("string"))[
        ["green", "green_signal_group"]
    ]
    fd["company_id"] = fd["company_id"].astype("string")
    fd = fd.join(attrs, on="company_id")
    fd["green"] = fd["green"].fillna(0).astype(int)

    g, o = _split(fd)
    s1 = fd[_is_stage1(fd)]
    s23 = fd[_is_stage23(fd)]
    n_g, n_o, n_s1, n_s23 = len(g), len(o), len(s1), len(s23)

    rows = []
    for stage in _stage_sort(fd["stage_group"].dropna().unique()):
        gn = int((g["stage_group"] == stage).sum())
        on = int((o["stage_group"] == stage).sum())
        s1n = int((s1["stage_group"] == stage).sum())
        s23n = int((s23["stage_group"] == stage).sum())
        gs = gn / n_g if n_g else float("nan")
        os_ = on / n_o if n_o else float("nan")
        rows.append(
            {
                "stage_group": stage,
                "green_pct": round(gs, 4),
                "other_pct": round(os_, 4),
                "pp_difference": _pp(gs, os_),
                "green_pct_stage1": round(s1n / n_s1, 4) if n_s1 else float("nan"),
                "green_pct_stage2plus3": round(s23n / n_s23, 4) if n_s23 else float("nan"),
                "n_green": gn,
                "n_others": on,
                "n_startups": gn + on,
            }
        )
    return pd.DataFrame(rows, columns=cols)


# --------------------------------------------------------------------------
# Deal-grain green attribution
# --------------------------------------------------------------------------
def _deals_with_green(firm: pd.DataFrame, deals: pd.DataFrame) -> pd.DataFrame:
    d = deals.copy()
    d["company_id"] = d["company_id"].astype("string")
    green_by = firm.set_index(firm["company_id"].astype("string"))["green"]
    d["green"] = d["company_id"].map(green_by).fillna(0).astype(int)
    return d


# --------------------------------------------------------------------------
# T4.15 deal stage composition (deal grain)
# --------------------------------------------------------------------------
def build_stage_composition(firm: pd.DataFrame, deals: pd.DataFrame) -> pd.DataFrame:
    cols = ["stage_group", "green_pct", "other_pct", "pp_difference",
            "n_green", "n_others", "n_startups"]
    if deals.empty:
        return pd.DataFrame(columns=cols)
    d = _deals_with_green(firm, deals)
    g, o = _split(d)
    n_g, n_o = len(g), len(o)
    rows = []
    for stage in _stage_sort(d["stage_group"].dropna().unique()):
        gn = int((g["stage_group"] == stage).sum())
        on = int((o["stage_group"] == stage).sum())
        gs = gn / n_g if n_g else float("nan")
        os_ = on / n_o if n_o else float("nan")
        rows.append(
            {
                "stage_group": stage,
                "green_pct": round(gs, 4),
                "other_pct": round(os_, 4),
                "pp_difference": _pp(gs, os_),
                "n_green": gn,
                "n_others": on,
                "n_startups": gn + on,
            }
        )
    return pd.DataFrame(rows, columns=cols)


# --------------------------------------------------------------------------
# T4.16 median deal size by stage (deals with recorded size)
# --------------------------------------------------------------------------
def build_deal_size_by_stage(firm: pd.DataFrame, deals: pd.DataFrame) -> pd.DataFrame:
    cols = ["stage_group", "green_median", "other_median", "median_ratio",
            "n_green", "n_others", "n_startups"]
    if deals.empty:
        return pd.DataFrame(columns=cols)
    d = _deals_with_green(firm, deals)
    d["deal_size"] = _num(d["deal_size"])
    d = d[d["deal_size"].notna()]
    rows = []
    for stage in _stage_sort(d["stage_group"].dropna().unique()):
        sub = d[d["stage_group"] == stage]
        g, o = _split(sub)
        g_med, o_med = _median(g["deal_size"]), _median(o["deal_size"])
        rows.append(
            {
                "stage_group": stage,
                "green_median": g_med,
                "other_median": o_med,
                "median_ratio": _ratio(g_med, o_med),
                "n_green": len(g),
                "n_others": len(o),
                "n_startups": len(sub),
            }
        )
    return pd.DataFrame(rows, columns=cols)


# --------------------------------------------------------------------------
# T4.17 financing trajectories (financed subsample, censoring rule R4)
# --------------------------------------------------------------------------
def _traj_row(measure, g_stat, o_stat, eligibility, n_g, n_o) -> dict:
    diff = (round(g_stat - o_stat, 2)
            if pd.notna(g_stat) and pd.notna(o_stat) else float("nan"))
    return {
        "measure": measure,
        "green_stat": g_stat,
        "other_stat": o_stat,
        "difference": diff,
        "eligibility": eligibility,
        "n_green": int(n_g),
        "n_others": int(n_o),
        "n_startups": int(n_g) + int(n_o),
    }


def _progression_flags(deals: pd.DataFrame, from_stages, to_stages) -> pd.DataFrame:
    """Per firm: earliest from-stage date and whether a to-stage deal is later."""
    d = deals[["company_id", "deal_date", "stage_group"]].copy()
    d["deal_date"] = pd.to_datetime(d["deal_date"], errors="coerce")
    frm = (
        d[d["stage_group"].isin(from_stages)]
        .groupby("company_id")["deal_date"].min().reset_index(name="from_date")
    )
    to = d[d["stage_group"].isin(to_stages)][["company_id", "deal_date"]]
    merged = frm.merge(to, on="company_id", how="left")
    merged["is_after"] = merged["deal_date"] > merged["from_date"]
    prog = merged.groupby("company_id").agg(
        from_date=("from_date", "first"),
        progressed=("is_after", "max"),
    ).reset_index()
    prog["progressed"] = prog["progressed"].fillna(False).astype(bool)
    return prog


def build_trajectories(firm: pd.DataFrame, deals: pd.DataFrame) -> pd.DataFrame:
    cols = ["measure", "green_stat", "other_stat", "difference", "eligibility",
            "n_green", "n_others", "n_startups"]
    fin = _financed(firm)
    g, o = _split(fin)
    rows = []

    rows.append(_traj_row(
        "median_n_deals", _median(g["n_deals"]), _median(o["n_deals"]),
        "financed", len(g), len(o),
    ))
    g2 = float((_num(g["n_deals"]) >= 2).mean()) if len(g) else float("nan")
    o2 = float((_num(o["n_deals"]) >= 2).mean()) if len(o) else float("nan")
    rows.append(_traj_row(
        "share_ge_2_rounds", round(g2, 4), round(o2, 4), "financed", len(g), len(o),
    ))

    if not deals.empty:
        cutoff_year = config.SNAPSHOT_YEAR - config.FOLLOWON_MIN_WINDOW_YEARS
        d = _deals_with_green(firm, deals)
        d["deal_date"] = pd.to_datetime(d["deal_date"], errors="coerce")

        # Months between round 1 and round 2, for firms whose first deal is old
        # enough to have permitted a follow-on (rule R4).
        ds = d.sort_values(["company_id", "deal_date"], kind="stable")
        ds["rank"] = ds.groupby("company_id").cumcount()
        first = ds[ds["rank"] == 0][["company_id", "green", "deal_date"]].rename(
            columns={"deal_date": "date1"})
        second = ds[ds["rank"] == 1][["company_id", "deal_date"]].rename(
            columns={"deal_date": "date2"})
        pair = first.merge(second, on="company_id", how="left")
        eligible = pair[pair["date1"].dt.year <= cutoff_year].copy()
        eligible["months_1_2"] = (
            (eligible["date2"] - eligible["date1"]).dt.days / 30.44
        )
        elig_pairs = eligible[eligible["months_1_2"].notna()]
        gp, op = _split(elig_pairs)
        rows.append(_traj_row(
            "median_months_round1_to_2",
            _median(gp["months_1_2"]), _median(op["months_1_2"]),
            f"financed; first deal year <= {cutoff_year} and has a 2nd round",
            len(gp), len(op),
        ))

        # Progression seed -> early VC and early -> later VC (rule R4 on from-date).
        for measure, from_stages, to_stages in (
            ("share_seed_to_early_vc", {"Angel/Seed"}, {"Early-stage VC"}),
            ("share_early_to_later_vc", {"Early-stage VC"}, {"Later-stage VC"}),
        ):
            prog = _progression_flags(d, from_stages, to_stages)
            green_by = firm.set_index(firm["company_id"].astype("string"))["green"]
            prog["company_id"] = prog["company_id"].astype("string")
            prog["green"] = prog["company_id"].map(green_by).fillna(0).astype(int)
            prog = prog[prog["from_date"].dt.year <= cutoff_year]
            gp, op = _split(prog)
            gs = float(gp["progressed"].mean()) if len(gp) else float("nan")
            os_ = float(op["progressed"].mean()) if len(op) else float("nan")
            label = "/".join(sorted(from_stages))
            rows.append(_traj_row(
                measure, round(gs, 4), round(os_, 4),
                f"has a {label} deal with year <= {cutoff_year}",
                len(gp), len(op),
            ))

    return pd.DataFrame(rows, columns=cols)


# --------------------------------------------------------------------------
# F4.4 cumulative share financed by years since founding (full pop, rule R4)
# --------------------------------------------------------------------------
def build_cumulative_financed(firm: pd.DataFrame) -> pd.DataFrame:
    age = _num(firm["age_years"])
    fund_lag = _num(firm.get("first_funding_lag"))
    vc_lag = _num(firm.get("first_vc_lag"))
    green = (firm["green"] == 1)
    rows = []
    for h in config.FINANCED_CURVE_HORIZONS:
        eligible = age >= h
        g_mask = eligible & green
        o_mask = eligible & ~green
        n_g = int(g_mask.sum())
        n_o = int(o_mask.sum())
        rows.append(
            {
                "years_since_founding": h,
                "green_share_financed": (round(int(((fund_lag <= h) & g_mask).sum()) / n_g, 4)
                                         if n_g else float("nan")),
                "other_share_financed": (round(int(((fund_lag <= h) & o_mask).sum()) / n_o, 4)
                                         if n_o else float("nan")),
                "green_share_vc": (round(int(((vc_lag <= h) & g_mask).sum()) / n_g, 4)
                                   if n_g else float("nan")),
                "other_share_vc": (round(int(((vc_lag <= h) & o_mask).sum()) / n_o, 4)
                                   if n_o else float("nan")),
                "n_green": n_g,
                "n_others": n_o,
                "n_startups": n_g + n_o,
            }
        )
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------
# Orchestration
# --------------------------------------------------------------------------
def build_all(firm: pd.DataFrame, deals: pd.DataFrame | None = None) -> Step5Result:
    result = Step5Result()
    deals = deals if deals is not None else pd.DataFrame()

    result.tables["T4_09_funding_access"] = build_funding_access(firm)
    result.tables["T4_09b_funding_access_by_cohort"] = build_funding_access_by_cohort(firm)
    result.tables["T4_10_total_raised_by_cohort"] = build_total_raised_by_cohort(firm)
    result.tables["T4_11_first_financing_size_by_stage"] = build_first_size_by_stage(firm, deals)
    result.tables["T4_12_post_valuation"] = build_post_valuation(firm, deals)
    result.tables["T4_13_time_to_financing"] = build_time_to_financing(firm)
    result.tables["T4_14_first_financing_type"] = build_first_financing_type(firm, deals)
    result.tables["T4_15_stage_composition"] = build_stage_composition(firm, deals)
    result.tables["T4_16_median_deal_size_by_stage"] = build_deal_size_by_stage(firm, deals)
    result.tables["T4_17_financing_trajectories"] = build_trajectories(firm, deals)
    result.tables["F4_04_cumulative_financed"] = build_cumulative_financed(firm)

    result.caption["T4_09_funding_access"] = (
        "Access is the extensive margin on the full 116,005 population (rule N2); "
        "financed comes from the deal record, never from total_raised > 0."
    )
    result.caption["T4_09b_funding_access_by_cohort"] = (
        "Founding-cohort-adjusted access (rules N2, N4): green-vs-other reach of any "
        "financing, any VC, any grant and any accelerator within each cohort, so a "
        "2016-2018 firm's longer fundraising window is not compared with a 2025 one's. "
        "Shares use each cohort group's own denominator (green_n_cohort / "
        "other_n_cohort); low_n_flag marks cohorts with fewer than 30 green firms."
    )
    result.caption["T4_10_total_raised_by_cohort"] = (
        "Amounts on the financed subsample only (rule N1), within founding cohort "
        "(rule N4): a 2017 firm has had far longer to raise than a 2025 one."
    )
    result.caption["T4_15_stage_composition"] = (
        "Deal grain: n_green / n_others / n_startups count deals, not firms."
    )
    result.caption["F4_04_cumulative_financed"] = (
        "Censored per rule R4: at each horizon only firms old enough to have a full "
        "window are counted (n_startups), so young firms are not read as failures."
    )
    return result


def write_outputs(result: Step5Result, output_dir: Path | None = None) -> Path:
    out = Path(output_dir or config.OUTPUT_DIR)
    out.mkdir(parents=True, exist_ok=True)
    for name, df in result.tables.items():
        path = out / f"{name}.csv"
        df.to_csv(path, index=False)
        print(f"[step5] wrote {path}  ({len(df)} rows)")
    if result.caption:
        cap = pd.DataFrame(
            [{"output": k, "caption": v} for k, v in result.caption.items()]
        )
        cap.to_csv(out / "captions_step5.csv", index=False)
        print(f"[step5] wrote {out / 'captions_step5.csv'}")
    return out


def acceptance_report(firm: pd.DataFrame, result: Step5Result) -> list[str]:
    lines: list[str] = []

    fin = _financed(firm)
    g_fin, o_fin = _split(fin)
    lines.append(
        f"financed subsample: {len(fin)} (green={len(g_fin)}, other={len(o_fin)}) "
        f"(expected {config.FINANCED_TOTAL})"
    )
    if len(fin) != config.FINANCED_TOTAL:
        lines.append("  WARN: financed count differs from the expected 47,714")

    t49 = result.tables["T4_09_funding_access"].set_index("financing_type")
    if "any_financing" in t49.index:
        g_all, _ = _split(firm)
        share_fin_green = float((g_all["financed"] == 1).mean()) if len(g_all) else float("nan")
        lines.append(
            f"T4.9 any_financing green_pct={t49.loc['any_financing', 'green_pct']} "
            f"(Step 3 share_financed green={round(share_fin_green, 4)})"
        )

    t49b = result.tables.get("T4_09b_funding_access_by_cohort")
    if t49b is not None and not t49b.empty and "any_financing" in t49.index:
        fin_rows = t49b[t49b["financing_type"] == "any_financing"]
        by_cohort_n = int(fin_rows["n_startups"].sum())
        overall_n = int(t49.loc["any_financing", "n_startups"])
        lines.append(f"T4.9b any_financing cohort n sum={by_cohort_n} "
                     f"(T4.9 any_financing n={overall_n})")
        if by_cohort_n != overall_n:
            lines.append("  WARN: T4.9b cohort split does not reconcile with T4.9")

    t10 = result.tables["T4_10_total_raised_by_cohort"]
    tr = t10[t10["amount_field"] == "total_raised"]
    tr_n = int(tr["n_startups"].sum())
    tr_expected = _n_nonnull(fin["total_raised"])
    lines.append(f"T4.10 total_raised cohort n sum={tr_n} "
                 f"(financed with total_raised={tr_expected})")
    if tr_n != tr_expected:
        lines.append("  WARN: T4.10 cohort n does not reconcile with financed total_raised")

    n_deals_with_size = int(_num(fin["n_deals_with_size"]).sum())
    n_deals_total = int(_num(fin["n_deals"]).sum())
    lines.append(f"T4.10 size context: n_deals_with_size/n_deals = "
                 f"{n_deals_with_size}/{n_deals_total}")

    t15 = result.tables["T4_15_stage_composition"]
    lines.append(f"T4.15 total deals={int(t15['n_startups'].sum())}")

    t16 = result.tables["T4_16_median_deal_size_by_stage"]
    has_grant = "Grant" in set(t16["stage_group"]) if not t16.empty else False
    lines.append(f"T4.16 Grant row present: {has_grant}")
    if not t16.empty and has_grant:
        grant = t16[t16["stage_group"] == "Grant"].iloc[0]
        lines.append(f"  Grant median: green={grant['green_median']} "
                     f"other={grant['other_median']} ratio={grant['median_ratio']}")

    t13 = result.tables["T4_13_time_to_financing"]
    for measure in ("first_funding_lag", "first_vc_lag"):
        row = t13[(t13["measure"] == measure) & (t13["cohort"] == "all")]
        if not row.empty:
            r = row.iloc[0]
            lines.append(f"T4.13 {measure} (all): green_median={r['green_median']} "
                         f"other_median={r['other_median']} diff={r['difference']}")

    return lines
