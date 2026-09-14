from __future__ import annotations

import ipaddress
import socket
from dataclasses import dataclass


@dataclass
class LanAccessRuntime:
    enabled: bool = False
    host: str | None = None
    port: int | None = None

    @property
    def default_host(self) -> str:
        return "0.0.0.0" if self.enabled else "127.0.0.1"

    @property
    def active(self) -> bool:
        return self.enabled and not is_loopback_host(self.host or self.default_host)


def is_loopback_host(host: str) -> bool:
    if host.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def lan_ipv4_addresses() -> list[str]:
    candidates: set[str] = set()
    try:
        candidates.update(
            str(item[4][0])
            for item in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET)
        )
    except OSError:
        pass
    try:
        # UDP connect selects the default interface without sending a packet.
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            probe.connect(("192.0.2.1", 9))
            candidates.add(str(probe.getsockname()[0]))
    except OSError:
        pass
    addresses = []
    for candidate in candidates:
        try:
            address = ipaddress.IPv4Address(candidate)
        except ValueError:
            continue
        if address.is_private and not (
            address.is_loopback or address.is_unspecified or address.is_multicast
        ):
            addresses.append(str(address))
    return sorted(addresses, key=ipaddress.IPv4Address)
