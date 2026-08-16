---
title: Image Pull Failures
description: Diagnose ErrImagePull and ImagePullBackOff — verify the reference, registry authentication, and the node's network path.
tags: [kubernetes, pod, troubleshooting, image]
version: "1.0"
source_url: https://kubernetes.io/docs/tasks/debug/debug-application/debug-pods/
---

## Symptoms

The pod stays in `Waiting` with reason `ErrImagePull` or
`ImagePullBackOff`; events name the failing image.

## Diagnosis

1. Read the exact image reference and the pull error message:

   ```sh
   kubectl describe pod <pod> -n <namespace> | grep -A4 Events
   ```

2. `manifest unknown` / `not found`: the tag does not exist. Check for a
   typo, a deleted tag, or a digest that never reached this registry.

3. `unauthorized` / `pull access denied`: the namespace lacks an
   `imagePullSecret`, or the secret's credentials expired:

   ```sh
   kubectl get sa <serviceaccount> -n <namespace> -o jsonpath='{.imagePullSecrets}'
   ```

4. Timeout / connection errors: the node cannot reach the registry —
   proxy settings, firewall egress rules, or registry outage.

## Remediation

- Fix the tag or secret, then delete the pod so the controller retries
  immediately instead of waiting out the backoff.
- For private registries, recreate the `imagePullSecret` from a working
  `docker login` and re-attach it to the ServiceAccount.
- Pin by digest for critical workloads to make "tag deleted" failures
  impossible.
