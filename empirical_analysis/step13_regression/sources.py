"""Input access for Step 13 (common-horizon regression).

Loads the Step 5b canonical five-year firm panel (`first5_analysis.parquet`).
That single file already carries every control and `_5yr` outcome variable
needed by every regression family here, so no other input is read. No
transformation happens here.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from . import config


def log(msg: str) -> None:
    if config.VERBOSE:
        print(msg)


def resolve_firm_panel(firm_panel_path: Path | None = None) -> Path:
    """Accept either the parquet file or the Step 5b output directory."""
    path = Path(firm_panel_path or config.FIRM_PANEL)
    if path.is_dir():
        candidate = path / "first5_analysis.parquet"
        if not candidate.exists():
            raise FileNotFoundError(
                f"--firm-panel is a directory but {candidate} is missing. "
                "Point --firm-panel at first5_analysis.parquet (run "
                "step5b_fixed_horizon first), or at the Step 5b output "
                "folder that contains that file."
            )
        return candidate
    return path


def load_firm_panel(firm_panel_path: Path | None = None) -> pd.DataFrame:
    """Load first5_analysis.parquet (one row per common-horizon eligible firm)."""
    path = resolve_firm_panel(firm_panel_path)
    if not path.exists():
        raise FileNotFoundError(
            f"{path} does not exist. Run "
            "`python -m empirical_analysis.step5b_fixed_horizon.run` first "
            "to produce first5_analysis.parquet."
        )
    df = pd.read_parquet(path)
    log(f"[step13] load firm panel: {path} rows={len(df)}")
    return df
