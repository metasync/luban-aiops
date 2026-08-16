---
title: KubePodNotReady
description: A pod has not reached the Ready condition for an extended period — triage container states, readiness probes, and events.
tags: [kubernetes, pod, alerting, KubePodNotReady]
version: "1.0"
source_url: https://github.com/prometheus-operator/runbooks
---

## Meaning

The `KubePodNotReady` alert fires when a pod's `Ready` condition has been
false for longer than the alert threshold (typically 15 minutes). The pod
exists and is scheduled, but it is not serving traffic.

## Impact

Workload capacity is reduced. If the pod belongs to a Deployment or
StatefulSet, the controller may already have started replacements; if it is
a singleton (DaemonSet member, standalone pod), the capability it provides
is degraded.

## Triage

1. Identify the pod and its controller:

   ```sh
   kubectl get pod <pod> -n <namespace> -o wide
   kubectl get pod <pod> -n <namespace> -o jsonpath='{.metadata.ownerReferences[*].kind}'
   ```

2. Read the pod events — scheduling, image pull, and probe failures show up
   here first:

   ```sh
   kubectl describe pod <pod> -n <namespace>
   ```

3. Check container states (`waiting.reason` is usually the root cause:
   `CrashLoopBackOff`, `ImagePullBackOff`, `CreateContainerConfigError`):

   ```sh
   kubectl get pod <pod> -n <namespace> -o jsonpath='{.status.containerStatuses[*].state}'
   ```

4. If the container is running but not ready, inspect the readiness probe:
   wrong port/path, slow startup, or a dependency the container is waiting
   on. Compare `readinessProbe` against the application's actual endpoint.

5. Check recent logs for startup failures:

   ```sh
   kubectl logs <pod> -n <namespace> --previous
   ```

## Remediation

- Fix the underlying cause surfaced by events/logs (image, config, probe).
- For flapping probes, raise `initialDelaySeconds` or switch to a startup
  probe rather than disabling readiness checks.
- If the node is the problem, cordon and drain it, then delete the pod so
  the controller reschedules it.
