"""Inspect policy resolution from the command line.

python -m controlplane_policy resolve --usecase supportassist --geo eu
python -m controlplane_policy list
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from controlplane_policy import PolicyEngine, PolicyLoadError, PolicyRepo
from controlplane_policy.resolver import PolicyResolutionError

_DEFAULT_DIR = Path(__file__).resolve().parents[2] / "policies"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="controlplane_policy")
    parser.add_argument("--dir", type=Path, default=_DEFAULT_DIR, help="policies/ directory")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("list", help="list available use cases and jurisdictions")

    r = sub.add_parser("resolve", help="resolve and print an effective policy")
    r.add_argument("--usecase", default=None)
    r.add_argument("--geo", default=None)

    args = parser.parse_args(argv)

    try:
        engine = PolicyEngine(PolicyRepo.from_dir(args.dir))
    except PolicyLoadError as exc:
        print(f"policy load error: {exc}", file=sys.stderr)
        return 2

    if args.cmd == "list":
        catalog = {"usecases": engine.usecases, "jurisdictions": engine.jurisdictions}
        print(json.dumps(catalog, indent=2))
        return 0

    try:
        policy = engine.resolve(args.usecase, args.geo)
    except PolicyResolutionError as exc:
        print(f"resolution error: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(policy.model_dump(mode="json"), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
