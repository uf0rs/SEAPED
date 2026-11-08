"""Launch probe: start the packaged exe, let it render, then terminate it."""
import os
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXE = os.path.join(ROOT, "dist", "SEAPED.exe")


def main() -> int:
    print("probing:", EXE, "exists:", os.path.exists(EXE))
    p = subprocess.Popen(
        [EXE],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        stdin=subprocess.DEVNULL,
    )
    time.sleep(12)
    alive = p.poll() is None
    print("still running after 12s (TUI up):", alive)
    if not alive:
        err = p.stderr.read().decode("utf-8", "replace") if p.stderr else ""
        print("exited early, code:", p.returncode)
        print(err[:3000])
        return 1
    p.kill()
    try:
        p.wait(timeout=10)
    except subprocess.TimeoutExpired:
        print("warning: process did not terminate within 10s")
        return 1
    # PyInstaller onefile may leave a child process behind
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(p.pid), "/T", "/F"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run(["taskkill", "/IM", "SEAPED.exe", "/F"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print("terminated cleanly, code:", p.returncode)
    print("probe OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
