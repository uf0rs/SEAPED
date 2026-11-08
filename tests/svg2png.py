"""Convert already-captured SVG screenshots to PNG."""
import glob
import io
import os
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from svglib.svglib import svg2rlg
from reportlab.graphics import renderPM

shots = os.path.join(os.path.dirname(os.path.abspath(__file__)), "shots")
for svg_path in sorted(glob.glob(os.path.join(shots, "*.svg"))):
    png_path = svg_path[:-4] + ".png"
    try:
        drawing = svg2rlg(io.BytesIO(open(svg_path, "rb").read()))
        renderPM.drawToFile(drawing, png_path, fmt="PNG", dpi=96,
                            defaultColor=(13, 16, 23))
        print("ok", os.path.basename(png_path), os.path.getsize(png_path))
    except Exception as exc:  # noqa: BLE001
        print("fail", os.path.basename(svg_path), exc)
