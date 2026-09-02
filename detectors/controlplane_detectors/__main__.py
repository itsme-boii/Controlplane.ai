"""Run every detector over one input and print the results as JSON.

    python -m controlplane_detectors "the text to analyse" \
        --source "a grounding document" --source "another"
"""

from __future__ import annotations

import argparse
import asyncio
import json

from controlplane_detectors.base import DetectorContext
from controlplane_detectors.registry import default_detectors


async def _run(text: str, sources: list[str], usecase: str | None, geo: str | None) -> None:
    context = DetectorContext(
        usecase_id=usecase,
        jurisdiction=geo,
        source_documents=sources,
    )
    results = await asyncio.gather(*(d.analyze(text, context) for d in default_detectors()))
    print(json.dumps([r.model_dump(mode="json") for r in results], indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(prog="controlplane_detectors")
    parser.add_argument("text")
    parser.add_argument("--source", action="append", default=[], dest="sources")
    parser.add_argument("--usecase", default=None)
    parser.add_argument("--geo", default=None)
    args = parser.parse_args()
    asyncio.run(_run(args.text, args.sources, args.usecase, args.geo))


if __name__ == "__main__":
    main()
