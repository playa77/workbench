"""Shared rate limiter — slowapi Limiter singleton for use across route modules."""

from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address, default_limits=[])
