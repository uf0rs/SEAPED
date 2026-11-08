"""``python -m seaped`` entry point (also used by the packaged executable)."""

import argparse
import sys


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="seaped",
        description="SEAPED — Professional Load Testing Suite "
                    "(run only against systems you own or may test).",
    )
    parser.add_argument("--version", action="store_true", help="print version and exit")
    parser.add_argument(
        "--smoke",
        action="store_true",
        help="run the built-in self test and exit (used to verify a build)",
    )
    parser.add_argument(
        "--lang",
        choices=["ru", "en"],
        default=None,
        help="interface language (overrides the saved preference)",
    )
    parser.add_argument(
        "--agent",
        action="store_true",
        help="run in distributed agent mode (see: seaped --agent --help)",
    )
    return parser


def main(argv=None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    parser = build_parser()
    args, unknown = parser.parse_known_args(argv)

    if args.lang:
        from seaped.i18n import save_setting, set_language

        set_language(args.lang)
        save_setting("lang", args.lang)
    elif not (args.version or args.smoke or args.agent):
        # first launch asks for the language; flags run non-interactive
        from seaped.i18n import ensure_language

        ensure_language(ask=True)
    else:
        from seaped.i18n import ensure_language

        ensure_language(ask=False)

    if args.version:
        from seaped import SUBTITLE, __version__

        print(f"SEAPED {__version__} — {SUBTITLE}")
        return 0

    if args.smoke:
        from seaped.selftest import run_selftest

        return run_selftest()

    if args.agent:
        from seaped.dist.agent import main as agent_main

        return agent_main(unknown)

    from seaped.ui.app import SeapedApp

    SeapedApp().run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
