"""Preview the Three Horizons curves visual (no scenarios) as a PNG.

The bundle PPTX renders this in-process with scenarios mapped on the curves,
via ``app/services/wiley_three_horizons_viz.py``. This script is just a
manual sanity-check that the base curves still match the React component.

    python scripts/render_three_horizons.py
"""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.services.wiley_three_horizons_viz import render_to_png  # noqa: E402

if __name__ == "__main__":
    out = Path(__file__).resolve().parents[1] / "data" / "wiley_horizons" / "three_horizons_curves.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "wb") as f:
        render_to_png([], f)
    print(f"wrote {out} ({out.stat().st_size} bytes)")
