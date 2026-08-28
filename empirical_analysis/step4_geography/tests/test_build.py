"""Tests for Step 4 (geography).

A small synthetic firm table (three countries, one below the reporting minimum)
exercises the geography builders: the country location quotient against the fixed
EU-wide reference (rule N9 — the sub-minimum country stays in the denominator), the
Stage 1 / Stage 2+3 robustness split (R1), the Eurostat per-capita join and its
Spearman check (T4.7), group-own-denominator concentration (T4.8), and the city
ranking with its minimum and modal country (AP2).
"""

from __future__ import annotations

import pandas as pd

from empirical_analysis.step4_geography.build import (
    build_all,
    build_city_ranking,
    build_concentration,
    build_country_specialisation,
    build_per_capita,
    spearman_per_capita,
    write_outputs,
)

TEST_MIN_COUNTRY_N = 2   # fixture is tiny; 500 would exclude everything
TEST_MIN_CITY_N = 2


def _firm_frame() -> pd.DataFrame:
    # Germany 4 (green F1,F2), France 4 (green F5), Italy 1 (green F9, below min).
    # Total 9 firms, 4 green -> EU intensity 4/9 = 0.4444.
    return pd.DataFrame(
        [
            {"company_id": "F1", "green": 1, "green_signal_group": "Stage 1",
             "hq_country": "Germany", "hq_city": "Berlin"},
            {"company_id": "F2", "green": 1, "green_signal_group": "Stage 2+3",
             "hq_country": "Germany", "hq_city": "Berlin"},
            {"company_id": "F3", "green": 0, "green_signal_group": "none",
             "hq_country": "Germany", "hq_city": "Berlin"},
            {"company_id": "F4", "green": 0, "green_signal_group": "none",
             "hq_country": "Germany", "hq_city": "Munich"},
            {"company_id": "F5", "green": 1, "green_signal_group": "Stage 1",
             "hq_country": "France", "hq_city": "Paris"},
            {"company_id": "F6", "green": 0, "green_signal_group": "none",
             "hq_country": "France", "hq_city": "Paris"},
            {"company_id": "F7", "green": 0, "green_signal_group": "none",
             "hq_country": "France", "hq_city": "Lyon"},
            {"company_id": "F8", "green": 0, "green_signal_group": "none",
             "hq_country": "France", "hq_city": "   "},  # blank city
            {"company_id": "F9", "green": 1, "green_signal_group": "Stage 1",
             "hq_country": "Italy", "hq_city": "Rome"},
        ]
    )


def _population_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"geo_code": "DE", "country_eurostat": "Germany", "year": 2024,
             "population": 8_000_000},
            {"geo_code": "FR", "country_eurostat": "France", "year": 2024,
             "population": 6_000_000},
            {"geo_code": "IT", "country_eurostat": "Italy", "year": 2024,
             "population": 5_000_000},
        ]
    )


def test_country_specialisation_lq_uses_full_population_reference():
    t46 = build_country_specialisation(
        _firm_frame(), min_country_n=TEST_MIN_COUNTRY_N
    ).set_index("country")
    # Italy (n=1) is below the minimum -> no row, but stays in the EU denominator.
    assert "Italy" not in t46.index
    assert set(t46.index) == {"Germany", "France"}

    # Germany intensity 0.5; EU reference is 4/9 (Italy's green firm counted), so
    # lq = 0.5 / (4/9) = 1.125.  If Italy were dropped from the denominator the
    # reference would be 3/8 and lq would read 1.333 -> this pins rule N9.
    assert t46.loc["Germany", "n_green"] == 2
    assert t46.loc["Germany", "n_others"] == 2
    assert t46.loc["Germany", "n_startups"] == 4
    assert t46.loc["Germany", "green_intensity"] == 0.5
    assert t46.loc["Germany", "lq"] == 1.125
    assert t46.loc["Germany", "share_of_european_green"] == 0.5  # 2 of 4 EU green


def test_country_specialisation_stage_split():
    t46 = build_country_specialisation(
        _firm_frame(), min_country_n=TEST_MIN_COUNTRY_N
    ).set_index("country")
    # Stage 1 green firms EU-wide = F1,F5,F9 = 3 -> ref 3/9. Germany stage1 = F1 (1
    # of 4) -> 0.25 / (3/9) = 0.75. Stage 2+3 EU-wide = F2 = 1 -> ref 1/9; Germany
    # stage23 = F2 (1 of 4) -> 0.25 / (1/9) = 2.25.
    assert t46.loc["Germany", "lq_stage1"] == 0.75
    assert t46.loc["Germany", "lq_stage2plus3"] == 2.25


def test_per_capita_join_and_spearman():
    t46 = build_country_specialisation(_firm_frame(), min_country_n=1)
    t47 = build_per_capita(t46, _population_frame()).set_index("country")
    assert t47.loc["Germany", "population_m"] == 8.0
    assert t47.loc["Germany", "startups_per_million"] == 0.5    # 4 / 8
    assert t47.loc["Germany", "green_per_million"] == 0.25      # 2 / 8

    rho, n = spearman_per_capita(t47.reset_index())
    # spm ranks IT(0.2)<DE(0.5)<FR(0.667), intensity ranks FR<DE<IT -> perfect inversion.
    assert n == 3
    assert rho == -1.0


def test_per_capita_keeps_unmatched_country_as_na():
    firm = _firm_frame()
    firm.loc[firm["company_id"] == "F9", "hq_country"] = "Russia"  # no Eurostat code
    t46 = build_country_specialisation(firm, min_country_n=1)
    t47 = build_per_capita(t46, _population_frame()).set_index("country")
    assert "Russia" in t47.index
    assert pd.isna(t47.loc["Russia", "population_m"])


def test_concentration_uses_group_own_denominator():
    t48 = build_concentration(_firm_frame()).set_index("measure")
    # Green firms span 3 countries (DE2, FR1, IT1) -> top5 share = 4/4 = 1.0.
    assert t48.loc["top5_country_share", "green"] == 1.0
    # Other firms span DE2, FR3 -> 5/5 = 1.0.
    assert t48.loc["top5_country_share", "other"] == 1.0


def test_city_ranking_minimum_and_modal_country():
    ap2 = build_city_ranking(_firm_frame(), min_city_n=TEST_MIN_CITY_N)
    ap2i = ap2.set_index("city")
    # Berlin (3) and Paris (2) clear the minimum; Munich/Lyon/Rome (1) and the blank
    # city do not.
    assert set(ap2i.index) == {"Berlin", "Paris"}
    assert ap2i.loc["Berlin", "n_green"] == 2
    assert ap2i.loc["Berlin", "n_others"] == 1
    assert ap2i.loc["Berlin", "n_startups"] == 3
    assert ap2i.loc["Berlin", "country"] == "Germany"


def test_city_ranking_folds_accent_and_case_variants():
    # Zürich / Zurich / zurich are one city; the modal spelling ("Zurich", 2x) wins.
    firm = pd.DataFrame(
        [
            {"company_id": "Z1", "green": 1, "green_signal_group": "Stage 1",
             "hq_country": "Switzerland", "hq_city": "Zürich"},
            {"company_id": "Z2", "green": 0, "green_signal_group": "none",
             "hq_country": "Switzerland", "hq_city": "Zurich"},
            {"company_id": "Z3", "green": 0, "green_signal_group": "none",
             "hq_country": "Switzerland", "hq_city": "zurich"},
        ]
    )
    ap2 = build_city_ranking(firm, min_city_n=TEST_MIN_CITY_N)
    # All three collapse to a single row rather than three separate cities.
    assert len(ap2) == 1
    row = ap2.iloc[0]
    assert row["city"] == "Zurich"        # modal original spelling
    assert row["n_startups"] == 3
    assert row["n_green"] == 1
    assert row["country"] == "Switzerland"


def test_build_all_and_write(tmp_path):
    result = build_all(
        _firm_frame(), _population_frame(),
        min_country_n=TEST_MIN_COUNTRY_N, min_city_n=TEST_MIN_CITY_N,
    )
    for key in ("T4_06_country_specialisation", "T4_07_per_capita_crosscheck",
                "T4_08_concentration", "AP2_city_ranking",
                "F4_02_green_count_by_country", "F4_03_lq_by_country"):
        assert key in result.tables
    # F4.3 is ranked by lq descending.
    lq_fig = result.tables["F4_03_lq_by_country"]
    assert list(lq_fig["lq"]) == sorted(lq_fig["lq"], reverse=True)
    assert (lq_fig["reference"] == 1.0).all()

    out = write_outputs(result, tmp_path)
    reread = pd.read_csv(out / "T4_06_country_specialisation.csv")
    assert not reread.empty
    assert (tmp_path / "captions_step4.csv").exists()
