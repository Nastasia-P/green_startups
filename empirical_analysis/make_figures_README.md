# Thesis figures — `make_figures.py`

Renders the Chapter 4 thesis figures as PNGs from the analysis CSVs. Green
start-ups are drawn in green and other European start-ups in grey consistently
across every figure; percentage values are printed on the bars; there are no
figure titles and no on-plot source text (only axis labels and a small legend).

## Prerequisites

1. The source CSVs must exist (see the table below). Two of them are produced by
   Step 14, so run the upstream steps first if needed:

   ```bash
   python -m empirical_analysis.step5b_fixed_horizon.run
   python -m empirical_analysis.step14_public_private.run
   ```

2. `matplotlib` must be installed (pinned in
   [`requirements.txt`](requirements.txt)):

   ```bash
   pip install -r empirical_analysis/requirements.txt   # or: pip install "matplotlib>=3.8"
   ```

   If `matplotlib` is missing, the script does not crash — each figure is
   skipped with a clear message.

## Run

From the repository root:

```bash
# all figures, default folders
python -m empirical_analysis.make_figures
```

By default it reads CSVs from `data/outputs/chapter4/` and writes PNGs to
`data/outputs/chapter4/figures/`.

### Optional arguments

| Argument | Default | Purpose |
|---|---|---|
| `--input-dir PATH` | `data/outputs/chapter4` | Folder containing the source CSVs. |
| `--output-dir PATH` | `<input-dir>/figures` | Folder for the PNGs (follows `--input-dir` if not set). |
| `--only ID [ID ...]` | all | Render only these figures. Valid IDs: `1 4 5 6 S1`. |

Examples:

```bash
# CSVs in a custom folder; PNGs written to <that folder>/figures
python -m empirical_analysis.make_figures --input-dir /path/to/csvs

# custom CSV folder and a separate output folder
python -m empirical_analysis.make_figures \
    --input-dir /path/to/csvs \
    --output-dir /path/to/figures

# render a subset only
python -m empirical_analysis.make_figures --only 4 5 S1
```

Run `python -m empirical_analysis.make_figures --help` for the same reference.

## Figures, sources and outputs

All source CSVs must live in `--input-dir`.

| Figure | Output PNG | Source CSV | Produced by |
|---|---|---|---|
| Figure 1 — founding-cohort composition | `fig1_founding_cohort_composition.png` | `F4_01_green_share_by_cohort.csv` | Step 3 |
| Figure 4 — first-five-year financing access | `fig4_first5_financing_access.png` | `T_first5_access.csv` | Step 5b |
| Figure 5 — first-five-year investor-type mix | `fig5_first5_investor_type_participation.png` | `T_first5_investor_type_participation.csv` | Step 14 |
| Figure 6 — green share of firms vs recorded capital | `fig6_green_share_firms_vs_capital.png` | `T4_26_green_share_firms_vs_capital.csv` | Step 7 |
| Figure S1 — first-five-year public/private participation | `figS1_first5_public_private.png` | `T_first5_public_private.csv` | Step 14 |

Figure 3 (the green location-quotient choropleth) is **not** produced by this
script; the map set is rendered separately by
[`step4_maps`](step4_maps/) (`F4_M5_green_lq.png` / `.pdf`).

## Colour scheme

- Green start-ups: dark green (`#2e7d32`).
- Other European start-ups: grey (`#9e9e9e`).
- Figure 6 second measure (green share of recorded capital): light green
  (`#a5d6a7`) — both Figure 6 bars describe green firms.

## Notes

- The pure data-prep helpers (`prep_*`) use only pandas and are unit-tested in
  [`tests/test_make_figures.py`](tests/test_make_figures.py); matplotlib is
  imported lazily inside the render functions.
- Figures 4, 5 and S1 report first-five-year (common-horizon) measures; Figures
  5 and S1 condition on firms having at least one recorded investor in the
  window (the INVESTED denominator).
