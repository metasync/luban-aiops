---
kind: external_dependency
name: Redis Session Store
slug: redis
category: external_dependency
category_hints:
    - vendor_identity
    - client_constraint
scope:
    - '**'
source_files:
    - shared/platform-ops/gitops/dev-k8s/base/infra/redis-deployment.yaml
---

Redis 7.2 serves as the session store and message bus for the agent-platform, providing durable session state and inter-service communication. The deployment uses Redis with append-only mode disabled for development, mounted with an emptyDir volume for ephemeral storage. All Python services depend on the redis>=6.2,<7.0 client library for session persistence and caching operations.