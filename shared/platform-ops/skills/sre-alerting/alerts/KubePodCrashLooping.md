---
title: KubePodCrashLooping
description: A container keeps restarting in a crash loop — capture previous-container logs, identify the exit cause, and break the loop.
tags: [kubernetes, pod, alerting, KubePodCrashLooping, CrashLoopBackOff]
version: "1.0"
source_url: https://github.com/prometheus-operator/runbooks
---

## Meaning

`KubePodCrashLooping` fires when a container restarts repeatedly
(`restartCount` climbing with a `CrashLoopBackOff` wait reason). The
application exits shortly after every start.

## Impact

The workload is unavailable or degraded; every restart risks data loss for
non-idempotent startup work.

## Triage

1. Capture the logs of the last crashed container instance **before**
   deleting anything:

   ```sh
   kubectl logs <pod> -n <namespace> --previous
   ```

2. Check the exit code — it narrows the failure class:

   ```sh
   kubectl get pod <pod> -n <namespace> \
     -o jsonpath='{.status.containerStatuses[0].lastState.terminated}'
   ```

   Common codes: `1`/`2` application error, `137` OOM-killed, `139`
   segmentation fault, `143` SIGTERM.

3. Exit code `137`: compare `resources.limits.memory` against the app's
   real footprint; the pod is being OOM-killed.

4. Configuration errors (`CreateContainerConfigError`): missing Secret or
   ConfigMap keys referenced by env/volumes.

## Remediation

- Application error: fix and redeploy; the crash loop is a symptom.
- OOM: raise the memory limit or fix the leak; confirm with `kubectl top`.
- Config error: repair the referenced Secret/ConfigMap, then delete the pod
  to force a fast retry instead of waiting out the backoff.
