"""Isolated PAPER-only entry point for FOMO Brain.

Keeps the legacy executable available for diagnostics, while selecting the
validated historical-unknown isolation path on this experimental branch.
No exchange orders or broker credentials are used by this wrapper.
"""
import os
import subprocess
import sys


def main() -> int:
    env = os.environ.copy()
    env["BRAIN_UNKNOWN_ISOLATION"] = "1"
    env["BRAIN_M4_LAB"] = "0"
    env["BRAIN_M4_FRESH_LAB"] = "1"
    env["BRAIN_M4_ISOLATION"] = "1"
    env["BRAIN_QUOTE_GUARD"] = "1"
    # The pinned legacy contracts are supplied by the workflow.
    for name in ("BRAIN_CONTROL_LEGACY_ADDRESS", "BRAIN_PATTERN_LEGACY_ADDRESS"):
        if not env.get(name):
            print(f"PAPER preflight failed: missing {name}", file=sys.stderr)
            return 2
    print("PAPER entrypoint: legacy unknown isolation enabled; quote guard preserved", flush=True)
    return subprocess.call([sys.executable, "fomo_brain.py"], env=env)


if __name__ == "__main__":
    raise SystemExit(main())
