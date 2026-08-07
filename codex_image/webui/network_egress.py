from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from math import isfinite
from pathlib import Path
from types import MappingProxyType
from typing import Any, Literal, Mapping, cast
from urllib.parse import urlsplit, urlunsplit

from codex_image.httpx_transport import HttpxTransport

from .schemas import DEFAULT_WEBUI_NETWORK_EGRESS_SETTINGS_PATH

NetworkEgressMode = Literal["system", "direct", "custom"]
NetworkEgressRoute = Literal["system", "direct", "proxy"]
NetworkEgressSettingValue = str | int
ImageRequestTimeoutSource = Literal["settings", "environment", "default"]

IMAGE_REQUEST_TIMEOUT_ENV = "CODEX_IMAGE_REQUEST_TIMEOUT_SECONDS"
DEFAULT_IMAGE_REQUEST_TIMEOUT_SECONDS = 600
MIN_IMAGE_REQUEST_TIMEOUT_SECONDS = 60
MAX_IMAGE_REQUEST_TIMEOUT_SECONDS = 1800
DEFAULT_IMAGE_REQUEST_RETRY_COUNT = 2
MIN_IMAGE_REQUEST_RETRY_COUNT = 0
MAX_IMAGE_REQUEST_RETRY_COUNT = 5

_DEFAULT_SETTINGS: dict[str, NetworkEgressSettingValue] = {
    "mode": "system",
    "custom_proxy_url": "",
    "image_request_timeout_seconds": DEFAULT_IMAGE_REQUEST_TIMEOUT_SECONDS,
    "image_request_retry_count": DEFAULT_IMAGE_REQUEST_RETRY_COUNT,
}
_VALID_MODES = frozenset({"system", "direct", "custom"})


@dataclass(frozen=True)
class ImageRequestPolicy:
    timeout_seconds: float
    retry_count: int
    timeout_source: ImageRequestTimeoutSource


def _normalize_proxy_url(value: Any) -> str:
    candidate = str(value or "").strip()
    if not candidate:
        return ""

    try:
        parsed = urlsplit(candidate)
        port = parsed.port
    except ValueError as exc:
        raise ValueError("Custom proxy URL is invalid") from exc

    scheme = parsed.scheme.lower()
    if scheme not in {"http", "https"}:
        raise ValueError("Custom proxy URL must use http or https")
    if not parsed.hostname:
        raise ValueError("Custom proxy URL must include a host")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("Custom proxy URL must not include credentials")
    if parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
        raise ValueError("Custom proxy URL must be an origin without a path, query, or fragment")

    hostname = parsed.hostname
    if ":" in hostname and not hostname.startswith("["):
        hostname = f"[{hostname}]"
    netloc = hostname
    if port is not None:
        netloc = f"{netloc}:{port}"
    return urlunsplit((scheme, netloc, "", "", ""))


def _bounded_integer(
    value: Any,
    *,
    field: str,
    minimum: int,
    maximum: int,
) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{field} must be an integer")
    if value < minimum or value > maximum:
        raise ValueError(f"{field} must be between {minimum} and {maximum}")
    return value


def _environment_timeout_seconds() -> float | None:
    raw = os.getenv(IMAGE_REQUEST_TIMEOUT_ENV, "").strip()
    if not raw:
        return None
    try:
        parsed = float(raw)
    except ValueError:
        return None
    return parsed if isfinite(parsed) and parsed > 0 else None


def _normalize_route_settings(
    payload: Mapping[str, Any],
    *,
    current: Mapping[str, Any] | None = None,
) -> dict[str, str]:
    baseline = current or _DEFAULT_SETTINGS
    mode = str(payload.get("mode", baseline["mode"]) or "").strip().lower()
    if mode not in _VALID_MODES:
        raise ValueError("Network egress mode must be system, direct, or custom")

    custom_proxy_url = _normalize_proxy_url(
        payload.get("custom_proxy_url", baseline.get("custom_proxy_url", ""))
    )
    if mode == "custom" and not custom_proxy_url:
        raise ValueError("Custom proxy URL is required in custom mode")
    return {
        "mode": mode,
        "custom_proxy_url": custom_proxy_url,
    }


def _editable_settings_from_payload(
    payload: Mapping[str, Any],
) -> dict[str, NetworkEgressSettingValue]:
    try:
        route = _normalize_route_settings(payload)
    except ValueError:
        route = {
            "mode": str(_DEFAULT_SETTINGS["mode"]),
            "custom_proxy_url": str(_DEFAULT_SETTINGS["custom_proxy_url"]),
        }

    try:
        timeout_seconds = _bounded_integer(
            payload.get(
                "image_request_timeout_seconds",
                DEFAULT_IMAGE_REQUEST_TIMEOUT_SECONDS,
            ),
            field="image_request_timeout_seconds",
            minimum=MIN_IMAGE_REQUEST_TIMEOUT_SECONDS,
            maximum=MAX_IMAGE_REQUEST_TIMEOUT_SECONDS,
        )
    except ValueError:
        timeout_seconds = DEFAULT_IMAGE_REQUEST_TIMEOUT_SECONDS

    try:
        retry_count = _bounded_integer(
            payload.get(
                "image_request_retry_count",
                DEFAULT_IMAGE_REQUEST_RETRY_COUNT,
            ),
            field="image_request_retry_count",
            minimum=MIN_IMAGE_REQUEST_RETRY_COUNT,
            maximum=MAX_IMAGE_REQUEST_RETRY_COUNT,
        )
    except ValueError:
        retry_count = DEFAULT_IMAGE_REQUEST_RETRY_COUNT

    return {
        **route,
        "image_request_timeout_seconds": timeout_seconds,
        "image_request_retry_count": retry_count,
    }


def _normalize_settings(payload: Mapping[str, Any]) -> dict[str, str]:
    return _normalize_route_settings(payload)


@dataclass(frozen=True)
class NetworkEgressSnapshot:
    mode: NetworkEgressMode
    route: NetworkEgressRoute
    proxy_map: Mapping[str, str] | None
    image_request_timeout_seconds: float
    image_request_retry_count: int
    image_request_timeout_source: ImageRequestTimeoutSource

    def task_metadata(self) -> dict[str, str | int | float]:
        return {
            "mode": self.mode,
            "route": self.route,
            "image_request_timeout_seconds": self.image_request_timeout_seconds,
            "image_request_retry_count": self.image_request_retry_count,
            "image_request_timeout_source": self.image_request_timeout_source,
        }


class NetworkEgressSettings:
    def __init__(self, path: Path | str = DEFAULT_WEBUI_NETWORK_EGRESS_SETTINGS_PATH) -> None:
        self.path = Path(path)

    def _read_payload(self) -> dict[str, Any]:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return {}
        if not isinstance(payload, dict):
            return {}
        return payload

    def read(self) -> dict[str, NetworkEgressSettingValue]:
        return _editable_settings_from_payload(self._read_payload())

    def request_policy(self) -> ImageRequestPolicy:
        payload = self._read_payload()
        try:
            retry_count = _bounded_integer(
                payload.get(
                    "image_request_retry_count",
                    DEFAULT_IMAGE_REQUEST_RETRY_COUNT,
                ),
                field="image_request_retry_count",
                minimum=MIN_IMAGE_REQUEST_RETRY_COUNT,
                maximum=MAX_IMAGE_REQUEST_RETRY_COUNT,
            )
        except ValueError:
            retry_count = DEFAULT_IMAGE_REQUEST_RETRY_COUNT

        if "image_request_timeout_seconds" in payload:
            try:
                timeout_seconds = _bounded_integer(
                    payload["image_request_timeout_seconds"],
                    field="image_request_timeout_seconds",
                    minimum=MIN_IMAGE_REQUEST_TIMEOUT_SECONDS,
                    maximum=MAX_IMAGE_REQUEST_TIMEOUT_SECONDS,
                )
            except ValueError:
                pass
            else:
                return ImageRequestPolicy(
                    timeout_seconds=timeout_seconds,
                    retry_count=retry_count,
                    timeout_source="settings",
                )

        environment_timeout = _environment_timeout_seconds()
        if environment_timeout is not None:
            return ImageRequestPolicy(
                timeout_seconds=environment_timeout,
                retry_count=retry_count,
                timeout_source="environment",
            )
        return ImageRequestPolicy(
            timeout_seconds=DEFAULT_IMAGE_REQUEST_TIMEOUT_SECONDS,
            retry_count=retry_count,
            timeout_source="default",
        )

    def write(
        self,
        payload: Mapping[str, Any],
    ) -> dict[str, NetworkEgressSettingValue]:
        current_payload = self._read_payload()
        current = _editable_settings_from_payload(current_payload)
        clean: dict[str, NetworkEgressSettingValue] = {
            **_normalize_route_settings(payload, current=current),
        }
        policy_fields = (
            (
                "image_request_timeout_seconds",
                MIN_IMAGE_REQUEST_TIMEOUT_SECONDS,
                MAX_IMAGE_REQUEST_TIMEOUT_SECONDS,
            ),
            (
                "image_request_retry_count",
                MIN_IMAGE_REQUEST_RETRY_COUNT,
                MAX_IMAGE_REQUEST_RETRY_COUNT,
            ),
        )
        for field, minimum, maximum in policy_fields:
            if field in payload:
                clean[field] = _bounded_integer(
                    payload[field],
                    field=field,
                    minimum=minimum,
                    maximum=maximum,
                )
                continue
            if field not in current_payload:
                continue
            try:
                clean[field] = _bounded_integer(
                    current_payload[field],
                    field=field,
                    minimum=minimum,
                    maximum=maximum,
                )
            except ValueError:
                pass
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path: str | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                delete=False,
                dir=self.path.parent,
                prefix=f".{self.path.name}.",
                suffix=".tmp",
            ) as tmp:
                tmp_path = tmp.name
                tmp.write(json.dumps(clean, indent=2, ensure_ascii=False))
                tmp.flush()
                os.fsync(tmp.fileno())
            os.replace(tmp_path, self.path)
            tmp_path = None
        finally:
            if tmp_path is not None:
                try:
                    Path(tmp_path).unlink()
                except FileNotFoundError:
                    pass
        return _editable_settings_from_payload(clean)


class NetworkEgressManager:
    def __init__(self, settings: NetworkEgressSettings | None = None) -> None:
        self.settings = settings or NetworkEgressSettings()

    def snapshot(self, payload: Mapping[str, Any] | None = None) -> NetworkEgressSnapshot:
        clean = self.settings.read() if payload is None else _normalize_settings(payload)
        policy = self.settings.request_policy()
        mode = cast(NetworkEgressMode, clean["mode"])
        if mode == "system":
            return NetworkEgressSnapshot(
                mode=mode,
                route="system",
                proxy_map=None,
                image_request_timeout_seconds=policy.timeout_seconds,
                image_request_retry_count=policy.retry_count,
                image_request_timeout_source=policy.timeout_source,
            )
        if mode == "direct":
            return NetworkEgressSnapshot(
                mode=mode,
                route="direct",
                proxy_map=MappingProxyType({}),
                image_request_timeout_seconds=policy.timeout_seconds,
                image_request_retry_count=policy.retry_count,
                image_request_timeout_source=policy.timeout_source,
            )

        proxy_url = str(clean["custom_proxy_url"])
        return NetworkEgressSnapshot(
            mode=mode,
            route="proxy",
            proxy_map=MappingProxyType({"http": proxy_url, "https": proxy_url}),
            image_request_timeout_seconds=policy.timeout_seconds,
            image_request_retry_count=policy.retry_count,
            image_request_timeout_source=policy.timeout_source,
        )

    @staticmethod
    def transport(
        snapshot: NetworkEgressSnapshot,
        *,
        timeout_seconds: float | None = None,
    ) -> HttpxTransport:
        return HttpxTransport(
            timeout=(
                snapshot.image_request_timeout_seconds
                if timeout_seconds is None
                else timeout_seconds
            ),
            proxy_map=snapshot.proxy_map,
        )
