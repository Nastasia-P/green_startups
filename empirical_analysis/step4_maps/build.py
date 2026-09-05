"""Build the Step 4 map set: five European choropleth maps from Step 4 CSV outputs.

Read-only over the input CSVs. Loads the committed geometry, joins each map's value
column via the country -> ISO alpha-2 key, reprojects to EPSG:3035, and renders static
PNG + PDF maps plus a manifest and a text report.

Maps 1-4 use a sequential colormap with quantile classification (k=5). Map 5 (green
location quotient) uses a diverging colormap centred on the European benchmark LQ = 1
via ``TwoSlopeNorm(vcenter=1.0)``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

import geopandas as gpd
import matplotlib

matplotlib.use("Agg")  # headless rendering on the HPC node
import matplotlib.pyplot as plt
from matplotlib.cm import ScalarMappable
from matplotlib.colors import LogNorm, Normalize
from matplotlib.ticker import FuncFormatter
import pandas as pd
from shapely.geometry import box

from . import config


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------
def load_geometry(path: Path | None = None) -> gpd.GeoDataFrame:
    """Load the committed country geometry and reproject to the European CRS."""
    path = Path(path) if path is not None else config.GEOMETRY_FILE
    if not path.exists():
        raise FileNotFoundError(
            f"Geometry not found: {path}. Run "
            "`python -m empirical_analysis.step4_maps.fetch_geometry` first."
        )
    gdf = gpd.read_file(path)
    if "iso_a2" not in gdf.columns:
        raise KeyError(f"Geometry {path} is missing the 'iso_a2' join field.")
    # Clip to the European window in lon/lat before reprojecting, dropping overseas
    # territories (Caribbean, French Guiana, Azores, Canaries) that otherwise blow out
    # the frame. Done in EPSG:4326 where the box edges are straightforward.
    if gdf.crs is None:
        gdf = gdf.set_crs("EPSG:4326")
    else:
        gdf = gdf.to_crs("EPSG:4326")
    europe = box(*config.EUROPE_BBOX_LONLAT)
    gdf = gdf.clip(europe)
    gdf = gdf[~gdf.geometry.is_empty & gdf.geometry.notna()]
    return gdf.to_crs(config.MAP_CRS)


def _read_source(input_dir: Path, filename: str) -> pd.DataFrame:
    fp = input_dir / filename
    if not fp.exists():
        raise FileNotFoundError(f"Step 4 input not found: {fp}")
    df = pd.read_csv(fp)
    if "country" not in df.columns:
        raise KeyError(f"{fp} has no 'country' column.")
    return df


def load_sources(input_dir: Path | None = None) -> dict[str, pd.DataFrame]:
    """Load the three Step 4 CSVs referenced by the map specs."""
    input_dir = Path(input_dir) if input_dir is not None else config.INPUT_DIR
    files = {spec["source_file"] for spec in config.MAP_SPECS}
    return {name: _read_source(input_dir, name) for name in files}


# ---------------------------------------------------------------------------
# Join
# ---------------------------------------------------------------------------
def _attach_value(
    geom: gpd.GeoDataFrame, df: pd.DataFrame, column: str
) -> gpd.GeoDataFrame:
    """Join ``df[column]`` onto the geometry via country -> ISO2, failing loudly.

    Fatal if a data country cannot be mapped to an ISO2 code, or if a data country's
    ISO2 is absent from the geometry. Countries that are in the geometry but absent from
    this CSV are kept with a NaN value and drawn grey ("no data").
    """
    if column not in df.columns:
        raise KeyError(f"Column {column!r} not found in source (have {list(df.columns)}).")

    work = df[["country", column]].copy()
    work["iso2"] = work["country"].map(config.COUNTRY_TO_ISO2)
    unknown = sorted(work.loc[work["iso2"].isna(), "country"].unique())
    if unknown:
        raise ValueError(
            f"{len(unknown)} country name(s) in the data have no ISO2 mapping: {unknown}"
        )

    geom_iso = set(geom["iso_a2"])
    not_in_geom = sorted(work.loc[~work["iso2"].isin(geom_iso), "country"].unique())
    if not_in_geom:
        raise ValueError(
            f"{len(not_in_geom)} data country(ies) have no geometry: {not_in_geom}. "
            "Re-run fetch_geometry to rebuild the committed GeoJSON."
        )

    merged = geom.merge(
        work[["iso2", column]], left_on="iso_a2", right_on="iso2", how="left"
    )
    return merged


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------
@dataclass
class MapResult:
    spec_id: str
    title: str
    source_file: str
    column: str
    n_countries: int
    vmin: float
    vmax: float
    top: list[tuple[str, float]]
    bottom: list[tuple[str, float]]
    outputs: list[str]


def _view_bounds(geom: gpd.GeoDataFrame) -> tuple[float, float, float, float]:
    """Compute a European view window from the geometry, excluding Russia's extent."""
    frame = geom[~geom["iso_a2"].isin(config.VIEW_EXCLUDE_ISO2)]
    minx, miny, maxx, maxy = frame.total_bounds
    mx = (maxx - minx) * config.VIEW_MARGIN_FRAC
    my = (maxy - miny) * config.VIEW_MARGIN_FRAC
    return (minx - mx, miny - my, maxx + mx, maxy + my)


def _style_axes(ax, bounds: tuple[float, float, float, float]) -> None:
    ax.set_xlim(bounds[0], bounds[2])
    ax.set_ylim(bounds[1], bounds[3])
    ax.set_aspect("equal")
    ax.set_axis_off()


def _finish(fig, ax, spec: dict) -> None:
    ax.set_title(
        f"{spec['title']}\n{spec['block']}",
        fontsize=13, fontweight="bold", loc="left",
    )
    fig.text(
        0.01, 0.01,
        f"Source: Step 4 output {spec['source_file']} (column '{spec['column']}'). "
        "Projection: ETRS89 / LAEA Europe (EPSG:3035).",
        fontsize=7, color="#555555",
    )


def _plain_number(v, pos=None) -> str:
    """Human-readable plain number (no scientific notation)."""
    if v <= 0:
        return "0"
    if v >= 1000:
        return f"{v:,.0f}"
    if v >= 10:
        return f"{v:.0f}"
    if v >= 1:
        return f"{v:.1f}".rstrip("0").rstrip(".")
    return f"{v:.2f}".rstrip("0").rstrip(".")


_PLAIN_FMT = FuncFormatter(_plain_number)


def _colorbar(fig, ax, sm, label: str):
    cbar = fig.colorbar(sm, ax=ax, shrink=0.6, pad=0.02)
    cbar.set_label(label, fontsize=config.CBAR_LABEL_FONTSIZE)
    cbar.ax.tick_params(labelsize=config.CBAR_TICK_FONTSIZE)
    return cbar


def _log_ticks(vmin: float, vmax: float) -> list[float]:
    """Real min/max plus the power-of-ten decades in between (no crowding)."""
    lo, hi = math.floor(math.log10(vmin)), math.ceil(math.log10(vmax))
    decades = [10.0 ** k for k in range(lo, hi + 1)]
    inner = [d for d in decades if d > vmin * 1.5 and d < vmax / 1.5]
    return [vmin] + inner + [vmax]


def _render_log(merged: gpd.GeoDataFrame, spec: dict, bounds, ax, fig) -> None:
    """Continuous viridis fill on a log scale, with a plain-number colorbar.

    Counts and per-capita densities are heavily right-skewed, so a log colour scale keeps
    the whole range legible. The colorbar is anchored to the real minimum (smallest
    positive value) and maximum, labelled as plain numbers. Zero values (e.g. countries
    with no green start-ups) sit at the darkest colour (clipped to the minimum).
    """
    col = spec["column"]
    valued = merged[merged[col].notna()].copy()
    missing = merged[merged[col].isna()]

    vals = valued[col].astype(float)
    positive = vals[vals > 0]
    pmin = float(positive.min()) if len(positive) else 1.0
    vmax = float(vals.max())
    valued["_plot"] = vals.clip(lower=pmin)   # zeros -> darkest colour
    norm = LogNorm(vmin=pmin, vmax=vmax)

    if not missing.empty:
        missing.plot(ax=ax, color=config.MISSING_COLOR,
                     edgecolor=config.EDGE_COLOR, linewidth=config.EDGE_WIDTH)
    valued.plot(
        ax=ax, column="_plot", cmap=config.SEQUENTIAL_CMAP, norm=norm,
        edgecolor=config.EDGE_COLOR, linewidth=config.EDGE_WIDTH,
    )
    _style_axes(ax, bounds)
    sm = ScalarMappable(cmap=config.SEQUENTIAL_CMAP, norm=norm)
    sm.set_array([])
    cbar = _colorbar(fig, ax, sm, spec["legend_title"])
    cbar.set_ticks(_log_ticks(pmin, vmax))
    cbar.ax.yaxis.set_major_formatter(_PLAIN_FMT)
    cbar.minorticks_off()


def _render_lq(merged: gpd.GeoDataFrame, spec: dict, bounds, ax, fig) -> None:
    """Green location quotient on the shared viridis scheme (linear), with the LQ = 1
    European benchmark marked by a black line on the colorbar."""
    col = spec["column"]
    valued = merged[merged[col].notna()]
    missing = merged[merged[col].isna()]
    vmin = float(valued[col].min())
    vmax = float(valued[col].max())
    norm = Normalize(vmin=vmin, vmax=vmax)

    if not missing.empty:
        missing.plot(ax=ax, color=config.MISSING_COLOR,
                     edgecolor=config.EDGE_COLOR, linewidth=config.EDGE_WIDTH)
    valued.plot(
        ax=ax,
        column=col,
        cmap=config.SEQUENTIAL_CMAP,
        norm=norm,
        edgecolor=config.EDGE_COLOR,
        linewidth=config.EDGE_WIDTH,
    )
    _style_axes(ax, bounds)
    sm = ScalarMappable(cmap=config.SEQUENTIAL_CMAP, norm=norm)
    sm.set_array([])
    cbar = _colorbar(fig, ax, sm, spec["legend_title"])
    ticks = sorted({vmin, 0.5, config.LQ_CENTER, 1.5, 2.0, 2.5, vmax})
    cbar.set_ticks([t for t in ticks if vmin <= t <= vmax])
    cbar.ax.yaxis.set_major_formatter(_PLAIN_FMT)
    if vmin <= config.LQ_CENTER <= vmax:
        cbar.ax.axhline(config.LQ_CENTER, color="black", linewidth=1.2)


def _summarise(merged: gpd.GeoDataFrame, spec: dict) -> tuple:
    col = spec["column"]
    valued = merged[merged[col].notna()][["admin", col]].copy()
    ordered = valued.sort_values(col, ascending=False)
    top = [(r["admin"], float(r[col])) for _, r in ordered.head(3).iterrows()]
    bottom = [(r["admin"], float(r[col])) for _, r in ordered.tail(3).iterrows()]
    return len(valued), float(valued[col].min()), float(valued[col].max()), top, bottom


def render_map(
    geom: gpd.GeoDataFrame,
    sources: dict[str, pd.DataFrame],
    spec: dict,
    bounds,
    output_dir: Path,
) -> MapResult:
    """Render one map to PNG + PDF and return its summary."""
    df = sources[spec["source_file"]]
    merged = _attach_value(geom, df, spec["column"])

    fig, ax = plt.subplots(figsize=config.FIG_SIZE)
    if spec["kind"] == "lq":
        _render_lq(merged, spec, bounds, ax, fig)
    else:
        _render_log(merged, spec, bounds, ax, fig)
    _finish(fig, ax, spec)
    fig.tight_layout()

    output_dir.mkdir(parents=True, exist_ok=True)
    outputs: list[str] = []
    for ext, kw in (("png", {"dpi": config.PNG_DPI}), ("pdf", {})):
        out = output_dir / f"{spec['output_stem']}.{ext}"
        fig.savefig(out, bbox_inches="tight", **kw)
        outputs.append(out.name)
    plt.close(fig)

    n, vmin, vmax, top, bottom = _summarise(merged, spec)
    if config.VERBOSE:
        print(f"[maps] {spec['id']} {spec['title']}: n={n} min={vmin} max={vmax}")
    return MapResult(
        spec_id=spec["id"], title=spec["title"], source_file=spec["source_file"],
        column=spec["column"], n_countries=n, vmin=vmin, vmax=vmax,
        top=top, bottom=bottom, outputs=outputs,
    )


# ---------------------------------------------------------------------------
# Manifest + report
# ---------------------------------------------------------------------------
def write_manifest(results: list[MapResult], output_dir: Path) -> Path:
    rows = [
        {
            "map_id": r.spec_id,
            "title": r.title,
            "source_file": r.source_file,
            "source_column": r.column,
            "n_countries": r.n_countries,
            "value_min": round(r.vmin, 4),
            "value_max": round(r.vmax, 4),
            "output_png": next((o for o in r.outputs if o.endswith(".png")), ""),
            "output_pdf": next((o for o in r.outputs if o.endswith(".pdf")), ""),
        }
        for r in results
    ]
    out = output_dir / "maps_manifest.csv"
    pd.DataFrame(rows).to_csv(out, index=False)
    return out


def report_lines(results: list[MapResult], n_geometry: int) -> list[str]:
    lines = [
        "Step 4 map set - build report",
        "=" * 60,
        f"Geometry countries : {n_geometry}",
        f"Analytical countries: {len(config.ANALYTICAL_COUNTRIES)}",
        f"Maps rendered      : {len(results)}",
        "",
    ]
    for r in results:
        lines.append(f"[{r.spec_id}] {r.title}")
        lines.append(f"    source     : {r.source_file} (column '{r.column}')")
        lines.append(f"    countries  : {r.n_countries}  (all 46 expected)")
        lines.append(f"    value range: {r.vmin:.4g} .. {r.vmax:.4g}")
        top = ", ".join(f"{n} ({v:.4g})" for n, v in r.top)
        bot = ", ".join(f"{n} ({v:.4g})" for n, v in reversed(r.bottom))
        lines.append(f"    highest    : {top}")
        lines.append(f"    lowest     : {bot}")
        lines.append(f"    outputs    : {', '.join(r.outputs)}")
        lines.append("")
    return lines


def write_report(lines: list[str], output_dir: Path) -> Path:
    out = output_dir / "maps_report.txt"
    out.write_text("\n".join(lines) + "\n")
    return out


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------
def build_all(
    input_dir: Path | None = None,
    geometry_path: Path | None = None,
    output_dir: Path | None = None,
) -> list[MapResult]:
    """Render all five maps and write the manifest and report."""
    input_dir = Path(input_dir) if input_dir is not None else config.INPUT_DIR
    output_dir = Path(output_dir) if output_dir is not None else config.OUTPUT_DIR

    geom = load_geometry(geometry_path)
    sources = load_sources(input_dir)
    bounds = _view_bounds(geom)

    results = [
        render_map(geom, sources, spec, bounds, output_dir)
        for spec in config.MAP_SPECS
    ]

    write_manifest(results, output_dir)
    write_report(report_lines(results, len(geom)), output_dir)
    return results
