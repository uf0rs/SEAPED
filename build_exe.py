"""Build the SEAPED Windows executable with PyInstaller.

Usage:
    python build_exe.py            # -> dist\\SEAPED.exe
    python build_exe.py --onefile  # default: single file
    python build_exe.py --onedir   # faster start, folder next to the exe
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def main() -> int:
    parser = argparse.ArgumentParser(description="Build SEAPED.exe")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--onefile", action="store_true", default=True,
                       help="single executable (default)")
    group.add_argument("--onedir", action="store_true",
                       help="folder distribution (faster startup)")
    args = parser.parse_args()

    try:
        import PyInstaller.__main__
    except ImportError:
        print("PyInstaller is required:  pip install pyinstaller")
        return 1

    mode = "--onedir" if args.onedir else "--onefile"
    argv = [
        str(ROOT / "run.py"),
        "--name=SEAPED",
        mode,
        "--console",
        "--clean",
        "--noconfirm",
        "--collect-data=textual",
        "--collect-submodules=textual",
        "--distpath", str(ROOT / "dist"),
        "--workpath", str(ROOT / "build"),
        "--specpath", str(ROOT / "build"),
    ]

    print("Running PyInstaller:", " ".join(argv))
    PyInstaller.__main__.run(argv)

    out = ROOT / "dist" / ("SEAPED" if args.onedir else "SEAPED.exe")
    print("\nBuild finished:", out)
    if out.exists():
        try:
            size = out.stat().st_size / (1024 * 1024)
            print(f"Size: {size:.1f} MB")
        except OSError:
            pass
        print("\nVerify the build with:  dist\\SEAPED.exe --smoke")
    return 0


if __name__ == "__main__":
    sys.exit(main())
