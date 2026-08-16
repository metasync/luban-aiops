---
title: KubeDeploymentReplicasMismatch
description: A Deployment has fewer ready replicas than desired for an extended period — find which pods are missing or stuck and why.
tags: [kubernetes, deployment, alerting, KubeDeploymentReplicasMismatch]
version: "1.0"
source_url: https://github.com/prometheus-operator/runbooks
---

## Meaning

`KubeDeploymentReplicasMismatch` fires when a Deployment's ready replica
count stays below `spec.replicas` (typically for 15 minutes). New pods are
failing to come up or existing pods keep dying.

## Impact

The workload runs under capacity; sustained mismatches usually indicate a
systemic problem (bad release, exhausted resources) rather than a transient
one.

## Triage

1. Compare desired, current, and ready counts:

   ```sh
   kubectl get deployment <name> -n <namespace>
   ```

2. Find the pods that are missing or not ready:

   ```sh
   kubectl get pods -n <namespace> -l app=<label> -o wide
   ```

3. The root cause lives in the failing pods — follow the pod-level
   runbooks: `KubePodNotReady` for stuck pods, `KubePodCrashLooping` for
   restarting containers, `KubeContainerWaiting` for pods that never start.

4. If no pods were created at all, check the Deployment and ReplicaSet
   events for scheduler or quota failures:

   ```sh
   kubectl describe deployment <name> -n <namespace>
   ```

## Remediation

- Bad release: roll back (`kubectl rollout undo deployment/<name>`) and fix
  forward.
- Resource starvation: free node capacity or lower requests, then delete
  the pending pods.
- Quota exceeded: adjust the ResourceQuota or the replica count.
