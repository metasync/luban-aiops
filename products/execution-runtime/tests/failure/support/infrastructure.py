"""Owned local Docker resources, never an environment-supplied database."""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import secrets
import shutil
import subprocess
import sys
from uuid import uuid4

import psycopg

ROOT = Path(__file__).resolve().parents[5]
COMPOSE = Path(__file__).with_name("compose.yaml")
PRODUCTS = {
    "execution-runtime": "execution_runtime",
    "agent-platform": "agent_service",
    "tool-gateway": "tool_gateway",
    "platform-gateway": "platform_gateway",
}


class PrerequisiteError(RuntimeError):
    pass


def command(args: list[str], *, env=None, timeout=30) -> str:
    """Do not propagate command output: Docker errors can contain credentials."""
    try:
        result = subprocess.run(args, env=env, capture_output=True, text=True,
                                timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired):
        raise PrerequisiteError(f"{args[0]} unavailable or exceeded watchdog") from None
    if result.returncode:
        raise PrerequisiteError(f"{args[0]} prerequisite/resource operation failed")
    return result.stdout.strip()


def prerequisites() -> dict:
    for executable in ("docker", "uv"):
        if not shutil.which(executable):
            raise PrerequisiteError(f"install {executable} before running failure proofs")
    # Only local Unix-socket daemons are in scope. No implicit remote Docker host.
    if os.environ.get("DOCKER_HOST") or os.environ.get("DOCKER_CONTEXT"):
        raise PrerequisiteError("unset Docker endpoint overrides; select a local context")
    context = json.loads(command(["docker", "context", "inspect"]))[0]
    if not context["Endpoints"]["docker"]["Host"].startswith("unix://"):
        raise PrerequisiteError("failure proofs require a local Unix-socket Docker daemon")
    docker = json.loads(command(["docker", "version", "--format", "{{json .}}"] ))
    compose = command(["docker", "compose", "version", "--short"])
    match = re.match(r"v?(\d+)\.", compose)
    if not match or int(match[1]) < 2:
        raise PrerequisiteError("Docker Compose v2 or a compatible successor is required")
    versions = {}
    for product, module in PRODUCTS.items():
        python = ROOT / "products" / product / ".venv/bin/python"
        if not python.is_file():
            raise PrerequisiteError(f"run make -C products/{product} sync first")
        versions[product] = command([
            str(python), "-c", f"import {module}; import sys; print(sys.version.split()[0])"
        ])
    return {"docker": docker["Server"]["Version"], "compose": compose,
            "uv": command(["uv", "--version"]), "python": sys.version.split()[0],
            "product_python": versions,
            "git_head": command(["git", "-C", str(ROOT), "rev-parse", "HEAD"]),
            "dirty": bool(command(["git", "-C", str(ROOT), "status", "--porcelain"]))}


class DisposablePostgres:
    def __init__(self):
        self.owner = uuid4().hex
        self.project = f"spec063-{self.owner}"
        self.password = secrets.token_hex(24)
        self.env = {key: value for key, value in os.environ.items()
                    if key in {"PATH", "HOME", "TMPDIR", "DOCKER_CONFIG"}}
        self.env.update(SPEC063_OWNER=self.owner, SPEC063_DB_PASSWORD=self.password)
        self.dsn = ""
        self.metadata = {}
        self.started = False

    def compose(self, *args, timeout=60):
        return command(["docker", "compose", "--project-name", self.project,
                        "--file", str(COMPOSE), *args], env=self.env, timeout=timeout)

    def start(self):
        self.started = True
        try:
            self.compose("up", "--detach", "--wait", "--wait-timeout", "45", timeout=120)
            container = self.compose("ps", "--quiet", "postgres")
            label = command(["docker", "inspect", "--format",
                             '{{index .Config.Labels "io.luban.spec063.owner"}}', container])
            if label != self.owner:
                raise PrerequisiteError("database ownership verification failed")
            endpoint = self.compose("port", "postgres", "5432")
            if not re.fullmatch(r"127\.0\.0\.1:\d+", endpoint):
                raise PrerequisiteError("database must be bound only to loopback")
            port = int(endpoint.rsplit(":", 1)[1])
            self.dsn = (f"host=127.0.0.1 port={port} user=spec063 dbname=spec063 "
                        f"password={self.password} connect_timeout=2 sslmode=disable")
            with self.connect() as conn:
                version = conn.execute("SHOW server_version_num").fetchone()[0]
                if int(version) // 10000 != 16:
                    raise PrerequisiteError("failure proofs require PostgreSQL 16")
                durability = {key: conn.execute(f"SHOW {key}").fetchone()[0]
                              for key in ("fsync", "full_page_writes", "synchronous_commit")}
                if any(value != "on" for value in durability.values()):
                    raise PrerequisiteError("Postgres durability is not enabled")
            image_id = command(["docker", "inspect", "--format", "{{.Image}}", container])
            digests = json.loads(command(["docker", "image", "inspect", "--format",
                                          "{{json .RepoDigests}}", image_id]))
            self.metadata = {"project": self.project, "postgres_version": version,
                             "image_id": image_id, "image_digests": digests,
                             "durability": durability}
            return self
        except BaseException:
            self.close()
            raise

    def connect(self):
        if not self.dsn:
            raise PrerequisiteError("disposable Postgres has not started")
        return psycopg.connect(self.dsn, options="-c statement_timeout=2000 -c lock_timeout=2000")

    def close(self):
        if not self.started:
            return
        # Verify every object targeted by Compose, not only the container. Refuse
        # teardown if a name was reused or ownership evidence is missing.
        for kind, list_args in (
            ("container", ["ps", "-aq"]),
            ("volume", ["volume", "ls", "-q"]),
            ("network", ["network", "ls", "-q"]),
        ):
            ids = command(["docker", *list_args, "--filter",
                           f"label=com.docker.compose.project={self.project}"]).split()
            for object_id in ids:
                template = ('{{index .Config.Labels "io.luban.spec063.owner"}}'
                            if kind == "container" else
                            '{{index .Labels "io.luban.spec063.owner"}}')
                label = command(["docker", kind, "inspect", "--format", template, object_id])
                if label != self.owner:
                    raise PrerequisiteError("refusing teardown of unowned Docker resource")
        self.compose("down", "--volumes", "--timeout", "5")
        self.started = False
