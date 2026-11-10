"""Declared diagnosis runbook profiles (SPEC-076 phase 5, R-7).

The bounded read-only orchestration loop (``services.orchestration``) is built
**once, runbook-agnostic** (OQ-7). Each of the four operator-named
detect→troubleshoot→propose workflows (memo §8 Q5) is expressed here as a
**declared** :class:`~agent_service.services.orchestration.DiagnosisProfile` —
its trigger, its read-only ``diagnostician`` toolkit families, the ordered
member steps of its fan-out, and the *shape* of the remediation it may propose:

- **(a)** ``servicenow-incident`` — ServiceNow incident → **diagnosis**
  (SPEC-067 read tools + observability + k8s + recent changes); diagnosis-only.
- **(b)** ``observability-alert`` — alert → **correlated diagnosis**
  (metrics/traces/logs/k8s); diagnosis-only.
- **(c)** ``post-deploy-verify`` — post-deploy health verify → **propose
  rollback** (k8s rollout status + error-rate metrics + logs).
- **(d)** ``k8s-pod-degradation`` — pod-degradation triage → **root cause +
  proposed remediation** (pod events + container logs + config/secret diffs +
  node health).

The ``diagnostician`` toolkit is narrowed by risk tier + token ``roles`` alone
(SPEC-073 R-2 ``_narrow_for_role`` → ``_filter_read_only`` keeps ``risk_level ==
"read"`` only) — **not** by runbook family. The per-profile ``read_families``
and the ``diagnostician_read_families`` union are **declarative documentation**
of which read families each runbook intends to exercise: they shape neither the
member prompt (composed from ``step.prompt`` alone) nor the toolkit filter, and
``diagnostician_read_families`` has no production caller. Read-only is enforced
structurally — every member turn rides ``read_only=True``, so a mutating step is
impossible inside the loop (R-1) regardless of family.

A profile whose ``remediation_shape`` is ``None`` is **diagnosis-only**: it can
never be staged by an executor (``stage_remediation`` fails closed), so runbooks
(a) and (b) cannot propose a mutation at all. Runbooks (c) and (d) declare a
remediation *shape*, which an executor may stage onto the existing HITL card
(R-4) — never dispatch autonomously (ADR-0017 Decision 2 defers autonomous
resolve).

The phase-5 trigger is **operator-invoked** (OQ-3): a human operator starts a
diagnosis — optionally anchored on an existing incident record — through
``POST /api/v2/diagnose``. Unattended machine-trigger ingestion (webhook/alert
auto-fire, dedup, storm control) is the named follow-up **``FU-076``**, not
phase-5 scope.

A profile is **pure data** — no agentscope type appears here (SPEC-018 gate
point 4), and nothing in this module binds a role or opens a turn.
"""

from __future__ import annotations

from agent_service.services.orchestration import DiagnosisProfile, MemberStep

# ---------------------------------------------------------------------------
# (a) ServiceNow-incident → diagnosis (spec R-7 (a)). Diagnosis-only: the
# incident workflow produces a correlated root-cause read, not a staged
# mutation, so remediation_shape is None (an executor can never stage it).
# ---------------------------------------------------------------------------
SERVICENOW_INCIDENT = DiagnosisProfile(
    name="servicenow-incident",
    trigger="operator-invoked on a ServiceNow incident record",
    read_families=("servicenow", "observability", "kubernetes", "changes"),
    steps=(
        MemberStep(
            task_id="incident-record",
            prompt=(
                "Read the ServiceNow incident record with its updates, "
                "comments, and linked configuration items (SPEC-067 read "
                "tools). Summarize the reported symptom, the affected service, "
                "and the timeline."
            ),
        ),
        MemberStep(
            task_id="observability-signals",
            prompt=(
                "Read the observability signals — metrics, traces, and logs — "
                "for the affected service around the incident window. "
                "Summarize the anomaly and when it began."
            ),
        ),
        MemberStep(
            task_id="kubernetes-state",
            prompt=(
                "Read the Kubernetes workload state — pods, events, and rollout "
                "status — for the affected service. Summarize any degradation "
                "or restart pattern."
            ),
        ),
        MemberStep(
            task_id="recent-changes",
            prompt=(
                "Read recent changes and deployments that could explain the "
                "incident. Summarize the most likely change-related cause."
            ),
        ),
    ),
    remediation_shape=None,
)

# ---------------------------------------------------------------------------
# (b) observability-alert → correlated diagnosis (spec R-7 (b)). Diagnosis-only.
# ---------------------------------------------------------------------------
OBSERVABILITY_ALERT = DiagnosisProfile(
    name="observability-alert",
    trigger="operator-invoked on an observability alert",
    read_families=("observability", "kubernetes"),
    steps=(
        MemberStep(
            task_id="metric-anomaly",
            prompt=(
                "Read the alerting metric and correlate the anomaly window "
                "against its baseline. Summarize the deviation and its shape."
            ),
        ),
        MemberStep(
            task_id="trace-localization",
            prompt=(
                "Read traces for the affected service to localize the latency "
                "or error to a span, dependency, or code path. Summarize the "
                "hot path."
            ),
        ),
        MemberStep(
            task_id="log-correlation",
            prompt=(
                "Read logs around the anomaly window for new error signatures "
                "or exceptions. Summarize what the logs corroborate."
            ),
        ),
        MemberStep(
            task_id="kubernetes-context",
            prompt=(
                "Read the Kubernetes workload state for the affected service "
                "(pods, events, resource pressure). Summarize any infra-side "
                "contributor."
            ),
        ),
    ),
    remediation_shape=None,
)

# ---------------------------------------------------------------------------
# (c) post-deploy health verify → propose rollback (spec R-7 (c)). Declares a
# remediation shape, so an executor may stage a rollback proposal onto HITL.
# ---------------------------------------------------------------------------
POST_DEPLOY_VERIFY = DiagnosisProfile(
    name="post-deploy-verify",
    trigger="operator-invoked after a deployment",
    read_families=("kubernetes", "observability"),
    steps=(
        MemberStep(
            task_id="rollout-status",
            prompt=(
                "Read the Kubernetes rollout status for the new revision "
                "(replica availability, rollout progress, pod readiness). "
                "Summarize whether the rollout is healthy."
            ),
        ),
        MemberStep(
            task_id="error-rate-delta",
            prompt=(
                "Read error-rate and latency metrics comparing the window "
                "before and after the deploy. Summarize any regression."
            ),
        ),
        MemberStep(
            task_id="new-error-logs",
            prompt=(
                "Read logs for new error signatures that appeared since the "
                "deploy. Summarize whether they implicate the new revision."
            ),
        ),
    ),
    remediation_shape=(
        "roll the deployment back to the last known-good revision"
    ),
)

# ---------------------------------------------------------------------------
# (d) Kubernetes pod-degradation triage → root cause + proposed remediation
# (spec R-7 (d)). Declares a remediation shape (wired end-to-end with (a)).
# ---------------------------------------------------------------------------
K8S_POD_DEGRADATION = DiagnosisProfile(
    name="k8s-pod-degradation",
    trigger="operator-invoked on a degraded Kubernetes pod or workload",
    read_families=("kubernetes", "config", "observability"),
    steps=(
        MemberStep(
            task_id="pod-events",
            prompt=(
                "Read the pod's Kubernetes events and status — restarts, liveness"
                "/readiness probe failures, OOMKilled, back-off. Summarize the "
                "degradation signal."
            ),
        ),
        MemberStep(
            task_id="container-logs",
            prompt=(
                "Read the container logs for the degraded pod (current and "
                "previous terminated container). Summarize the error or crash "
                "signature."
            ),
        ),
        MemberStep(
            task_id="config-secret-diffs",
            prompt=(
                "Read recent config and secret diffs for the workload "
                "(ConfigMap/Secret changes, env drift). Summarize any change "
                "that could explain the degradation."
            ),
        ),
        MemberStep(
            task_id="node-health",
            prompt=(
                "Read the health of the node the pod is scheduled on "
                "(conditions, resource pressure, disk/memory). Summarize any "
                "node-side contributor."
            ),
        ),
    ),
    remediation_shape=(
        "restart or reschedule the degraded pod, or roll back the offending "
        "config change"
    ),
)

# The four declared runbooks, in spec order (a, b, c, d). Pure data — the loop
# is runbook-agnostic and consumes any DiagnosisProfile.
PROFILES: tuple[DiagnosisProfile, ...] = (
    SERVICENOW_INCIDENT,
    OBSERVABILITY_ALERT,
    POST_DEPLOY_VERIFY,
    K8S_POD_DEGRADATION,
)

_BY_NAME: dict[str, DiagnosisProfile] = {p.name: p for p in PROFILES}


def all_profiles() -> tuple[DiagnosisProfile, ...]:
    """Every declared runbook profile, in spec order (a, b, c, d)."""
    return PROFILES


def profile_names() -> tuple[str, ...]:
    """The closed set of valid profile names an operator may invoke."""
    return tuple(_BY_NAME)


def get_profile(name: str) -> DiagnosisProfile | None:
    """Resolve a declared profile by name, or ``None`` if it is not one.

    Fail-closed: the operator-invoked trigger refuses an unknown profile rather
    than defaulting to a wider runbook (the caller maps ``None`` to a 4xx).
    """
    return _BY_NAME.get(name)


def diagnostician_read_families() -> tuple[str, ...]:
    """The **union** of the four runbooks' declared read-tier families (R-7 acceptance).

    Documentation of intent only: this union has **no production caller** and does
    **not** select the ``diagnostician`` toolkit. The live toolkit is narrowed by
    **risk tier + token ``roles``** (SPEC-073 R-2, read-only) in ``runtime_kernel``,
    independent of runbook family, so adding a runbook does not by itself widen any
    member's tools. Kept as a data-integrity check that the declared families cover
    the spec runbooks (memo §8 Q5); the split is derived from the real runbooks,
    never hardcoded separately.
    """
    union: set[str] = set()
    for profile in PROFILES:
        union.update(profile.read_families)
    return tuple(sorted(union))
