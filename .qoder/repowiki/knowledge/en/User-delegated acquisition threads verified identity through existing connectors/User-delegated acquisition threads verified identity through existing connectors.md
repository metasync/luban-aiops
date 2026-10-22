---
kind: design
name: User-delegated acquisition threads verified identity through existing connectors instead of changing kernel contracts
source: session
category: adr
---

# User-delegated acquisition threads verified identity through existing connectors instead of changing kernel contracts

_Source: coding plans from commit period a96f2ac → 102c0b4 — records intent at planning time; the implementation may lag or differ._

**Status:** accepted

## Context
`BaseTool.execute(parameters, identity)` already receives identity, but HTTP and MCP connectors do not yet carry it into outbound acquisition. The plan must add a new acquisition path without altering tool schemas, risk tiers, signed execution, or kernel contracts.

## Decision drivers
- minimal surface area on existing connectors
- identity threading via existing call chain
- MCP edits limited to adapter identity propagation
- no model/kernel parameter changes

## Considered options
- **Thread gateway-verified identity through existing connector calls and add a dedicated `user_delegated_client.py`** — pros: preserves tool schemas/risk tiers/signature contracts, limits MCP changes to the shipped adapter, keeps machine-grant behavior unchanged
- **Introduce a new transport or kernel identity parameter** _(rejected)_ — pros: clean separation of concerns; cons: breaks existing contracts, expands attack surface, requires changes across tool schemas and kernel boundaries

## Decision
Keep existing machine-grant client behavior unchanged. Thread gateway-verified identity through existing connector calls (`tools/auth_resolution.py`, `tools/http_connector.py`, `ingestion/mcp_adapter.py`) and implement the approved noninteractive acquisition in a separate `tools/user_delegated_client.py`. Do not expose upstream or target tokens to the kernel, model, transcript, or browser.

## Consequences
Two-user/two-target isolation, cache hits/expiry/refresh, concurrency, wrong audience, missing subject/session, expired/revoked grants, and malformed responses must be tested across both HTTP and MCP consumers. Failed acquisition must open no target session and invoke none of the existing Basic/bearer/machine-grant paths.