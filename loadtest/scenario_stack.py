"""Stack control for load tests: scale, stop, kill, restore, hardware info, loadtest config."""

from __future__ import annotations

import asyncio
import os
import platform
import shutil
from pathlib import Path
from typing import Any

import asyncpg
from redis.asyncio import Redis

REPO = Path(__file__).resolve().parent.parent
PROJECT = "alerting"
LOADTEST_CONFIG = [REPO / "config/rules/loadtest-events.yaml"]


async def run_cmd(*args: str) -> str:
    """Run a command in the repo root and return stdout; raises on a non-zero exit."""
    proc = await asyncio.create_subprocess_exec(
        *args,
        cwd=REPO,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    out, err = await proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(f"{' '.join(args)} failed: {err.decode().strip()}")
    return out.decode().strip()


def has_docker() -> bool:
    """False inside the compose network, where the generator has no docker CLI."""
    return shutil.which("docker") is not None


async def compose(*args: str) -> str:
    """Run `docker compose -p alerting ...`."""
    return await run_cmd("docker", "compose", "-p", PROJECT, *args)


async def running_containers(service: str) -> list[str]:
    """Container ids of the running replicas of a compose service."""
    out = await compose("ps", "-q", "--status", "running", service)
    return [line for line in out.splitlines() if line]


async def scale(service: str, replicas: int, settle_s: float = 5.0) -> None:
    """Scale one service without recreating or rebuilding anything else."""
    await compose(
        "up", "-d", "--no-recreate", "--no-deps", "--no-build",
        "--scale", f"{service}={replicas}", service,
    )  # fmt: skip
    for _ in range(60):
        if len(await running_containers(service)) == replicas:
            break
        await asyncio.sleep(1)
    await asyncio.sleep(settle_s)  # let new consumers join their group


async def restore_stack() -> None:
    """Back to processor=1, delivery=2 (the compose default) and mock-gateway started.

    Skipped without a docker CLI (generator running inside the compose network): scenarios that
    scale or stop services must run on the host.
    """
    if not has_docker():
        print("no docker CLI here: stack left as is (in-network generator)")
        return
    await compose(
        "up", "-d", "--no-recreate", "--no-deps", "--no-build",
        "--scale", "processor=1", "--scale", "delivery=2",
        "processor", "delivery", "mock-gateway",
    )  # fmt: skip


async def kill_one(service: str) -> str:
    """`docker kill` the last replica of a service; returns its container id."""
    containers = await running_containers(service)
    await run_cmd("docker", "kill", containers[-1])
    return containers[-1][:12]


async def hardware(replicas: dict[str, int | None] | None = None) -> dict[str, Any]:
    """Host and Docker details for the results table."""
    info: dict[str, Any] = {
        "os": platform.platform(),
        "machine": platform.machine(),
        "cpu_cores": os.cpu_count(),
        "replicas": replicas or {},
    }
    try:
        info["cpu_model"] = await run_cmd("sysctl", "-n", "machdep.cpu.brand_string")
        info["ram_gb"] = round(int(await run_cmd("sysctl", "-n", "hw.memsize")) / 2**30, 1)
    except (RuntimeError, FileNotFoundError):
        info["cpu_model"] = platform.processor() or "unknown"
    try:
        docker = await run_cmd(
            "docker", "info", "--format", "{{.ServerVersion}}|{{.NCPU}}|{{.MemTotal}}"
        )
        version, ncpu, mem = docker.split("|")
        info |= {
            "docker_version": version,
            "docker_vm_cpus": int(ncpu),
            "docker_vm_ram_gb": round(int(mem) / 2**30, 1),
        }
    except (RuntimeError, ValueError, FileNotFoundError):  # no docker CLI inside the network
        info["docker_version"] = "unknown"
    return info


async def install_loadtest_config(pool: asyncpg.Pool, redis: Redis) -> None:
    """Save the loadtest source and rule through the config save path (idempotent).

    Done here instead of relying on the bind-mounted `config/` so a run works from any checkout.
    """
    from alerting_core.config.watcher import handle_config_file_change

    for file in LOADTEST_CONFIG:
        await handle_config_file_change(file, pool, redis)
