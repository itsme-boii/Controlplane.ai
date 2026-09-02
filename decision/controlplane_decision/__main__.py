"""Turn detector output into a decision from the command line.

Pipe the detector CLI straight in:

    python -m controlplane_detectors "the answer" --source "a source doc" \
        | python -m controlplane_decision --usecase knowledgecopilot --geo eu

``--response-text`` (the exact text the detectors analysed) enables the redaction
preview for an ``edit`` decision.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from controlplane_detectors import DetectionResult
from controlplane_policy import PolicyEngine, PolicyLoadError, PolicyRepo
from controlplane_policy.resolver import PolicyResolutionError

from controlplane_decision import DecisionEngine

_DEFAULT_DIR = Path(__file__).resolve().parents[2] / "policies"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="controlplane_decision")
    parser.add_argument("--dir", type=Path, default=_DEFAULT_DIR, help="policies/ directory")
    parser.add_argument("--usecase", default=None)
    parser.add_argument("--geo", default=None)
    parser.add_argument(
        "--response-text",
        default="",
        help="the text the detectors analysed; enables the edit-tier redaction preview",
    )
    args = parser.parse_args(argv)

    raw = sys.stdin.read()
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(f"stdin is not the detector JSON output: {exc}", file=sys.stderr)
        return 2
    results = [DetectionResult.model_validate(item) for item in payload]

    try:
        engine = PolicyEngine(PolicyRepo.from_dir(args.dir))
        policy = engine.resolve(args.usecase, args.geo)
    except (PolicyLoadError, PolicyResolutionError) as exc:
        print(f"policy error: {exc}", file=sys.stderr)
        return 1

    decision = DecisionEngine().decide(args.response_text, results, policy)
    print(json.dumps(decision.model_dump(mode="json"), indent=2))
    return 0 if not decision.fail_safe_triggered else 3


if __name__ == "__main__":
    raise SystemExit(main())
