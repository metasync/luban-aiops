# SPEC-062 Tasks: Secure Password Generation and Delivery Tools

Task states: `[ ]` pending, `[x]` done. Keep tasks small and tied to requirement IDs.

## Stage 1 — Contracts

- [x] R-2: canonical `shared/shared-contracts/policies/password-policy.yaml`
      with one `default` policy; packaged copy synced by `make sync-policy`.
- [x] R-2: `validate_password_policy.py` and `make validate-password-policy` in
      `verify`; reject floor/class drift, missing consumer, malformed input,
      and packaged-copy drift. Regression tests exercise these refusals.
- [x] R-3/R-4: `secret_delivered` audit vocabulary, service mirror, portal filter
      and schema tests; metadata only, no value field.
- [x] R-3: `secret_delivery` stream schema title v12; stable `$id` unchanged.
      Carries `delivery_id`, `channel`, `expires_at`, optional recipient only.
      Kernel-emitted frames validate against the shared schema.
- [x] R-4: `secrets:deliver` grants for platform-admin, approver, operator;
      canonical bundle and all consumer copies agree. Format version stays 1.
      Policy validation and both engines' scenario suites pass.

## Stage 2 — Configuration (deny-by-default)

- [x] R-7: tool-gateway `from_env()` parsing for generation enablement, policy
      path/tightening, buffer backend/TTL/capacity/Redis, SMTP/TLS, recipient
      allowlist and strict mode; defaults disable generation and leave SMTP unset.
- [x] R-2/R-7: startup rejects weakening overrides, unknown classes, invalid
      backend and invalid bounds; runtime policy lookup remains fail-closed.
- [x] R-4/R-7: `AGENT_EMAIL_RECIPIENT_ALLOWLIST` controls park-time card warning;
      gateway strict mode independently controls send-time refusal. Both are
      documented as paired config, not automatically synchronized.
- [x] Configuration default, tightening, named-policy and email-inert tests pass.

## Stage 3 — Buffer + connector + redemption route

- [x] R-3: `SecretDeliveryBuffer` protocol with memory and Redis implementations
      in `tools/secret_delivery.py`; monotonic TTL/capacity for memory, `SET EX`
      and atomic `GETDEL` for Redis. Wrong-owner attempts burn the handle.
      Factory defaults to memory; Redis startup failure records memory fallback.
- [x] R-5: `DeliveryChannel`/`DeliveryOutcome` interface; connector-owned registry
      implements local `PortalCopyChannel` and external `EmailChannel`.
      `register_channel` is the extension seam; portal-copy cannot be replaced
      by an external sender or invoked through the write-tier dispatcher.
- [x] R-1/R-2: read-tier `secrets.generate_password` in `secrets_connector.py`;
      `secrets.choice` generation and `secrets.randbelow` Fisher-Yates shuffle.
      Required-class seeds plus full-alphabet remainder meet conservative entropy:
      `(length - class_count) * log2(full_alphabet_size) + sum(log2(class_size))`.
      Short requests raise to policy minimum; impossible and oversized requests
      refuse with `INVALID_PARAMETERS`. No model-side generation.
- [x] R-2: `PasswordPolicyStore` reads packaged or configured YAML, refreshes on
      mtime change, refuses unreadable/invalid policy without stale fallback,
      and supports additive named policies and tightening-only overrides.
- [x] R-1/R-3: raw `generated_password` survives the gateway exact-key redactor
      for model use; default `handoff="portal_copy"` adds opaque UUID/expiry.
      `handoff="none"` omits the buffer. Verified requester subject is authority;
      forwarded session ID is context only.
- [x] R-4: `ToolDefinition.extra_required_actions` enforced before execution;
      write-tier `secrets.deliver` requires `secrets:deliver` plus `tools:mutate`.
      Email uses mandatory certificate-validated STARTTLS, validated mailbox and
      exact-address/domain allowlisting. Missing SMTP/TLS refuses; strict mode
      rejects outside recipients. Success audits metadata at SMTP acceptance.
- [x] R-3/R-7: gated connector wiring builds one shared buffer; authenticated
      `GET /api/v2/secrets/delivery/{delivery_id}` requires a verified token even
      in dev auth posture, validates UUID, returns no-store value once, and
      emits metadata-only audit. Other attempts share unavailable posture.
- [x] Generation, policy, discovery, both buffer backends, route JWT, email TLS,
      refusal, authorization, audit and extension tests pass. Redis I/O and SMTP
      are replaced under tests; no live email or Redis service is required.

## Stage 4 — Kernel masking, delivery frame and email card

- [x] R-1/R-3: `redact_result_data` and literal masking operate on copies of
      result/evidence/error data; original model and signing arguments stay real.
- [x] R-1/R-3: harvest raw, percent-encoded and quote-plus generated literals;
      mask blocking, streaming and resumed prose, structured output, snapshots
      and legacy transcripts before tool-block removal. Retain knowledge while
      an agent is cached, including compacted contexts. Owner deletion clears
      session caches; turn-local literals still protect an in-flight snapshot.
- [x] R-3: emit validated metadata-only `secret_delivery` alongside tool results;
      persist/replay it independently of result-data truncation.
- [x] R-4: email action card names channel/recipient and masks password without
      changing the signed digest. Outside-list warning requires explicit boolean
      acknowledgment before claim; denial needs no acknowledgment.
- [x] R-3: capture requester token ephemerally across approval resume/re-parking
      for generation only; missing requester token refuses fallback. Approved
      writes retain approver authority. Completed pending objects clear the token.
- [x] Projection, lifecycle, card, authority and vocabulary regressions pass;
      logging/error paths tested with intentional provider echoes stay masked.

## Stage 5 — platform-gateway + operator-portal

- [x] R-3: authenticated, delegated `GET /api/v1/secrets/delivery/{id}` proxy;
      canonical UUID, no redirects/cache, sanitized upstream failures.
- [x] R-4: register `secrets:deliver` in both policy engines; enforce it at
      confirmation admission independently of tier/self-approval restrictions.
- [x] R-3: decode/deduplicate live and replay handles; explicit click fetches
      directly to clipboard without plaintext React state, DOM or storage.
      Persist only tab-local spent markers; expired and unavailable controls
      stay disabled. Missing auth/clipboard prevents redemption.
- [x] R-4: chat and approvals inbox both render the warning acknowledgment and
      relay its strict boolean. Denial remains available without acknowledgment.
- [x] Proxy, decoder, replay, clipboard, card and policy tests pass; full portal
      suite and production TypeScript/Vite build pass. No visual live-browser
      validation or OS clipboard manipulation was performed.

## Stage 6 — Skill, samples, docs, GitOps, e2e

- [x] R-6: `knowledge` skill
      `shared/platform-ops/skills/platform-runbooks/guides/GeneratePassword.md`
      cites the R-2 contract by reference (no divergent numbers), names
      portal-copy vs. email, and forbids restating a generated value.
      Discoverable by `skills.search` (`test_shipped_password_skill_is_discoverable`).
- [x] R-6: both `acme-admin` runbooks gained the generate-and-hand-off branch —
      `ResetAcmePassword.md` (precondition + post-verification step 10) and
      `RecoverAcmeAccount.md` (composition precondition).
- [x] R-7: `GATEWAY_SECRETS_ENABLED=false` + activation block in
      `dev-k8s/base/tool-gateway/runtime-config.env`; email off in base; SMTP
      password provisioned by `sync-email-secrets.sh` (never in the ConfigMap).
      `make overlays` renders `dev-k8s` and all runtime profiles with the new
      keys and email off (verified in `make verify`).
- [x] R-7: `configuration-reference.md` (Feature Activation Matrix rows +
      per-variable defaults/cross-service chain), `tool-configuration.md`
      (Secrets Connector tool table, activation checklist, error codes) and
      `skills-guide.md` (generate-and-deliver request shape) documented.
- [x] R-8: `shared/platform-ops/e2e/secret-delivery-demo.sh` generates, redeems
      via the Copy-password path, asserts the value is absent from every
      projection while `secret_delivered` is present; registered in the `make e2e`
      list and run in local mode by `make verify`. `--live` requires explicit opt-in.
- [x] R-8: mutation spot-checks pass — result/evidence projection bypass
      (`test_result_projection_mutation_is_detected`), dropped literal harvest
      (`test_generated_harvest_mutation_is_detected`) and weakened owner-scope
      check (`test_owner_scope_mutation_is_detected_for_each_backend`) each trip
      an assertion; in-memory monkeypatches only, no production-source edits. The
      live demo heredoc is compiled and executed under mocked network/log I/O
      (`test_live_demo_with_mocked_io`).
- [x] R-8: tool-gateway, agent-platform and platform-gateway suites green; full
      `make verify` green including the new `validate-password-policy` leg and an
      unchanged `validate-secret-vocabulary`. Redis I/O and SMTP are faked under
      tests; no live Redis, email, deployment, browser or OS clipboard was used.

## Acceptance evidence (R-1…R-8)

Requirement → primary tests. All paths relative to the repo root.

- **R-1 raw-for-model / copy-only masking** —
  `products/tool-gateway/tests/test_secrets_connector.py`
  (`test_generation_shares_injected_empty_buffer`,
  `test_invalid_parameters_are_bounded_and_do_not_echo`);
  `products/agent-platform/tests/test_kernel_middleware.py`
  (`test_generation_masks_evidence_but_preserves_model_result`,
  `test_result_projection_mutation_is_detected`).
- **R-2 CSPRNG + policy contract, fail-closed** —
  `test_secrets_connector.py` (`test_csprng_and_tightening`,
  `test_named_policy_and_env_tightening_against_loaded_contract`,
  `test_missing_and_invalid_policy_refuse_without_stale_fallback`,
  `test_validator_rejects_drift_missing_consumers_and_malformed_classes`);
  `make validate-password-policy` leg in `verify`.
- **R-3 one-time portal-copy handoff + no-plaintext projections** —
  `products/tool-gateway/tests/test_secret_delivery.py`
  (`test_both_backends_single_use_ttl_and_owner`,
  `test_owner_scope_mutation_is_detected_for_each_backend`,
  `test_shared_buffer_redeems_once_with_no_store_and_metadata_only_audit`,
  `test_foreign_approver_expiry_and_unknown_have_same_posture`,
  `test_authentication_is_mandatory_even_in_dev_posture`);
  `products/agent-platform/tests/test_prose_redaction.py`
  (`test_generated_literal_registered_mid_turn_and_retained`,
  `test_generated_harvest_mutation_is_detected`,
  `test_generated_literal_masks_snapshot_and_legacy_transcript`,
  `test_generated_literal_masks_confirmation_resume`,
  `test_literal_cache_never_forgets_a_live_compacted_agent`);
  `products/agent-platform/tests/test_secret_delivery_integration.py`
  (`test_generation_projection_and_redeem_roundtrip`,
  `test_live_demo_with_mocked_io`);
  `products/platform-gateway/tests/test_workspace_proxies.py`
  (`SecretRedemptionProxyTests`); portal
  `src/chat/__tests__/TurnGroup.test.tsx`,
  `src/stream/__tests__/decoder.test.ts`,
  `src/stream/__tests__/useChatStream.test.ts`.
- **R-4 external email delivery + approval authority** —
  `test_secrets_connector.py` (`test_email_fail_closed_and_allowlist`,
  `test_email_success_body_and_audit_do_not_leak`, `test_tls_cannot_be_disabled`,
  `test_external_channel_registry_is_the_only_extension_seam`,
  `test_extra_action_denied_before_transport_even_when_mutate_allowed`);
  `products/agent-platform/tests/test_hitl_confirmations.py`
  (`test_email_projection_masks_value_without_changing_arguments`,
  `test_email_warning_checked_before_confirmation_claim`,
  `test_resume_preserves_requester_token_across_repark`);
  `products/agent-platform/tests/test_gateway_tools.py`
  (`test_generation_override_does_not_change_other_tool_authority`);
  `products/platform-gateway/tests/test_chat_confirm.py`
  (`test_delivery_permission_is_independent_of_approval_tier`); portal
  `src/chat/__tests__/ConfirmationCard.test.tsx`,
  `src/views/__tests__/ApprovalsView.test.tsx`.
- **R-5 channel registry is the only extension seam** —
  `test_secrets_connector.py`
  (`test_external_channel_registry_is_the_only_extension_seam`).
- **R-6 skill discoverability + runbook branches** —
  `products/skills-hub/tests/test_scoring.py`
  (`test_shipped_password_skill_is_discoverable`);
  `GeneratePassword.md`, `ResetAcmePassword.md`, `RecoverAcmeAccount.md`.
- **R-7 deny-by-default configuration** —
  `test_secrets_connector.py` (`test_config_defaults_and_validation`);
  `make overlays` render in `verify`; `configuration-reference.md`,
  `tool-configuration.md`, `skills-guide.md`.
- **R-8 e2e + mutation + full gate** —
  `shared/platform-ops/e2e/secret-delivery-demo.sh`;
  `test_secret_delivery_integration.py::test_live_demo_with_mocked_io`;
  the three mutation checks above; full `make verify`.
- **Audit vocabulary (`secret_delivered`, metadata-only)** —
  portal `src/views/audit/__tests__/constants.test.ts`;
  `test_secret_delivery.py` metadata-only audit assertions.

## Delivery Gate

- [x] all acceptance criteria in `spec.md` verified (see Acceptance evidence above)
- [x] living state docs updated (`tool-configuration.md`,
      `configuration-reference.md`, `skills-guide.md`, the `acme-admin` reset
      walkthroughs, `delivery-roadmap.md`, spec index)
- [x] `CHANGELOG.md` 0.41.0 entry added referencing SPEC-062
- [x] spec index in `docs/specs/README.md` row set to `delivered`
- [x] `VERSION` bumped to 0.41.0 (lockstep validated by `make validate-version`)
- [x] spec status set to `delivered` (2026-09-22, v0.41.0)

