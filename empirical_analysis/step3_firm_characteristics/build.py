"""Step 3 build logic: the firm-characteristic tables.

Everything is descriptive: split the firm table into green vs other European
start-ups and summarise. Medians are primary; a mean appears only beside the median
for age (rule N6). Every statistic carries its own n. Percentages within a group use
that group's denominator; cross-group rows say which denominator they use.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from empirical_analysis.chapter4.sample_register import build_sample_register

from . import config
from .sources import log


@dataclass
class Step3Result:
    tables: dict[str, pd.DataFrame] = field(default_factory=dict)
    caption: dict[str, str] = field(default_factory=dict)


# --------------------------------------------------------------------------
# Small statistics helpers
# --------------------------------------------------------------------------
def _num(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def _present(series: pd.Series) -> pd.Series:
    """True where a value is present (non-null, non-blank for strings)."""
    s = series
    if s.dtype == object or str(s.dtype) == "string":
        stripped = s.astype("string").str.strip()
        return (stripped.notna() & (stripped != "")).fillna(False).astype(bool)
    return s.notna()


def _median(series: pd.Series) -> tuple[float, int]:
    s = _num(series)
    n = int(s.notna().sum())
    return (round(float(s.median()), 2) if n else float("nan"), n)


def _quantile(series: pd.Series, q: float) -> tuple[float, int]:
    s = _num(series)
    n = int(s.notna().sum())
    return (round(float(s.quantile(q)), 2) if n else float("nan"), n)


def _mean(series: pd.Series) -> tuple[float, int]:
    s = _num(series)
    n = int(s.notna().sum())
    return (round(float(s.mean()), 2) if n else float("nan"), n)


def _split(firm: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    green = firm[firm["green"] == 1]
    other = firm[firm["green"] != 1]
    return green, other


def _row(characteristic, green_stat, green_n, other_stat, other_n, difference):
    return {
        "characteristic": characteristic,
        "green_stat": green_stat,
        "green_n": green_n,
        "other_stat": other_stat,
        "other_n": other_n,
        "difference": difference,
    }


def _pp(green_share: float, other_share: float) -> float:
    """Percentage-point difference between two shares (each in 0..1)."""
    if pd.isna(green_share) or pd.isna(other_share):
        return float("nan")
    return round((green_share - other_share) * 100, 1)


# --------------------------------------------------------------------------
# T4.1 master descriptive table
# --------------------------------------------------------------------------
def build_master_descriptive(firm: pd.DataFrame) -> pd.DataFrame:
    g, o = _split(firm)
    rows: list[dict] = []

    rows.append(_row("n_firms", len(g), len(g), len(o), len(o),
                     round(len(g) / len(firm), 4) if len(firm) else float("nan")))

    gm, gn = _median(g["year_founded"]); om, on = _median(o["year_founded"])
    rows.append(_row("median_year_founded", gm, gn, om, on, round(gm - om, 2)))

    gm, gn = _median(g["age_years"]); om, on = _median(o["age_years"])
    rows.append(_row("median_age", gm, gn, om, on, round(gm - om, 2)))
    if config.SHOW_MEAN_FOR_AGE:
        gm, gn = _mean(g["age_years"]); om, on = _mean(o["age_years"])
        rows.append(_row("mean_age", gm, gn, om, on, round(gm - om, 2)))
    gq, gn = _quantile(g["age_years"], 0.25); oq, on = _quantile(o["age_years"], 0.25)
    rows.append(_row("age_q25", gq, gn, oq, on, round(gq - oq, 2)))
    gq, gn = _quantile(g["age_years"], 0.75); oq, on = _quantile(o["age_years"], 0.75)
    rows.append(_row("age_q75", gq, gn, oq, on, round(gq - oq, 2)))

    # Cohort shares (denominator = group size; cohort is always present).
    for label in config.COHORT_ORDER:
        g_hit = (g["cohort"] == label); o_hit = (o["cohort"] == label)
        gs = float(g_hit.mean()) if len(g) else float("nan")
        os_ = float(o_hit.mean()) if len(o) else float("nan")
        rows.append(_row(f"share_cohort_{label}", round(gs, 4), int(g_hit.sum()),
                         round(os_, 4), int(o_hit.sum()), _pp(gs, os_)))

    gm, gn = _median(g["employees"]); om, on = _median(o["employees"])
    rows.append(_row("median_employees", gm, gn, om, on, round(gm - om, 2)))
    gq, gn = _quantile(g["employees"], 0.25); oq, on = _quantile(o["employees"], 0.25)
    rows.append(_row("employees_q25", gq, gn, oq, on, round(gq - oq, 2)))
    gq, gn = _quantile(g["employees"], 0.75); oq, on = _quantile(o["employees"], 0.75)
    rows.append(_row("employees_q75", gq, gn, oq, on, round(gq - oq, 2)))

    # Employee-band shares (denominator = firms with a known band).
    g_band_known = _present(g["employee_band"]); o_band_known = _present(o["employee_band"])
    g_bden = int(g_band_known.sum()); o_bden = int(o_band_known.sum())
    for label in config.EMPLOYEE_BAND_ORDER:
        g_hit = (g["employee_band"] == label); o_hit = (o["employee_band"] == label)
        gs = (int(g_hit.sum()) / g_bden) if g_bden else float("nan")
        os_ = (int(o_hit.sum()) / o_bden) if o_bden else float("nan")
        rows.append(_row(f"share_emp_{label}", round(gs, 4), int(g_hit.sum()),
                         round(os_, 4), int(o_hit.sum()), _pp(gs, os_)))

    # Top-N primary sectors overall (denominator = group size).
    top_sectors = (
        firm["primary_sector"].astype("string").str.strip()
        .replace("", pd.NA).dropna().value_counts().head(config.TOP_N_SECTORS).index.tolist()
    )
    for sector in top_sectors:
        g_hit = (g["primary_sector"] == sector); o_hit = (o["primary_sector"] == sector)
        gs = float(g_hit.mean()) if len(g) else float("nan")
        os_ = float(o_hit.mean()) if len(o) else float("nan")
        rows.append(_row(f"share_sector_{sector}", round(gs, 4), int(g_hit.sum()),
                         round(os_, 4), int(o_hit.sum()), _pp(gs, os_)))

    # Financing status (access, full population).
    gs = float((g["financed"] == 1).mean()) if len(g) else float("nan")
    os_ = float((o["financed"] == 1).mean()) if len(o) else float("nan")
    rows.append(_row("share_financed", round(gs, 4), int((g["financed"] == 1).sum()),
                     round(os_, 4), int((o["financed"] == 1).sum()), _pp(gs, os_)))
    rows.append(_row("share_not_financed", round(1 - gs, 4), int((g["financed"] != 1).sum()),
                     round(1 - os_, 4), int((o["financed"] != 1).sum()), _pp(1 - gs, 1 - os_)))

    return pd.DataFrame(rows)


# --------------------------------------------------------------------------
# F4.1 green share by founding cohort
# --------------------------------------------------------------------------
def build_green_share_by_cohort(firm: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for label in config.COHORT_ORDER:
        sub = firm[firm["cohort"] == label]
        n_all = len(sub)
        n_green = int((sub["green"] == 1).sum())
        rows.append(
            {
                "cohort": label,
                "n_green": n_green,
                "n_all": n_all,
                "green_share": round(n_green / n_all, 4) if n_all else float("nan"),
                "overall_benchmark": config.GREEN_BENCHMARK,
            }
        )
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------
# T4.2 business status distribution
# --------------------------------------------------------------------------
def _status_distribution(g: pd.DataFrame, o: pd.DataFrame) -> pd.DataFrame:
    """Raw status shares, green vs other. No grouping (decision D2)."""
    g_known = g[_present(g["business_status"])]
    o_known = o[_present(o["business_status"])]
    g_counts = g_known["business_status"].astype("string").str.strip().value_counts()
    o_counts = o_known["business_status"].astype("string").str.strip().value_counts()
    statuses = sorted(set(g_counts.index) | set(o_counts.index))
    g_den = int(len(g_known)); o_den = int(len(o_known))
    rows = []
    for status in statuses:
        gn = int(g_counts.get(status, 0)); on = int(o_counts.get(status, 0))
        gs = gn / g_den if g_den else float("nan")
        os_ = on / o_den if o_den else float("nan")
        rows.append(
            {
                "business_status": status,
                "green_n": gn, "green_pct": round(gs, 4),
                "other_n": on, "other_pct": round(os_, 4),
                "pp_difference": _pp(gs, os_),
            }
        )
    out = pd.DataFrame(rows)
    if not out.empty:
        out = out.sort_values("green_n", ascending=False).reset_index(drop=True)
    return out


def build_business_status(firm: pd.DataFrame) -> pd.DataFrame:
    g, o = _split(firm)
    return _status_distribution(g, o)


def build_business_status_by_cohort(firm: pd.DataFrame) -> pd.DataFrame:
    frames = []
    for label in config.COHORT_ORDER:
        sub = firm[firm["cohort"] == label]
        g, o = _split(sub)
        part = _status_distribution(g, o)
        if not part.empty:
            part.insert(0, "cohort", label)
            frames.append(part)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


# --------------------------------------------------------------------------
# T4.3 industry composition (from the long relational table)
# --------------------------------------------------------------------------
def _industry_composition(
    industries: pd.DataFrame, green_by_company: pd.Series, level_col: str, label: str
) -> pd.DataFrame:
    cols = [
        label, "green_n", "green_pct_of_green", "other_n", "other_pct_of_other",
        "lq", "n_firms_tagged",
    ]
    if industries.empty or level_col not in industries.columns:
        return pd.DataFrame(columns=cols)

    tag = industries[["company_id", level_col]].copy()
    tag["company_id"] = tag["company_id"].astype("string")
    tag[level_col] = tag[level_col].astype("string").str.strip()
    tag = tag[(tag[level_col].notna()) & (tag[level_col] != "")]
    # One firm counts once per distinct tag value.
    tag = tag.drop_duplicates(subset=["company_id", level_col])
    tag["green"] = tag["company_id"].map(green_by_company).fillna(0).astype(int)

    green_firms_tagged = tag.loc[tag["green"] == 1, "company_id"].nunique()
    other_firms_tagged = tag.loc[tag["green"] != 1, "company_id"].nunique()
    all_tagged = green_firms_tagged + other_firms_tagged
    overall_green_share = green_firms_tagged / all_tagged if all_tagged else float("nan")

    grp = tag.groupby(level_col)["green"]
    rows = []
    for value, series in grp:
        gn = int((series == 1).sum()); on = int((series != 1).sum())
        sector_total = gn + on
        sector_green_share = gn / sector_total if sector_total else float("nan")
        lq = (
            round(sector_green_share / overall_green_share, 3)
            if overall_green_share and not pd.isna(overall_green_share) and overall_green_share > 0
            else float("nan")
        )
        rows.append(
            {
                label: value,
                "green_n": gn,
                "green_pct_of_green": round(gn / green_firms_tagged, 4) if green_firms_tagged else float("nan"),
                "other_n": on,
                "other_pct_of_other": round(on / other_firms_tagged, 4) if other_firms_tagged else float("nan"),
                "lq": lq,
                "n_firms_tagged": sector_total,
            }
        )
    out = pd.DataFrame(rows, columns=cols)
    if not out.empty:
        out = out.sort_values("green_n", ascending=False).reset_index(drop=True)
    return out


def build_industry_tables(
    firm: pd.DataFrame, industries: pd.DataFrame
) -> dict[str, pd.DataFrame]:
    green_by_company = firm.set_index(firm["company_id"].astype("string"))["green"]
    return {
        "T4_03_industry_composition": _industry_composition(
            industries, green_by_company, "industry_sector", "industry_sector"),
        "T4_03_industry_group": _industry_composition(
            industries, green_by_company, "industry_group", "industry_group"),
        "T4_03_industry_code": _industry_composition(
            industries, green_by_company, "industry_code", "industry_code"),
    }


# --------------------------------------------------------------------------
# T4.4 green subsegment decomposition (verticals, green firms only)
# --------------------------------------------------------------------------
def build_green_subsegments(firm: pd.DataFrame, verticals: pd.DataFrame) -> pd.DataFrame:
    cols = ["vertical", "n_firms", "pct_of_green", "median_age",
            "median_total_raised", "n_with_funding"]
    if verticals.empty or "vertical" not in verticals.columns:
        return pd.DataFrame(columns=cols)

    green_ids = set(firm.loc[firm["green"] == 1, "company_id"].astype("string"))
    n_green = len(green_ids)

    v = verticals[["company_id", "vertical"]].copy()
    v["company_id"] = v["company_id"].astype("string")
    v["vertical"] = v["vertical"].astype("string").str.strip()
    v = v[(v["vertical"].notna()) & (v["vertical"] != "")]
    v = v[v["company_id"].isin(green_ids)].drop_duplicates(subset=["company_id", "vertical"])

    attrs = firm[["company_id", "age_years", "total_raised", "financed"]].copy()
    attrs["company_id"] = attrs["company_id"].astype("string")
    v = v.merge(attrs, on="company_id", how="left")

    rows = []
    for vertical, sub in v.groupby("vertical"):
        n_firms = sub["company_id"].nunique()
        med_age, _ = _median(sub["age_years"])
        med_raised, _ = _median(sub["total_raised"])
        rows.append(
            {
                "vertical": vertical,
                "n_firms": n_firms,
                "pct_of_green": round(n_firms / n_green, 4) if n_green else float("nan"),
                "median_age": med_age,
                "median_total_raised": med_raised,
                "n_with_funding": int((sub["financed"] == 1).sum()),
            }
        )
    out = pd.DataFrame(rows, columns=cols)
    if not out.empty:
        out = out.sort_values("n_firms", ascending=False).reset_index(drop=True)
    return out


# --------------------------------------------------------------------------
# T4.5 employment by cohort
# --------------------------------------------------------------------------
def build_employment_by_cohort(firm: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for label in config.COHORT_ORDER:
        sub = firm[firm["cohort"] == label]
        g, o = _split(sub)
        row = {"cohort": label}
        for prefix, part in (("green", g), ("other", o)):
            med, n = _median(part["employees"])
            q25, _ = _quantile(part["employees"], 0.25)
            q75, _ = _quantile(part["employees"], 0.75)
            row[f"{prefix}_median_employees"] = med
            row[f"{prefix}_q25"] = q25
            row[f"{prefix}_q75"] = q75
            row[f"{prefix}_n"] = n
            band_known = int(_present(part["employee_band"]).sum())
            for band in config.EMPLOYEE_BAND_ORDER:
                hit = int((part["employee_band"] == band).sum())
                key = f"{prefix}_share_{band}"
                row[key] = round(hit / band_known, 4) if band_known else float("nan")
        rows.append(row)
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------
# Orchestration
# --------------------------------------------------------------------------
def build_all(
    firm: pd.DataFrame,
    industries: pd.DataFrame,
    verticals: pd.DataFrame,
    deals: pd.DataFrame | None = None,
) -> Step3Result:
    result = Step3Result()
    result.tables["T4_00_sample_register"] = build_sample_register(
        firm, industries=industries, verticals=verticals, deals=deals,
    )
    result.tables["T4_01_master_descriptive"] = build_master_descriptive(firm)
    result.tables["F4_01_green_share_by_cohort"] = build_green_share_by_cohort(firm)
    result.tables["T4_02_business_status"] = build_business_status(firm)
    result.tables["T4_02_business_status_by_cohort"] = build_business_status_by_cohort(firm)
    result.tables.update(build_industry_tables(firm, industries))
    result.tables["T4_04_green_subsegments"] = build_green_subsegments(firm, verticals)
    result.tables["T4_05_employment_by_cohort"] = build_employment_by_cohort(firm)

    result.caption["F4_01_green_share_by_cohort"] = (
        "Cohort composition, not a time trend: a 2026 snapshot of currently eligible "
        "firms is not a historically reconstructed annual population."
    )
    result.caption["T4_03_industry_composition"] = (
        "Percentages can sum above 100% because firms carry multiple industry tags."
    )
    return result


def write_outputs(result: Step3Result, output_dir: Path | None = None) -> Path:
    out = Path(output_dir or config.OUTPUT_DIR)
    out.mkdir(parents=True, exist_ok=True)
    for name, df in result.tables.items():
        path = out / f"{name}.csv"
        df.to_csv(path, index=False)
        print(f"[step3] wrote {path}  ({len(df)} rows)")
    if result.caption:
        cap = pd.DataFrame(
            [{"output": k, "caption": v} for k, v in result.caption.items()]
        )
        cap.to_csv(out / "captions.csv", index=False)
        print(f"[step3] wrote {out / 'captions.csv'}")
    return out


def acceptance_report(result: Step3Result) -> list[str]:
    lines: list[str] = []
    reg = result.tables.get("T4_00_sample_register")
    if reg is not None and not reg.empty:
        master = reg[reg["section"] == "master"].set_index("statistic")
        if "full_population" in master.index:
            fp = master.loc["full_population"]
            lines.append(
                f"T4.00 sample register: {len(reg)} rows; full={int(fp['n_total'])} "
                f"green={int(fp['n_green'])} financed="
                f"{int(master.loc['financed_subsample', 'n_total'])}"
            )
    t41 = result.tables["T4_01_master_descriptive"].set_index("characteristic")
    if "n_firms" in t41.index:
        gn = int(t41.loc["n_firms", "green_n"]); on = int(t41.loc["n_firms", "other_n"])
        lines.append(f"T4.1 n_firms: green={gn} other={on} total={gn + on} "
                     f"(expected green={config.GREEN_TOTAL}, total={config.POP_TOTAL})")
        if gn != config.GREEN_TOTAL or gn + on != config.POP_TOTAL:
            lines.append("  WARN: firm counts differ from the expected population")

    f41 = result.tables["F4_01_green_share_by_cohort"]
    green_sum = int(f41["n_green"].sum()); all_sum = int(f41["n_all"].sum())
    lines.append(f"F4.1 cohorts: {len(f41)} rows, green across cohorts={green_sum}, "
                 f"all={all_sum}")
    if green_sum != config.GREEN_TOTAL:
        lines.append(f"  WARN: cohort green sum {green_sum} != {config.GREEN_TOTAL}")
    if all_sum != config.POP_TOTAL:
        lines.append(f"  WARN: cohort all sum {all_sum} != {config.POP_TOTAL}")
    bench = f41["overall_benchmark"].unique().tolist()
    if bench != [config.GREEN_BENCHMARK]:
        lines.append(f"  WARN: F4.1 benchmark {bench} != {config.GREEN_BENCHMARK}")

    ind = result.tables["T4_03_industry_composition"]
    if not ind.empty:
        pct_sum = round(float(ind["green_pct_of_green"].sum()) * 100, 1)
        lines.append(f"T4.3 green tag-share sum: {pct_sum}% (>100% expected; firms hold "
                     "multiple tags)")

    sub = result.tables["T4_04_green_subsegments"]
    lines.append(f"T4.4 green subsegments: {len(sub)} verticals")

    return lines
