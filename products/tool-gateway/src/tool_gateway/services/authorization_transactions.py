"""SPEC-070 transient routing contract; storage/custody implementations pending.

This module deliberately registers no backend or app state. A future factory
must refuse multi-replica authorization without shared Postgres and must never
fall back to memory after a backend failure. No method grants execution authority.
"""

from datetime import datetime
from typing import Protocol, runtime_checkable

from pydantic import AwareDatetime, Field, model_validator

from tool_gateway.schemas.authorization import (
    AuthorizationModel,
    AuthorizationStatus,
    CallbackStatus,
    ChallengeId,
    DisplayLabel,
    LocalReturnPath,
)


class AuthorizationLifetimes(AuthorizationModel):
    start_ttl_seconds: int = Field(default=60, strict=True, gt=0)
    transaction_ttl_seconds: int = Field(default=600, strict=True, gt=0)

    @model_validator(mode="after")
    def _bounded_start(self) -> "AuthorizationLifetimes":
        if self.start_ttl_seconds > self.transaction_ttl_seconds:
            raise ValueError("start lifetime must not exceed transaction lifetime")
        return self


class AuthorizationTransaction(AuthorizationModel):
    """Routing state only. State handles and encrypted verifiers live in R-6.

    ``consumed`` marks the callback claim, not start-handle use. Start handles
    have their own single-use claims and cannot extend this record's expiry.
    ``updated_at`` supports the status projection. Owner and config binding
    must be recovered from authenticated server context, never callback input.
    """

    challenge_id: ChallengeId
    owner_namespace: str = Field(strict=True, min_length=1)
    owner_sub: str = Field(strict=True, min_length=1)
    target: DisplayLabel
    credential_set_id: str = Field(strict=True, min_length=1)
    config_generation: str = Field(strict=True, min_length=1)
    session_id: str = Field(strict=True, min_length=1)
    call_id: str = Field(strict=True, min_length=1)
    return_url: LocalReturnPath
    status: AuthorizationStatus = "pending"
    created_at: AwareDatetime
    updated_at: AwareDatetime
    expires_at: AwareDatetime
    consumed: bool = Field(default=False, strict=True)

    @model_validator(mode="after")
    def _ordered_times(self) -> "AuthorizationTransaction":
        if self.expires_at <= self.created_at or self.updated_at < self.created_at:
            raise ValueError("invalid authorization transaction lifetime")
        return self


@runtime_checkable
class AuthorizationTransactionStore(Protocol):
    """Required behavior for the R-6 foundation, not an implemented store.

    All owner reads/claims bind namespace AND subject. Wrong owner, missing,
    expired or spent claims return None without revealing which check failed.
    Stores check time/config atomically, even before cleanup. Callback claim
    and finalization must coordinate with encrypted state/custody; a provider
    exchange is not atomic with Postgres. Lost outcomes cannot be retried as
    undispatched. Cancel/config invalidation must win over late finalization.
    """

    @property
    def backend_name(self) -> str: ...

    @property
    def shared(self) -> bool: ...

    async def initialize(self) -> None: ...

    async def create(self, transaction: AuthorizationTransaction) -> None:
        """Insert once; never overwrite an existing binding or extend expiry."""
        ...

    async def get(
        self, challenge_id: str, owner_namespace: str, owner_sub: str, *, now: datetime,
    ) -> AuthorizationTransaction | None:
        """Non-destructive owner projection, including terminal status until eviction."""
        ...

    async def claim_callback(
        self, challenge_id: str, owner_namespace: str, owner_sub: str,
        config_generation: str, *, now: datetime,
    ) -> AuthorizationTransaction | None:
        """Atomically consume one pending, unexpired, generation-matching callback."""
        ...

    async def finish(
        self, challenge_id: str, owner_namespace: str, owner_sub: str,
        config_generation: str, status: CallbackStatus, *, now: datetime,
    ) -> bool:
        """Finalize a claimed pending transaction; no revival after cancel/expiry."""
        ...

    async def cancel(
        self, challenge_id: str, owner_namespace: str, owner_sub: str, *, now: datetime,
    ) -> None:
        """Idempotent no-oracle cancellation; burn pending secret state, not credentials."""
        ...

    async def expire(self, *, now: datetime, limit: int) -> int:
        """Bounded sweep; callback safety must not depend on this having run."""
        ...

    async def ready(self) -> bool: ...

    async def close(self) -> None: ...
