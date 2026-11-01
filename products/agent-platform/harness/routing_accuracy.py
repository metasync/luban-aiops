#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SPEC-071 R-3 — offline routing-accuracy measurement harness.

The opt-in ``ModelRouterMiddleware`` ships **default-off**. Any move to
default-on, or to a broader candidate set, is gated on a *measurement* — the
SPEC-066 "measure before building" discipline applied to per-turn routing
quality. This harness produces that measurement over a labeled turn sample:

* routing **accuracy** — did the classifier select the intended candidate?
* the **added per-reply latency** — the wall time of the classification call
  that ``on_reply`` incurs at ``ReplyStartEvent`` before the reply is served;
* the classification call's **token cost** — via a *bounded, measurement-only*
  counter that mirrors SPEC-065's ``agent_llm_tokens_total{provider,model,
  direction}`` label shape. The classification call bypasses
  ``TokenUsageMiddleware`` (it is a direct ``generate_structured_output`` on a
  separate ``ChatModelBase``, not the agent's ``_call_model``), so it is absent
  from the emitted metrics *by design* (SPEC-071 R-2); this counter observes it
  for the report only and never emits, exports, or synthesizes a value.

**Offline and NOT a CI dependency.** The harness lives outside ``tests/`` and is
never named ``test_*.py``, so ``uv run pytest`` (``make test`` / ``make
verify``) does not collect it, and no make target invokes it. A *live* run calls
the real classifier over the real candidates and therefore needs provider
credentials plus the router knob/candidate-map env; ``--self-test`` exercises
the harness mechanics offline against a deterministic stub classifier (no
credentials, no network) so the tooling itself is verifiable in isolation.

Usage (from ``products/agent-platform``)::

    uv run python harness/routing_accuracy.py --self-test          # offline mechanics
    uv run python harness/routing_accuracy.py                      # live measurement
    uv run python harness/routing_accuracy.py --min-accuracy 0.9   # operator gate

Default-on is a **separate operator decision** evidenced by this measurement;
this harness never flips the knob and ships no default change.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Sequence
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[3]
_DEFAULT_SAMPLE = Path(__file__).resolve().parent / "routing_sample.json"
_EVIDENCE_ROOT = ROOT / ".workspaces" / "spec071-evidence"

# SPEC-065 R-1 direction vocabulary, mirrored so the measurement-only counter
# reports the classification cost in the same shape as ``agent_llm_tokens_total``
# (see ``kernel_middleware.TokenUsageMiddleware._record``).
_DIRECTIONS = (
    ("input", "input_tokens"),
    ("output", "output_tokens"),
    ("cache_input", "cache_input_tokens"),
    ("cache_creation", "cache_creation_input_tokens"),
)


class HarnessPrerequisiteError(RuntimeError):
    """The live harness is not configured/credentialed to produce a measurement."""


@dataclass(frozen=True)
class SampleTurn:
    """One labeled turn: the user text and the candidate it *should* route to."""

    id: str
    text: str
    intended: str


@dataclass
class CallRecord:
    """One observed classification call: its wall latency and provider usage."""

    latency_s: float
    usage: Any | None


@dataclass(frozen=True)
class TurnResult:
    id: str
    intended: str
    selected: str | None
    correct: bool
    fail_soft: bool
    latency_ms: float
    input_tokens: int
    output_tokens: int


def _usage_tokens(usage: Any, attr: str) -> int:
    if usage is None:
        return 0
    return int(getattr(usage, attr, 0) or 0)


class ClassificationTokenCounter:
    """Bounded, measurement-only token counter (SPEC-071 R-3).

    Mirrors the ``agent_llm_tokens_total{provider,model,direction}`` label shape
    but accumulates purely in memory for the report. A call whose response
    carries no ``usage`` records nothing — tokens are never synthesized or
    estimated, matching the SPEC-065 discipline.
    """

    def __init__(self) -> None:
        self._totals: dict[tuple[str, str, str], int] = {}
        self.calls_with_usage = 0

    def record(self, provider: str, model: str, usage: Any | None) -> None:
        if usage is None:
            return
        self.calls_with_usage += 1
        for direction, attr in _DIRECTIONS:
            value = _usage_tokens(usage, attr)
            if value:
                key = (provider, model, direction)
                self._totals[key] = self._totals.get(key, 0) + value

    def total(self, direction: str) -> int:
        return sum(v for (_p, _m, d), v in self._totals.items() if d == direction)

    def snapshot(self) -> dict:
        out: dict = {}
        for (provider, model, direction), value in sorted(self._totals.items()):
            out.setdefault(provider, {}).setdefault(model, {})[direction] = value
        return out


class MeasuringClassifier:
    """Measurement-only shim over the router's classifier model.

    Intercepts ``generate_structured_output`` — the sole call ``_route`` makes on
    a ``ChatModelBase`` classifier — records the wall-clock latency and the
    provider ``usage`` into the bounded counter, then delegates **unchanged**. It
    is deliberately not a ``ClassifierModelBase``/``ChatModelBase`` subclass, so
    ``_route``'s ``isinstance`` check still takes the structured-output branch:
    routing behaviour is identical, only observed.
    """

    def __init__(self, inner: Any, counter: ClassificationTokenCounter,
                 provider: str, model: str) -> None:
        self._inner = inner
        self._counter = counter
        self._provider = provider
        self._model = model
        self.calls: list[CallRecord] = []

    async def generate_structured_output(
        self, messages: list, structured_model: Any, **kwargs: Any
    ) -> Any:
        started = time.perf_counter()
        try:
            res = await self._inner.generate_structured_output(
                messages, structured_model, **kwargs
            )
        except Exception:
            # A classifier failure still costs the elapsed time (and any partial
            # provider spend is invisible to us); record latency, no usage.
            self.calls.append(CallRecord(time.perf_counter() - started, None))
            raise
        usage = getattr(res, "usage", None)
        self._counter.record(self._provider, self._model, usage)
        self.calls.append(CallRecord(time.perf_counter() - started, usage))
        return res

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)


def _percentile(values: Sequence[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    rank = (len(ordered) - 1) * (pct / 100.0)
    low = int(rank)
    high = min(low + 1, len(ordered) - 1)
    frac = rank - low
    return ordered[low] * (1.0 - frac) + ordered[high] * frac


@dataclass
class Measurement:
    """Aggregated routing-quality measurement over a labeled sample."""

    turns: list[TurnResult]
    counter: ClassificationTokenCounter
    classifier: tuple[str, str]
    candidates: tuple[str, ...]

    @property
    def total(self) -> int:
        return len(self.turns)

    @property
    def correct(self) -> int:
        return sum(1 for t in self.turns if t.correct)

    @property
    def incorrect(self) -> int:
        return sum(1 for t in self.turns if not t.correct and not t.fail_soft)

    @property
    def fail_soft(self) -> int:
        return sum(1 for t in self.turns if t.fail_soft)

    @property
    def accuracy(self) -> float:
        return self.correct / self.total if self.total else 0.0

    def confusion(self) -> dict:
        matrix: dict = {}
        for t in self.turns:
            row = matrix.setdefault(t.intended, {})
            key = t.selected if t.selected is not None else "<fail-soft>"
            row[key] = row.get(key, 0) + 1
        return matrix

    def summary(self) -> dict:
        lat = [t.latency_ms for t in self.turns]
        n = self.total
        return {
            "sample_size": n,
            "candidates": list(self.candidates),
            "classifier": {"provider": self.classifier[0], "model": self.classifier[1]},
            "accuracy": round(self.accuracy, 4),
            "correct": self.correct,
            "incorrect": self.incorrect,
            "fail_soft": self.fail_soft,
            "added_latency_ms": {
                "mean": round(sum(lat) / len(lat), 2) if lat else 0.0,
                "p50": round(_percentile(lat, 50), 2),
                "p95": round(_percentile(lat, 95), 2),
                "max": round(max(lat), 2) if lat else 0.0,
            },
            "classification_token_cost": {
                "calls_with_usage": self.counter.calls_with_usage,
                "input_tokens_total": self.counter.total("input"),
                "output_tokens_total": self.counter.total("output"),
                "mean_input_tokens_per_turn": round(self.counter.total("input") / n, 2) if n else 0.0,
                "mean_output_tokens_per_turn": round(self.counter.total("output") / n, 2) if n else 0.0,
                "by_label": self.counter.snapshot(),
            },
            "confusion": self.confusion(),
            "turns": [
                {
                    "id": t.id, "intended": t.intended, "selected": t.selected,
                    "correct": t.correct, "fail_soft": t.fail_soft,
                    "latency_ms": round(t.latency_ms, 2),
                    "input_tokens": t.input_tokens, "output_tokens": t.output_tokens,
                }
                for t in self.turns
            ],
        }

    def report(self) -> str:
        s = self.summary()
        lat, tok = s["added_latency_ms"], s["classification_token_cost"]
        lines = [
            "SPEC-071 R-3 routing-accuracy measurement",
            f"  classifier      : {s['classifier']['provider']}/{s['classifier']['model']}",
            f"  candidates      : {', '.join(s['candidates']) or '(none)'}",
            f"  sample size     : {s['sample_size']}",
            f"  accuracy        : {s['accuracy']:.1%}  "
            f"({s['correct']} correct / {s['incorrect']} incorrect / {s['fail_soft']} fail-soft)",
            f"  added latency   : mean {lat['mean']} ms  p50 {lat['p50']}  "
            f"p95 {lat['p95']}  max {lat['max']}",
            f"  classif. tokens : input {tok['input_tokens_total']}  output {tok['output_tokens_total']}  "
            f"(mean/turn in {tok['mean_input_tokens_per_turn']} / out {tok['mean_output_tokens_per_turn']}; "
            f"{tok['calls_with_usage']} calls with usage)",
            "  confusion (intended -> selected):",
        ]
        for intended, row in s["confusion"].items():
            cells = ", ".join(f"{sel}x{n}" for sel, n in sorted(row.items()))
            lines.append(f"    {intended:>10} -> {cells}")
        return "\n".join(lines)


async def measure_routing(
    router: Any, shim: MeasuringClassifier, sample: Sequence[SampleTurn],
    counter: ClassificationTokenCounter, classifier_labels: tuple[str, str],
    candidates: tuple[str, ...],
) -> Measurement:
    """Drive the router's real ``_route`` over the sample and aggregate.

    ``_route`` is the exact classification path ``on_reply`` invokes at
    ``ReplyStartEvent``; calling it directly measures the routing decision (and
    its fail-soft behaviour) without spinning a full agent/stream.
    """
    results: list[TurnResult] = []
    for turn in sample:
        before = len(shim.calls)
        selected = await router._route(turn.text)
        new_calls = shim.calls[before:]
        results.append(TurnResult(
            id=turn.id,
            intended=turn.intended,
            selected=selected,
            correct=(selected is not None and selected == turn.intended),
            fail_soft=(selected is None),
            latency_ms=sum(c.latency_s for c in new_calls) * 1000.0,
            input_tokens=sum(_usage_tokens(c.usage, "input_tokens") for c in new_calls),
            output_tokens=sum(_usage_tokens(c.usage, "output_tokens") for c in new_calls),
        ))
    return Measurement(results, counter, classifier_labels, candidates)


def load_sample(path: Path) -> list[SampleTurn]:
    raw = json.loads(path.read_text())
    if not isinstance(raw, list) or not raw:
        raise HarnessPrerequisiteError(f"sample {path} must be a non-empty JSON array")
    turns: list[SampleTurn] = []
    for i, item in enumerate(raw):
        try:
            turns.append(SampleTurn(str(item["id"]), str(item["text"]), str(item["intended"])))
        except (KeyError, TypeError) as exc:
            raise HarnessPrerequisiteError(
                f"sample {path} item {i} is missing id/text/intended: {exc}"
            ) from exc
    return turns


def build_live_router() -> tuple[Any, MeasuringClassifier, ClassificationTokenCounter,
                                 tuple[str, str], tuple[str, ...]]:
    """Build the *production* router from env settings, wrapped for measurement.

    Reuses ``AgentKernel._build_middlewares(routing_allowed=True)`` so the
    harness measures the exact wiring the platform arms on a default-resolved
    turn — no reimplementation, no drift.
    """
    from agent_service.runtime_kernel import AgentKernel
    from agent_service.services.model_catalog import MODEL_CATALOG
    from agentscope.middleware import ModelRouterMiddleware

    kernel = AgentKernel()  # RuntimeSettings.from_env(); construction is lazy/offline
    settings = kernel.settings
    problems = []
    if not settings.model_router_enabled:
        problems.append("AGENTSCOPE_MODEL_ROUTER_ENABLED is not true")
    if not settings.model_router_candidates:
        problems.append("AGENTSCOPE_MODEL_ROUTER_CANDIDATES is empty/unset")
    if not settings.model_router_model:
        problems.append("AGENTSCOPE_MODEL_ROUTER_MODEL is unset")
    if problems:
        raise HarnessPrerequisiteError(
            "router not configured for a live measurement: " + "; ".join(problems)
            + ". The router ships default-off; set the knob + candidate map + "
            "classifier model (and provider credentials) to measure."
        )
    try:
        middlewares = kernel._build_middlewares(routing_allowed=True)
    except Exception as exc:  # UnknownModelError, credential/provider build errors
        raise HarnessPrerequisiteError(
            f"router build failed (a candidate/classifier model id may be unknown "
            f"or uncredentialed): {exc}"
        ) from exc
    router = next((m for m in middlewares if isinstance(m, ModelRouterMiddleware)), None)
    if router is None:
        raise HarnessPrerequisiteError("router middleware was not built despite being configured")

    # Resolve bounded {provider, model} labels exactly as TokenUsageMiddleware does.
    real_classifier = router.classifier_model
    model_name = getattr(real_classifier, "model", None)
    entry = MODEL_CATALOG.get(model_name) if isinstance(model_name, str) else None
    labels = (str(entry.provider), str(entry.model_name)) if entry is not None else ("unknown", "unknown")

    counter = ClassificationTokenCounter()
    shim = MeasuringClassifier(real_classifier, counter, labels[0], labels[1])
    router.classifier_model = shim
    candidates = tuple(spec.name for spec in settings.model_router_candidates)
    return router, shim, counter, labels, candidates


def _self_test() -> int:
    """Exercise the harness mechanics offline against a deterministic stub.

    Uses the *real* ``ModelRouterMiddleware._route`` (so accuracy, fail-soft on
    exception, and fail-soft on an unknown candidate are all exercised) with a
    stub classifier returning canned decisions/usage. Asserts the aggregation
    math; no credentials, no network.
    """
    from agentscope.middleware import ChatModelCandidate, ModelRouterMiddleware

    _RAISE = object()
    plan: dict[str, Any] = {
        "quick lookup turn": "fast",
        "deep multi-step reasoning turn": "deep",
        "another deep analysis turn": "fast",        # wrong on purpose
        "classifier explodes here": _RAISE,           # fail-soft (exception)
        "picks an unknown candidate": "nonexistent",  # fail-soft (unknown name)
    }
    sample = [
        SampleTurn("t1", "quick lookup turn", "fast"),
        SampleTurn("t2", "deep multi-step reasoning turn", "deep"),
        SampleTurn("t3", "another deep analysis turn", "deep"),
        SampleTurn("t4", "classifier explodes here", "fast"),
        SampleTurn("t5", "picks an unknown candidate", "deep"),
    ]

    class _StubClassifier:
        async def generate_structured_output(self, messages, structured_model, **kwargs):
            last = messages[-1]
            text = last.get_text_content() if hasattr(last, "get_text_content") else last.content
            decision = plan.get(text)
            if decision is _RAISE:
                raise RuntimeError("stub classifier failure")
            usage = SimpleNamespace(input_tokens=10, output_tokens=5, time=0.01,
                                    cache_input_tokens=0, cache_creation_input_tokens=0)
            return SimpleNamespace(content={"choice": decision}, usage=usage)

    router = ModelRouterMiddleware(
        classifier_model=_StubClassifier(),
        candidates=[
            ChatModelCandidate(name="fast", model=object(), description="quick, simple tasks"),
            ChatModelCandidate(name="deep", model=object(), description="complex, multi-step reasoning"),
        ],
    )
    counter = ClassificationTokenCounter()
    shim = MeasuringClassifier(router.classifier_model, counter, "stub", "stub-classifier")
    router.classifier_model = shim

    measurement = asyncio.run(
        measure_routing(router, shim, sample, counter, ("stub", "stub-classifier"), ("fast", "deep"))
    )
    s = measurement.summary()

    failures: list[str] = []

    def check(label: str, got: Any, want: Any) -> None:
        if got != want:
            failures.append(f"{label}: got {got!r}, want {want!r}")

    check("sample_size", s["sample_size"], 5)
    check("correct", s["correct"], 2)              # t1 fast/fast, t2 deep/deep
    check("incorrect", s["incorrect"], 1)          # t3 fast vs intended deep
    check("fail_soft", s["fail_soft"], 2)          # t4 raised, t5 unknown candidate
    check("accuracy", s["accuracy"], 0.4)
    check("classifier_calls", len(shim.calls), 5)  # one observed call per turn
    check("calls_with_usage", s["classification_token_cost"]["calls_with_usage"], 4)  # t4 raised -> no usage
    check("input_tokens_total", s["classification_token_cost"]["input_tokens_total"], 40)   # 4 x 10
    check("output_tokens_total", s["classification_token_cost"]["output_tokens_total"], 20)  # 4 x 5
    check("confusion", s["confusion"], {
        "fast": {"fast": 1, "<fail-soft>": 1},   # t1 correct; t4 raised (intended fast)
        "deep": {"deep": 1, "fast": 1, "<fail-soft>": 1},  # t2 correct; t3 wrong; t5 unknown
    })
    by_id = {t.id: t for t in measurement.turns}
    check("t4_no_tokens", (by_id["t4"].input_tokens, by_id["t4"].output_tokens), (0, 0))
    check("t5_tokens_counted", (by_id["t5"].input_tokens, by_id["t5"].output_tokens), (10, 5))
    check("latency_samples_nonneg", all(t.latency_ms >= 0.0 for t in measurement.turns), True)

    print(measurement.report())
    if failures:
        print("\nSELF-TEST FAILED:", file=sys.stderr)
        for f in failures:
            print(f"  - {f}", file=sys.stderr)
        return 1
    print("\nSELF-TEST PASSED: accuracy, fail-soft, latency and token accounting verified offline.")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="SPEC-071 R-3 offline routing-accuracy measurement harness."
    )
    parser.add_argument("--self-test", action="store_true",
                        help="exercise the harness mechanics offline against a stub classifier")
    parser.add_argument("--sample", type=Path, default=_DEFAULT_SAMPLE,
                        help="labeled turn sample JSON (default: harness/routing_sample.json)")
    parser.add_argument("--min-accuracy", type=float, default=None,
                        help="optional operator gate: exit 1 if measured accuracy is below this fraction")
    parser.add_argument("--evidence-dir", type=Path, default=None,
                        help="override the evidence output dir (default: .workspaces/spec071-evidence/<run_id>)")
    parser.add_argument("--no-evidence", action="store_true",
                        help="report to stdout only; do not write an evidence file")
    args = parser.parse_args(argv)

    if args.self_test:
        return _self_test()

    try:
        sample = load_sample(args.sample)
        router, shim, counter, labels, candidates = build_live_router()
    except HarnessPrerequisiteError as exc:
        print(f"SPEC-071 R-3 harness prerequisite failure: {exc}", file=sys.stderr)
        return 2
    uncovered = sorted({t.intended for t in sample} - set(candidates))
    if uncovered:
        print(
            f"SPEC-071 R-3 harness prerequisite failure: the sample intends candidates "
            f"{uncovered} that are not in the configured candidate map {list(candidates)}. "
            f"Adapt the sample labels or the candidate names so they agree.",
            file=sys.stderr,
        )
        return 2

    measurement = asyncio.run(measure_routing(router, shim, sample, counter, labels, candidates))
    print(measurement.report())

    if not args.no_evidence:
        run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:12]
        out_dir = args.evidence_dir or (_EVIDENCE_ROOT / run_id)
        out_dir.mkdir(parents=True, exist_ok=True)
        evidence = out_dir / "measurement.json"
        payload = {
            "spec": "SPEC-071", "requirement": "R-3", "stage": "routing-accuracy",
            "run_id": run_id, "generated_at": datetime.now(timezone.utc).isoformat(),
            "sample_path": str(args.sample), "measurement": measurement.summary(),
        }
        evidence.write_text(json.dumps(payload, indent=2) + "\n")
        print(f"  evidence        : {evidence}")

    if args.min_accuracy is not None and measurement.accuracy < args.min_accuracy:
        print(
            f"  GATE            : accuracy {measurement.accuracy:.1%} < required "
            f"{args.min_accuracy:.1%} — FAIL",
            file=sys.stderr,
        )
        return 1
    print("  note            : default-on is a SEPARATE operator decision gated on this "
          "measurement; the router ships default-off and this harness never flips it.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
