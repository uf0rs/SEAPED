"""SEAPED launcher (development mode and PyInstaller entry point).

Run with:  python run.py            (application)
           python run.py --smoke    (built-in self test)
           python run.py --version
Build:     python build_exe.py      -> dist\\SEAPED.exe
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    from seaped.__main__ import main as seaped_main

    return seaped_main(sys.argv[1:])


if __name__ == "__main__":
    raise SystemExit(_main())
