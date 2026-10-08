"""Opt-in independent DNS for indirect image assets affected by Fake-IP DNS."""
from __future__ import annotations

import asyncio
import ipaddress
import json

import httpx

from .asset_urls import UnsafeAssetURLError
from .http import _https_ssl_context
from .http_connection import stream_with_connection_retries, transport_failure


ASSET_DNS_ENDPOINT = "https://cloudflare-dns.com/dns-query"
ASSET_DNS_TIMEOUT_SECONDS = 8
MAX_ASSET_DNS_RESPONSE_BYTES = 64 * 1024


async def resolve_fake_ip_hostname(
    hostname: str, *, proxy: str | None = None, connect_retry_count: int = 0,
) -> tuple[str, ...]:
    name = hostname.encode("idna").decode("ascii").rstrip(".").lower()
    try:
        async with httpx.AsyncClient(
            timeout=ASSET_DNS_TIMEOUT_SECONDS, proxy=proxy, trust_env=False,
            verify=_https_ssl_context() or True, follow_redirects=False,
        ) as client:
            async def query(record_type: str, number: int) -> list[str]:
                async with stream_with_connection_retries(
                    client, "GET", (ASSET_DNS_ENDPOINT,), retry_count=connect_retry_count,
                    phase="image_dns_lookup", hostname="cloudflare-dns.com", route="proxy" if proxy else "direct",
                    params={"name": name, "type": record_type},
                    headers={"Accept": "application/dns-json"},
                ) as response:
                    if response.status_code != 200:
                        raise UnsafeAssetURLError("independent image DNS query failed")
                    body = bytearray()
                    async for chunk in response.aiter_bytes():
                        body.extend(chunk[: MAX_ASSET_DNS_RESPONSE_BYTES + 1 - len(body)])
                        if len(body) > MAX_ASSET_DNS_RESPONSE_BYTES:
                            raise UnsafeAssetURLError("independent image DNS response exceeded its size limit")
                payload = json.loads(body)
                questions = payload.get("Question", [])
                if (payload.get("Status") != 0 or len(questions) != 1
                        or questions[0].get("name", "").rstrip(".").lower() != name
                        or questions[0].get("type") != number):
                    raise UnsafeAssetURLError("independent image DNS returned an invalid answer")
                addresses = []
                for answer in payload.get("Answer", []):
                    if answer.get("type") == number:
                        address = ipaddress.ip_address(answer["data"])
                        if address.version != (4 if number == 1 else 6):
                            raise ValueError("address family mismatch")
                        addresses.append(str(address))
                return addresses

            # TaskGroup cancels the other query if one fails or the request is cancelled.
            async with asyncio.TaskGroup() as group:
                ipv4 = group.create_task(query("A", 1))
                ipv6 = group.create_task(query("AAAA", 28))
            addresses = tuple(dict.fromkeys([*ipv4.result(), *ipv6.result()]))
            if not addresses:
                raise UnsafeAssetURLError("independent image DNS returned no addresses")
            return addresses
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        failure = transport_failure(exc)
        if failure is not None:
            raise failure from None
        raise UnsafeAssetURLError("independent image DNS could not resolve the asset hostname") from exc
