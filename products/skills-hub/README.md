# Skills Hub

## Purpose

`skills-hub` manages the lifecycle of Git-based Markdown skills and related knowledge artifacts.

It is responsible for:

- Git-based ingestion
- Markdown validation
- metadata normalization
- indexing and retrieval support
- making team-owned knowledge available to the platform

## Ownership

Recommended owner:

- knowledge platform or operations enablement team

## Current Scope

This project currently provides the workspace placeholder and boundary definition for:

- Git-based skill ingestion paths
- Markdown validation and metadata normalization
- indexing and retrieval service boundaries
- cited runbook and skill support for operator workflows

## Expected Integration Points

- external Git repositories for skill ingestion
- `agent-platform` for retrieval-driven answer enrichment
- `operator-portal` for cited source visibility
- `shared/shared-contracts` for skill metadata and retrieval payloads

## Boundary

This project does not execute tools, authorize actions, or own live session orchestration.
