"""Step 4 build logic: the geography tables.

Everything is descriptive. Group by country and city, count green vs all, and derive
specialisation (the location quotient) against the fixed EU-wide reference. Country
and EU denominators use the full 116,005 population (rule N9); the location-quotient
reference is fixed at the EU level so excluding sub-500 countries does not move the
LQ of the countries that remain. Every reported row carries its own firm count.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from . import config
from .sources import log


@dataclass
class Step4Result:
    tables: dict[str, pd.DataFrame] = field(default_factory=dict)
    caption: dict[str, str] = field(default_factory=dict)
    diagnostics: dict[str, float] = field(default_factory=dict)


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------
def _clean_str(series: pd.Series) -> pd.Series:
    """Trimmed string column; blanks become NA."""
    s = series.astype("string").str.strip()
    return s.mask(s == "")


def _city_key(name: str) -> str:
    """Accent- and case-insensitive key so 'Zurich' and 'Zürich' collapse to one."""
    decomposed = unicodedata.normalize("NFKD", name)
    stripped = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return " ".join(stripped.casefold().split())


def _canonical_city(city: pd.Series) -> pd.Series:
    """Map accent/case variants of a city name to a single canonical spelling.

    PitchBook stores the same city under several spellings (Zurich / Zürich,
    Asnieres-sur-Seine / Asnières-sur-Seine). Grouping on the raw string splits one
    city across rows. We fold each name to an accent-insensitive, case-insensitive
    key and relabel every variant with the most frequent original spelling for that
    key (ties broken alphabetically for determinism).
    """
    present = city.dropna()
    if present.empty:
        return city
    df = pd.DataFrame({"orig": present})
    df["key"] = df["orig"].map(_city_key)
    counts = (
        df.groupby(["key", "orig"]).size().reset_index(name="c")
        .sort_values(["key", "c", "orig"], ascending=[True, False, True])
    )
    canon = counts.drop_duplicates("key").set_index("key")["orig"]
    keys = city.map(lambda x: _city_key(x) if isinstance(x, str) else pd.NA)
    return keys.map(canon).astype("string")


def _eu_green_intensity(firm: pd.DataFrame) -> float:
    """Fixed EU-wide reference for the location quotient (rule N9)."""
    n_all = len(firm)
    n_green = int((firm["green"] == 1).sum())
    return n_green / n_all if n_all else float("nan")


def _is_stage(firm: pd.DataFrame, label: str) -> pd.Series:
    if "green_signal_group" not in firm.columns:
        return pd.Series(False, index=firm.index)
    return (firm["green"] == 1) & (firm["green_signal_group"] == label)


# --------------------------------------------------------------------------
# T4.6 country distribution and specialisation
# --------------------------------------------------------------------------
def build_country_specialisation(
    firm: pd.DataFrame, min_country_n: int | None = None
) -> pd.DataFrame:
    min_n = config.MIN_COUNTRY_N if min_country_n is None else min_country_n

    country = _clean_str(firm["hq_country"])
    green = (firm["green"] == 1)
    n_green_total = int(green.sum())

    # Fixed EU-wide references (rule N9): full population and full green ledger.
    eu_ref = _eu_green_intensity(firm)
    stage1 = _is_stage(firm, config.STAGE1_LABEL)
    stage23 = _is_stage(firm, config.STAGE23_LABEL)
    eu_ref_s1 = int(stage1.sum()) / len(firm) if len(firm) else float("nan")
    eu_ref_s23 = int(stage23.sum()) / len(firm) if len(firm) else float("nan")

    work = pd.DataFrame(
        {
            "country": country,
            "green": green.astype(int),
            "stage1": stage1.astype(int),
            "stage23": stage23.astype(int),
        }
    ).dropna(subset=["country"])

    grp = work.groupby("country")
    agg = grp.agg(
        n_green=("green", "sum"),
        n_startups=("green", "size"),
        green_stage1_n=("stage1", "sum"),
        green_stage23_n=("stage23", "sum"),
    ).reset_index()

    agg = agg[agg["n_startups"] >= min_n].copy()
    agg["n_others"] = agg["n_startups"] - agg["n_green"]

    agg["share_of_european_green"] = (
        agg["n_green"] / n_green_total if n_green_total else float("nan")
    ).round(4)
    agg["green_intensity"] = (agg["n_green"] / agg["n_startups"]).round(4)
    agg["lq"] = (agg["green_intensity"] / eu_ref).round(3) if eu_ref else float("nan")
    agg["lq_stage1"] = (
        (agg["green_stage1_n"] / agg["n_startups"]) / eu_ref_s1
    ).round(3) if eu_ref_s1 else float("nan")
    agg["lq_stage2plus3"] = (
        (agg["green_stage23_n"] / agg["n_startups"]) / eu_ref_s23
    ).round(3) if eu_ref_s23 else float("nan")
    agg["low_n_flag"] = (agg["n_green"] < config.LOW_N_FLAG).astype(int)

    cols = [
        "country", "share_of_european_green", "green_intensity", "lq",
        "lq_stage1", "lq_stage2plus3", "low_n_flag",
        "n_green", "n_others", "n_startups",
    ]
    out = agg[cols].sort_values("n_green", ascending=False).reset_index(drop=True)
    log(f"[step4] T4.6: {len(out)} countries with n>={min_n}")
    return out


# --------------------------------------------------------------------------
# T4.7 per-capita cross-check
# --------------------------------------------------------------------------
def build_per_capita(
    t46: pd.DataFrame, population: pd.DataFrame
) -> pd.DataFrame:
    cols = [
        "country", "population_m", "startups_per_million", "green_per_million",
        "green_intensity", "lq", "n_green", "n_others", "n_startups",
    ]
    if t46.empty:
        return pd.DataFrame(columns=cols)

    out = t46[
        ["country", "n_startups", "n_green", "n_others", "green_intensity", "lq"]
    ].copy()
    out["iso2"] = out["country"].map(config.COUNTRY_TO_ISO2)

    if population is not None and not population.empty:
        pop = population[["iso2", "population"]].copy()
        pop["iso2"] = pop["iso2"].astype("string")
        out["iso2"] = out["iso2"].astype("string")
        out = out.merge(pop, on="iso2", how="left")
    else:
        out["population"] = pd.NA

    out["population_m"] = (out["population"] / 1_000_000).round(3)
    out["startups_per_million"] = (out["n_startups"] / out["population_m"]).round(1)
    out["green_per_million"] = (out["n_green"] / out["population_m"]).round(2)

    out = out[cols].sort_values("n_startups", ascending=False).reset_index(drop=True)
    matched = int(out["population_m"].notna().sum())
    log(f"[step4] T4.7: {matched}/{len(out)} countries matched to World Bank")
    return out


def spearman_per_capita(t47: pd.DataFrame) -> tuple[float, int]:
    """Spearman correlation between startups_per_million and green_intensity."""
    sub = t47.dropna(subset=["startups_per_million", "green_intensity"])
    n = len(sub)
    if n < 3:
        return (float("nan"), n)
    rho = sub["startups_per_million"].corr(
        sub["green_intensity"], method="spearman"
    )
    return (round(float(rho), 3), n)


# --------------------------------------------------------------------------
# T4.8 geographic concentration
# --------------------------------------------------------------------------
def _shares(counts: pd.Series) -> pd.Series:
    total = counts.sum()
    return counts / total if total else counts * float("nan")


def _top_k_share(counts: pd.Series, k: int) -> float:
    shares = _shares(counts.sort_values(ascending=False))
    return round(float(shares.head(k).sum()), 4) if len(shares) else float("nan")


def _hhi(counts: pd.Series) -> float:
    shares = _shares(counts)
    return round(float((shares ** 2).sum()), 4) if len(shares) else float("nan")


def build_concentration(firm: pd.DataFrame) -> pd.DataFrame:
    country = _clean_str(firm["hq_country"])
    city = _canonical_city(_clean_str(firm["hq_city"]))
    green = (firm["green"] == 1)

    g_country = country[green].value_counts()
    o_country = country[~green].value_counts()
    g_city = city[green].value_counts()
    o_city = city[~green].value_counts()

    rows = []

    def _row(measure: str, g_val: float, o_val: float) -> dict:
        diff = (round(g_val - o_val, 4)
                if pd.notna(g_val) and pd.notna(o_val) else float("nan"))
        return {"measure": measure, "green": g_val, "other": o_val, "difference": diff}

    for k in config.TOP_COUNTRY_K:
        rows.append(_row(f"top{k}_country_share",
                         _top_k_share(g_country, k), _top_k_share(o_country, k)))
    rows.append(_row(f"top{config.TOP_CITY_K}_city_share",
                     _top_k_share(g_city, config.TOP_CITY_K),
                     _top_k_share(o_city, config.TOP_CITY_K)))
    rows.append(_row("hhi_country", _hhi(g_country), _hhi(o_country)))

    return pd.DataFrame(rows)


# --------------------------------------------------------------------------
# AP2 city-level ranking
# --------------------------------------------------------------------------
def build_city_ranking(
    firm: pd.DataFrame, min_city_n: int | None = None
) -> pd.DataFrame:
    min_n = config.MIN_CITY_N if min_city_n is None else min_city_n

    city = _canonical_city(_clean_str(firm["hq_city"]))
    country = _clean_str(firm["hq_country"])
    green = (firm["green"] == 1)
    n_green_total = int(green.sum())

    work = pd.DataFrame(
        {"city": city, "country": country, "green": green.astype(int)}
    ).dropna(subset=["city"])

    grp = work.groupby("city")
    agg = grp.agg(
        n_green=("green", "sum"),
        n_startups=("green", "size"),
    ).reset_index()

    # Modal country per city (a city name can appear under more than one country).
    modal = (
        work.dropna(subset=["country"])
        .groupby(["city", "country"]).size().reset_index(name="c")
        .sort_values(["city", "c"], ascending=[True, False])
        .drop_duplicates("city")[["city", "country"]]
    )
    agg = agg.merge(modal, on="city", how="left")

    agg = agg[agg["n_startups"] >= min_n].copy()
    agg["n_others"] = agg["n_startups"] - agg["n_green"]
    agg["share_of_european_green"] = (
        agg["n_green"] / n_green_total if n_green_total else float("nan")
    ).round(4)
    agg["green_intensity"] = (agg["n_green"] / agg["n_startups"]).round(4)
    agg["low_n_flag"] = (agg["n_green"] < config.LOW_N_FLAG).astype(int)

    cols = [
        "city", "country", "share_of_european_green", "green_intensity",
        "low_n_flag", "n_green", "n_others", "n_startups",
    ]
    out = agg[cols].sort_values("n_green", ascending=False).reset_index(drop=True)
    log(f"[step4] AP2: {len(out)} cities with n>={min_n}")
    return out


# --------------------------------------------------------------------------
# Figure data
# --------------------------------------------------------------------------
def build_green_count_figure(t46: pd.DataFrame) -> pd.DataFrame:
    """F4.2: absolute green count by country, ranked as T4.6."""
    return t46[["country", "n_green", "n_others", "n_startups"]].copy()


def build_lq_figure(t46: pd.DataFrame) -> pd.DataFrame:
    """F4.3: location quotient by country, ranked by lq descending."""
    out = t46[["country", "lq", "n_green", "n_others", "n_startups"]].copy()
    out["reference"] = 1.0
    out = out[["country", "lq", "reference", "n_green", "n_others", "n_startups"]]
    return out.sort_values("lq", ascending=False).reset_index(drop=True)


# --------------------------------------------------------------------------
# Orchestration
# --------------------------------------------------------------------------
def build_all(
    firm: pd.DataFrame,
    population: pd.DataFrame | None = None,
    min_country_n: int | None = None,
    min_city_n: int | None = None,
) -> Step4Result:
    result = Step4Result()
    population = population if population is not None else pd.DataFrame()

    t46 = build_country_specialisation(firm, min_country_n=min_country_n)
    t47 = build_per_capita(t46, population)
    result.tables["T4_06_country_specialisation"] = t46
    result.tables["T4_07_per_capita_crosscheck"] = t47
    result.tables["T4_08_concentration"] = build_concentration(firm)
    result.tables["AP2_city_ranking"] = build_city_ranking(firm, min_city_n=min_city_n)
    result.tables["F4_02_green_count_by_country"] = build_green_count_figure(t46)
    result.tables["F4_03_lq_by_country"] = build_lq_figure(t46)

    rho, n_rho = spearman_per_capita(t47)
    result.diagnostics["spearman_per_capita"] = rho
    result.diagnostics["spearman_n"] = n_rho

    result.caption["T4_06_country_specialisation"] = (
        "Location quotient uses the fixed EU-wide reference "
        f"(green/population = {config.EU_GREEN_INTENSITY}); lq>1 means the country is "
        "more green-specialised than Europe overall. Every country with at least one "
        "start-up is reported (no country floor); rows with fewer than "
        f"{config.LOW_N_FLAG} green firms carry low_n_flag=1 and are read as "
        "indicative. The EU reference is fixed at the full population (rule N9), so "
        "the LQ of any country is unaffected by which others are shown."
    )
    result.caption["T4_07_per_capita_crosscheck"] = (
        "Per-capita cross-check against World Bank total population (SP.POP.TOTL), a "
        "single latest vintage covering all 46 countries from one source and one "
        "reference year. PitchBook coverage varies by country, so read a low intensity "
        "against start-ups per capita before calling it low green specialisation."
    )
    result.caption["T4_08_concentration"] = (
        "Shares use each group's own total as the denominator, so green and other "
        "concentration are directly comparable."
    )
    result.caption["AP2_city_ranking"] = (
        "City names are folded across accent and case variants (Zürich = Zurich) and "
        "shown under their most frequent spelling, so one city is not split across "
        "rows. Cities keep the MIN_CITY_N floor; the modal country is reported when a "
        "city name occurs in more than one country."
    )
    return result


def write_outputs(result: Step4Result, output_dir: Path | None = None) -> Path:
    out = Path(output_dir or config.OUTPUT_DIR)
    out.mkdir(parents=True, exist_ok=True)
    for name, df in result.tables.items():
        path = out / f"{name}.csv"
        df.to_csv(path, index=False)
        print(f"[step4] wrote {path}  ({len(df)} rows)")
    if result.caption:
        cap = pd.DataFrame(
            [{"output": k, "caption": v} for k, v in result.caption.items()]
        )
        cap.to_csv(out / "captions_step4.csv", index=False)
        print(f"[step4] wrote {out / 'captions_step4.csv'}")
    return out


def acceptance_report(result: Step4Result) -> list[str]:
    lines: list[str] = []

    t46 = result.tables["T4_06_country_specialisation"]
    n_startups_sum = int(t46["n_startups"].sum())
    green_sum = int(t46["n_green"].sum())
    lines.append(
        f"T4.6: {len(t46)} countries reported (no floor); "
        f"included n_startups={n_startups_sum} of {config.POP_TOTAL}, "
        f"green={green_sum} of {config.GREEN_TOTAL}"
    )
    if not t46.empty:
        top = t46.iloc[0]
        lines.append(f"  top by n_green: {top['country']} "
                     f"(n_green={int(top['n_green'])}, lq={top['lq']})")
        n_sens = int((t46["n_startups"] >= config.MIN_COUNTRY_N_SENSITIVITY).sum())
        lines.append(f"  sensitivity: {n_sens} countries at n>="
                     f"{config.MIN_COUNTRY_N_SENSITIVITY} (the former floor)")
        flagged = int(t46["low_n_flag"].sum())
        if flagged:
            lines.append(f"  {flagged} country row(s) flagged green_n<{config.LOW_N_FLAG}")

    t47 = result.tables["T4_07_per_capita_crosscheck"]
    matched = int(t47["population_m"].notna().sum())
    rho = result.diagnostics.get("spearman_per_capita")
    n_rho = int(result.diagnostics.get("spearman_n", 0))
    lines.append(
        f"T4.7: {matched}/{len(t47)} countries matched to World Bank population; "
        f"Spearman(startups_per_million, green_intensity)={rho} on n={n_rho} "
        f"(reference ~ {config.SPEARMAN_REFERENCE})"
    )
    unmatched = t47.loc[t47["population_m"].isna(), "country"].tolist()
    if unmatched:
        lines.append(f"  no population match (kept with NA): {', '.join(unmatched)}")

    t48 = result.tables["T4_08_concentration"].set_index("measure")
    for k in config.TOP_COUNTRY_K:
        key = f"top{k}_country_share"
        if key in t48.index:
            lines.append(f"T4.8 {key}: green={t48.loc[key, 'green']} "
                         f"other={t48.loc[key, 'other']} "
                         f"diff={t48.loc[key, 'difference']}")

    ap2 = result.tables["AP2_city_ranking"]
    lines.append(f"AP2: {len(ap2)} cities with n>={config.MIN_CITY_N} (city floor kept)")
    if not ap2.empty:
        top = ap2.iloc[0]
        lines.append(f"  top by n_green: {top['city']} ({top['country']}, "
                     f"n_green={int(top['n_green'])})")

    return lines
