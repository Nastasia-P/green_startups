# Step 4 — Geography

Self-contained specification. Everything needed to understand, run, or rebuild this
step is in this document; no other file needs to be open.

**Implements:** thesis outputs T4.6, T4.7, T4.8, AP2 and figure data F4.2, F4.3
**Implemented by:** `empirical_analysis/step4_geography/`
**Run with:** `python -m empirical_analysis.step4_geography.run`

---

## 1. Purpose

Step 4 describes *where* European green start-ups are, and separates two things that
raw counts conflate:

- **Size** — how many green firms a country has (absolute count).
- **Specialisation** — how green a country's start-up base is relative to Europe as a
  whole (the location quotient).

A country can be large and unremarkable (many start-ups, average green share) or small
and highly specialised (few start-ups, disproportionately green). The location
quotient makes that distinction, and it routinely inverts the raw-count ranking.

Step 4 is **descriptive only**. It reads the firm-level table from Step 2, groups by
country and city, and writes summary tables. It computes no new per-firm variables and
touches no deal or investor data.

**Coverage caveat (T4.7).** PitchBook coverage is not uniform across countries. Denser
coverage sweeps in many small firms unlikely to be tagged green, mechanically diluting
a country's green intensity. T4.7 exists to expose that: it cross-checks green
intensity against start-ups per capita, so a low location quotient driven by dense
coverage is not misread as genuinely low green specialisation.

---

## 2. Inputs

| Input | Grain | Used for |
|---|---|---|
| `company_analysis.parquet` (Step 2) | 1 per firm | T4.6, T4.8, AP2, F4.2, F4.3, and the country side of T4.7 |
| `eurostat_population.csv` | 1 per country | T4.7 only (population denominator) |

Columns consumed from `company_analysis`: `company_id`, `green`, `green_signal_group`,
`hq_country`, `hq_city`.

The firm table resolves in this order (first match wins); `--firm-table` overrides and
accepts either the Parquet file or the Step 2 output directory that contains it:

1. environment variable `STEP4_FIRM_TABLE`
2. the target machine's OneDrive `...\09_Python_Empirical Analysis\company_analysis.parquet`
3. `<repo>/data/outputs/company_analysis.parquet`

`eurostat_population.csv` resolves as `--population` > `STEP4_POPULATION` >
`<repo>/data/sources/eurostat_population.csv`. It is a committed file, so the run needs
no network. Regenerate it with `python -m empirical_analysis.step4_geography.fetch_eurostat`.

---

## 3. Conventions for every output

- Group labels are always **"Green start-ups"** and **"Other European start-ups"**
  (rule N10). Never "non-green".
- Every table reports its own **n** (country or city firm count) alongside any share.
- **Country denominators use the full 116,005 population** (rule N9), never PitchBook's
  global universe. The EU-wide denominators in the location quotient use all 116,005
  and all 8,306 green; the reference is fixed at the EU level, so which countries are
  shown does not move any country's LQ.
- **Country floor dropped (per request):** the decision-D4 500-firm gate is removed.
  `MIN_COUNTRY_N` is set to **1**, so **every country with at least one start-up gets a
  row**; thin cells carry `low_n_flag` (green < 30) and are read as indicative rather
  than dropped. The former 500 gate is printed only as a sensitivity count. Cities keep
  the **≥100** floor (`MIN_CITY_N`).
- **Robustness R1** (`green_signal_group`: Stage 1 vertical vs Stage 2+3 text) is
  applied to the location quotient in T4.6 as two extra columns.

---

## 4. Outputs

All tables are written as CSV. Figures are written as CSV data files first; the
plotted PDF is a later, cosmetic step (as with F4.1 in Step 3).

Destination resolves as: `--output-dir` > `STEP4_OUTPUT_DIR` > the target machine's
OneDrive `...\09_Python_Empirical Analysis\chapter4_outputs` > `<repo>/data/outputs/chapter4`.

### 4.1 `T4_06_country_specialisation.csv` — country distribution and specialisation (T4.6)

One row per country (all countries, no floor), ranked by `green_n` descending.

| Column | Formula / meaning |
|---|---|
| `country` | `hq_country` |
| `green_n` | green firms in the country |
| `n_startups` | all start-ups in the country |
| `share_of_european_green` | `green_n / 8,306` |
| `green_intensity` | `green_n / n_startups` |
| `lq` | `green_intensity / (8,306 / 116,005)` |
| `lq_stage1` | same, using only Stage 1 (vertical) green firms in the numerator |
| `lq_stage2plus3` | same, using only Stage 2+3 (text) green firms |
| `low_n_flag` | 1 if `green_n < 30` |

The location quotient's EU-wide reference (`8,306 / 116,005 ≈ 0.0716`) uses the full
population, so `lq > 1` means the country is more green-specialised than Europe overall.
The Stage-1 and Stage-2+3 variants divide their own EU green totals (6,636 and 1,670)
by 116,005 as the reference.

### 4.2 `T4_07_per_capita_crosscheck.csv` — per-capita cross-check (T4.7)

Same country set as T4.6, joined to Eurostat population. Countries without a population
match (e.g. Russia) keep NA in the population columns and are retained with a note.

| Column | Formula / meaning |
|---|---|
| `country` | `hq_country` |
| `population_m` | Eurostat population, millions |
| `n_startups` | from T4.6 |
| `green_n` | from T4.6 |
| `startups_per_million` | `n_startups / population_m` |
| `green_per_million` | `green_n / population_m` |
| `green_intensity` | from T4.6 |
| `lq` | from T4.6 |

The run prints Spearman correlation between `startups_per_million` and `green_intensity`
across countries with a population match. The spec's reference is about **-0.67** on 19
countries; a large deviation is warned, never fatal (the D4 threshold and the 8,306
ledger can shift the set).

### 4.3 `T4_08_concentration.csv` — geographic concentration (T4.8)

Are green start-ups more spatially concentrated than start-ups generally?

| Column | Content |
|---|---|
| `measure` | row label |
| `green` | value for green start-ups |
| `other` | value for other European start-ups |
| `difference` | green − other |

Rows: `top5_country_share`, `top10_country_share`, `top5_city_share`, `hhi_country`
(Herfindahl-Hirschman index over country shares, secondary). Shares use each group's own
total as the denominator, so green concentration is comparable to other concentration.

### 4.4 `AP2_city_ranking.csv` — city-level ranking (AP2)

One row per city with ≥100 start-ups, ranked by `green_n` descending.

| Column | Content |
|---|---|
| `city` | `hq_city` |
| `country` | modal `hq_country` for the city |
| `green_n` | green firms in the city |
| `n_startups` | all start-ups in the city |
| `share_of_european_green` | `green_n / 8,306` |
| `green_intensity` | `green_n / n_startups` |
| `low_n_flag` | 1 if `green_n < 30` |

### 4.5 `F4_02_green_count_by_country.csv` — figure data (F4.2)

Plot data for the absolute-count bar chart: `country`, `green_n`, ranked as T4.6.

### 4.6 `F4_03_lq_by_country.csv` — figure data (F4.3)

Plot data for the location-quotient figure: `country`, `lq`, `reference` (= 1.0 on every
row, the LQ = 1 line), ranked by `lq` descending.

---

## 5. Rules that apply throughout

- **Denominators are the full population (N9).** Country and EU totals count all
  116,005 firms; nothing is dropped for missing `hq_city` beyond that city's own row.
- **Missing is unknown.** A firm with a blank `hq_city` is excluded from city rows but
  still counts in its country and in the EU totals.
- **The location quotient reference is fixed at the EU level**, not recomputed per the
  reporting subset, so excluding sub-500 countries does not move the LQ of the
  countries that remain.

---

## 6. Eurostat population (T4.7)

Population is the only external data the whole plan uses (spec §Scope). It comes from
Eurostat table **`demo_pjan`** (population on 1 January), filtered to `sex = T`,
`age = TOTAL`, most recent year with broad country coverage.

`fetch_eurostat.py` downloads it through the public JSON-stat API and writes
`data/sources/eurostat_population.csv` with columns `geo_code`, `country_eurostat`,
`year`, `population`. The PitchBook `hq_country` → Eurostat `geo_code` name map lives in
`config.py` (`COUNTRY_TO_EUROSTAT`), covering the naming gaps: `United Kingdom → UK`,
`Czech Republic → CZ`/CZE, `Greece → EL`, plus the non-EU members Eurostat still
publishes (`Switzerland → CH`, `Norway → NO`). Countries with no Eurostat entry (e.g.
Russia) are kept with NA population.

The committed CSV is the runtime input, so the analysis machine needs no network.
Re-fetching is optional and only needed to refresh the year.

---

## 7. Acceptance checks

The run prints these at the end. Step 4 is done when they pass.

- [ ] T4.6 lists every country (all 46 in the current data; 20 at the former ≥500
      floor, printed as a sensitivity), ranked by `green_n`, and the sum of `n_startups`
      over countries equals the full 116,005
- [ ] `lq` uses the fixed EU reference `8,306 / 116,005`; a country at the EU average
      reads `lq ≈ 1`
- [ ] T4.7 joins Eurostat population; the Spearman(startups_per_million, green_intensity)
      is printed (reference ≈ -0.67)
- [ ] T4.8 shares use each group's own denominator; green vs other are comparable
- [ ] AP2 lists cities with ≥100 start-ups; firms with blank `hq_city` are excluded from
      city rows only
- [ ] every reported row carries its firm count `n`, and `green_n < 30` rows are flagged

---

## 8. Decisions taken, with defaults

| Decision | Default | Where to change |
|---|---|---|
| Country minimum denominator | 500 (sensitivity count at 800 printed) | `MIN_COUNTRY_N` in `config.py` |
| City minimum denominator | 100 | `MIN_CITY_N` in `config.py` |
| Low-n flag threshold | 30 | `LOW_N_FLAG` in `config.py` |
| Eurostat year | most recent broad-coverage year at fetch time | `fetch_eurostat.py` |
| PitchBook → Eurostat country map | EU27 + UK + CH + NO + neighbours | `COUNTRY_TO_EUROSTAT` in `config.py` |

---

## 9. Out of scope

- NUTS-2 regional cut (T4.27, decision D5) — needs a reliable city-to-NUTS mapping.
- Plotted PDF figures — this step writes the figure *data* only.
- Any funding, deal or investor analysis — Steps 5-6.
- Re-deriving the population or green flags — fixed by Chapter 3 and Step 1.

---

## 10. How to run it

```bash
# refresh the Eurostat population file (optional; needs network)
python -m empirical_analysis.step4_geography.fetch_eurostat

# build from the local Step 2 output
python -m empirical_analysis.step4_geography.run \
    --firm-table data/outputs/company_analysis.parquet \
    --output-dir data/outputs/chapter4

# on the target machine, the OneDrive paths resolve on their own
python -m empirical_analysis.step4_geography.run
```

Tests: `python -m pytest empirical_analysis/step4_geography/tests/ -q`
