# Shared SDK

## Purpose

`shared-sdk` contains shared libraries that help product projects consume common contracts and platform services consistently.

Typical contents include:

- service clients
- auth helpers
- tracing helpers
- typed event producers and consumers

## Ownership

Recommended owner:

- platform architecture or core platform team

## Current Scope

This module currently provides the workspace placeholder and boundary definition for:

- shared service clients
- reusable auth and tracing helpers
- typed event producer and consumer utilities
- integration helpers built on stable shared contracts

## Expected Integration Points

- `shared/shared-contracts` for canonical schemas
- `products/` modules that consume common service clients or helpers
- `shared/platform-ops` when deployment or runtime conventions require shared client behavior

## Boundary

This module should support reuse, but should not become a catch-all layer for unrelated platform logic.
