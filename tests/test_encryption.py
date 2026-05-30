"""Tests for workbench.core.encryption."""

import secrets

import pytest

from workbench.core.config import WorkbenchConfig
from workbench.core.encryption import decrypt, encrypt, init_encryption


def test_encrypt_decrypt_round_trip():
    key = secrets.token_hex(32)
    cfg = WorkbenchConfig(encryption_key=key)
    init_encryption(cfg)

    plaintext = "sk-or-v1-my-secret-api-key-12345"
    ciphertext = encrypt(plaintext)

    assert ciphertext != plaintext
    assert len(ciphertext) > 0
    assert decrypt(ciphertext) == plaintext


def test_encrypt_produces_different_ciphertexts():
    key = secrets.token_hex(32)
    cfg = WorkbenchConfig(encryption_key=key)
    init_encryption(cfg)

    plaintext = "my-secret"
    ct1 = encrypt(plaintext)
    ct2 = encrypt(plaintext)

    assert ct1 != ct2
    assert decrypt(ct1) == plaintext
    assert decrypt(ct2) == plaintext


def test_encrypt_empty_string():
    key = secrets.token_hex(32)
    cfg = WorkbenchConfig(encryption_key=key)
    init_encryption(cfg)

    ciphertext = encrypt("")
    assert decrypt(ciphertext) == ""


def test_encrypt_special_characters():
    key = secrets.token_hex(32)
    cfg = WorkbenchConfig(encryption_key=key)
    init_encryption(cfg)

    plaintext = "key\nwith\ttabs\r\nand unicode: cafe\u0301 \U0001F600"
    ciphertext = encrypt(plaintext)
    assert decrypt(ciphertext) == plaintext


def test_encrypt_long_text():
    key = secrets.token_hex(32)
    cfg = WorkbenchConfig(encryption_key=key)
    init_encryption(cfg)

    plaintext = "x" * 10000
    ciphertext = encrypt(plaintext)
    assert decrypt(ciphertext) == plaintext


def test_init_with_non_hex_key():
    key = "my-short-passphrase"
    cfg = WorkbenchConfig(encryption_key=key)
    init_encryption(cfg)

    plaintext = "test-value"
    ciphertext = encrypt(plaintext)
    assert decrypt(ciphertext) == plaintext


def test_init_with_exactly_32_byte_hex_key():
    key = "aa" * 32
    cfg = WorkbenchConfig(encryption_key=key)
    init_encryption(cfg)

    plaintext = "test-value"
    assert decrypt(encrypt(plaintext)) == plaintext


def test_uninitialized_raises():
    import workbench.core.encryption as enc_mod
    enc_mod._aes_key = None

    with pytest.raises(RuntimeError, match="Encryption not initialized"):
        enc_mod._get_key()


def test_empty_key_raises():
    import workbench.core.encryption as enc_mod
    enc_mod._aes_key = None

    cfg = WorkbenchConfig(encryption_key="")
    with pytest.raises(RuntimeError, match="ENCRYPTION_KEY"):
        init_encryption(cfg)
