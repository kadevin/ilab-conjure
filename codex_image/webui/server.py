from __future__ import annotations

import argparse
import contextlib
import signal
import threading
import time
from collections.abc import Generator, Sequence
from types import FrameType
from typing import Any

from uvicorn import Config, Server
from uvicorn.importer import import_from_string
from uvicorn.server import HANDLED_SIGNALS

from .shutdown_control import ShutdownCoordinator
from .lan_access import LanAccessRuntime


class WebUIServer(Server):
    REPEATED_SIGINT_GRACE_SECONDS = 1.0

    def __init__(
        self,
        config: Config,
        *,
        shutdown_coordinator: ShutdownCoordinator,
    ) -> None:
        super().__init__(config)
        self.shutdown_coordinator = shutdown_coordinator
        self._first_sigint_at: float | None = None

    def handle_exit(self, sig: int, frame: FrameType | None) -> None:
        self.shutdown_coordinator.request_shutdown()
        now = time.monotonic()
        if sig == signal.SIGINT:
            if self._first_sigint_at is None:
                self._first_sigint_at = now
            elif (
                now - self._first_sigint_at
                < self.REPEATED_SIGINT_GRACE_SECONDS
            ):
                return
        super().handle_exit(sig, frame)

    @contextlib.contextmanager
    def capture_signals(self) -> Generator[None, None, None]:
        if threading.current_thread() is not threading.main_thread():
            yield
            return
        original_handlers = {
            sig: signal.signal(sig, self.handle_exit)
            for sig in HANDLED_SIGNALS
        }
        try:
            yield
        finally:
            for sig, handler in original_handlers.items():
                signal.signal(sig, handler)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the iLab CONJURE WebUI")
    parser.add_argument("app", help="ASGI application import path")
    parser.add_argument("--host", help="Override the address selected by the LAN access setting")
    parser.add_argument("--port", type=int, default=8787)
    parser.add_argument("--no-access-log", action="store_false", dest="access_log")
    parser.add_argument("--timeout-graceful-shutdown", type=int, default=5)
    return parser


def _shutdown_coordinator(app: Any) -> ShutdownCoordinator:
    state = getattr(app, "state", None)
    coordinator = getattr(state, "webui_shutdown_coordinator", None)
    if not isinstance(coordinator, ShutdownCoordinator):
        raise RuntimeError(
            "The WebUI application does not expose a shutdown coordinator"
        )
    return coordinator


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        app = import_from_string(args.app)
        coordinator = _shutdown_coordinator(app)
        runtime = getattr(app.state, "lan_access", None)
        if not isinstance(runtime, LanAccessRuntime):
            runtime = LanAccessRuntime()
        runtime.host = args.host or runtime.default_host
        runtime.port = args.port
        config = Config(
            app,
            host=runtime.host,
            port=args.port,
            access_log=args.access_log,
            proxy_headers=False,
            timeout_graceful_shutdown=args.timeout_graceful_shutdown,
        )
        server = WebUIServer(
            config,
            shutdown_coordinator=coordinator,
        )
        server.run()
    except KeyboardInterrupt:
        return 0
    return 0 if server.started else 3


if __name__ == "__main__":
    raise SystemExit(main())
