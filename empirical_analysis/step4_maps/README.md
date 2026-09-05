# Step 4 map set (`step4_maps`)

Five European choropleth maps of the start-up / green start-up geography, rendered
directly from existing Step 4 CSV outputs. This is a **read-only visualisation layer**:
it computes no new measure and never touches firm-level data. It reads the Step 4 CSVs,
joins them to a committed country geometry, and writes static maps (PNG + PDF).

## The five maps

Grouped into three conceptual blocks.

**A. Absolute geographic distribution**

| Map | Question | Source file | Column |
| --- | --- | --- | --- |
| M1 - Total European start-ups by country | Where is the start-up population concentrated in absolute terms? | `F4_02_green_count_by_country.csv` | `n_startups` |
| M2 - Green start-ups by country | Where are the largest absolute populations of green start-ups? | `F4_02_green_count_by_country.csv` | `n_green` |

M1 and M2 are meant to be read together: does the green geography follow the overall
start-up geography, or are some countries disproportionately prominent in the green map?

**B. Population-adjusted geographic density**

| Map | Question | Source file | Column |
| --- | --- | --- | --- |
| M3 - Total start-ups per million inhabitants | Which countries have high overall start-up density after adjusting for population? | `T4_07_per_capita_crosscheck.csv` | `startups_per_million` |
| M4 - Green start-ups per million inhabitants | Which countries have high green-start-up density relative to population? | `T4_07_per_capita_crosscheck.csv` | `green_per_million` |

M3 and M4 are a comparison pair: they separate countries that have many green firms
because of a generally dense ecosystem (e.g. Norway) from countries that stand out
specifically in green firms per inhabitant.

**C. Relative green specialisation**

| Map | Question | Source file | Column |
| --- | --- | --- | --- |
| M5 - Green-start-up location quotient | Which countries have a larger or smaller green share of their start-ups than Europe overall? | `F4_03_lq_by_country.csv` | `lq` |

`LQ = (green_c / all_c) / (green_Europe / all_Europe)`. Interpretation is preserved from
Step 4: `LQ = 1` equals the European benchmark, `LQ > 1` is relative over-representation,
`LQ < 1` is under-representation. No separate "all-start-up LQ" map is produced: the green
LQ already uses each country's entire start-up population as its denominator.

## Rendering

- Projection: reprojected to **EPSG:3035** (ETRS89 / LAEA Europe, equal-area). Geometry
  is first clipped to a European lon/lat window (`EUROPE_BBOX_LONLAT`) so overseas
  territories carried in the Natural Earth polygons (Dutch/French Caribbean, French
  Guiana, the Azores, Canary and Madeira islands) are not drawn and do not blow out the
  frame. The view window is then computed from the geometry excluding Russia so Siberia
  does not dominate; Russia is still drawn and extends past the right edge (whole-Europe
  framing).
- Maps 1-4: sequential colormap (`viridis`) with a **continuous colorbar on a log scale**
  (`LogNorm`), because counts and densities are heavily right-skewed (e.g. UK ~18,862 vs
  San Marino 2). Zero values (e.g. countries with no green start-ups) are floored to half
  the smallest positive value so they render at the dark end of the scale. The pair-mates
  share colormap and colorbar style for visual comparison.
- Map 5: diverging colormap (`RdBu_r`) with `TwoSlopeNorm(vcenter=1.0)`, so the benchmark
  `LQ = 1` sits at the neutral midpoint (marked with a line on the colorbar); red is
  over-representation, blue is under-representation.
- Borders are thin and white (reference-map style). Micro-states (Andorra, Monaco, San
  Marino, Liechtenstein, Gibraltar, Malta) remain small at Europe scale - this is
  expected. Gibraltar's polygon is only available in the Natural Earth 1:10m layer, so it
  is appended from there.

## Geometry

The committed geometry is `data/sources/europe_ne50m.geojson` (46 countries, Natural
Earth Admin-0, subset via ISO alpha-2). It is fetched once with network access and then
committed so map rendering is fully offline:

```bash
python -m empirical_analysis.step4_maps.fetch_geometry
```

The join key is the ISO alpha-2 code (`ISO_A2_EH` in Natural Earth, which is populated
even where `ISO_A2` is `-99` for France, Norway and Kosovo), reusing
`COUNTRY_TO_ISO2` from `step4_geography.config` as the single source of truth. The join
**fails loudly** if any data country cannot be mapped to an ISO2 code or has no geometry.

## Running

```bash
python -m empirical_analysis.step4_maps.run --verbose
```

### Overridable inputs (first match wins)

| CLI flag | Env var | Default |
| --- | --- | --- |
| `--input-dir` | `STEP4_MAPS_INPUT_DIR` | `data/outputs/chapter4` |
| `--geometry` | `STEP4_MAPS_GEOMETRY` | `data/sources/europe_ne50m.geojson` |
| `--output-dir` | `STEP4_MAPS_OUTPUT_DIR` | `data/outputs/chapter4/maps` |

## Outputs (in the output directory)

- `F4_M1_total_startups.{png,pdf}`
- `F4_M2_green_startups.{png,pdf}`
- `F4_M3_startups_per_million.{png,pdf}`
- `F4_M4_green_per_million.{png,pdf}`
- `F4_M5_green_lq.{png,pdf}`
- `maps_manifest.csv` - one row per map (source file/column, value range, output files)
- `maps_report.txt` - crosswalk validation and per-map highest/lowest countries

## Dependencies

`geopandas`, `mapclassify`, `matplotlib` (see `empirical_analysis/requirements.txt`);
geopandas pulls in `shapely`, `pyproj` and `pyogrio`. Install with:

```bash
# install everything (base pipeline + mapping deps)
pip install -r empirical_analysis/requirements.txt

# or just the mapping deps for this module
pip install "geopandas>=1.0" "mapclassify>=2.6" "matplotlib>=3.8"
```

## Tests

```bash
pytest empirical_analysis/step4_maps/tests -q
```
