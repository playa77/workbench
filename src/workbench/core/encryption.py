"""AES-256-GCM encryption for user OpenRouter keys and other secrets."""

import logging
import os
from base64 import b64decode, b64encode

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from workbench.core.config import WorkbenchConfig

logger = logging.getLogger(__name__)

_aes_key: bytes | None = None

_APP_SALT = b"workbench.aes.key.v1"


def init_encryption(config: WorkbenchConfig) -> None:
    global _aes_key
    raw = config.encryption_key
    if not raw:
        raise RuntimeError(
            "ENCRYPTION_KEY is not set -- check .env or WORKBENCH_ENCRYPTION_KEY"
        )
    try:
        _aes_key = bytes.fromhex(raw)
    except ValueError:
        logger.warning(
            "ENCRYPTION_KEY is not valid hex. Using PBKDF2-HMAC-SHA256 key "
            "derivation with %d iterations. Generating a 64-char hex key "
            "is strongly recommended: python -c "
            "\"import secrets; print(secrets.token_hex(32))\"",
            600_000,
        )
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=_APP_SALT,
            iterations=600_000,
        )
        _aes_key = kdf.derive(raw.encode("utf-8"))
    if len(_aes_key) != 32:
        raise RuntimeError(
            f"ENCRYPTION_KEY must be 32 bytes (64 hex chars), got {len(_aes_key)} bytes"
        )


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


_encrypt_reports: bool = False


def set_encrypt_reports(enabled: bool) -> None:
    global _encrypt_reports
    _encrypt_reports = enabled


def encrypt_report_content(plaintext: str) -> str:
    if _encrypt_reports:
        return encrypt(plaintext)
    return plaintext


def decrypt_report_content(packed: str) -> str:
    if _encrypt_reports:
        return decrypt(packed)
    return packed
