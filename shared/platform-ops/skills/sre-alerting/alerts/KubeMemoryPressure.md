---
title: KubeMemoryPressure
description: A node reports MemoryPressure — verify real usage against allocatable, find the consumers, and relieve pressure before evictions cascade.
tags: [kubernetes, node, alerting, KubeMemoryPressure, memory]
version: "1.0"
source_url: https://github.com/prometheus-operator/runbooks
---

## Meaning

`KubeMemoryPressure` fires when the kubelet sets the node's
`MemoryPressure` condition to true: available memory has fallen below the
eviction threshold.

## Impact

The kubelet starts evicting best-effort pods first; sustained pressure
leads to scheduling refusals and pod churn across the node's workloads.

## Triage

1. Confirm the condition and the node's allocatable memory:

   ```sh
   kubectl describe node <node> | grep -A6 Conditions
   ```

2. Find the top memory consumers on the node:

   ```sh
   kubectl top pods -A --field-selector spec.nodeName=<node> --sort-by=memory
   ```

3. Compare the sum of pod requests against `Allocatable` — overcommit makes
   pressure inevitable even when current usage looks moderate.

## Remediation

- Immediate relief: move or scale down the largest non-critical consumers.
- Structural fix: raise memory limits/requests accuracy, add node capacity,
  or tune kubelet eviction thresholds for the cluster's workload mix.
- Verify eviction ordering afterwards: best-effort pods should be evicted
  before burstable/guaranteed ones.
