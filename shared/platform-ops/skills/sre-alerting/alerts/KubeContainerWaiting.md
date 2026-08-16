---
title: KubeContainerWaiting
description: A container is scheduled but waiting to start — diagnose image pulls, config errors, and resource starvation from the wait reason.
tags: [kubernetes, pod, alerting, KubeContainerWaiting]
version: "1.0"
source_url: https://github.com/prometheus-operator/runbooks
---

## Meaning

`KubeContainerWaiting` fires when a container stays in a `waiting` state —
it is scheduled onto a node but cannot start. The `waiting.reason` field is
the primary diagnostic signal.

## Impact

The pod contributes no capacity. Long waits compound: dependent services
time out and user-facing errors rise.

## Triage

1. Read the wait reason directly:

   ```sh
   kubectl get pod <pod> -n <namespace> \
     -o jsonpath='{.status.containerStatuses[*].state.waiting}'
   ```

2. Interpret the reason:
   - `ImagePullBackOff` / `ErrImagePull`: bad tag, registry auth, or
     network. Verify the image reference and registry credentials.
   - `CreateContainerConfigError`: a referenced Secret or ConfigMap (or a
     key inside it) does not exist.
   - `ContainerCreating` stuck: usually a volume or CNI problem — check
     node events and the CSI driver.
   - `RunContainerError`: runtime-level failure; check `kubectl describe`
     events and the node's container runtime logs.

3. Check node-level events when the pod events are silent:

   ```sh
   kubectl get events -n <namespace> --field-selector involvedObject.name=<pod>
   ```

## Remediation

- Fix the named resource (image tag, Secret, ConfigMap) and delete the pod
  to retry immediately.
- For registry problems, test the pull from the node's network path, not
  from a workstation.
