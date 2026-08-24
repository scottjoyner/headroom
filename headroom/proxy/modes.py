"""Proxy run mode helpers.

Canonical modes:
- token: prioritize compression (history may be rewritten for max savings)
- cache: prioritize provider prefix cache stability (freeze prior turns)

The mode default is provider-aware: remote/SaaS targets stay cache-first,
while local/self-hosted targets default to token-first compression.
"""

from __future__ import annotations

import ipaddress
import logging
from urllib.parse import urlparse

from headroom.proxy.proxy_mode_policy import (
    PROXY_MODE_CACHE,
    PROXY_MODE_TOKEN,
    normalize_proxy_mode_decision,
)

logger = logging.getLogger("headroom.proxy")

_LOCAL_HOST_SUFFIXES = (".local", ".lan", ".internal", ".home.arpa", ".ts.net")
_LOCAL_HOSTNAMES = {"localhost", "ip6-localhost", "ip6-loopback"}
_TAILSCALE_CGNAT = ipaddress.ip_network("100.64.0.0/10")


def normalize_proxy_mode(mode: str | None, *, default: str = PROXY_MODE_TOKEN) -> str:
    """Normalize a user-provided proxy mode to canonical token/cache values."""
    decision = normalize_proxy_mode_decision(mode, default=default)
    if decision.unknown:
        logger.warning("Unknown HEADROOM_MODE '%s', falling back to '%s'", mode, default)
    elif decision.alias_used:
        logger.info("HEADROOM_MODE alias '%s' normalized to '%s'", mode, decision.normalized)
    return decision.normalized


def is_token_mode(mode: str | None) -> bool:
    """Return True when mode resolves to token mode."""
    return normalize_proxy_mode(mode) == PROXY_MODE_TOKEN


def is_cache_mode(mode: str | None) -> bool:
    """Return True when mode resolves to cache mode."""
    return normalize_proxy_mode(mode) == PROXY_MODE_CACHE


def is_local_upstream_url(upstream_url: str | None) -> bool:
    """Return True when the upstream looks like a local or self-hosted target.

    We treat loopback, private/LAN ranges, Tailscale CGNAT addresses, and common
    local DNS suffixes as self-hosted. Everything else is considered remote.
    """

    if not upstream_url:
        return False

    parsed = urlparse(upstream_url)
    host = parsed.hostname or ""
    if not host:
        return False

    host = host.strip().lower().strip(".")
    if host in _LOCAL_HOSTNAMES or any(host.endswith(suffix) for suffix in _LOCAL_HOST_SUFFIXES):
        return True

    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False

    return (
        ip.is_loopback
        or ip.is_private
        or ip.is_link_local
        or ip in _TAILSCALE_CGNAT
    )


def classify_upstream_lane(upstream_url: str | None) -> str:
    """Classify the upstream lane for telemetry.

    Returns ``local`` for self-hosted/private targets and ``remote`` otherwise.
    """

    return "local" if is_local_upstream_url(upstream_url) else "remote"


def default_proxy_mode_for_upstream(upstream_url: str | None) -> str:
    """Pick the default proxy mode for a target URL.

    Local/self-hosted upstreams default to token mode because the local lane is
    the place where we want aggressive compression. Remote/SaaS upstreams stay
    cache-first so we preserve KV/prefix cache hits.
    """

    return PROXY_MODE_TOKEN if is_local_upstream_url(upstream_url) else PROXY_MODE_CACHE
