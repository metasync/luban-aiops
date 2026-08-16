---
title: Crash Loops and OOM Kills
description: Interpret container exit codes to separate application crashes from OOM kills, then apply the matching fix.
tags: [kubernetes, pod, troubleshooting, oom, crashloop]
version: "1.0"
source_url: https://kubernetes.io/docs/tasks/debug/debug-application/debug-pods/
---

## Symptoms

The pod's container restarts repeatedly; the pod shows
`CrashLoopBackOff`. Two root-cause families dominate: application crashes
and OOM kills.

## Diagnosis

1. Read the last terminated state for the exit code and reason:

   ```sh
   kubectl get pod <pod> -n <namespace> \
     -o jsonpath='{.status.containerStatuses[0].lastState.terminated}'
   ```

2. Exit code `137` with reason `OOMKilled`: the kernel killed the process
   for exceeding its memory limit. Compare working-set against
   `resources.limits.memory`:

   ```sh
   kubectl top pod <pod> -n <namespace> --containers
   ```

3. Other exit codes (`1`, `2`, `139`): application failure. Capture the
   previous instance's logs before anything else:

   ```sh
   kubectl logs <pod> -n <namespace> --previous
   ```

## Remediation

- OOM: raise the limit with headroom, or fix the leak (heap dump on a
  staging replica). Never remove the limit instead of sizing it.
- Crash on startup: missing config, failing dependency health-check, or a
  migration that already ran — the logs say which.
- After the fix, delete the pod to skip the exponential backoff wait.
