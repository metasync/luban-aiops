"""SPEC-070 OQ-7 — delegated target-authorization runtime (tool-gateway routes).

Covers the ``/api/v2/targets/authorizations`` workflow: the default-off
authorization gate and its fail-closed validation, the platform-gateway
authorization-workload JWT verifier (dedicated ``luban-target-authorization-handoff``
audience), the genuine delegated-human bearer verification for the owner-scoped
edges, and the six route handlers driving the transaction store + acquisition
client under ``targets:authorize`` policy and exact owner scope.

Every refusal must be a fixed, non-sensitive class: no token, code, state, PKCE,
browser proof, provider URL, or ``error_description`` ever reaches a response,
a log line, or an audit detail.
"""

import asyncio
import os
import time
import unittest
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit
from uuid import UUID

import jwt as pyjwt
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from pydantic import SecretStr

from tool_gateway.app import create_app
from tool_gateway.core.config import (
    DEFAULT_AUTHORIZATION_WORKLOAD_AUDIENCE,
    GatewaySettings,
    get_settings,
)
from tool_gateway.schemas.api import IdentityContext
from tool_gateway.schemas.authorization import (
    AuthorizationCallbackRequest,
    AuthorizationRequired,
    AuthorizationStartRequest,
    BrowserResetRequest,
    ProviderUrlRequest,
)
from tool_gateway.services import authorization_service, delegated_invoke
from tool_gateway.services.authorization_transaction_store import (
    MemoryAuthorizationTransactionStore,
    build_transaction_store,
)
from tool_gateway.services.authorization_transactions import AuthorizationTransaction
from tool_gateway.services.custody_crypto import CustodyError
from tool_gateway.services.policy_engine import reset_policy_state
from tool_gateway.tools.delegated_configuration import DelegatedConfiguration
from tool_gateway.tools.user_delegated_client import DelegatedAcquisitionError

# Delegated-human trust (the SAME issuer/audience/JWKS/actor set the worker and
# the private execution route use — owner_namespace is pinned to this issuer).
IDENTITY_ISSUER = "trusted-identity-issuer"
IDENTITY_AUDIENCE = "tool-gateway"
IDENTITY_JWKS = "https://identity.test/jwks"
IDENTITY_ACTORS = ("platform-gateway",)

# Authorization-handoff workload trust (platform-gateway projected SA token).
AUTH_WORKLOAD_ISSUER = "https://cluster.issuer"
AUTH_WORKLOAD_JWKS = "https://cluster.issuer/jwks"
AUTH_WORKLOAD_SUBJECT = "system:serviceaccount:platform-gateway:platform-gateway"

# Postgres custody runtime (shared with the acquisition gate).
DB_URL = "postgresql://gateway@db.internal:5432/gateway"
KEYRING_PATH = "/etc/tool-gateway/delegated-keyring.json"
CONFIG_PATH = "/etc/tool-gateway/delegated.json"
SET_ID = "ansible-prod"
TRUSTED_CALLBACK = "https://gw.internal/api/v1/targets/authorizations/callback"


def _authorization_settings(**overrides) -> GatewaySettings:
    """A fully provisioned authorization runtime; overrides loosen one leg."""
    kwargs = dict(
        delegated_authorization_enabled=True,
        # Postgres custody infrastructure.
        delegated_custody_db_url=DB_URL,
        delegated_custody_keyring_path=KEYRING_PATH,
        delegated_custody_config_path=CONFIG_PATH,
        delegated_custody_set_id=SET_ID,
        delegated_custody_trusted_callback=TRUSTED_CALLBACK,
        # Delegated-human trust set.
        delegated_identity_issuer=IDENTITY_ISSUER,
        delegated_identity_jwks_url=IDENTITY_JWKS,
        delegated_identity_audience=IDENTITY_AUDIENCE,
        delegated_identity_actors=IDENTITY_ACTORS,
        # Authorization-workload trust set.
        authorization_workload_issuer=AUTH_WORKLOAD_ISSUER,
        authorization_workload_jwks_url=AUTH_WORKLOAD_JWKS,
        authorization_workload_audience=DEFAULT_AUTHORIZATION_WORKLOAD_AUDIENCE,
        authorization_workload_subjects=(AUTH_WORKLOAD_SUBJECT,),
    )
    kwargs.update(overrides)
    return GatewaySettings(**kwargs)


_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _mint_human(
    sub: str,
    username: str,
    roles: list[str],
    *,
    iss: str = IDENTITY_ISSUER,
    aud: str = IDENTITY_AUDIENCE,
    authentication_source: str = "oidc",
    act=None,
    exp=None,
    iat=None,
) -> str:
    """Mint a genuine delegated-human bearer (owner_namespace == iss)."""
    now = int(time.time())
    claims = {
        "iss": iss,
        "aud": [aud],
        "sub": sub,
        "username": username,
        "roles": roles,
        "groups": [],
        "iat": iat if iat is not None else now - 1,
        "exp": exp if exp is not None else now + 300,
        "authentication_source": authentication_source,
        "act": {"sub": "platform-gateway"} if act is None else act,
    }
    return pyjwt.encode(claims, _KEY, algorithm="RS256")


def _mint_auth_workload(
    *,
    iss: str = AUTH_WORKLOAD_ISSUER,
    aud: str = DEFAULT_AUTHORIZATION_WORKLOAD_AUDIENCE,
    sub: str = AUTH_WORKLOAD_SUBJECT,
    exp=None,
) -> str:
    """Mint the platform-gateway projected SA token for the handoff audience."""
    now = int(time.time())
    claims = {
        "iss": iss,
        "aud": [aud],
        "sub": sub,
        "iat": now - 1,
        "exp": exp if exp is not None else now + 300,
    }
    return pyjwt.encode(claims, _KEY, algorithm="RS256")


class _FakeRequest:
    """Exposes only the Authorization header the verifiers read."""

    def __init__(self, bearer: str | None = None) -> None:
        self.headers = {"authorization": f"Bearer {bearer}"} if bearer is not None else {}


@contextmanager
def _patch_auth_jwks():
    """Point the authorization workload + shared human JWKS resolvers at _KEY."""
    public_key = _KEY.public_key()
    fake = type(
        "FakeClient",
        (),
        {"get_signing_key_from_jwt": lambda _self, _t: type("K", (), {"key": public_key})()},
    )()
    with patch.object(authorization_service, "_auth_workload_jwks_client", return_value=fake), \
            patch.object(delegated_invoke, "_human_jwks_client", return_value=fake):
        yield


class AuthorizationConfigGateTests(unittest.TestCase):
    """Enabling the authorization runtime without full trust must fail closed."""

    def test_disabled_by_default(self) -> None:
        settings = GatewaySettings()
        self.assertFalse(settings.delegated_authorization_enabled)
        self.assertEqual(settings.delegated_custody_db_url, "")
        self.assertEqual(
            settings.authorization_workload_audience,
            DEFAULT_AUTHORIZATION_WORKLOAD_AUDIENCE,
        )
        self.assertEqual(settings.authorization_workload_subjects, ())

    def test_audience_default_is_the_dedicated_handoff(self) -> None:
        # The authorization handoff audience is distinct from the execution
        # handoff audience; a public token carries neither.
        self.assertEqual(
            DEFAULT_AUTHORIZATION_WORKLOAD_AUDIENCE,
            "luban-target-authorization-handoff",
        )

    def test_enabled_without_anything_raises(self) -> None:
        with self.assertRaises(ValueError):
            GatewaySettings(delegated_authorization_enabled=True)

    def test_enabled_without_custody_runtime_raises(self) -> None:
        # Identity + workload trust present, but no Postgres custody DSN.
        with self.assertRaises(ValueError):
            _authorization_settings(delegated_custody_db_url="")

    def test_enabled_with_non_postgres_dsn_raises(self) -> None:
        with self.assertRaises(ValueError):
            _authorization_settings(delegated_custody_db_url="sqlite:///gateway.db")

    def test_enabled_with_wrong_callback_path_raises(self) -> None:
        with self.assertRaises(ValueError):
            _authorization_settings(
                delegated_custody_trusted_callback="https://gw.internal/api/v1/wrong"
            )

    def test_enabled_without_identity_trust_raises(self) -> None:
        with self.assertRaises(ValueError):
            _authorization_settings(delegated_identity_issuer="")

    def test_enabled_without_identity_actors_raises(self) -> None:
        with self.assertRaises(ValueError):
            _authorization_settings(delegated_identity_actors=())

    def test_enabled_without_workload_trust_raises(self) -> None:
        with self.assertRaises(ValueError):
            _authorization_settings(authorization_workload_issuer="")

    def test_enabled_without_workload_subjects_raises(self) -> None:
        with self.assertRaises(ValueError):
            _authorization_settings(authorization_workload_subjects=())

    def test_enabled_with_full_runtime_constructs(self) -> None:
        settings = _authorization_settings()
        self.assertTrue(settings.delegated_authorization_enabled)
        self.assertEqual(
            settings.authorization_workload_subjects, (AUTH_WORKLOAD_SUBJECT,)
        )
        self.assertEqual(
            settings.authorization_workload_audience,
            "luban-target-authorization-handoff",
        )

    def test_authorization_gate_is_independent_of_acquisition(self) -> None:
        # The acquisition wiring composes its client off
        # ``delegated_acquisition_enabled`` alone; enabling authorization must
        # not require acquisition and vice versa.
        settings = _authorization_settings(delegated_acquisition_enabled=False)
        self.assertTrue(settings.delegated_authorization_enabled)
        self.assertFalse(settings.delegated_acquisition_enabled)


class AuthorizationConfigEnvTests(unittest.TestCase):
    def test_from_env_maps_the_authorization_runtime(self) -> None:
        env = {
            "GATEWAY_DELEGATED_AUTHORIZATION_ENABLED": "true",
            "GATEWAY_DELEGATED_CUSTODY_DB_URL": DB_URL,
            "GATEWAY_DELEGATED_CUSTODY_KEYRING_PATH": KEYRING_PATH,
            "GATEWAY_DELEGATED_CUSTODY_CONFIG_PATH": CONFIG_PATH,
            "GATEWAY_DELEGATED_CUSTODY_SET_ID": SET_ID,
            "GATEWAY_DELEGATED_CUSTODY_TRUSTED_CALLBACK": TRUSTED_CALLBACK,
            "GATEWAY_DELEGATED_IDENTITY_ISSUER": IDENTITY_ISSUER,
            "GATEWAY_DELEGATED_IDENTITY_JWKS_URL": IDENTITY_JWKS,
            "GATEWAY_DELEGATED_IDENTITY_AUDIENCE": IDENTITY_AUDIENCE,
            "GATEWAY_DELEGATED_IDENTITY_ACTORS": ",".join(IDENTITY_ACTORS),
            "GATEWAY_AUTHORIZATION_WORKLOAD_ISSUER": AUTH_WORKLOAD_ISSUER,
            "GATEWAY_AUTHORIZATION_WORKLOAD_JWKS_URL": AUTH_WORKLOAD_JWKS,
            "GATEWAY_AUTHORIZATION_WORKLOAD_SUBJECTS": AUTH_WORKLOAD_SUBJECT,
        }
        with patch.dict(os.environ, env, clear=False):
            settings = GatewaySettings.from_env()
        self.assertTrue(settings.delegated_authorization_enabled)
        self.assertEqual(settings.authorization_workload_issuer, AUTH_WORKLOAD_ISSUER)
        self.assertEqual(settings.authorization_workload_jwks_url, AUTH_WORKLOAD_JWKS)
        self.assertEqual(
            settings.authorization_workload_audience,
            "luban-target-authorization-handoff",
        )
        self.assertEqual(
            settings.authorization_workload_subjects, (AUTH_WORKLOAD_SUBJECT,)
        )


class AuthorizationWorkloadVerifierTests(unittest.TestCase):
    """The provider-url/callback edges accept only the platform-gateway SA token."""

    def setUp(self) -> None:
        authorization_service.reset_authorization_state()
        delegated_invoke.reset_delegated_state()

    def tearDown(self) -> None:
        authorization_service.reset_authorization_state()
        delegated_invoke.reset_delegated_state()

    def _reject(self, token: str | None) -> int:
        settings = _authorization_settings()
        with _patch_auth_jwks(), \
                self.assertRaises(authorization_service.AuthorizationError) as ctx:
            authorization_service.authenticate_authorization_workload(
                settings, _FakeRequest(token)
            )
        return ctx.exception.status_code

    def test_verifies_exact_subject(self) -> None:
        settings = _authorization_settings()
        with _patch_auth_jwks():
            subject = authorization_service.authenticate_authorization_workload(
                settings, _FakeRequest(_mint_auth_workload())
            )
        self.assertEqual(subject, AUTH_WORKLOAD_SUBJECT)

    def test_missing_bearer_rejected(self) -> None:
        self.assertEqual(self._reject(None), 401)

    def test_execution_audience_rejected(self) -> None:
        # An execution-handoff token must never drive the authorization edges.
        self.assertEqual(
            self._reject(_mint_auth_workload(aud="luban-target-execution-handoff")), 401
        )

    def test_unregistered_subject_rejected(self) -> None:
        self.assertEqual(
            self._reject(_mint_auth_workload(sub="system:serviceaccount:other:svc")), 401
        )

    def test_expired_token_rejected(self) -> None:
        self.assertEqual(self._reject(_mint_auth_workload(exp=int(time.time()) - 10)), 401)

    def test_detail_never_echoes_token(self) -> None:
        settings = _authorization_settings()
        token = _mint_auth_workload(aud="wrong-audience")
        with _patch_auth_jwks(), \
                self.assertRaises(authorization_service.AuthorizationError) as ctx:
            authorization_service.authenticate_authorization_workload(
                settings, _FakeRequest(token)
            )
        self.assertNotIn(token, ctx.exception.detail)


class AuthorizationHumanVerifierTests(unittest.TestCase):
    """The owner-scoped edges accept only a genuine delegated-human bearer."""

    def setUp(self) -> None:
        authorization_service.reset_authorization_state()
        delegated_invoke.reset_delegated_state()

    def tearDown(self) -> None:
        authorization_service.reset_authorization_state()
        delegated_invoke.reset_delegated_state()

    def _reject(self, token: str | None) -> int:
        settings = _authorization_settings()
        with _patch_auth_jwks(), \
                self.assertRaises(authorization_service.AuthorizationError) as ctx:
            authorization_service.authenticate_authorization_human(
                settings, _FakeRequest(token)
            )
        return ctx.exception.status_code

    def test_derives_owner_subject_and_roles(self) -> None:
        settings = _authorization_settings()
        token = _mint_human("alice-immutable", "alice", ["operator"])
        with _patch_auth_jwks():
            identity = authorization_service.authenticate_authorization_human(
                settings, _FakeRequest(token)
            )
        self.assertEqual(identity.subject, "alice-immutable")
        self.assertEqual(identity.username, "alice")
        self.assertEqual(identity.roles, ["operator"])
        self.assertEqual(identity.actor, "platform-gateway")

    def test_missing_bearer_is_unauthenticated(self) -> None:
        self.assertEqual(self._reject(None), 401)

    def test_development_provenance_rejected(self) -> None:
        token = _mint_human(
            "alice-immutable", "alice", ["operator"], authentication_source="development"
        )
        self.assertEqual(self._reject(token), 403)

    def test_foreign_actor_rejected(self) -> None:
        token = _mint_human("alice-immutable", "alice", ["operator"], act={"sub": "mallory-gw"})
        self.assertEqual(self._reject(token), 403)

    def test_wrong_audience_rejected(self) -> None:
        token = _mint_human("alice-immutable", "alice", ["operator"], aud="some-other-service")
        self.assertEqual(self._reject(token), 403)

    def test_expired_token_rejected(self) -> None:
        token = _mint_human("alice-immutable", "alice", ["operator"], iat=100, exp=200)
        self.assertEqual(self._reject(token), 403)


# -- AuthorizationService orchestration -------------------------------------
#
# These tests drive the six handlers over a real Memory transaction store (the
# browser-proof/single-use/expiry authority is the shipped store, not a mock), a
# fake custody configuration source, and a fake acquisition client. The provider
# channel and code exchange are unit-tested in test_user_delegated_client.py, so
# the client is faked here to isolate orchestration, owner scope, and the
# no-oracle / entitlement / denial mappings. ``complete_authorization`` is
# Postgres-only, so the callback code-success leg uses a Memory subclass that
# supplies it and mirrors the durable publication flip.

OWNER_NS = IDENTITY_ISSUER
OWNER_SUB = "alice-immutable"
TARGET = "Automation"
GEN = "gen1"
CHALLENGE = "11111111-1111-4111-8111-111111111111"
OTHER_CHALLENGE = "22222222-2222-4222-8222-222222222222"
BROWSER_SECRET = "cookie-secret-value"
SVC_NOW = datetime.now(timezone.utc)


def _delegated_config(**over) -> DelegatedConfiguration:
    base = dict(
        scheme="oauth2_authorization_code", target=TARGET,
        authorization_url="https://oauth.test/authorize", token_url="https://oauth.test/token",
        renewal_url="https://oauth.test/token", identity_url="https://oauth.test/whoami",
        client_id="client", client_secret="opaque-client-value", client_auth="client_secret_basic",
        redirect_uri="https://portal.test/api/v1/targets/authorizations/callback",
        scope="read", allowed_scopes="read write", oauth_origins="https://oauth.test",
        resource_origins="https://resource.test", pkce_method="S256", store="postgres",
        config_revision="1", identity_profile="json_immutable_id", identity_claim="id",
        identity_mapping_path="/run/mapping.json", access_cache_ttl_seconds="300",
        refresh_max_lifetime_seconds="2592000",
    )
    base.update(over)
    return DelegatedConfiguration.parse(base)


def _identity(sub: str = OWNER_SUB, *, roles=("operator",)) -> IdentityContext:
    return IdentityContext(subject=sub, username="alice", email=None, groups=[],
                           roles=list(roles), actor="platform-gateway")


def _txn(challenge_id=CHALLENGE, *, status="pending", expires_in=600, ns=OWNER_NS,
         sub=OWNER_SUB, target=TARGET, generation=GEN, consumed=False) -> AuthorizationTransaction:
    created = SVC_NOW - timedelta(seconds=1)
    return AuthorizationTransaction(
        challenge_id=challenge_id, owner_namespace=ns, owner_sub=sub, target=target,
        credential_set_id="user", config_generation=generation, session_id="ses-1", call_id="call-1",
        return_url="/", status=status, created_at=created, updated_at=created,
        expires_at=SVC_NOW + timedelta(seconds=expires_in), consumed=consumed)


class _ServiceCustody:
    """Authoritative configuration/linkage source for the entitlement recheck."""

    # The producer binds a challenge to this credential-set id (SPEC-070).
    set_id = "user"

    def __init__(self, *, linkage=None, generation=GEN, target=TARGET, sync_raises=None):
        self._config = _delegated_config(target=target)
        self._linkage = {(OWNER_NS, OWNER_SUB): "42"} if linkage is None else linkage
        self._generation = generation
        self.sync_raises = sync_raises
        self.sync_calls = 0

    async def sync_configuration(self):
        self.sync_calls += 1
        if self.sync_raises is not None:
            raise self.sync_raises
        return self._config, self._linkage, None, self._generation, "fingerprint"


class _FakeAcquisitionClient:
    def __init__(self, *, bundle=None, exchange_raises=None, url_raises=None):
        self._bundle = bundle
        self._exchange_raises = exchange_raises
        self._url_raises = url_raises
        self.build_calls = 0
        self.exchange_calls = 0
        self.last_state = None

    def build_authorization_url(self, config, *, state, verifier):
        self.build_calls += 1
        if self._url_raises is not None:
            raise self._url_raises
        self.last_state = state
        return f"https://oauth.test/authorize?client_id=client&state={state}"

    async def exchange_authorization_code(self, config, linkage, *, owner, code, verifier):
        self.exchange_calls += 1
        if self._exchange_raises is not None:
            raise self._exchange_raises
        return self._bundle


class _CompletingStore(MemoryAuthorizationTransactionStore):
    """Memory store plus the Postgres-only ``complete_authorization`` publication."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.complete_calls = 0
        self.complete_returns = SimpleNamespace(generation=GEN, epoch=2, target_account="42", scopes="read")

    async def complete_authorization(self, claim, *, target_account, scopes, refresh_secret,
                                     refresh_expires_at, now):
        self.complete_calls += 1
        record = claim.transaction
        self._records[record.challenge_id] = record.model_copy(update={"status": "authorized", "updated_at": now})
        self._secrets.pop(record.challenge_id, None)
        return self.complete_returns


def _bundle():
    return SimpleNamespace(scopes="read", refresh_secret=SecretStr("rt"),
                           refresh_expires_at=SVC_NOW + timedelta(seconds=100000))


def _make_service(*, records=(), custody=None, client=None, store=None, now=SVC_NOW, audit=None):
    store = store if store is not None else build_transaction_store(backend="memory", replicas=1)

    async def _seed():
        for record in records:
            await store.create(record)

    asyncio.run(_seed())
    service = authorization_service.AuthorizationService(
        store=store,
        custody=custody if custody is not None else _ServiceCustody(),
        client=client if client is not None else _FakeAcquisitionClient(),
        utcnow=lambda: now,
        audit=audit,
    )
    return service, store


async def _drive_to_state(store, *, challenge=CHALLENGE, ns=OWNER_NS, sub=OWNER_SUB,
                          secret=BROWSER_SECRET, now=SVC_NOW):
    """Issue+consume a start handle and prepare state, returning the state secret."""
    token = await store.issue_start(challenge, ns, sub, browser_secret=SecretStr(secret), now=now)
    prepared = await store.consume_start(token, browser_bindings={challenge: secret}, now=now)
    assert prepared is not None
    return prepared.state


class AuthorizationProducerTests(unittest.TestCase):
    """SPEC-070 producer: a verified ``authorization_required`` acquisition
    failure becomes a durable pending challenge plus safe public metadata.

    The producer is the bridge to the kernel's bounded stop: it must mint a
    single-use transaction bound to the verified owner, the authoritative
    target/generation, the credential set, and the exact invocation
    (session_id, call_id), and return ONLY ``{challenge_id, target,
    expires_at}``. Every configuration/entitlement/store failure is fail-closed
    ``None`` — never a challenge id that was not durably inserted, never an
    oracle, and never a secret.
    """

    def test_produce_creates_durable_pending_challenge(self) -> None:
        service, store = _make_service()
        produced = asyncio.run(service.produce_challenge(
            owner_namespace=OWNER_NS, owner_sub=OWNER_SUB,
            session_id="ses-1", call_id="call-1"))
        self.assertIsInstance(produced, AuthorizationRequired)
        # A freshly minted canonical uuid4 challenge id.
        self.assertEqual(UUID(produced.challenge_id).version, 4)
        self.assertEqual(produced.target, TARGET)
        self.assertGreater(produced.expires_at, SVC_NOW)
        # The durable transaction is pending and bound to the exact context.
        txn = asyncio.run(store.get(produced.challenge_id, OWNER_NS, OWNER_SUB, now=SVC_NOW))
        self.assertIsNotNone(txn)
        self.assertEqual(txn.status, "pending")
        self.assertFalse(txn.consumed)
        self.assertEqual(txn.target, TARGET)
        self.assertEqual(txn.credential_set_id, "user")
        self.assertEqual(txn.config_generation, GEN)
        self.assertEqual(txn.session_id, "ses-1")
        self.assertEqual(txn.call_id, "call-1")

    def test_produce_returns_only_safe_metadata(self) -> None:
        service, _store = _make_service()
        produced = asyncio.run(service.produce_challenge(
            owner_namespace=OWNER_NS, owner_sub=OWNER_SUB,
            session_id="ses-1", call_id="call-1"))
        # Exactly the public triple the kernel promotes — no owner, token, state,
        # PKCE verifier, provider URL, or set id ever rides the metadata.
        self.assertEqual(
            set(produced.model_dump(mode="json", exclude_none=True)),
            {"challenge_id", "target", "expires_at"})

    def test_produce_binds_current_generation_and_target(self) -> None:
        service, store = _make_service(
            custody=_ServiceCustody(generation="gen2", target="OtherTarget"))
        produced = asyncio.run(service.produce_challenge(
            owner_namespace=OWNER_NS, owner_sub=OWNER_SUB,
            session_id="ses-2", call_id="call-2"))
        self.assertEqual(produced.target, "OtherTarget")
        txn = asyncio.run(store.get(produced.challenge_id, OWNER_NS, OWNER_SUB, now=SVC_NOW))
        self.assertEqual(txn.config_generation, "gen2")
        self.assertEqual(txn.target, "OtherTarget")

    def test_produce_fails_closed_when_configuration_unavailable(self) -> None:
        service, store = _make_service(
            custody=_ServiceCustody(sync_raises=CustodyError("configuration_unavailable")))
        produced = asyncio.run(service.produce_challenge(
            owner_namespace=OWNER_NS, owner_sub=OWNER_SUB,
            session_id="ses-1", call_id="call-1"))
        self.assertIsNone(produced)
        self.assertEqual(store._records, {})

    def test_produce_fails_closed_without_administered_linkage(self) -> None:
        # No administered owner->target mapping: a challenge could never
        # complete, so none is minted (no unusable-challenge oracle).
        service, store = _make_service(custody=_ServiceCustody(linkage={}))
        produced = asyncio.run(service.produce_challenge(
            owner_namespace=OWNER_NS, owner_sub=OWNER_SUB,
            session_id="ses-1", call_id="call-1"))
        self.assertIsNone(produced)
        self.assertEqual(store._records, {})

    def test_produce_fails_closed_on_store_conflict(self) -> None:
        class _ConflictStore(MemoryAuthorizationTransactionStore):
            async def create(self, transaction):
                raise CustodyError("transaction_conflict")

        service, _store = _make_service(store=_ConflictStore())
        produced = asyncio.run(service.produce_challenge(
            owner_namespace=OWNER_NS, owner_sub=OWNER_SUB,
            session_id="ses-1", call_id="call-1"))
        self.assertIsNone(produced)


class AuthorizationServiceTests(unittest.TestCase):
    def _error(self, coro) -> int:
        with self.assertRaises(authorization_service.AuthorizationError) as ctx:
            asyncio.run(coro)
        return ctx.exception.status_code

    def test_start_mints_single_use_handle_and_stores_only_the_secret_hash(self) -> None:
        service, store = _make_service(records=[_txn()])
        request = AuthorizationStartRequest(browser_secret=BROWSER_SECRET)

        async def prove():
            response = await service.start(_authorization_settings(), _identity(), CHALLENGE, request)
            self.assertTrue(response.start_token.get_secret_value())
            self.assertLessEqual(response.expires_at, SVC_NOW + timedelta(seconds=60))
            state = store._secrets[CHALLENGE]
            self.assertIsNotNone(state["browser_secret_hash"])
            self.assertNotIn(BROWSER_SECRET, repr(state))

        asyncio.run(prove())

    def test_start_foreign_or_unknown_challenge_is_404(self) -> None:
        service, _store = _make_service(records=[_txn()])
        request = AuthorizationStartRequest(browser_secret=BROWSER_SECRET)
        settings = _authorization_settings()
        # A challenge owned by someone else is indistinguishable from an unknown one.
        self.assertEqual(
            self._error(service.start(settings, _identity("mallory"), CHALLENGE, request)), 404)
        self.assertEqual(
            self._error(service.start(settings, _identity(), OTHER_CHALLENGE, request)), 404)

    def test_start_expired_is_404_and_terminal_is_409(self) -> None:
        settings = _authorization_settings()
        request = AuthorizationStartRequest(browser_secret=BROWSER_SECRET)
        # Expired: a pending challenge read past its expiry flips to expired → 404.
        expired, _ = _make_service(records=[_txn()], now=SVC_NOW + timedelta(seconds=601))
        self.assertEqual(self._error(expired.start(settings, _identity(), CHALLENGE, request)), 404)
        # Terminal (canceled/authorized) challenges are a 409, not a 404 oracle.
        # ``create`` only accepts pending rows, so terminal state is injected directly.
        for terminal in ("canceled", "authorized"):
            store = build_transaction_store(backend="memory", replicas=1)
            store._records[CHALLENGE] = _txn(status=terminal)
            service, _ = _make_service(store=store)
            self.assertEqual(
                self._error(service.start(settings, _identity(), CHALLENGE, request)), 409)

    def test_start_entitlement_gaps_are_403(self) -> None:
        settings = _authorization_settings()
        request = AuthorizationStartRequest(browser_secret=BROWSER_SECRET)
        # No administered owner->target mapping.
        no_link, _ = _make_service(records=[_txn()], custody=_ServiceCustody(linkage={}))
        self.assertEqual(self._error(no_link.start(settings, _identity(), CHALLENGE, request)), 403)
        # Unreadable/invalidated configuration.
        down, _ = _make_service(records=[_txn()],
                                custody=_ServiceCustody(sync_raises=CustodyError("configuration_unavailable")))
        self.assertEqual(self._error(down.start(settings, _identity(), CHALLENGE, request)), 403)
        # A config generation that no longer matches the challenge.
        rolled, _ = _make_service(records=[_txn()], custody=_ServiceCustody(generation="gen2"))
        self.assertEqual(self._error(rolled.start(settings, _identity(), CHALLENGE, request)), 403)

    def test_provider_url_consumes_start_once_with_browser_proof(self) -> None:
        service, store = _make_service(records=[_txn()])
        settings = _authorization_settings()

        async def prove():
            start = await service.start(settings, _identity(), CHALLENGE,
                                        AuthorizationStartRequest(browser_secret=BROWSER_SECRET))
            nav = ProviderUrlRequest(start_token=start.start_token,
                                     browser_bindings={CHALLENGE: SecretStr(BROWSER_SECRET)})
            response = await service.provider_url(nav)
            url = response.provider_url.get_secret_value()
            self.assertIn("state=", url)
            self.assertEqual(service._client.build_calls, 1)
            # A repeated navigation cannot obtain another provider URL.
            with self.assertRaises(authorization_service.AuthorizationError) as ctx:
                await service.provider_url(nav)
            self.assertEqual(ctx.exception.status_code, 404)

        asyncio.run(prove())

    def test_provider_url_preparation_failure_leaves_start_unconsumed(self) -> None:
        service, store = _make_service(records=[_txn()])

        async def prove():
            start = await service.start(_authorization_settings(), _identity(), CHALLENGE,
                                        AuthorizationStartRequest(browser_secret=BROWSER_SECRET))
            nav = ProviderUrlRequest(start_token=start.start_token,
                                     browser_bindings={CHALLENGE: SecretStr(BROWSER_SECRET)})
            before = dict(store._secrets[CHALLENGE])
            with patch("tool_gateway.services.authorization_transaction_store.secrets.token_urlsafe",
                       side_effect=["unreleased-state", CustodyError("injected_preparation_failure")]):
                with self.assertRaises(CustodyError):
                    await service.provider_url(nav)
            self.assertEqual(store._secrets[CHALLENGE], before)
            self.assertEqual(service._client.build_calls, 0)
            self.assertEqual(service._client.exchange_calls, 0)
            self.assertIsNotNone(await service.provider_url(nav))
            self.assertEqual(service._client.build_calls, 1)

        asyncio.run(prove())

    def test_provider_url_wrong_browser_proof_is_404(self) -> None:
        service, _store = _make_service(records=[_txn()])
        settings = _authorization_settings()

        async def prove():
            start = await service.start(settings, _identity(), CHALLENGE,
                                        AuthorizationStartRequest(browser_secret=BROWSER_SECRET))
            nav = ProviderUrlRequest(start_token=start.start_token,
                                     browser_bindings={CHALLENGE: SecretStr("wrong-secret")})
            with self.assertRaises(authorization_service.AuthorizationError) as ctx:
                await service.provider_url(nav)
            self.assertEqual(ctx.exception.status_code, 404)
            self.assertEqual(service._client.build_calls, 0)

        asyncio.run(prove())

    def test_provider_url_rechecks_entitlement_after_acknowledged_preparation(self) -> None:
        service, store = _make_service(records=[_txn()])
        consume = store.consume_start

        async def invalidate_after_preparation(*args, **kwargs):
            prepared = await consume(*args, **kwargs)
            service._custody._generation = "replaced-generation"
            return prepared

        async def prove():
            start = await service.start(_authorization_settings(), _identity(), CHALLENGE,
                                        AuthorizationStartRequest(browser_secret=BROWSER_SECRET))
            nav = ProviderUrlRequest(start_token=start.start_token,
                                     browser_bindings={CHALLENGE: SecretStr(BROWSER_SECRET)})
            with patch.object(store, "consume_start", side_effect=invalidate_after_preparation):
                with self.assertRaises(authorization_service.AuthorizationError) as ctx:
                    await service.provider_url(nav)
                self.assertEqual(ctx.exception.status_code, 403)
            self.assertTrue(store._secrets[CHALLENGE]["start_consumed"])
            self.assertEqual(service._client.build_calls, 0)
            self.assertEqual(service._client.exchange_calls, 0)
            with self.assertRaises(authorization_service.AuthorizationError) as ctx:
                await service.provider_url(nav)
            self.assertEqual(ctx.exception.status_code, 404)

        asyncio.run(prove())

    def test_provider_url_configuration_failure_is_502_and_never_builds_a_url(self) -> None:
        client = _FakeAcquisitionClient(
            url_raises=DelegatedAcquisitionError("configuration_failure", "reserved params"))
        service, _store = _make_service(records=[_txn()], client=client)
        settings = _authorization_settings()

        async def prove():
            start = await service.start(settings, _identity(), CHALLENGE,
                                        AuthorizationStartRequest(browser_secret=BROWSER_SECRET))
            nav = ProviderUrlRequest(start_token=start.start_token,
                                     browser_bindings={CHALLENGE: SecretStr(BROWSER_SECRET)})
            with self.assertRaises(authorization_service.AuthorizationError) as ctx:
                await service.provider_url(nav)
            self.assertEqual(ctx.exception.status_code, 502)

        asyncio.run(prove())

    def test_callback_denial_maps_access_denied_to_canceled_and_others_to_failed(self) -> None:
        for denial, expected in (("access_denied", "canceled"), ("server_error", "failed")):
            service, store = _make_service(records=[_txn()])

            async def prove(denial=denial, expected=expected, service=service, store=store):
                state = await _drive_to_state(store)
                denied = AuthorizationCallbackRequest(
                    state=state.get_secret_value(),
                    browser_bindings={CHALLENGE: SecretStr(BROWSER_SECRET)}, denial=denial)
                response = await service.callback(denied)
                self.assertEqual(response.status, expected)
                self.assertEqual(response.return_url, f"/authorizations/return/{CHALLENGE}")
                row = await store.get(CHALLENGE, OWNER_NS, OWNER_SUB, now=SVC_NOW)
                self.assertEqual(row.status, expected)

            asyncio.run(prove())

    def test_callback_unknown_state_returns_failed_root_without_an_oracle(self) -> None:
        service, store = _make_service(records=[_txn()])

        async def prove():
            bogus = AuthorizationCallbackRequest(state="not-a-real-state",
                                                 browser_bindings={CHALLENGE: SecretStr(BROWSER_SECRET)},
                                                 code="opaque-code")
            response = await service.callback(bogus)
            self.assertEqual(response.status, "failed")
            self.assertEqual(response.return_url, "/")
            self.assertEqual(service._client.exchange_calls, 0)
            # The pending transaction is untouched by an unmatched callback.
            row = await store.get(CHALLENGE, OWNER_NS, OWNER_SUB, now=SVC_NOW)
            self.assertEqual(row.status, "pending")

        asyncio.run(prove())

    def test_callback_code_success_authorizes_and_publishes(self) -> None:
        store = _CompletingStore()
        service, _ = _make_service(records=[_txn()], store=store,
                                   client=_FakeAcquisitionClient(bundle=_bundle()))

        async def prove():
            state = await _drive_to_state(store)
            callback = AuthorizationCallbackRequest(state=state.get_secret_value(),
                                                    browser_bindings={CHALLENGE: SecretStr(BROWSER_SECRET)},
                                                    code="opaque-code")
            response = await service.callback(callback)
            self.assertEqual(response.status, "authorized")
            self.assertEqual(response.return_url, f"/authorizations/return/{CHALLENGE}")
            self.assertEqual(store.complete_calls, 1)
            row = await store.get(CHALLENGE, OWNER_NS, OWNER_SUB, now=SVC_NOW)
            self.assertEqual(row.status, "authorized")

        asyncio.run(prove())

    def test_callback_code_exchange_failure_finishes_failed(self) -> None:
        client = _FakeAcquisitionClient(
            exchange_raises=DelegatedAcquisitionError("invalid_grant", "provider rejected"))
        service, store = _make_service(records=[_txn()], client=client)

        async def prove():
            state = await _drive_to_state(store)
            callback = AuthorizationCallbackRequest(state=state.get_secret_value(),
                                                    browser_bindings={CHALLENGE: SecretStr(BROWSER_SECRET)},
                                                    code="opaque-code")
            response = await service.callback(callback)
            self.assertEqual(response.status, "failed")
            self.assertEqual(response.return_url, f"/authorizations/return/{CHALLENGE}")
            row = await store.get(CHALLENGE, OWNER_NS, OWNER_SUB, now=SVC_NOW)
            self.assertEqual(row.status, "failed")

        asyncio.run(prove())

    def test_status_is_owner_scoped_and_404_for_foreign(self) -> None:
        service, _store = _make_service(records=[_txn()])
        settings = _authorization_settings()

        async def prove():
            projection = await service.status(settings, _identity(), CHALLENGE)
            self.assertEqual(projection.status, "pending")
            self.assertEqual(projection.challenge_id, CHALLENGE)
            self.assertEqual(projection.target, TARGET)
            with self.assertRaises(authorization_service.AuthorizationError) as ctx:
                await service.status(settings, _identity("mallory"), CHALLENGE)
            self.assertEqual(ctx.exception.status_code, 404)

        asyncio.run(prove())

    def test_cancel_is_idempotent_and_no_oracle(self) -> None:
        service, store = _make_service(records=[_txn()])
        settings = _authorization_settings()

        async def prove():
            self.assertIsNone(await service.cancel(settings, _identity(), CHALLENGE))
            row = await store.get(CHALLENGE, OWNER_NS, OWNER_SUB, now=SVC_NOW)
            self.assertEqual(row.status, "canceled")
            # Cancelling again, or a foreign/unknown challenge, never raises nor oracles.
            self.assertIsNone(await service.cancel(settings, _identity(), CHALLENGE))
            self.assertIsNone(await service.cancel(settings, _identity("mallory"), CHALLENGE))
            self.assertIsNone(await service.cancel(settings, _identity(), OTHER_CHALLENGE))

        asyncio.run(prove())

    def test_browser_reset_cancels_only_matching_owned_pending(self) -> None:
        service, store = _make_service(records=[
            _txn(CHALLENGE),
            _txn(OTHER_CHALLENGE, sub="mallory-immutable"),
        ])
        settings = _authorization_settings()

        async def prove():
            # Bind a browser secret to the owned challenge only.
            await store.issue_start(CHALLENGE, OWNER_NS, OWNER_SUB,
                                    browser_secret=SecretStr(BROWSER_SECRET), now=SVC_NOW)
            reset = BrowserResetRequest(browser_bindings={
                CHALLENGE: SecretStr(BROWSER_SECRET),
                OTHER_CHALLENGE: SecretStr(BROWSER_SECRET),
            })
            canceled = await service.browser_reset(settings, _identity(), reset)
            self.assertEqual(canceled, 1)
            owned = await store.get(CHALLENGE, OWNER_NS, OWNER_SUB, now=SVC_NOW)
            self.assertEqual(owned.status, "canceled")
            foreign = await store.get(OTHER_CHALLENGE, OWNER_NS, "mallory-immutable", now=SVC_NOW)
            self.assertEqual(foreign.status, "pending")

        asyncio.run(prove())


# -- Route (HTTP boundary) integration --------------------------------------
#
# These tests drive the real FastAPI app (``create_app``) through ``TestClient``
# with a Memory-backed ``AuthorizationService`` injected on ``app.state`` and
# per-test settings overridden. The focus is the route seam the service tests
# cannot see: the default-off gate failing closed *before* auth, the human vs.
# workload auth wiring, ``targets:authorize`` policy, owner scope, the HTTP status
# mapping, ``no-store`` headers, SecretStr unwrapping at the JSON boundary, and
# end-to-end redaction of every bearer/secret across responses and log sinks.

_START = f"/api/v2/targets/authorizations/{CHALLENGE}/start"
_STATUS = f"/api/v2/targets/authorizations/{CHALLENGE}"
_CANCEL = f"/api/v2/targets/authorizations/{CHALLENGE}/cancel"
_PROVIDER_URL = "/api/v2/targets/authorizations/provider-url"
_CALLBACK = "/api/v2/targets/authorizations/callback"
_BROWSER_RESET = "/api/v2/targets/authorizations/browser-reset"


class AuthorizationRouteTests(unittest.TestCase):
    def setUp(self) -> None:
        reset_policy_state()
        authorization_service.reset_authorization_state()

    def tearDown(self) -> None:
        reset_policy_state()
        authorization_service.reset_authorization_state()

    def _client(self, settings, *, service=None) -> TestClient:
        app = create_app()
        app.dependency_overrides[get_settings] = lambda: settings
        if service is not None:
            # Override the lazily-built Postgres service with a Memory-backed one.
            app.state.authorization_service = service
        return TestClient(app)

    @staticmethod
    def _bearer(token: str) -> dict:
        return {"Authorization": f"Bearer {token}"}

    def _human(self, sub=OWNER_SUB, username="alice", roles=("operator",), **kw) -> str:
        return _mint_human(sub, username, list(roles), **kw)

    # -- gate fails closed before any authentication --------------------------

    def test_disabled_gate_fails_closed_before_auth(self) -> None:
        service, _ = _make_service(records=[_txn()])
        client = self._client(
            _authorization_settings(delegated_authorization_enabled=False), service=service)
        # No bearer at all: the gate refuses before authentication is attempted.
        response = client.post(_START, json={"browser_secret": BROWSER_SECRET})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "target authorization not enabled")

    def test_missing_service_fails_closed(self) -> None:
        # Enabled settings, but create_app() built no service (global gate off) and
        # none is injected: the route fails closed even with a valid human bearer.
        client = self._client(_authorization_settings())
        with _patch_auth_jwks():
            response = client.post(_START, json={"browser_secret": BROWSER_SECRET},
                                   headers=self._bearer(self._human()))
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "target authorization unavailable")

    # -- human-edge authentication and policy ---------------------------------

    def test_start_missing_bearer_is_401(self) -> None:
        service, _ = _make_service(records=[_txn()])
        client = self._client(_authorization_settings(), service=service)
        response = client.post(_START, json={"browser_secret": BROWSER_SECRET})
        self.assertEqual(response.status_code, 401)

    def test_start_development_provenance_is_403(self) -> None:
        service, _ = _make_service(records=[_txn()])
        client = self._client(_authorization_settings(), service=service)
        token = self._human(authentication_source="development")
        with _patch_auth_jwks():
            response = client.post(_START, json={"browser_secret": BROWSER_SECRET},
                                   headers=self._bearer(token))
        self.assertEqual(response.status_code, 403)

    def test_start_auditor_policy_denial_is_403(self) -> None:
        # A genuine, authenticated auditor is denied by targets:authorize policy.
        service, _ = _make_service(records=[_txn()])
        client = self._client(_authorization_settings(), service=service)
        token = self._human(roles=("auditor",))
        with _patch_auth_jwks():
            response = client.post(_START, json={"browser_secret": BROWSER_SECRET},
                                   headers=self._bearer(token))
        self.assertEqual(response.status_code, 403)

    # -- workload-edge authentication -----------------------------------------

    def test_provider_url_missing_workload_bearer_is_401(self) -> None:
        service, _ = _make_service(records=[_txn()])
        client = self._client(_authorization_settings(), service=service)
        response = client.post(_PROVIDER_URL, json={
            "start_token": "handle", "browser_bindings": {CHALLENGE: BROWSER_SECRET}})
        self.assertEqual(response.status_code, 401)

    def test_callback_execution_audience_workload_is_401(self) -> None:
        # An execution-handoff token must never drive the authorization edges.
        service, _ = _make_service(records=[_txn()])
        client = self._client(_authorization_settings(), service=service)
        bad = _mint_auth_workload(aud="luban-target-execution-handoff")
        with _patch_auth_jwks():
            response = client.post(_CALLBACK, json={
                "state": "s", "browser_bindings": {CHALLENGE: BROWSER_SECRET}, "code": "c"},
                headers=self._bearer(bad))
        self.assertEqual(response.status_code, 401)

    # -- owner scope, status mapping, no-store --------------------------------

    def test_status_owner_scope_is_404_no_oracle(self) -> None:
        service, _ = _make_service(records=[_txn()])
        client = self._client(_authorization_settings(), service=service)
        with _patch_auth_jwks():
            foreign = client.get(_STATUS, headers=self._bearer(self._human(sub="mallory-immutable")))
            unknown = client.get(f"/api/v2/targets/authorizations/{OTHER_CHALLENGE}",
                                 headers=self._bearer(self._human()))
        # Wrong-owner and unknown are indistinguishable.
        self.assertEqual(foreign.status_code, 404)
        self.assertEqual(unknown.status_code, 404)

    def test_status_returns_owner_projection_no_store(self) -> None:
        service, _ = _make_service(records=[_txn()])
        client = self._client(_authorization_settings(), service=service)
        with _patch_auth_jwks():
            response = client.get(_STATUS, headers=self._bearer(self._human()))
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["challenge_id"], CHALLENGE)
        self.assertEqual(body["status"], "pending")
        self.assertEqual(body["target"], TARGET)
        self.assertEqual(response.headers["Cache-Control"], "no-store")
        self.assertEqual(response.headers["Referrer-Policy"], "no-referrer")

    def test_cancel_is_204_idempotent_no_oracle(self) -> None:
        service, _ = _make_service(records=[_txn()])
        client = self._client(_authorization_settings(), service=service)
        with _patch_auth_jwks():
            first = client.post(_CANCEL, headers=self._bearer(self._human()))
            again = client.post(_CANCEL, headers=self._bearer(self._human()))
            foreign = client.post(f"/api/v2/targets/authorizations/{OTHER_CHALLENGE}/cancel",
                                  headers=self._bearer(self._human()))
        # Found, spent, and wrong-owner all collapse to a single 204.
        for response in (first, again, foreign):
            self.assertEqual(response.status_code, 204)
            self.assertEqual(response.headers["Cache-Control"], "no-store")

    def test_malformed_challenge_id_is_422(self) -> None:
        service, _ = _make_service(records=[_txn()])
        client = self._client(_authorization_settings(), service=service)
        with _patch_auth_jwks():
            response = client.get("/api/v2/targets/authorizations/not-a-uuid",
                                  headers=self._bearer(self._human()))
        self.assertEqual(response.status_code, 422)

    # -- full handoff through HTTP --------------------------------------------

    def test_full_handoff_start_provider_url_callback(self) -> None:
        store = _CompletingStore()
        service, _ = _make_service(records=[_txn()], store=store,
                                   client=_FakeAcquisitionClient(bundle=_bundle()))
        client = self._client(_authorization_settings(), service=service)
        human, workload = self._human(), _mint_auth_workload()
        with _patch_auth_jwks():
            start = client.post(_START, json={"browser_secret": BROWSER_SECRET},
                                headers=self._bearer(human))
            self.assertEqual(start.status_code, 200)
            start_token = start.json()["start_token"]
            # SecretStr is unwrapped at the JSON boundary, never redacted to stars.
            self.assertTrue(start_token)
            self.assertNotEqual(start_token, "**********")

            nav = client.post(_PROVIDER_URL, json={
                "start_token": start_token, "browser_bindings": {CHALLENGE: BROWSER_SECRET}},
                headers=self._bearer(workload))
            self.assertEqual(nav.status_code, 200)
            provider_url = nav.json()["provider_url"]
            self.assertIn("state=", provider_url)
            state = parse_qs(urlsplit(provider_url).query)["state"][0]

            done = client.post(_CALLBACK, json={
                "state": state, "browser_bindings": {CHALLENGE: BROWSER_SECRET},
                "code": "opaque-code"}, headers=self._bearer(workload))
        self.assertEqual(done.status_code, 200)
        body = done.json()
        self.assertEqual(body["status"], "authorized")
        self.assertEqual(body["return_url"], f"/authorizations/return/{CHALLENGE}")
        self.assertEqual(store.complete_calls, 1)

    def test_callback_unknown_state_returns_failed_root(self) -> None:
        service, _ = _make_service(records=[_txn()])
        client = self._client(_authorization_settings(), service=service)
        with _patch_auth_jwks():
            response = client.post(_CALLBACK, json={
                "state": "bogus-state", "browser_bindings": {CHALLENGE: BROWSER_SECRET},
                "code": "opaque-code"}, headers=self._bearer(_mint_auth_workload()))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "failed", "return_url": "/"})

    def test_browser_reset_cancels_owned_pending_via_http(self) -> None:
        service, _ = _make_service(records=[
            _txn(CHALLENGE), _txn(OTHER_CHALLENGE, sub="mallory-immutable")])
        client = self._client(_authorization_settings(), service=service)
        human = self._human()
        with _patch_auth_jwks():
            started = client.post(_START, json={"browser_secret": BROWSER_SECRET},
                                  headers=self._bearer(human))
            self.assertEqual(started.status_code, 200)
            reset = client.post(_BROWSER_RESET, json={"browser_bindings": {
                CHALLENGE: BROWSER_SECRET, OTHER_CHALLENGE: BROWSER_SECRET}},
                headers=self._bearer(human))
        self.assertEqual(reset.status_code, 200)
        # Only the caller's own matching pending challenge is canceled.
        self.assertEqual(reset.json(), {"canceled": 1})

    # -- redaction across responses and log sinks -----------------------------

    def test_no_bearer_or_secret_leaks_into_response_or_logs(self) -> None:
        service, _ = _make_service(records=[_txn()])
        client = self._client(_authorization_settings(), service=service)
        human, workload = self._human(), _mint_auth_workload()
        with _patch_auth_jwks(), \
                patch("tool_gateway.services.gateway_service.emit_audit_event") as emit, \
                patch("tool_gateway.services.gateway_service.LOGGER") as gw_logger, \
                patch("tool_gateway.services.authorization_service.LOGGER") as auth_logger:
            start = client.post(_START, json={"browser_secret": BROWSER_SECRET},
                                headers=self._bearer(human))
            start_token = start.json()["start_token"]
            nav = client.post(_PROVIDER_URL, json={
                "start_token": start_token, "browser_bindings": {CHALLENGE: BROWSER_SECRET}},
                headers=self._bearer(workload))
        provider_url = nav.json()["provider_url"]
        # No bearer or browser secret reaches any response body.
        for body in (start.text, nav.text):
            self.assertNotIn(human, body)
            self.assertNotIn(workload, body)
            self.assertNotIn(BROWSER_SECRET, body)
        # Nor does any secret reach the policy/authorization log or audit sink. The
        # start handle and provider URL are legitimately returned but never logged.
        sink = (str(emit.call_args_list) + str(gw_logger.info.call_args_list)
                + str(gw_logger.warning.call_args_list)
                + str(auth_logger.info.call_args_list)
                + str(auth_logger.warning.call_args_list))
        for secret in (human, workload, BROWSER_SECRET, start_token, provider_url):
            self.assertNotIn(secret, sink)


class _AuditCapture:
    """Records the bounded kwargs the service hands its ``target_authorization`` emitter.

    ``_emit_authorization`` is the service's only audit hook, so capturing its
    kwargs proves exactly which lifecycle transitions were recorded — and that a
    callback never fabricates a ``tool_invoked`` (that shape carries no
    ``operation``/``authorization_outcome``, and the service has no path to emit
    one).
    """

    def __init__(self) -> None:
        self.events: list[dict] = []

    def __call__(self, **kwargs) -> None:
        self.events.append(kwargs)


class TargetAuthorizationAuditTests(unittest.TestCase):
    """SPEC-070 R-4a/R-4c (plan line 155): the narrowly scoped
    ``target_authorization`` event is emitted ONLY at an actual stored transition
    the service just finalized, with bounded operation/outcome/reason fields, and
    dedupes on the store's single-use finalization. A successful ``authorized`` is
    emitted only from acknowledged publication — never from a callback response
    alone and never as a stand-in ``tool_invoked`` — and an authorization failure
    is recorded as its real outcome, never overstated as a delegated success.
    """

    def test_callback_authorized_emits_single_user_delegated_event(self) -> None:
        store = _CompletingStore()
        audit = _AuditCapture()
        service, _ = _make_service(
            records=[_txn()], store=store, audit=audit,
            client=_FakeAcquisitionClient(bundle=_bundle()))

        async def prove():
            state = await _drive_to_state(store)
            callback = AuthorizationCallbackRequest(
                state=state.get_secret_value(),
                browser_bindings={CHALLENGE: SecretStr(BROWSER_SECRET)},
                code="opaque-code")
            response = await service.callback(callback)
            self.assertEqual(response.status, "authorized")

        asyncio.run(prove())
        # Acknowledged publication is the ONLY authority that records a delegated
        # success, and it records exactly one.
        self.assertEqual(len(audit.events), 1)
        event = audit.events[0]
        self.assertEqual(event["operation"], "enroll")
        self.assertEqual(event["authorization_outcome"], "authorized")
        self.assertEqual(event["delegation_mode"], "user_delegated")
        self.assertIsNone(event["reason"])
        # Correlation rides separate bounded fields; no bearer/code/state/verifier/
        # browser secret/provider URL/owner namespace is present.
        self.assertEqual(event["challenge_id"], CHALLENGE)
        self.assertEqual(event["target"], TARGET)
        self.assertEqual(event["session_id"], "ses-1")
        self.assertEqual(event["owner_sub"], OWNER_SUB)
        self.assertNotIn(OWNER_NS, str(event))

    def test_callback_denial_emits_canceled_with_bounded_reason(self) -> None:
        audit = _AuditCapture()
        service, store = _make_service(records=[_txn()], audit=audit)

        async def prove():
            state = await _drive_to_state(store)
            callback = AuthorizationCallbackRequest(
                state=state.get_secret_value(),
                browser_bindings={CHALLENGE: SecretStr(BROWSER_SECRET)},
                denial="access_denied")
            response = await service.callback(callback)
            self.assertEqual(response.status, "canceled")

        asyncio.run(prove())
        self.assertEqual(len(audit.events), 1)
        event = audit.events[0]
        self.assertEqual(event["operation"], "enroll")
        self.assertEqual(event["authorization_outcome"], "canceled")
        # The bounded DenialReason literal, never the provider's free text.
        self.assertEqual(event["reason"], "access_denied")
        # A denial/cancel is never overstated as a delegated success.
        self.assertIsNone(event["delegation_mode"])

    def test_callback_exchange_failure_emits_failed_with_reason(self) -> None:
        audit = _AuditCapture()
        client = _FakeAcquisitionClient(
            exchange_raises=DelegatedAcquisitionError("invalid_grant", "provider rejected"))
        service, store = _make_service(records=[_txn()], client=client, audit=audit)

        async def prove():
            state = await _drive_to_state(store)
            callback = AuthorizationCallbackRequest(
                state=state.get_secret_value(),
                browser_bindings={CHALLENGE: SecretStr(BROWSER_SECRET)},
                code="opaque-code")
            response = await service.callback(callback)
            self.assertEqual(response.status, "failed")

        asyncio.run(prove())
        self.assertEqual(len(audit.events), 1)
        event = audit.events[0]
        self.assertEqual(event["operation"], "enroll")
        self.assertEqual(event["authorization_outcome"], "failed")
        self.assertEqual(event["reason"], "code_exchange_failed")
        self.assertIsNone(event["delegation_mode"])
        # The provider's error_description free text never reaches the reason.
        self.assertNotIn("provider rejected", str(event))

    def test_owner_cancel_emits_once_and_dedupes_on_repeat(self) -> None:
        audit = _AuditCapture()
        service, _store = _make_service(records=[_txn()], audit=audit)
        settings = _authorization_settings()

        async def prove():
            self.assertIsNone(await service.cancel(settings, _identity(), CHALLENGE))
            # A repeat cancel and a foreign/unknown challenge finalize nothing, so
            # the single-use store transition emits exactly once (idempotent 204).
            self.assertIsNone(await service.cancel(settings, _identity(), CHALLENGE))
            self.assertIsNone(await service.cancel(settings, _identity("mallory"), CHALLENGE))
            self.assertIsNone(await service.cancel(settings, _identity(), OTHER_CHALLENGE))

        asyncio.run(prove())
        self.assertEqual(len(audit.events), 1)
        event = audit.events[0]
        self.assertEqual(event["operation"], "cancel")
        self.assertEqual(event["authorization_outcome"], "canceled")
        self.assertEqual(event["challenge_id"], CHALLENGE)
        self.assertEqual(event["target"], TARGET)
        self.assertEqual(event["owner_sub"], OWNER_SUB)
        self.assertIsNone(event["delegation_mode"])

    def test_no_emitter_wired_is_inert(self) -> None:
        # The default construction (no audit emitter) stays inert and byte-identical:
        # an authorized callback still succeeds and records nothing.
        store = _CompletingStore()
        service, _ = _make_service(
            records=[_txn()], store=store,
            client=_FakeAcquisitionClient(bundle=_bundle()))

        async def prove():
            state = await _drive_to_state(store)
            callback = AuthorizationCallbackRequest(
                state=state.get_secret_value(),
                browser_bindings={CHALLENGE: SecretStr(BROWSER_SECRET)},
                code="opaque-code")
            response = await service.callback(callback)
            self.assertEqual(response.status, "authorized")

        asyncio.run(prove())

    def test_app_emitter_maps_lifecycle_outcomes_to_audit_envelope(self) -> None:
        # The emitter the service actually receives from ``app`` maps a bounded
        # lifecycle outcome onto the canonical audit envelope: a
        # ``target_authorization`` event_type, top-level ``outcome`` success only for
        # ``authorized`` (a cancel is an error, never a delegated success), the
        # bounded correlation on ``details``, and the top-level ``delegation_mode``
        # omitted when unset so it is never an assertion of ``none``.
        from tool_gateway.app import _target_authorization_emitter

        captured: list[dict] = []
        with patch("tool_gateway.services.audit_emitter.emit_audit_event",
                   side_effect=lambda _settings, event: captured.append(event)):
            emitter = _target_authorization_emitter(_authorization_settings())
            emitter(operation="enroll", authorization_outcome="authorized",
                    challenge_id=CHALLENGE, target=TARGET, session_id="ses-1",
                    owner_sub=OWNER_SUB, reason=None, delegation_mode="user_delegated")
            emitter(operation="cancel", authorization_outcome="canceled",
                    challenge_id=CHALLENGE, target=TARGET, session_id="ses-1",
                    owner_sub=OWNER_SUB, reason="access_denied", delegation_mode=None)

        self.assertEqual(len(captured), 2)
        authorized, canceled = captured
        self.assertEqual(authorized["event_type"], "target_authorization")
        self.assertEqual(authorized["outcome"], "success")
        self.assertEqual(authorized["subject"], OWNER_SUB)
        self.assertEqual(authorized["session_id"], "ses-1")
        self.assertEqual(authorized["delegation_mode"], "user_delegated")
        self.assertEqual(authorized["details"], {
            "operation": "enroll", "authorization_outcome": "authorized",
            "challenge_id": CHALLENGE, "target": TARGET})
        self.assertEqual(canceled["event_type"], "target_authorization")
        self.assertEqual(canceled["outcome"], "error")
        self.assertNotIn("delegation_mode", canceled)
        self.assertEqual(canceled["details"], {
            "operation": "cancel", "authorization_outcome": "canceled",
            "challenge_id": CHALLENGE, "target": TARGET, "reason": "access_denied"})
        # SPEC-070 plan line 156 end-to-end link: both real lifecycle envelopes must
        # satisfy the shared audit-event contract the audit-service ingestion model is
        # bound to, so what the gateway emits is exactly what audit ingests/persists/
        # queries — the ``authorized`` success carrying its top-level mode and the
        # ``canceled`` error omitting it (never an assertion of ``none``).
        import json
        from pathlib import Path

        import jsonschema

        schema = json.loads((Path(__file__).resolve().parents[3] / "shared" /
                             "shared-contracts/schemas/audit-event.schema.json").read_text())
        jsonschema.validate(authorized, schema)
        jsonschema.validate(canceled, schema)


if __name__ == "__main__":
    unittest.main()
