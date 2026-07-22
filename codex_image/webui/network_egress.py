from __future__ import annotations

import json
import re
import socket
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping
from urllib import request
from urllib.parse import urlsplit

from codex_image.http import Transport, UrllibTransport

NETWORK_EGRESS_MODES = {"auto", "system", "direct", "custom"}
DEFAULT_NETWORK_EGRESS_MODE = "system"
NETWORK_EGRESS_PROBE_URL = "https://chatgpt.com/"
_PROXY_SCHEMES = {"http", "https"}
_URL_CREDENTIAL_PATTERN = re.compile(r"(?i)(https?://)[^\s/@]+@")


def _normalize_proxy_url(value: Any, *, required: bool = False) -> str:
    raw = str(value or "").strip()
    if not raw:
        if required:
            raise ValueError("Custom proxy URL is required")
        return ""
    parsed = urlsplit(raw)
    if parsed.scheme.lower() not in _PROXY_SCHEMES:
        raise ValueError("Proxy URL must use http:// or https://")
    if not parsed.hostname:
        raise ValueError("Proxy URL must include a host")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("Proxy credentials are not supported; use a local credential-free proxy endpoint")
    if parsed.query or parsed.fragment or parsed.path not in ("", "/"):
        raise ValueError("Proxy URL must contain only scheme, host, and optional port")
    try:
        parsed.port
    except ValueError as exc:
        raise ValueError("Proxy URL contains an invalid port") from exc
    return raw.rstrip("/")


def _safe_proxy_label(proxy_url: str) -> str:
    if not proxy_url:
        return ""
    parsed = urlsplit(proxy_url)
    if not parsed.hostname:
        return ""
    host = f"[{parsed.hostname}]" if ":" in parsed.hostname else parsed.hostname
    try:
        port = parsed.port
    except ValueError:
        port = None
    return f"{parsed.scheme.lower()}://{host}{f':{port}' if port else ''}"


def _safe_error_message(exc: Exception) -> str:
    message = _URL_CREDENTIAL_PATTERN.sub(r"\1***@", str(exc)).strip()
    return message or exc.__class__.__name__


def _proxy_endpoint(proxy_url: str) -> tuple[str, int] | None:
    parsed = urlsplit(proxy_url)
    if not parsed.hostname:
        return None
    try:
        port = parsed.port
    except ValueError:
        return None
    return parsed.hostname, port or (443 if parsed.scheme.lower() == "https" else 80)


def _filtered_system_proxies(values: Mapping[str, str] | None = None) -> dict[str, str]:
    raw = dict(values) if values is not None else request.getproxies()
    proxies: dict[str, str] = {}
    for scheme in ("http", "https"):
        value = str(raw.get(scheme) or "").strip()
        parsed = urlsplit(value)
        if value and parsed.scheme.lower() in _PROXY_SCHEMES and parsed.hostname:
            proxies[scheme] = value
    return proxies


@dataclass(frozen=True)
class ResolvedNetworkEgress:
    requested_mode: str
    route: str
    source: str
    proxy_url: str = ""
    proxy_map: dict[str, str] = field(default_factory=dict, repr=False)

    def public_snapshot(self) -> dict[str, Any]:
        return {
            "requested_mode": self.requested_mode,
            "route": self.route,
            "source": self.source,
            "proxy_url": _safe_proxy_label(self.proxy_url),
        }


class NetworkEgressSettings:
    def __init__(self, path: Path) -> None:
        self.path = path

    @staticmethod
    def defaults() -> dict[str, str]:
        return {"mode": DEFAULT_NETWORK_EGRESS_MODE, "custom_proxy_url": ""}

    @classmethod
    def normalize(cls, payload: Any, *, current: Mapping[str, Any] | None = None) -> dict[str, str]:
        if not isinstance(payload, dict):
            raise ValueError("Network egress settings payload must be an object")
        base = dict(current or cls.defaults())
        mode = str(payload.get("mode", base.get("mode", DEFAULT_NETWORK_EGRESS_MODE)) or "").strip().lower()
        if mode not in NETWORK_EGRESS_MODES:
            raise ValueError("Network egress mode must be auto, system, direct, or custom")
        custom_proxy_url = _normalize_proxy_url(
            payload.get("custom_proxy_url", base.get("custom_proxy_url", "")),
            required=mode == "custom",
        )
        return {"mode": mode, "custom_proxy_url": custom_proxy_url}

    def read(self) -> dict[str, str]:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return self.defaults()
        try:
            return self.normalize(payload)
        except ValueError:
            return self.defaults()

    def write(self, payload: dict[str, Any]) -> dict[str, str]:
        settings = self.normalize(payload, current=self.read())
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(settings, indent=2, ensure_ascii=False), encoding="utf-8")
        return settings


class NetworkEgressManager:
    def __init__(
        self,
        settings: NetworkEgressSettings,
        *,
        proxy_connector: Callable[[tuple[str, int], float], Any] | None = None,
        proxy_check_timeout: float = 0.35,
    ) -> None:
        self.settings = settings
        self.proxy_connector = proxy_connector or socket.create_connection
        self.proxy_check_timeout = proxy_check_timeout

    def _proxy_reachable(self, proxy_url: str) -> bool:
        endpoint = _proxy_endpoint(proxy_url)
        if endpoint is None:
            return False
        try:
            connection = self.proxy_connector(endpoint, self.proxy_check_timeout)
        except OSError:
            return False
        close = getattr(connection, "close", None)
        if callable(close):
            close()
        return True

    def resolve(self, payload: Mapping[str, Any] | None = None) -> ResolvedNetworkEgress:
        current = self.settings.read()
        selected = NetworkEgressSettings.normalize(dict(payload), current=current) if payload is not None else current
        mode = selected["mode"]
        custom_proxy = selected["custom_proxy_url"]
        system_proxies = _filtered_system_proxies()
        system_proxy = system_proxies.get("https") or system_proxies.get("http") or ""

        if mode == "direct":
            return ResolvedNetworkEgress(mode, "direct", "direct")
        if mode == "custom":
            proxy_map = {"http": custom_proxy, "https": custom_proxy}
            return ResolvedNetworkEgress(mode, "proxy", "custom", custom_proxy, proxy_map)
        if mode == "system":
            if system_proxy:
                return ResolvedNetworkEgress(mode, "proxy", "system", system_proxy, system_proxies)
            return ResolvedNetworkEgress(mode, "direct", "system")

        if custom_proxy and self._proxy_reachable(custom_proxy):
            proxy_map = {"http": custom_proxy, "https": custom_proxy}
            return ResolvedNetworkEgress(mode, "proxy", "custom", custom_proxy, proxy_map)
        if system_proxy and self._proxy_reachable(system_proxy):
            return ResolvedNetworkEgress(mode, "proxy", "system", system_proxy, system_proxies)
        return ResolvedNetworkEgress(mode, "direct", "auto")

    @staticmethod
    def transport_for(resolved: ResolvedNetworkEgress, *, timeout: float | None = None) -> Transport:
        proxy_map = resolved.proxy_map if resolved.route == "proxy" else {}
        return UrllibTransport(timeout=timeout, proxy_map=proxy_map)

    def transport(self) -> Transport:
        return self.transport_for(self.resolve())

    def public_settings(self) -> dict[str, Any]:
        settings = self.settings.read()
        return {"settings": settings, "resolved": self.resolve().public_snapshot(), "restart_required": False}

    def probe(self, payload: Mapping[str, Any] | None = None) -> dict[str, Any]:
        resolved = self.resolve(payload)
        started_at = time.monotonic()
        try:
            response = self.transport_for(resolved, timeout=5.0).request(
                method="HEAD",
                url=NETWORK_EGRESS_PROBE_URL,
                headers={"User-Agent": "iLab-GPT-CONJURE-network-check"},
                body=b"",
            )
        except Exception as exc:
            return {
                "ok": False,
                "elapsed_ms": round((time.monotonic() - started_at) * 1000),
                "resolved": resolved.public_snapshot(),
                "error": _safe_error_message(exc),
            }
        return {
            "ok": True,
            "status": response.status,
            "elapsed_ms": round((time.monotonic() - started_at) * 1000),
            "resolved": resolved.public_snapshot(),
        }
