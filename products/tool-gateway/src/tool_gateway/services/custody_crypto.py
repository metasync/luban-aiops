"""Versioned authenticated custody envelopes; no retained-key fallback."""
from __future__ import annotations

import base64
import binascii
import hashlib
import json
import os
import re
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Mapping

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from pydantic import SecretStr

from tool_gateway.tools.delegated_configuration import ConfigurationError, read_json


class CustodyError(ValueError):
    """Fixed failure classes only; never wrap provider/driver messages."""


def capability_hash(value: SecretStr) -> str:
    return hashlib.sha256(value.get_secret_value().encode()).hexdigest()


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


@dataclass(frozen=True, repr=False)
class KeySnapshot:
    active_key_id: str
    recovery_epoch: str
    fingerprint_key: bytes = field(repr=False)
    keys: Mapping[str, bytes] = field(repr=False)

    def encrypt(self, secret: SecretStr, purpose: str, binding: dict) -> bytes:
        raw = secret.get_secret_value()
        if not raw or len(raw.encode()) > 65536:
            raise CustodyError("invalid_secret")
        header = canonical([1, self.active_key_id, self.recovery_epoch])
        nonce = os.urandom(12)
        aad = canonical(["luban-custody", 1, self.active_key_id, self.recovery_epoch, purpose, binding])
        ciphertext = AESGCM(self.keys[self.active_key_id]).encrypt(nonce, raw.encode(), aad)
        return len(header).to_bytes(2, "big") + header + nonce + ciphertext

    def decrypt(self, blob: bytes, purpose: str, binding: dict) -> SecretStr:
        try:
            length = int.from_bytes(blob[:2], "big")
            version, key_id, epoch = json.loads(blob[2:2 + length])
            if version != 1 or epoch != self.recovery_epoch:
                raise ValueError
            nonce = blob[2 + length:14 + length]
            aad = canonical(["luban-custody", 1, key_id, epoch, purpose, binding])
            raw = AESGCM(self.keys[key_id]).decrypt(nonce, blob[14 + length:], aad)
            return SecretStr(raw.decode())
        except (ValueError, TypeError, KeyError, UnicodeError, InvalidTag):
            raise CustodyError("decryption_failed") from None


class Keyring:
    def __init__(self, path: str):
        self._path = path

    def snapshot(self) -> KeySnapshot:
        try:
            data = read_json(self._path)
            if not isinstance(data, dict) or set(data) != {"active_key_id", "recovery_epoch", "fingerprint_key", "keys"}:
                raise ValueError
            for key in ("active_key_id", "recovery_epoch"):
                if not isinstance(data[key], str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", data[key]):
                    raise ValueError
            if not isinstance(data["keys"], dict) or not 1 <= len(data["keys"]) <= 32:
                raise ValueError
            keys = {}
            for key_id, encoded in data["keys"].items():
                if not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", key_id) or not isinstance(encoded, str):
                    raise ValueError
                raw = base64.b64decode(encoded, validate=True)
                if len(raw) != 32:
                    raise ValueError
                keys[key_id] = raw
            if not isinstance(data["fingerprint_key"], str):
                raise ValueError
            fingerprint = base64.b64decode(data["fingerprint_key"], validate=True)
            if len(fingerprint) != 32 or data["active_key_id"] not in keys:
                raise ValueError
            return KeySnapshot(data["active_key_id"], data["recovery_epoch"], fingerprint, MappingProxyType(keys))
        except (ConfigurationError, ValueError, TypeError, KeyError, binascii.Error):
            raise CustodyError("keyring_unavailable") from None

    def encrypt(self, secret: SecretStr, purpose: str, binding: dict) -> bytes:
        return self.snapshot().encrypt(secret, purpose, binding)

    def decrypt(self, blob: bytes, purpose: str, binding: dict) -> SecretStr:
        return self.snapshot().decrypt(blob, purpose, binding)
