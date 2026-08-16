---
title: Debug Pods
description: Systematic pod troubleshooting — read the phase, conditions, events, and container states in order before touching anything.
tags: [kubernetes, pod, troubleshooting, debugging]
version: "1.0"
source_url: https://kubernetes.io/docs/tasks/debug/debug-application/debug-pods/
---

## Overview

Work through pod problems in this fixed order; skipping steps is the most
common cause of misdiagnosis.

## Step 1 — the phase and conditions

```sh
kubectl get pod <pod> -n <namespace> -o yaml
```

- `Pending`: scheduling problem (resources, affinity, taints) — check
  events for `FailedScheduling` reasons.
- `Waiting` / `ContainerCreating`: image pull, volume mount, or CNI
  problem.
- `Running` but not `Ready`: probe or dependency problem.
- `CrashLoopBackOff`: the container starts and exits — go to logs.

## Step 2 — events

```sh
kubectl describe pod <pod> -n <namespace>
```

Events are ordered chronologically; the last few usually contain the root
cause (`FailedMount`, `FailedScheduling`, `Unhealthy`, `FailedPullImage`).

## Step 3 — container logs

```sh
kubectl logs <pod> -n <namespace> -c <container>
kubectl logs <pod> -n <namespace> --previous   # after a crash
```

## Step 4 — probe configuration

Compare `livenessProbe` / `readinessProbe` port and path against what the
application actually serves. Probe misconfiguration is the leading cause of
pods that "work but are killed anyway".

## Step 5 — exec only as a last resort

```sh
kubectl exec -it <pod> -n <namespace> -- sh
```

Use exec to confirm a hypothesis formed from steps 1–4, not to explore.
