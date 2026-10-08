"""Retry connections before a request is sent, without replaying an image operation."""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
import errno
import ssl

import httpx


def exception_chain(exc: BaseException) -> list[BaseException]:
    pending, result, seen = [exc], [], set()
    while pending:
        current = pending.pop()
        if id(current) in seen:
            continue
        seen.add(id(current))
        result.append(current)
        nested = (current.__cause__, current.__context__, getattr(current, "reason", None),
                  *getattr(current, "exceptions", ()))
        pending.extend(item for item in nested if isinstance(item, BaseException))
    return result


def _certificate_failure(exc: BaseException) -> bool:
    return any(
        isinstance(item, ssl.SSLCertVerificationError)
        or "certificate_verify_failed" in str(item).lower()
        or "certificate verify failed" in str(item).lower()
        for item in exception_chain(exc)
    )


class HTTPTransportFailure(RuntimeError):
    """A diagnosed HTTP failure whose connection retries have already been handled."""

    def __init__(self, *, phase: str, hostname: str, route: str, attempts: int, error: BaseException):
        self.phase = phase
        self.hostname = hostname
        self.route = route
        self.attempts = attempts
        chain = exception_chain(error)
        codes = list(dict.fromkeys(
            errno.errorcode[item.errno] for item in chain
            if isinstance(item, OSError) and item.errno in errno.errorcode
        ))
        reason = ("TLS_CERTIFICATE_VERIFY_FAILED" if _certificate_failure(error)
                  else "/".join([type(error).__name__, *codes]))
        # Never interpolate exception messages, URLs, query strings, headers or request bodies.
        super().__init__(f"HTTP request failed [stage={phase}, host={hostname}, route={route}, "
                         f"attempts={attempts}, reason={reason}]")


def transport_failure(exc: BaseException) -> HTTPTransportFailure | None:
    return next((item for item in exception_chain(exc) if isinstance(item, HTTPTransportFailure)), None)


def connection_retry_delay(failed_round: int) -> float:
    return min(2.0, 0.5 * 2**failed_round)


@asynccontextmanager
async def stream_with_connection_retries(
    client, method, urls, *, retry_count: int, phase: str, hostname: str, route: str, **kwargs,
):
    attempts = 0
    for round_index in range(retry_count + 1):
        for index, url in enumerate(urls):
            opened = False
            attempts += 1
            try:
                async with client.stream(method, url, **kwargs) as response:
                    opened = True
                    yield response
                    return
            except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
                if opened:
                    if phase != "upstream_request":
                        raise HTTPTransportFailure(phase=phase, hostname=hostname, route=route,
                                                   attempts=attempts, error=exc) from exc
                    raise
                if _certificate_failure(exc) or (round_index == retry_count and index == len(urls) - 1):
                    raise HTTPTransportFailure(phase=phase, hostname=hostname, route=route,
                                               attempts=attempts, error=exc) from exc
            except httpx.TransportError as exc:
                if phase == "upstream_request":
                    raise
                raise HTTPTransportFailure(phase=phase, hostname=hostname, route=route,
                                           attempts=attempts, error=exc) from exc
        await asyncio.sleep(connection_retry_delay(round_index))
