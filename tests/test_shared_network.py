"""Tests for shared.network — SSRF protection and URL validation."""

import socket
from unittest.mock import patch

import pytest

from workbench.shared.network import _is_private_ip, validate_public_url


# ---- _is_private_ip ----


def test_private_ip_10():
    assert _is_private_ip("10.0.0.1") is True


def test_private_ip_172_16():
    assert _is_private_ip("172.16.0.1") is True


def test_private_ip_192_168():
    assert _is_private_ip("192.168.1.1") is True


def test_private_ip_127():
    assert _is_private_ip("127.0.0.1") is True


def test_private_ip_link_local():
    assert _is_private_ip("169.254.1.1") is True


def test_public_ip():
    assert _is_private_ip("8.8.8.8") is False


def test_invalid_ip():
    assert _is_private_ip("not-an-ip") is False


def test_private_ipv6_loopback():
    assert _is_private_ip("::1") is True


def test_private_ipv6_link_local():
    assert _is_private_ip("fe80::1") is True


def test_private_ipv6_ula():
    assert _is_private_ip("fc00::1") is True


# ---- validate_public_url ----


def test_validate_public_url_bad_scheme():
    with pytest.raises(ValueError, match="scheme"):
        validate_public_url("ftp://example.com")


def test_validate_public_url_no_hostname():
    with pytest.raises(ValueError, match="hostname"):
        validate_public_url("http://")


def test_validate_public_url_unresolvable():
    with patch("workbench.shared.network.socket.getaddrinfo", side_effect=socket.gaierror("fail")):
        with pytest.raises(ValueError, match="Cannot resolve"):
            validate_public_url("https://nonexistent.domain.example")


def test_validate_public_url_private_ip():
    with patch("workbench.shared.network.socket.getaddrinfo", return_value=[
        (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 80)),
    ]):
        with pytest.raises(ValueError, match="internal/private"):
            validate_public_url("https://localhost")


def test_validate_public_url_public_ip():
    with patch("workbench.shared.network.socket.getaddrinfo", return_value=[
        (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 443)),
    ]):
        result = validate_public_url("https://example.com")
    assert result == "https://example.com"
