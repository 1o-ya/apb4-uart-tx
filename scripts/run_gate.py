"""Convenience entrypoint for an individual gate with a fresh evidence directory."""
from __future__ import annotations
import argparse
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("gate", choices=("formal", "mutations", "unit"))
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    stamp = datetime.now(ZoneInfo("Asia/Tokyo")).strftime("%Y%m%dT%H%M%S%f")
    out = root / "reports/runs" / f"{args.gate}-{stamp}"
    out.parent.mkdir(parents=True, exist_ok=True)
    script = {"formal": "formal_check.py", "mutations": "mutation_check.py", "unit": "unit_check.py"}[args.gate]
    result = subprocess.run([sys.executable, str(root / "scripts" / script),
                             "--out", str(out)], cwd=root, check=False)
    raise SystemExit(result.returncode)


if __name__ == "__main__":
    main()
