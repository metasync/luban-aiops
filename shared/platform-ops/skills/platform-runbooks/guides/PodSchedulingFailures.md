---
title: Pod Scheduling Failures
description: Decode FailedScheduling events — insufficient CPU/memory, unsatisfiable affinity, and taints without tolerations.
tags: [kubernetes, pod, troubleshooting, scheduling]
version: "1.0"
source_url: https://kubernetes.io/docs/tasks/debug/debug-application/debug-pods/
---

## Symptoms

The pod stays `Pending`; events contain `FailedScheduling` with a message
like `0/3 nodes are available: 3 Insufficient memory`.

## Diagnosis

1. Read the full scheduling failure message — it enumerates every node and
   why it was rejected:

   ```sh
   kubectl describe pod <pod> -n <namespace> | grep -A8 Events
   ```

2. Interpret the reasons:
   - `Insufficient cpu` / `Insufficient memory`: requests exceed the
     nodes' allocatable minus committed sums.
   - `node(s) had untolerated taint`: taints present without matching
     tolerations.
   - `node(s) didn't match Pod's node affinity/selector`: label mismatch.
   - `node(s) had volume node affinity conflict`: the bound PV pins the
     pod to a specific zone or node.

3. Check real headroom:

   ```sh
   kubectl describe nodes | grep -A6 "Allocated resources"
   ```

## Remediation

- Right-size requests (many workloads request far more than they use).
- For taints, decide whether the workload should tolerate them — do not
  remove node taints to force scheduling.
- For affinity dead-ends, relax the requirement to `preferredDuringScheduling`
  where hard exclusivity is not actually required.
