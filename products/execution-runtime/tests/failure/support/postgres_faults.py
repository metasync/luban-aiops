"""Real commit acknowledgment loss, including a PostgreSQL wire proxy."""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import socket
import struct
import threading

import psycopg
from psycopg.conninfo import conninfo_to_dict, make_conninfo

from .barriers import CONTEXT


class CommitFaultConnection:
    def __init__(self, connection, mode):
        if mode not in {"ack_lost", "rollback"}:
            raise ValueError("unknown commit fault")
        self.connection, self.mode = connection, mode

    def __getattr__(self, name):
        return getattr(self.connection, name)

    def commit(self):
        if self.mode == "ack_lost":
            self.connection.commit()
        else:
            self.connection.rollback()
        raise psycopg.OperationalError("injected commit uncertainty")


class LedgerFaultConnection(CommitFaultConnection):
    """Inject at the actual statement/commit boundary, never bypass product SQL."""
    def __init__(self, connection, phase, mode):
        super().__init__(connection, mode)
        self.phase, self.armed = phase, False

    @property
    def autocommit(self):
        return self.connection.autocommit

    @autocommit.setter
    def autocommit(self, value):
        self.connection.autocommit = value

    def execute(self, query, params=None):
        if isinstance(query, str):
            if self.phase == "claim" and query.startswith("INSERT INTO execution_dispatch_claims"):
                self.armed = True
            if (self.phase == "receipt" and query.startswith("INSERT INTO execution_observations ")
                    and params[3] == "worker_result"):
                self.armed = True
        return self.connection.execute(query, params)

    def commit(self):
        if self.armed:
            return super().commit()
        return self.connection.commit()

    @contextmanager
    def transaction(self):
        with self.connection.transaction():
            yield
            if self.armed and self.mode == "rollback":
                raise psycopg.OperationalError("injected metadata rollback")
        if self.armed and self.mode == "ack_lost":
            raise psycopg.OperationalError("injected metadata commit uncertainty")


@dataclass
class FaultFactory:
    phase: str
    mode: str

    def __call__(self, dsn):
        from execution_runtime.services.execution_migration import connect
        return LedgerFaultConnection(connect(dsn), self.phase, self.mode)


def _read_exact(sock, length):
    result = bytearray()
    while len(result) < length:
        part = sock.recv(length - len(result))
        if not part:
            raise EOFError
        result.extend(part)
    return bytes(result)


def _proxy(listener, upstream, armed, dropped, ready):
    ready.set()

    def session(client):
        backend = socket.create_connection(upstream, timeout=5)
        client.settimeout(10)
        backend.settimeout(10)

        def forward_client():
            try:
                while data := client.recv(65536):
                    backend.sendall(data)
            except OSError:
                pass
            finally:
                try:
                    backend.shutdown(socket.SHUT_WR)
                except OSError:
                    pass

        sender = threading.Thread(target=forward_client, daemon=True)
        sender.start()
        try:
            while True:
                header = _read_exact(backend, 5)
                length = struct.unpack("!I", header[1:])[0]
                if not 4 <= length <= 1048576:
                    raise ValueError("invalid bounded Postgres frame")
                payload = _read_exact(backend, length - 4)
                if header[:1] == b"C" and payload == b"COMMIT\0" and armed.is_set():
                    armed.clear()
                    dropped.set()
                    break
                client.sendall(header + payload)
        except (EOFError, OSError):
            pass
        finally:
            for sock in (client, backend):
                try:
                    sock.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
                sock.close()
            sender.join(timeout=1)

    while True:
        client, _ = listener.accept()
        threading.Thread(target=session, args=(client,), daemon=True).start()


class CommitAckProxy:
    def __init__(self, dsn):
        parameters = conninfo_to_dict(dsn)
        if parameters.get("host") != "127.0.0.1" or parameters.get("sslmode") != "disable":
            raise ValueError("wire fault injection requires the disposable loopback database")
        self.armed, self.dropped, self.ready = (CONTEXT.Event() for _ in range(3))
        listener = socket.socket()
        listener.bind(("127.0.0.1", 0))
        listener.listen(16)
        self.dsn = make_conninfo(dsn, port=listener.getsockname()[1])
        self.process = CONTEXT.Process(target=_proxy, args=(
            listener, ("127.0.0.1", int(parameters["port"])),
            self.armed, self.dropped, self.ready))
        self.process.start()
        listener.close()
        if not self.ready.wait(5):
            self.close()
            raise AssertionError("Postgres proxy startup watchdog expired")

    def close(self):
        self.process.terminate()
        self.process.join(timeout=5)
        if self.process.is_alive():
            self.process.kill()
            self.process.join(timeout=5)
        assert not self.process.is_alive()
        self.process.close()


def observe_count(dsn, table, pipe):
    """Fresh OS process and connection; table identifier is escaped, never SQL input."""
    import os
    from psycopg import sql

    with psycopg.connect(dsn) as connection:
        count = connection.execute(sql.SQL("SELECT count(*) FROM {}").format(
            sql.Identifier(table))).fetchone()[0]
    pipe.send({"count": count, "pid": os.getpid()})
    pipe.close()


def independent_count(dsn, table):
    receive, send = CONTEXT.Pipe(duplex=False)
    process = CONTEXT.Process(target=observe_count, args=(dsn, table, send))
    process.start()
    send.close()
    try:
        assert receive.poll(10), "independent database observer watchdog expired"
        result = receive.recv()
        process.join(timeout=5)
        assert process.exitcode == 0
        return result
    finally:
        receive.close()
        if process.is_alive():
            process.kill()
            process.join(timeout=5)
        process.close()
