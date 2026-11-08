"""Convert captured SVG screenshots to PNG using headless Edge (keeps text).

Each conversion uses its own --user-data-dir so parallel/sequential runs never
reuse a stale browser instance.
"""
import glob
import os
import shutil
import subprocess
import sys
import tempfile
import time

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
SHOTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "shots")
W, H = 1848, 1174


def convert(svg_path: str, index: int) -> None:
    png_path = svg_path[:-4] + ".png"
    if os.path.exists(png_path):
        try:
            os.remove(png_path)
        except OSError:
            pass
    profile = os.path.join(tempfile.gettempdir(), f"seaped-shot-{index}-{os.getpid()}")
    shutil.rmtree(profile, ignore_errors=True)
    url = "file:///" + svg_path.replace("\\", "/")
    started = time.time()
    cmd = [
        EDGE, "--headless", "--disable-gpu", "--hide-scrollbars",
        "--no-first-run", "--no-default-browser-check",
        f"--user-data-dir={profile}",
        "--force-device-scale-factor=1",
        f"--window-size={W},{H}",
        f"--screenshot={png_path}", url,
    ]
    try:
        subprocess.run(cmd, timeout=90, capture_output=True)
    except Exception as exc:  # noqa: BLE001
        print("error", os.path.basename(svg_path), exc)
        return
    finally:
        shutil.rmtree(profile, ignore_errors=True)

    fresh = os.path.exists(png_path) and os.path.getmtime(png_path) >= started - 1
    size = os.path.getsize(png_path) if os.path.exists(png_path) else 0
    print(("ok  " if fresh and size > 1000 else "FAIL"),
          os.path.basename(png_path), size)


def main() -> None:
    only = sys.argv[1:] if len(sys.argv) > 1 else None
    files = sorted(glob.glob(os.path.join(SHOTS, "*.svg")))
    if only:
        files = [f for f in files if any(o in f for o in only)]
    for i, svg in enumerate(files, 1):
        convert(svg, i)


if __name__ == "__main__":
    main()
