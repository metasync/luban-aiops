"""SPEC-070 acquisition — lifespan wiring of the user-delegated client.

Plan §"Runtime composition and bounds" (line 73): *wire a separate user-delegated
client into the tool-gateway lifespan and the existing HTTP/MCP authentication
seam; keep the machine-grant client unchanged.* Delegated mode stays **off**
until Postgres custody and the versioned key mount are configured (line 76), so
these tests prove:

* the client factory returns ``None`` by default, and a delegated set therefore
  fails closed at the connector (never a machine grant, never a reauth loop);
* enabling acquisition without the full custody runtime fails closed at startup;
* a fully configured gate composes a real :class:`UserDelegatedClient` over a
  :class:`PostgresCustodyStore` bound to the administered set — with **no**
  database or provider connection opened at construction;
* ``_build_tool_registry`` threads that one client into both the HTTP connector
  and the Ansible MCP binding.
"""

import os
import types
import unittest
from unittest.mock import patch

from tool_gateway.app import _build_delegated_client, _build_tool_registry
from tool_gateway.core.config import GatewaySettings
from tool_gateway.services.custody_crypto import Keyring
from tool_gateway.services.delegated_custody import PostgresCustodyStore
from tool_gateway.tools.user_delegated_client import UserDelegatedClient

DB_URL = "postgresql://gateway@db.internal:5432/gateway"
KEYRING_PATH = "/etc/tool-gateway/delegated-keyring.json"
CONFIG_PATH = "/etc/tool-gateway/delegated.json"
SET_ID = "ansible-prod"
TRUSTED_CALLBACK = "https://gw.internal/api/v1/targets/authorizations/callback"


def _acquisition_settings(**overrides) -> GatewaySettings:
    kwargs = dict(
        delegated_acquisition_enabled=True,
        delegated_custody_db_url=DB_URL,
        delegated_custody_keyring_path=KEYRING_PATH,
        delegated_custody_config_path=CONFIG_PATH,
        delegated_custody_set_id=SET_ID,
        delegated_custody_trusted_callback=TRUSTED_CALLBACK,
    )
    kwargs.update(overrides)
    return GatewaySettings(**kwargs)


class DelegatedAcquisitionGateTests(unittest.TestCase):
    def test_disabled_by_default(self) -> None:
        settings = GatewaySettings()
        self.assertFalse(settings.delegated_acquisition_enabled)
        self.assertEqual(settings.delegated_custody_db_url, "")
        # A disabled gate composes no client, so a delegated set fails closed.
        self.assertIsNone(_build_delegated_client(settings))

    def test_enabled_without_custody_runtime_raises(self) -> None:
        with self.assertRaises(ValueError):
            GatewaySettings(delegated_acquisition_enabled=True)

    def test_enabled_without_keyring_raises(self) -> None:
        with self.assertRaises(ValueError):
            _acquisition_settings(delegated_custody_keyring_path="")

    def test_enabled_without_set_id_raises(self) -> None:
        with self.assertRaises(ValueError):
            _acquisition_settings(delegated_custody_set_id="")

    def test_enabled_with_non_postgres_dsn_raises(self) -> None:
        with self.assertRaises(ValueError):
            _acquisition_settings(delegated_custody_db_url="sqlite:///gateway.db")

    def test_enabled_with_wrong_callback_path_raises(self) -> None:
        with self.assertRaises(ValueError):
            _acquisition_settings(
                delegated_custody_trusted_callback="https://gw.internal/api/v1/wrong"
            )

    def test_enabled_with_insecure_callback_raises(self) -> None:
        with self.assertRaises(ValueError):
            _acquisition_settings(
                delegated_custody_trusted_callback=(
                    "http://gw.internal/api/v1/targets/authorizations/callback"
                )
            )


class DelegatedClientFactoryTests(unittest.TestCase):
    def test_full_configuration_composes_custody_backed_client(self) -> None:
        # Construction is side-effect free: no DB socket, no keyring read, no
        # provider call — the custody store connects lazily per acquisition.
        client = _build_delegated_client(_acquisition_settings())
        self.assertIsInstance(client, UserDelegatedClient)
        custody = client._custody
        self.assertIsInstance(custody, PostgresCustodyStore)
        self.assertEqual(custody.set_id, SET_ID)
        self.assertEqual(custody._db_url, DB_URL)
        self.assertEqual(custody.config_path, CONFIG_PATH)
        self.assertEqual(custody.trusted_callback, TRUSTED_CALLBACK)
        self.assertIsInstance(custody.keyring, Keyring)


class DelegatedAcquisitionEnvTests(unittest.TestCase):
    def test_from_env_maps_the_custody_runtime(self) -> None:
        env = {
            "GATEWAY_DELEGATED_ACQUISITION_ENABLED": "true",
            "GATEWAY_DELEGATED_CUSTODY_DB_URL": DB_URL,
            "GATEWAY_DELEGATED_CUSTODY_KEYRING_PATH": KEYRING_PATH,
            "GATEWAY_DELEGATED_CUSTODY_CONFIG_PATH": CONFIG_PATH,
            "GATEWAY_DELEGATED_CUSTODY_SET_ID": SET_ID,
            "GATEWAY_DELEGATED_CUSTODY_TRUSTED_CALLBACK": TRUSTED_CALLBACK,
        }
        with patch.dict(os.environ, env):
            settings = GatewaySettings.from_env()
        self.assertTrue(settings.delegated_acquisition_enabled)
        self.assertEqual(settings.delegated_custody_db_url, DB_URL)
        self.assertEqual(settings.delegated_custody_keyring_path, KEYRING_PATH)
        self.assertEqual(settings.delegated_custody_config_path, CONFIG_PATH)
        self.assertEqual(settings.delegated_custody_set_id, SET_ID)
        self.assertEqual(settings.delegated_custody_trusted_callback, TRUSTED_CALLBACK)


class RegistryWiringTests(unittest.TestCase):
    def test_ansible_binding_threads_delegated_client(self) -> None:
        from tool_gateway.ingestion.ansible_binding import (
            build_ansible_mcp_connector,
        )

        sentinel = object()
        connector = build_ansible_mcp_connector(
            GatewaySettings(), delegated_client=sentinel
        )
        self.assertIs(connector._delegated, sentinel)

    def test_registry_injects_one_client_into_http_and_mcp(self) -> None:
        settings = GatewaySettings(http_enabled=True, ansible_mcp_enabled=True)
        sentinel = object()
        captured: dict = {}

        class _FakeHttpConnector:
            def __init__(self, **kwargs):
                captured["http"] = kwargs.get("delegated_client")

            def register_tools(self, registry):
                return None

        def _fake_ansible(settings, *, delegated_client=None):
            captured["ansible"] = delegated_client
            return types.SimpleNamespace(register_tools=lambda registry: None)

        with patch("tool_gateway.app.get_settings", return_value=settings), \
                patch("tool_gateway.app._build_delegated_client", return_value=sentinel), \
                patch("tool_gateway.tools.http_connector.HttpConnector", _FakeHttpConnector), \
                patch(
                    "tool_gateway.ingestion.ansible_binding.build_ansible_mcp_connector",
                    _fake_ansible,
                ):
            _build_tool_registry()

        self.assertIs(captured["http"], sentinel)
        self.assertIs(captured["ansible"], sentinel)


if __name__ == "__main__":
    unittest.main()
