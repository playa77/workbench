"""Network validation utilities — anti-SSRF URL validation for public-facing deployments."""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

_BLOCKED_NETWORKS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("100.64.0.0/10"),
    ipaddress.ip_network("198.18.0.0/15"),
]

_BLOCKED_IPV6_NETWORKS = [
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fe80::/10"),
    ipaddress.ip_network("fc00::/7"),
]


def _is_private_ip(host: str) -> bool:
    """Check if an IP address falls within a blocked private/internal network."""
    try:
        addr = ipaddress.ip_address(host)
    except ValueError:
        return False

    if addr.version == 4:
        return any(addr in net for net in _BLOCKED_NETWORKS)
    return any(addr in net for net in _BLOCKED_IPV6_NETWORKS)


def validate_public_url(raw_url: str) -> str:
    """Validate that *raw_url* points to a publicly reachable host.

    Resolves both IPv4 and IPv6 addresses and rejects any URL whose
    resolved IP falls within reserved private ranges (RFC 1918, link-local,
    loopback, or cloud metadata endpoints).

    Returns the sanitized URL on success.

    Raises:
        ValueError: If the URL is invalid, unresolvable, or points to a
            private/internal address.
    """
    parsed = urlparse(raw_url)

    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"URL scheme must be http or https, got: {parsed.scheme}")

    hostname = parsed.hostname
    if not hostname:
        raise ValueError("URL has no resolvable hostname")

    try:
        ip_list = socket.getaddrinfo(hostname, None, 0, socket.SOCK_STREAM)
    except socket.gaierror:
        raise ValueError(f"Cannot resolve hostname: {hostname}") from None

    resolved_ips = {addr[4][0] for addr in ip_list}

    for ip_str in resolved_ips:
        if _is_private_ip(ip_str):
            raise ValueError(
                f"URL resolves to internal/private IP ({ip_str}). "
                "Only publicly routable addresses are allowed."
            )

    return raw_url
