---
title: KubeNodeNotReady
description: A node has left the Ready condition — check kubelet health, node conditions, and safely reschedule workloads.
tags: [kubernetes, node, alerting, KubeNodeNotReady]
version: "1.0"
source_url: https://github.com/prometheus-operator/runbooks
---

## Meaning

`KubeNodeNotReady` fires when a node's `Ready` condition is not true for an
extended period. The kubelet is unresponsive or the node reports pressure.

## Impact

Pods on the node are not managed; after the pod-eviction timeout
(~5 minutes by default) the scheduler starts replacements elsewhere. The
cluster loses one machine's worth of capacity.

## Triage

1. Read the node conditions — they name the pressure type:

   ```sh
   kubectl describe node <node>
   ```

   Look for `MemoryPressure`, `DiskPressure`, `PIDPressure`,
   `NetworkUnavailable`.

2. Check kubelet status on the node (or its systemd/journal logs if it is
   reachable):

   ```sh
   kubectl get node <node> -o jsonpath='{.status.conditions[?(@.type=="Ready")]}'
   ```

3. Check node events for container-runtime and network failures:

   ```sh
   kubectl get events --field-selector involvedObject.name=<node> -A
   ```

4. List pods stuck on the node — they stay `Terminating` while the kubelet
   is down:

   ```sh
   kubectl get pods -A --field-selector spec.nodeName=<node>
   ```

## Remediation

- Recoverable node: fix the kubelet/runtime (restart services, free disk),
  and the node re-joins on its own.
- Dead node: `kubectl cordon <node>`, then `kubectl drain` (with
  `--ignore-daemonsets`), and delete the node object if the machine is
  gone.
- Do not force-delete stateful pods with local storage until data impact
  is understood.
