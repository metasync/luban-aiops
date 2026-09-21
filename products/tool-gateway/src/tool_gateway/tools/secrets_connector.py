"""Secrets connector: secure password generation and one-time delivery.

SPEC-062. Two tools over one connector:

  read tier   secrets.generate_password   CSPRNG generation to policy; optionally
                                          stashes the value for the portal Copy
                                          handoff and returns an opaque
                                          ``delivery_id`` (never the value in a
                                          frame).
  write tier  secrets.deliver             the single dispatcher for channels that
                                          send a secret *outside* the session
                                          (``email`` now; Teams/Slack additive).
                                          Requires ``secrets:deliver`` in addition
                                          to ``tools:mutate`` (extra_required_actions).

The generated value is a secret from the moment it exists. It is real only in
bounded, intentional places — this process transiently, the kernel's working
context (via the ``generated_password`` result field, which survives the gateway's
exact-key ``redact_result`` gate so the agent can pass it to a reset or a
delivery), the delivery buffer for exactly one authenticated redemption, and the
approved TLS SMTP transport for an email send — and masked or absent everywhere
else. Every projection this connector controls keeps it out: the email channel
never logs it, and the ``secret_delivered`` audit event carries only the delivery
metadata (channel, recipient, delivery_id), never the value.

Portal-copy is folded into generation (user-decided at plan time): the gateway
derives required actions from a tool's single static ``risk_level``, so one tool
cannot be read-tier for a local handoff and write-tier for an external send. The
local handoff therefore rides read-tier generation; the write tier gates only the
external ``secrets.deliver`` dispatcher. Both go through one ``DeliveryChannel``
seam (R-5).
"""

from __future__ import annotations

import asyncio
import logging
import smtplib
import ssl
import re
import time
from uuid import uuid4
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage

from tool_gateway.tools.base import (
    BaseTool,
    ToolDefinition,
    ToolResult,
    build_evidence,
    make_error_result,
)
from tool_gateway.tools.password_policy import (
    MAX_PASSWORD_LENGTH,
    PasswordPolicyError,
    PasswordPolicyStore,
    apply_overrides,
    generate_password,
    reconcile_length,
)
from tool_gateway.tools.registry import ToolRegistry
from tool_gateway.tools.secret_delivery import (
    DeliveryChannel,
    DeliveryOutcome,
    InMemorySecretDeliveryBuffer,
    SecretDeliveryBuffer,
)

LOGGER = logging.getLogger(__name__)

SOURCE_SYSTEM = "secrets"
CATEGORY = "secrets"

# The channel vocabulary ``secrets.deliver`` accepts. ``portal_copy`` is not
# here: it is the intrinsic *local* handoff owned by generation, not an external
# send. Adding Teams/Slack is a new channel class plus a registry entry.
EXTERNAL_CHANNELS = ("email",)

# Emitted to the audit sink when a generated secret reaches a human. The value
# is never a field.
SecretDeliveredSink = Callable[[dict, dict], None]


def valid_email_address(value: object) -> bool:
    """Accept one ASCII mailbox, never a display name, list, or header."""
    return isinstance(value, str) and len(value) <= 254 and re.fullmatch(
        r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?", value
    ) is not None and ".." not in value


def _iso_expiry(ttl_seconds: int) -> str:
    return (
        datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)
    ).isoformat()


def _refusal(
    tool_name: str,
    status: str,
    code: str,
    message: str,
    risk_level: str,
    duration_ms: int,
) -> ToolResult:
    """A structured ``denied``/``error`` envelope carrying the evidence."""
    return ToolResult(
        tool_name=tool_name,
        status=status,
        evidence=build_evidence(risk_level, SOURCE_SYSTEM, duration_ms),
        error={"code": code, "message": message},
    )


# ---------------------------------------------------------------------------
# Delivery channels (R-5)
# ---------------------------------------------------------------------------


class PortalCopyChannel:
    """The local handoff: stash the value for one authenticated redemption.

    Invoked from generation. It never emits ``secret_delivered`` — that fires at
    redemption (``api/routes/secrets.py``), when the value actually reaches the
    operator, not when a handle is minted.
    """

    name = "portal_copy"

    def __init__(
        self, buffer: SecretDeliveryBuffer, ttl_seconds: int
    ) -> None:
        self._buffer = buffer
        self._ttl_seconds = int(ttl_seconds)

    async def send(
        self, value: str, recipient: str | None, context: dict
    ) -> DeliveryOutcome:
        if not context.get("sub"):
            return DeliveryOutcome(channel=self.name, delivered=False, error_code="INVALID_PARAMETERS")
        delivery_id = self._buffer.stash(
            value=value,
            owner_sub=str(context.get("sub") or ""),
            session_id=context.get("session_id"),
            ttl_seconds=self._ttl_seconds,
        )
        return DeliveryOutcome(
            channel=self.name,
            delivered=True,
            recipient=None,
            delivery_id=delivery_id,
            expires_at=_iso_expiry(self._ttl_seconds),
        )


class EmailChannel:
    """The external email sender (R-4), gated and fail-closed.

    Unconfigured SMTP → ``EMAIL_NOT_CONFIGURED``, nothing sent. A strict
    allowlist with an out-of-allowlist recipient → ``EMAIL_RECIPIENT_NOT_ALLOWED``,
    nothing sent. The value and the message body are never logged. ``transport``
    is a test seam replacing the real SMTP send at the single call site.
    """

    name = "email"

    def __init__(
        self,
        host: str = "",
        port: int = 587,
        user: str = "",
        password: str = "",
        sender: str = "",
        use_tls: bool = True,
        recipient_allowlist: tuple[str, ...] = (),
        strict_allowlist: bool = False,
        transport: Callable[[EmailMessage, str], None] | None = None,
    ) -> None:
        self._host = host
        self._port = int(port)
        self._user = user
        self._password = password
        self._sender = sender
        self._use_tls = use_tls
        # Normalize the allowlist to lowercase domains; an entry may be a bare
        # domain or a ``@domain`` form.
        self._allowlist = frozenset(
            entry.strip().lower().lstrip("@")
            for entry in recipient_allowlist
            if entry and entry.strip()
        )
        self._strict = strict_allowlist
        self._transport = transport

    @property
    def configured(self) -> bool:
        return bool(self._host and valid_email_address(self._sender or self._user) and self._use_tls)

    def recipient_allowed(self, recipient: str) -> bool:
        """True when the recipient's domain is on the allowlist.

        An empty allowlist allows nothing under a strict posture (deny-by-default);
        a non-strict posture leaves the decision to the send anyway, so this is
        consulted for the strict gate and surfaced for the card warning kernel-side.
        """
        domain = recipient.rsplit("@", 1)[-1].strip().lower() if "@" in recipient else ""
        return valid_email_address(recipient) and (
            domain in self._allowlist or recipient.lower() in self._allowlist
        )

    def _default_transport(self, message: EmailMessage, recipient: str) -> None:
        with smtplib.SMTP(self._host, self._port, timeout=10) as smtp:
            smtp.starttls(context=ssl.create_default_context())
            if self._user:
                smtp.login(self._user, self._password)
            if smtp.send_message(message, to_addrs=[recipient]):
                raise smtplib.SMTPException("recipient refused")

    async def send(
        self, value: str, recipient: str | None, context: dict
    ) -> DeliveryOutcome:
        if not self.configured:
            return DeliveryOutcome(
                channel=self.name,
                delivered=False,
                recipient=recipient,
                error_code="EMAIL_NOT_CONFIGURED",
                error_message=(
                    "Email delivery requires GATEWAY_EMAIL_HOST, a valid sender, "
                    "and GATEWAY_EMAIL_USE_TLS=true; nothing was sent."
                ),
            )
        if not valid_email_address(recipient):
            return DeliveryOutcome(
                channel=self.name,
                delivered=False,
                recipient=recipient,
                error_code="INVALID_PARAMETERS",
                error_message="A valid 'recipient' email address is required.",
            )
        if self._strict and not self.recipient_allowed(recipient):
            return DeliveryOutcome(
                channel=self.name,
                delivered=False,
                recipient=recipient,
                error_code="EMAIL_RECIPIENT_NOT_ALLOWED",
                error_message=(
                    f"Recipient {recipient} is not on "
                    "GATEWAY_EMAIL_RECIPIENT_ALLOWLIST and the strict "
                    "allowlist is enabled; nothing was sent."
                ),
            )
        message = EmailMessage()
        message["From"] = self._sender or self._user
        message["To"] = recipient
        message["Subject"] = "A credential was generated for you"
        message.set_content(
            "A password was generated for you on the Luban platform.\n\n"
            f"{value}\n\nKeep this credential private.\n"
        )
        transport = self._transport or self._default_transport
        try:
            await asyncio.to_thread(transport, message, recipient)
        except (smtplib.SMTPException, OSError, ValueError) as exc:
            LOGGER.warning(
                "email secret delivery failed: %s", exc.__class__.__name__
            )
            return DeliveryOutcome(
                channel=self.name,
                delivered=False,
                recipient=recipient,
                error_code="UPSTREAM_ERROR",
                error_message=(
                    "The email could not be sent: "
                    f"{exc.__class__.__name__}."
                ),
            )
        LOGGER.info(
            "email secret delivered",
            extra={"channel": self.name, "request_id": context.get("request_id")},
        )
        return DeliveryOutcome(
            channel=self.name, delivered=True, recipient=recipient
        )


# ---------------------------------------------------------------------------
# Connector
# ---------------------------------------------------------------------------


class SecretsConnector:
    """Registers the secrets tools and owns the policy/buffer/channel wiring."""

    def __init__(
        self,
        *,
        policy_path: str = "",
        password_min_length: int | None = None,
        password_required_classes: tuple[str, ...] | None = None,
        password_exclude_ambiguous: bool = False,
        buffer: SecretDeliveryBuffer | None = None,
        delivery_ttl_seconds: int = 300,
        email_host: str = "",
        email_port: int = 587,
        email_user: str = "",
        email_password: str = "",
        email_from: str = "",
        email_use_tls: bool = True,
        email_recipient_allowlist: tuple[str, ...] = (),
        email_strict_allowlist: bool = False,
        secret_delivered_sink: SecretDeliveredSink | None = None,
        email_transport: Callable[[EmailMessage, str], None] | None = None,
    ) -> None:
        self._policy_store = PasswordPolicyStore(policy_path)
        self._min_length_override = password_min_length
        self._classes_override = password_required_classes
        self._exclude_ambiguous = password_exclude_ambiguous
        self._delivery_ttl_seconds = int(delivery_ttl_seconds)
        self._buffer = buffer if buffer is not None else InMemorySecretDeliveryBuffer(
            ttl_seconds=self._delivery_ttl_seconds
        )
        self._sink = secret_delivered_sink
        self._channels: dict[str, DeliveryChannel] = {
            PortalCopyChannel.name: PortalCopyChannel(self._buffer, self._delivery_ttl_seconds),
        }
        self.register_channel(EmailChannel(
            host=email_host, port=email_port, user=email_user, password=email_password,
            sender=email_from, use_tls=email_use_tls,
            recipient_allowlist=email_recipient_allowlist,
            strict_allowlist=email_strict_allowlist, transport=email_transport,
        ))

    def register_channel(self, channel: DeliveryChannel) -> None:
        """Register an external sender; local portal-copy cannot be replaced."""
        if channel.name == PortalCopyChannel.name:
            raise ValueError("portal_copy is the generation-only local handoff")
        self._channels[channel.name] = channel

    def external_channels(self) -> list[str]:
        return sorted(name for name in self._channels if name != PortalCopyChannel.name)

    @property
    def buffer(self) -> SecretDeliveryBuffer:
        return self._buffer

    def channel(self, name: str) -> DeliveryChannel | None:
        return self._channels.get(name)

    def effective_policy(self, name: str):
        """Load a named policy and apply the (tightening-only) env overrides."""
        policy = self._policy_store.get(name)
        if policy is None:
            return None
        return apply_overrides(
            policy,
            self._min_length_override,
            self._classes_override,
            self._exclude_ambiguous,
        )

    def policy_names(self) -> list[str]:
        return self._policy_store.names()

    def emit_secret_delivered(self, details: dict, identity: dict) -> None:
        if self._sink is not None:
            self._sink(details, identity)

    def register_tools(self, registry: ToolRegistry) -> None:
        """Register both tools.

        ``secrets.deliver`` is write-tier, so the registry's risk-tier admission
        (SPEC-021 R-1) refuses it when GATEWAY_MUTATING_TOOLS_ENABLED is off —
        the same division of labour the HTTP connector uses.
        """
        registry.register(GeneratePasswordTool(self))
        registry.register(DeliverSecretTool(self))


def _context(identity: dict) -> dict:
    return {
        "sub": identity.get("sub"),
        "session_id": identity.get("chat_session_id"),
        "request_id": identity.get("request_id"),
    }


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


class GeneratePasswordTool(BaseTool):
    """A read-tier CSPRNG password generator (R-1)."""

    def __init__(self, connector: SecretsConnector) -> None:
        self._connector = connector

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="secrets.generate_password",
            description=(
                "Generate a cryptographically secure password that conforms to "
                "the platform password policy. Use it when a reset or account "
                "recovery needs a new credential and the operator has not "
                "supplied one. The value is returned once for immediate use and, "
                "with handoff='portal_copy' (the default), is also stashed for a "
                "one-time Copy-password handoff in the portal — it is never "
                "written into the conversation transcript. Never restate the "
                "value in prose."
            ),
            risk_level="read",
            category=CATEGORY,
            parameters_schema={
                "type": "object",
                "properties": {
                    "length": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": MAX_PASSWORD_LENGTH,
                        "description": (
                            "Requested length; raised to the policy minimum when "
                            f"shorter (max {MAX_PASSWORD_LENGTH})."
                        ),
                    },
                    "policy": {
                        "type": "string",
                        "default": "default",
                        "description": (
                            "Named policy from the contract (default: 'default')."
                        ),
                    },
                    "exclude_ambiguous": {
                        "type": "boolean", "default": False,
                        "description": "Exclude visually ambiguous characters; can only tighten policy.",
                    },
                    "handoff": {
                        "type": "string",
                        "enum": ["portal_copy", "none"],
                        "default": "portal_copy",
                        "description": (
                            "'portal_copy' stashes the value for a one-time Copy "
                            "button and returns a delivery_id; 'none' generates "
                            "for immediate use with no handoff."
                        ),
                    },
                },
            },
        )

    async def execute(self, parameters: dict, identity: dict) -> ToolResult:
        start = time.perf_counter()
        tool_name = "secrets.generate_password"

        policy_name = parameters.get("policy", "default")
        handoff = parameters.get("handoff", "portal_copy")
        requested_length = parameters.get("length")
        exclude_ambiguous = parameters.get("exclude_ambiguous", False)
        if (
            not isinstance(policy_name, str)
            or handoff not in ("portal_copy", "none")
            or type(exclude_ambiguous) is not bool
            or (requested_length is not None and (
                type(requested_length) is not int or not 1 <= requested_length <= MAX_PASSWORD_LENGTH
            ))
        ):
            return make_error_result(
                tool_name, "INVALID_PARAMETERS", "Invalid policy, length, handoff, or exclusion parameter.",
                source_system=SOURCE_SYSTEM,
            )
        policy = self._connector.effective_policy(policy_name)
        if policy is None:
            return make_error_result(
                tool_name, "INVALID_PARAMETERS", "Password policy is unknown or unavailable.",
                source_system=SOURCE_SYSTEM,
            )
        policy = apply_overrides(policy, None, None, exclude_ambiguous)

        try:
            length = reconcile_length(policy, requested_length)
            value = generate_password(policy, length)
        except PasswordPolicyError as exc:
            # Fail closed: never emit a value the policy cannot satisfy.
            return make_error_result(
                tool_name, "INVALID_PARAMETERS", str(exc),
                source_system=SOURCE_SYSTEM,
            )

        # The field is named ``generated_password`` (not ``password``) so the
        # gateway's exact-key ``redact_result`` gate does not mask it before the
        # kernel receives it; the kernel's substring vocabulary still masks it in
        # every projection (see plan R-1).
        data: dict = {
            "generated_password": value,
            "length": length,
            "policy": policy_name,
        }

        if handoff == "portal_copy":
            channel = self._connector.channel(PortalCopyChannel.name)
            try:
                outcome = await channel.send(value, None, _context(identity)) if channel else None
            except Exception:
                outcome = None
            if outcome is None or not outcome.delivered or not outcome.delivery_id:
                return make_error_result(
                    tool_name, "UPSTREAM_ERROR", "The one-time handoff could not be created.",
                    source_system=SOURCE_SYSTEM,
                )
            data["delivery_id"] = outcome.delivery_id
            data["channel"] = outcome.channel
            data["expires_at"] = outcome.expires_at

        duration_ms = int((time.perf_counter() - start) * 1000)
        return ToolResult(
            tool_name=tool_name,
            status="success",
            data=data,
            evidence=build_evidence("read", SOURCE_SYSTEM, duration_ms),
        )


class DeliverSecretTool(BaseTool):
    """A write-tier dispatcher that sends a secret over an external channel (R-4).

    Requires ``secrets:deliver`` in addition to ``tools:mutate``
    (``extra_required_actions``), so the gateway denies an operator whose roles
    lack the capability before the connector is ever reached.
    """

    def __init__(self, connector: SecretsConnector) -> None:
        self._connector = connector

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="secrets.deliver",
            description=(
                "Deliver a generated secret to a human over an external channel "
                "(currently 'email'). Mutating and capability-gated: it requires "
                "operator confirmation and the secrets:deliver action. The value "
                "is masked in every projection and never logged. Use the "
                "portal Copy-password handoff (secrets.generate_password with "
                "handoff='portal_copy') for the in-session handoff instead."
            ),
            risk_level="write",
            category=CATEGORY,
            extra_required_actions=("secrets:deliver",),
            parameters_schema={
                "type": "object",
                "required": ["channel", "password"],
                "properties": {
                    "channel": {
                        "type": "string",
                        "enum": self._connector.external_channels(),
                        "description": "External delivery channel.",
                    },
                    "password": {
                        "type": "string",
                        "description": (
                            "The secret value to deliver. Masked in every "
                            "projection; never logged."
                        ),
                    },
                    "recipient": {
                        "type": "string",
                        "description": (
                            "Destination address (required for the email channel)."
                        ),
                    },
                },
            },
        )

    async def execute(self, parameters: dict, identity: dict) -> ToolResult:
        start = time.perf_counter()
        tool_name = "secrets.deliver"

        channel_name = parameters.get("channel")
        if not isinstance(channel_name, str) or not channel_name:
            return make_error_result(
                tool_name, "INVALID_PARAMETERS",
                "Parameter 'channel' is required.",
                risk_level="write", source_system=SOURCE_SYSTEM,
            )
        if channel_name not in self._connector.external_channels():
            return make_error_result(
                tool_name, "INVALID_PARAMETERS",
                "Unknown external delivery channel.",
                risk_level="write", source_system=SOURCE_SYSTEM,
            )
        value = parameters.get("password")
        if not isinstance(value, str) or not value:
            return make_error_result(
                tool_name, "INVALID_PARAMETERS",
                "Parameter 'password' must be a non-empty string.",
                risk_level="write", source_system=SOURCE_SYSTEM,
            )
        recipient = parameters.get("recipient")
        if recipient is not None and not isinstance(recipient, str):
            return make_error_result(
                tool_name, "INVALID_PARAMETERS",
                "Parameter 'recipient' must be a string.",
                risk_level="write", source_system=SOURCE_SYSTEM,
            )

        channel = self._connector.channel(channel_name)
        if channel is None:
            return make_error_result(
                tool_name, "INVALID_PARAMETERS",
                f"No sender registered for channel {channel_name!r}.",
                risk_level="write", source_system=SOURCE_SYSTEM,
            )

        try:
            outcome = await channel.send(value, recipient, _context(identity))
        except Exception:
            # A transport exception may contain the message or credential.
            return make_error_result(
                tool_name, "UPSTREAM_ERROR", "Secret delivery could not be completed.",
                risk_level="write", source_system=SOURCE_SYSTEM,
            )
        duration_ms = int((time.perf_counter() - start) * 1000)
        if not outcome.delivered:
            return _refusal(
                tool_name,
                "error",
                outcome.error_code or "UPSTREAM_ERROR",
                outcome.error_message or "Delivery failed.",
                "write",
                duration_ms,
            )

        # The channel accepted the value for the requester (portal-copy
        # redemption, or SMTP acceptance for email — not proof of inbox
        # delivery): emit ``secret_delivered`` (channel + recipient only,
        # never the value).
        data = {
            "delivery_id": outcome.delivery_id or str(uuid4()),
            "channel": outcome.channel,
            "delivered": True,
            "recipient": outcome.recipient,
        }
        self._connector.emit_secret_delivered(
            {key: data[key] for key in ("delivery_id", "channel", "recipient")}, identity,
        )
        return ToolResult(
            tool_name=tool_name,
            status="success",
            data=data,
            evidence=build_evidence("write", SOURCE_SYSTEM, duration_ms),
        )
