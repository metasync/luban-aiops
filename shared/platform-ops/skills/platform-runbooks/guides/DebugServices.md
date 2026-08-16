---
title: Debug Services
description: Debug a Kubernetes Service end to end — endpoints, selector match, DNS resolution, and kube-proxy reachability.
tags: [kubernetes, service, troubleshooting, dns, networking]
version: "1.0"
source_url: https://kubernetes.io/docs/tasks/debug/debug-application/debug-service/
---

## Overview

"Service unreachable" has exactly four candidate layers; test them in
order and stop at the first failure.

## Step 1 — does the Service exist with the right spec?

```sh
kubectl get svc <service> -n <namespace> -o yaml
```

Verify `spec.ports` (port/targetPort) and `spec.selector`.

## Step 2 — are there endpoints?

```sh
kubectl get endpoints <service> -n <namespace>
```

Empty endpoints means the selector matches zero ready pods. Cross-check:

```sh
kubectl get pods -n <namespace> -l <selector-key>=<selector-value>
```

Selector drift after a label change is the classic cause.

## Step 3 — DNS

From a pod in the cluster:

```sh
kubectl exec -it <probe-pod> -- nslookup <service>.<namespace>.svc.cluster.local
```

Failure here points at CoreDNS, not the Service.

## Step 4 — direct reachability

Test the ClusterIP and a pod IP directly to separate kube-proxy from
application problems:

```sh
kubectl exec -it <probe-pod> -- wget -qO- http://<pod-ip>:<targetPort>/healthz
```

## Remediation

- Selector mismatch: align the Service selector with pod labels.
- No ready pods: fix the pods (see the Debug Pods guide), not the Service.
- DNS failures: check CoreDNS pod health and its own endpoint.
