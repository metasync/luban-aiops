---
title: Generate a Password and Deliver It Securely
description: Generate a password for a reset or account recovery using the platform CSPRNG tool, then hand it to the requester through one-time portal copy or explicitly requested, approved email delivery.
tags: [password, generate, secret, delivery, reset, account-recovery, portal-copy, email]
version: "1.0"
kind: knowledge
---

## Policy

The authoritative strength rules are in
`shared/shared-contracts/policies/password-policy.yaml`, policy `default`.
The tool reads that contract; deployment and caller overrides may only tighten
it. Do not invent a password, duplicate the policy's numbers here, or claim
that a model-generated string meets the policy.

## Choose the value

- If the operator supplies a temporary password, use that value for the requested
  operation. Do not silently replace it or restate it in the response.
- If none is supplied for a requested reset, or the operator asks for a strong
  generated password, call `secrets.generate_password(policy="default",
  handoff="portal_copy")`. This is read tier and parks no card. Optional `length`
  and `exclude_ambiguous=true` may tighten the policy.
- If the tool is unavailable or refuses the request, stop and explain that secure
  generation is unavailable. Ask for feature activation or a caller-supplied
  temporary value; never fall back to model-side randomness.

## Use and hand over

1. Keep `generated_password` only in working context. Pass the exact raw value to
   the reset's secret-bearing argument. For the ACME sample's `newpw` URL, percent
   encode the value as one query-parameter value so symbols cannot alter the URL.
2. Follow the reset skill's own approval and verification. Generation grants no
   authority to mutate an account. A Copy-password control proves only that a
   password was generated, not that a reset succeeded.
3. Tell the requester to use **Copy password** in the originating session.
   Never redeem the handle on their behalf, restate the password in prose, put it
   in a title/card, or paste it into a document. Copy is authenticated, single-use
   and expires; the approver cannot copy a requester's password.
4. An expired or spent handle cannot be recovered from history. Do not generate a
   replacement and claim it is the account's current password. A new reset needs
   its own approval and verification. A process restart or model rebuild can also
   remove the raw working value; stop if only a masked placeholder remains.

## Optional email

Only when the operator explicitly asks to email the value to a named recipient,
call `secrets.deliver(channel="email", password=<working value>, recipient=<address>)`.
Email is a separate write-tier action requiring `tools:mutate`, `secrets:deliver`
and its own approval; a browser-flow approval does not authorize this send.
Outside the approved recipient list, the approver must acknowledge a warning.
Strict allowlist mode refuses that recipient outright. Unconfigured SMTP fails
closed. Do not retry around a denial or send to a different address automatically.

For email-only generation, `handoff="none"` avoids creating a Copy control; use
it only when the requested external handoff is explicit. `portal_copy` is not a
channel accepted by `secrets.deliver`.
