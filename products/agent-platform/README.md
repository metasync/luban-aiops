# Agent Platform

## Purpose

`agent-platform` is the runtime and orchestration kernel for the platform.

It is responsible for:

- AgentScope-based orchestration
- session and conversation state
- event streaming
- agent coordination
- interaction with policy, knowledge, and tool services

## Ownership

Recommended owner:

- agent platform or orchestration team

## Current Scope

This project currently provides the workspace placeholder and boundary definition for:

- AgentScope-based runtime services
- session and conversation state handling
- streaming response and event fan-out paths
- orchestration across identity, policy, knowledge, and tool services

## Expected Integration Points

- `identity-broker` for normalized identity context
- `policy-center` for action and approval decisions
- `skills-hub` for knowledge retrieval inputs
- `tool-gateway` for grounded tool access
- `shared/shared-contracts` and `shared/shared-sdk` for shared interfaces

## Boundary

This project may propose actions and request policy decisions, but it does not directly authorize or execute privileged operations.
