"""ARC-051 URL validator — SSRF protection for target endpoints (SRS-SEC-004, NFR-009).

Resolve the hostname before connecting; reject loopback, private, link-local, multicast, reserved,
unspecified and cloud-metadata ranges; reject non-wss schemes outside development; re-resolve at
connection time and compare against the validated address set to defeat DNS rebinding. Ambiguous
resolution denies.
"""

from __future__ import annotations

import ipaddress
import socket
from dataclasses import dataclass
from urllib.parse import urlparse

METADATA_HOSTS = {"metadata.google.internal", "metadata", "instance-data"}
METADATA_IPS = {ipaddress.ip_address("169.254.169.254"), ipaddress.ip_address("fd00:ec2::254"),
                ipaddress.ip_address("100.100.100.200")}


class SSRFBlocked(ValueError):
    def __init__(self, host_class: str, detail: str):
        super().__init__(f"{host_class}: {detail}")
        self.host_class = host_class


@dataclass(frozen=True)
class ValidatedURL:
    url: str
    scheme: str
    host: str
    port: int
    addresses: frozenset[str]


def classify(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> str | None:
    if ip in METADATA_IPS:
        return "cloud_metadata"
    if ip.is_loopback:
        return "loopback"
    if ip.is_link_local:
        return "link_local"
    if ip.is_private:
        return "private"
    if ip.is_multicast:
        return "multicast"
    if ip.is_reserved or ip.is_unspecified:
        return "reserved"
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        return classify(ip.ipv4_mapped)
    return None


def _resolve(host: str, port: int) -> set[str]:
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror as e:
        raise SSRFBlocked("unresolvable", f"{host}: {e}") from None
    return {str(info[4][0]) for info in infos}


def validate(url: str, environment: str, allowed_schemes: tuple[str, ...] = ("wss",),
             allow_hosts: frozenset[str] = frozenset()) -> ValidatedURL:
    p = urlparse(url)
    scheme = (p.scheme or "").lower()
    host = (p.hostname or "").lower()
    if not host:
        raise SSRFBlocked("invalid", "URL has no host")
    port = p.port or (443 if scheme in ("wss", "https") else 80)
    dev_loopback = environment == "development" and scheme == "ws" and host in ("127.0.0.1", "localhost", "::1")
    if scheme not in allowed_schemes and not dev_loopback:
        raise SSRFBlocked("scheme", f"scheme '{scheme}' not permitted; use {', '.join(allowed_schemes)}")
    if p.username or p.password:
        raise SSRFBlocked("invalid", "credentials in URL are not permitted")
    if host in METADATA_HOSTS:
        raise SSRFBlocked("cloud_metadata", host)
    addrs = _resolve(host, port)
    if not addrs:
        raise SSRFBlocked("unresolvable", host)
    if not dev_loopback and host not in allow_hosts:
        for a in addrs:
            cls = classify(ipaddress.ip_address(a.split("%")[0]))
            if cls:
                raise SSRFBlocked(cls, f"{host} resolves to a {cls.replace('_', '-')} address")
    return ValidatedURL(url, scheme, host, port, frozenset(addrs))


def recheck(v: ValidatedURL, environment: str, allow_hosts: frozenset[str] = frozenset()) -> None:
    """Re-resolve at connection time; any new address must also be public (DNS-rebinding defence)."""
    if environment == "development" and v.host in ("127.0.0.1", "localhost", "::1"):
        return
    if v.host in allow_hosts:
        return
    for a in _resolve(v.host, v.port):
        cls = classify(ipaddress.ip_address(a.split("%")[0]))
        if cls:
            raise SSRFBlocked(cls, f"{v.host} re-resolved to a {cls} address at connection time")
