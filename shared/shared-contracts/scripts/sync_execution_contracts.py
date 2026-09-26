"""Package canonical execution contracts in independent product distributions.

Use --write during development; the default check never repairs drift. Runtime
loads only packaged local resources and cannot fetch a schema over the network.
"""
from __future__ import annotations

import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SCHEMAS = ("execution-request", "execution-receipt", "execution-observation",
           "execution-recovery", "execution-handoff-response", "tool-result")
PRODUCTS = {"execution-runtime": "execution_runtime", "agent-platform": "agent_service"}


def sync(*, write=False):
    mismatches = []
    for product, package in PRODUCTS.items():
        destination = ROOT / "products" / product / "src" / package / "contracts"
        sources = [ROOT / "shared/shared-contracts/schemas" / f"{name}.schema.json" for name in SCHEMAS]
        sources.append(ROOT / "shared/shared-contracts/sql/execution-ledger-v1.sql")
        for source in sources:
            target = destination / source.name
            content = source.read_bytes()
            if target.is_file() and target.read_bytes() == content:
                continue
            mismatches.append(str(target.relative_to(ROOT)))
            if write:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(content)
    return mismatches


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    changed = sync(write=args.write)
    if changed:
        print(("Synchronized" if args.write else "Contract drift:") + "\n" + "\n".join(changed))
    raise SystemExit(0 if args.write or not changed else 1)
