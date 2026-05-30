"""AES-256-GCM encryption for user OpenRouter keys and other secrets."""

import os
import secrets
from base64 import b64decode, b64encode

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from workbench.core.config import WorkbenchConfig

_aes_key: bytes | None = None


def init_encryption(config: WorkbenchConfig) -> None:
    global _aes_key
    raw = config.encryption_key
    if not raw:
        raise RuntimeError("ENCRYPTION_KEY is not set — check .env or WORKBENCH_ENCRYPTION_KEY")
    try:
        _aes_key = bytes.fromhex(raw)
    except ValueError:
        _aes_key = raw.encode("utf-8").ljust(32, b"\x00")[:32]
    if len(_aes_key) != 32:
        raise RuntimeError(f"ENCRYPTION_KEY must be 32 bytes (64 hex chars), got {len(_aes_key)} bytes")


def _get_key() -> bytes:
    if _aes_key is None:
        raise RuntimeError("Encryption not initialized")
    return _aes_key


def encrypt(plaintext: str) -> str:
    key = _get_key()
    nonce = os.urandom(12)
    cipher = Cipher(algorithms.AES(key), modes.GCM(nonce))
    encryptor = cipher.encryptor()
    ciphertext = encryptor.update(plaintext.encode("utf-8")) + encryptor.finalize()
    return b64encode(nonce + encryptor.tag + ciphertext).decode("ascii")


def decrypt(packed: str) -> str:
    key = _get_key()
    raw = b64decode(packed)
    nonce, tag, ciphertext = raw[:12], raw[12:28], raw[28:]
    cipher = Cipher(algorithms.AES(key), modes.GCM(nonce, tag))
    decryptor = cipher.decryptor()
    return (decryptor.update(ciphertext) + decryptor.finalize()).decode("utf-8")
