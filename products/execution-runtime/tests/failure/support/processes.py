"""Spawned HTTP services and actual worker launchers; no production fault flags."""
from __future__ import annotations

import logging
import os
import socket
import time

import httpx

from .barriers import CONTEXT


class ProcessService:
    def __init__(self, target, *args, ready_path="/health/live"):
        self.socket = socket.socket()
        self.socket.bind(("127.0.0.1", 0))
        self.socket.listen(64)
        self.url = f"http://127.0.0.1:{self.socket.getsockname()[1]}"
        self.process = CONTEXT.Process(target=target, args=(self.socket, *args))
        self.process.start()
        self.socket.close()
        deadline = time.monotonic() + 15
        try:
            with httpx.Client(trust_env=False, timeout=0.25) as client:
                while time.monotonic() < deadline:
                    if not self.process.is_alive():
                        raise AssertionError("child exited before serving health")
                    try:
                        if client.get(self.url + ready_path).status_code == 200:
                            return
                    except httpx.HTTPError:
                        pass
                    time.sleep(0.025)
            raise AssertionError("child startup watchdog expired")
        except BaseException:
            self.close()
            raise

    @property
    def pid(self):
        return self.process.pid

    def kill(self):
        self.process.kill()
        self.process.join(timeout=5)
        assert not self.process.is_alive(), "child did not die after kill"
        assert self.process.exitcode != 0

    def close(self):
        if self.process.is_alive():
            self.process.terminate()
            self.process.join(timeout=5)
        if self.process.is_alive():
            self.kill()
        self.process.close()


class CanaryLogProbe:
    """Scan enabled log emissions in memory; retain counts, never raw records."""

    def __init__(self, canaries, path=None):
        self.canaries, self.path = canaries, path
        self.seen = self.leaked = 0

    def scan(self, record):
        from uuid import uuid4
        text = logging.Formatter().format(record) + repr(record.__dict__)
        leaked = any(value in text for value in self.canaries)
        self.seen += 1
        self.leaked += int(leaked)
        if self.path:
            from .http_services import record as persist
            persist(self.path, "log_scanned", str(uuid4()))
            if leaked:
                persist(self.path, "log_canary", str(uuid4()))

    def install(self):
        logging.disable(logging.NOTSET)
        logging.getLogger().setLevel(logging.INFO)
        # Intercept even non-propagating loggers before any handler prints raw text.
        # Scope is this disposable child only; production logging stays unchanged.
        probe = self
        logging.Logger.handle = lambda logger, record: probe.scan(record)
        logging.getLogger(__name__).info("minimization log capture ready")


def launch_worker(sock, settings, hooks=None, connection_factory=None, minimization=None):
    # Inherited developer URLs, auth, proxy configuration and exporters must never
    # escape to shared services from a disposable worker.
    keep = {k: v for k, v in os.environ.items() if k in {"PATH", "HOME", "TMPDIR"}}
    os.environ.clear()
    os.environ.update(keep)
    os.environ.update(settings)
    os.environ.update(OTEL_SDK_DISABLED="true", OTEL_TRACES_EXPORTER="none",
                      OTEL_METRICS_EXPORTER="none", OTEL_LOGS_EXPORTER="none")
    import uvicorn
    from execution_runtime.app import create_app
    from execution_runtime.core.config import get_settings

    get_settings.cache_clear()
    ledger = None
    if connection_factory:
        from execution_runtime.services.execution_ledger import ExecutionLedger
        configured = get_settings()
        ledger = ExecutionLedger(configured.state_db_url, configured.execution_signing_key,
                                 configured.admission_epoch, admission_enabled=configured.admission_enabled,
                                 connection_factory=connection_factory)
    app = create_app(ledger=ledger, lifecycle_hook=hooks)
    # Artifacts contain only explicit allowlisted evidence, never raw HTTP logs.
    if minimization:
        from .http_services import initialize, record
        from uuid import uuid4
        initialize(minimization["log_path"])
        CanaryLogProbe(minimization["canaries"], minimization["log_path"]).install()
        if minimization.get("exception"):
            send = httpx.AsyncClient.send

            async def failing_send(client, request, **kwargs):
                result = await send(client, request, **kwargs)
                if request.url.path == "/api/v2/tools/invoke":
                    await result.aclose()
                    record(minimization["log_path"], "exception_injected", str(uuid4()))
                    raise httpx.ReadError(minimization["exception"], request=request)
                return result

            httpx.AsyncClient.send = failing_send
    else:
        logging.disable(logging.CRITICAL)
    uvicorn.Server(uvicorn.Config(app, log_level="info" if minimization else "critical", access_log=False,
                                 timeout_graceful_shutdown=5)).run(sockets=[sock])
