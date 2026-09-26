"""Failure-proof entry point. Development harness runs are never delivery passes."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
from uuid import UUID, uuid4

from support.infrastructure import ROOT, DisposablePostgres, PrerequisiteError, prerequisites


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", choices=("campaign", "harness", "baseline-red", "development"), default="campaign")
    parser.add_argument("--select", help="development-only pytest expression; never a delivery gate")
    parser.add_argument("--cleanup-owner", type=UUID,
                        help="clean one known stranded local harness owner; all resource labels are verified")
    args = parser.parse_args()
    if args.cleanup_owner and (args.stage != "development" or args.select):
        parser.error("stranded cleanup requires development stage and no selected tests")
    if args.select and args.stage != "development":
        parser.error("selection is only allowed for non-delivery development runs")
    os.umask(0o077)
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:12]
    output = ROOT / ".workspaces/spec063-evidence" / run_id
    output.mkdir(parents=True)
    print(f"SPEC-063 {args.stage}; evidence: {output}", flush=True)
    try:
        versions = prerequisites()
    except PrerequisiteError as exc:
        (output / "prerequisites.json").write_text(json.dumps({"status": "blocked", "reason": str(exc)}))
        print(f"Prerequisite failure: {exc}", flush=True)
        return 2
    (output / "prerequisites.json").write_text(json.dumps(versions, indent=2) + "\n")
    if args.cleanup_owner:
        database = DisposablePostgres()
        database.owner = args.cleanup_owner.hex
        database.project = "spec063-" + database.owner
        database.env["SPEC063_OWNER"] = database.owner
        database.started = True
        database.close()
        (output / "cleanup.json").write_text(json.dumps({"project": database.project,
            "ownership_verified": True, "delivery_complete": False}) + "\n")
        print("Owned disposable resources cleaned; this is not a test pass", flush=True)
        return 0
    os.environ.update(OTEL_TRACES_EXPORTER="none", OTEL_METRICS_EXPORTER="none",
                      OTEL_LOGS_EXPORTER="none")
    import pytest

    status = pytest.main([str(Path(__file__).parent), "--proof-stage", args.stage,
                          "--proof-evidence", str(output / "evidence.json"),
                          "--junitxml", str(output / "junit.xml"),
                          "--basetemp", str(output / "scratch"), "--tb=short", "-q",
                          *(["-k", args.select] if args.select else [])])
    print(f"SPEC-063 {args.stage}: exit {status}; no live acceptance performed", flush=True)
    return int(status)


if __name__ == "__main__":
    raise SystemExit(main())
