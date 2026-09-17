"""In-memory state for the `acme-admin` console (SPEC-059 R-1).

One store, two surfaces: the JSON API (`api.py`) and the server-rendered HTML
pages (`pages.py`) are both routers over the module-level ``STORE`` below. That
is what makes cross-skill verification possible — `LockUnlockUser` mutates over
HTTP and `CheckUserStatus` reads the same row back off a rendered page.

There is deliberately no database and no persistence. The state model has a
consequence worth stating out loud: ``replicas: 1`` in the Deployment, because
two replicas would be two independent consoles that disagree.

Nothing here stores a password. The seeded demo users (`alice`, `bob`, `carol`,
`dave`) are records, not accounts — a password reset records *when* it happened
and bumps the revision, and the value itself is discarded.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

# The revision the deterministic seed sits at. `reseed()` returns here, so a
# demo run can always prove it started from a known state.
SEED_REVISION = 0

# Seed offsets from `started_at`, so the seed is deterministic *relative* to
# process start and `reseed()` restores byte-identical timestamps.
_SEED_OFFSETS: dict[str, timedelta] = {
    "alice": timedelta(days=-9),
    # Recently modified on purpose: a skill checking "what changed lately" has
    # something to find without waiting on a mutation of its own.
    "bob": timedelta(hours=-2),
    "carol": timedelta(days=-30),
    "dave": timedelta(days=-60),
}


class UnknownUser(Exception):
    """Raised when an identifier matches no seeded user. The API maps it to 404."""

    def __init__(self, identifier: str) -> None:
        super().__init__(f"unknown user: {identifier!r}")
        self.identifier = identifier


class NoOpMutation(Exception):
    """Raised when a mutation would change nothing. The API maps it to 409.

    SPEC-058 R-3's `mutation_confirmed` marker only means something if the
    target distinguishes "changed" from "already in that state", so this is a
    real status code rather than a silently accepted 200.
    """

    def __init__(self, identifier: str, reason: str) -> None:
        super().__init__(f"no-op mutation for {identifier!r}: {reason}")
        self.identifier = identifier
        self.reason = reason


class InvalidPassword(Exception):
    """Raised for a reset value the store refuses to record. Maps to 400.

    Kept in the store rather than only in the routers so neither surface can
    record an empty password by forgetting to validate.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(f"invalid password: {reason}")
        self.reason = reason


def iso_utc(moment: datetime) -> str:
    """Render an aware datetime as RFC 3339 at microsecond precision.

    Microseconds rather than seconds on purpose: two mutations a caller makes
    back to back must not produce an identical `last_modified`, or the field
    cannot say which action touched the row. `revision` is the authoritative
    discriminator; this keeps the human-readable one honest too.
    """
    return moment.astimezone(timezone.utc).isoformat(timespec="microseconds")


def _now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class User:
    """A console record. `revision` is the store revision that last touched it."""

    username: str
    full_name: str
    email: str
    role: str
    locked: bool = False
    password_changed_at: str | None = None
    last_modified: str | None = None
    revision: int = SEED_REVISION

    def to_list_dict(self) -> dict[str, object]:
        """The `GET /api/users` row: what a status check needs and no more."""
        return {
            "username": self.username,
            "locked": self.locked,
            "last_modified": self.last_modified,
            "revision": self.revision,
        }

    def to_detail_dict(self) -> dict[str, object]:
        """The `GET /api/users/{username}` row: the list fields plus identity."""
        detail = self.to_list_dict()
        detail.update(
            {
                "full_name": self.full_name,
                "email": self.email,
                "role": self.role,
                "password_changed_at": self.password_changed_at,
            }
        )
        return detail


@dataclass(frozen=True)
class _SeedRecord:
    username: str
    full_name: str
    email: str
    role: str
    locked: bool


# One of the four is pre-locked (SPEC-059 R-3), so a read-only skill has a
# non-uniform table to describe on the very first run.
_SEED: tuple[_SeedRecord, ...] = (
    _SeedRecord("alice", "Alice Johnson", "alice@example.com", "viewer", False),
    _SeedRecord("bob", "Bob Smith", "bob@example.com", "editor", False),
    _SeedRecord("carol", "Carol Williams", "carol@example.com", "admin", False),
    _SeedRecord("dave", "Dave Brown", "dave@example.com", "viewer", True),
)


class Store:
    """The whole application state: users, a monotonic revision, one reset record.

    Mutations are synchronous and short; the store is not guarded by a lock,
    which is fine for a single-replica tutorial target and is the reason the
    Deployment pins `replicas: 1`.
    """

    def __init__(self, started_at: datetime | None = None) -> None:
        self.started_at: datetime = started_at or _now()
        self.revision: int = SEED_REVISION
        self.last_reset: dict[str, str] | None = None
        self.users: dict[str, User] = {}
        self._seed()

    # --- seeding ---------------------------------------------------------

    def _seed(self) -> None:
        self.users = {}
        for record in _SEED:
            modified = self.started_at + _SEED_OFFSETS[record.username]
            self.users[record.username] = User(
                username=record.username,
                full_name=record.full_name,
                email=record.email,
                role=record.role,
                locked=record.locked,
                password_changed_at=None,
                last_modified=iso_utc(modified),
                revision=SEED_REVISION,
            )
        self.revision = SEED_REVISION
        self.last_reset = None

    def reseed(self) -> None:
        """Restore the exact deterministic seed.

        Backs `POST /internal/reset-demo`, which the demo scripts call before
        every run. `started_at` is *not* reset: uptime keeps counting from
        process start, and the seed timestamps stay anchored to it so the
        restored state is identical to the state the process began with.
        """
        self._seed()

    # --- reads -----------------------------------------------------------

    def all_users(self) -> list[User]:
        """Every user, ordered by username, so renders are stable."""
        return [self.users[name] for name in sorted(self.users)]

    @property
    def users_seeded(self) -> int:
        return len(_SEED)

    def resolve(self, identifier: str) -> User:
        """Find a user by **username or email** (case-insensitive).

        Both shapes address the same row because the shipped browser samples
        use email-shaped identifiers (`?user=alice@example.com`) and R-2 exists
        to make their rebase onto this app a retarget rather than a rewrite.
        """
        needle = (identifier or "").strip().lower()
        for user in self.users.values():
            if user.username.lower() == needle or user.email.lower() == needle:
                return user
        raise UnknownUser(identifier)

    # --- mutations -------------------------------------------------------

    def _stamp(self, user: User, moment: datetime) -> None:
        """Bump the global revision and stamp this user with it."""
        self.revision += 1
        user.revision = self.revision
        user.last_modified = iso_utc(moment)

    def lock(self, identifier: str) -> User:
        user = self.resolve(identifier)
        if user.locked:
            raise NoOpMutation(identifier, "user is already locked")
        user.locked = True
        self._stamp(user, _now())
        return user

    def unlock(self, identifier: str) -> User:
        user = self.resolve(identifier)
        if not user.locked:
            raise NoOpMutation(identifier, "user is not locked")
        user.locked = False
        self._stamp(user, _now())
        return user

    def set_password(self, identifier: str, password: str) -> User:
        """Record a reset. The value is validated by the caller and discarded.

        Nothing is stored or logged: this app has no usable demo password to
        protect, and a tutorial target that persisted one would teach the wrong
        habit. What survives is *when* the reset happened and which revision it
        produced — enough for a skill to verify the mutation landed.
        """
        user = self.resolve(identifier)
        if not password:
            raise InvalidPassword("new password must not be empty")
        moment = _now()
        user.password_changed_at = iso_utc(moment)
        self._stamp(user, moment)
        self.last_reset = {"username": user.username, "at": user.password_changed_at}
        return user


# The module-level singleton both routers share.
STORE = Store()
