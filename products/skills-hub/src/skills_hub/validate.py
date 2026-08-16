"""Standalone skill-source validator (SPEC-014 R-2).

Same code path the service uses at sync time, importable as a pre-flight for
team repositories:

    python -m skills_hub.validate <directory> [--source-id <id>]

Exit code 0 means every document in the directory passes the skill contract;
otherwise each rejection is printed as ``<path>: <reason>`` and the exit code
is 1.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

from skills_hub.services.ingestion import ingest_directory


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m skills_hub.validate",
        description="Validate a skill source directory against the skill contract.",
    )
    parser.add_argument("directory", help="skill source directory to validate")
    parser.add_argument(
        "--source-id",
        default="local-check",
        help="source_id to validate against (default: local-check)",
    )
    args = parser.parse_args(argv)

    root = Path(args.directory)
    result = ingest_directory(
        args.source_id, root, "local", datetime.now(timezone.utc)
    )
    for rejection in result.rejections:
        print(f"{rejection.path}: {rejection.reason}", file=sys.stderr)
    print(f"accepted: {len(result.records)}  rejected: {len(result.rejections)}")
    return 1 if result.rejections else 0


if __name__ == "__main__":
    raise SystemExit(main())
