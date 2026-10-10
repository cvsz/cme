#!/usr/bin/env python3
"""Check whether a pinned prior application image supports the live schema."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess

SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$", re.IGNORECASE)
IMAGE_ID_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$", re.IGNORECASE)


def report(state: str, detail: str) -> None:
    print(f"{state} - Application rollback compatibility: {detail}")


def run(
    command: list[str], *, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, capture_output=True, text=True, check=False, env=env, timeout=60)


def compose_command(*arguments: str) -> list[str]:
    command = ["docker", "compose"]
    for env_file in os.environ.get("CME_COMPOSE_ENV_FILES", "").split(os.pathsep):
        if env_file:
            command.extend(["--env-file", env_file])
    return [*command, *arguments]


def parse_compose_services(output: str) -> list[dict[str, object]]:
    try:
        result = json.loads(output)
        if isinstance(result, dict):
            return [result]
        if isinstance(result, list):
            return [item for item in result if isinstance(item, dict)]
    except json.JSONDecodeError:
        pass
    records = []
    for line in output.splitlines():
        if line.strip():
            item = json.loads(line)
            if isinstance(item, dict):
                records.append(item)
    return records


def compose_network() -> str | None:
    network_override = os.environ.get("CME_ROLLBACK_DOCKER_NETWORK")
    if network_override:
        return network_override
    status = run(compose_command("ps", "--format", "json"))
    if status.returncode != 0:
        return None
    try:
        api = next(
            item for item in parse_compose_services(status.stdout) if item.get("Service") == "api"
        )
    except (StopIteration, json.JSONDecodeError):
        return None
    inspected = run(
        [
            "docker",
            "inspect",
            "--format",
            "{{json .NetworkSettings.Networks}}",
            str(api["Name"]),
        ]
    )
    if inspected.returncode != 0:
        return None
    try:
        networks = json.loads(inspected.stdout)
        return next(iter(networks)) if networks else None
    except (json.JSONDecodeError, TypeError):
        return None


def main() -> int:
    image_id = os.environ.get("CME_ROLLBACK_IMAGE_ID", "")
    release_sha = os.environ.get("CME_ROLLBACK_RELEASE_SHA", "")
    if not IMAGE_ID_PATTERN.fullmatch(image_id) or not SHA_PATTERN.fullmatch(release_sha):
        report(
            "BLOCKED",
            "set CME_ROLLBACK_IMAGE_ID and CME_ROLLBACK_RELEASE_SHA from the prior release record",
        )
        return 2
    if shutil.which("docker") is None:
        report("BLOCKED", "Docker CLI is unavailable")
        return 2

    image = run(
        [
            "docker",
            "image",
            "inspect",
            "--format",
            '{{.Id}}|{{index .Config.Labels "org.opencontainers.image.revision"}}',
            image_id,
        ]
    )
    if image.returncode != 0:
        report("BLOCKED", "pinned rollback image is not available locally")
        return 2
    image_parts = image.stdout.strip().split("|", 1)
    if len(image_parts) != 2 or image_parts[0] != image_id or image_parts[1] != release_sha:
        report(
            "FAIL",
            "rollback image ID and embedded Git SHA do not match the prior release record",
        )
        return 1

    config = run(compose_command("config", "--format", "json"))
    if config.returncode != 0:
        report("BLOCKED", "Docker Compose configuration is unavailable")
        return 2
    try:
        api_env = json.loads(config.stdout)["services"]["api"].get("environment", {})
    except (json.JSONDecodeError, KeyError, TypeError):
        report("BLOCKED", "runtime database configuration is unavailable")
        return 2
    database_url = api_env.get("CME_DATABASE_URL")
    redis_url = api_env.get("CME_REDIS_URL")
    app_env = api_env.get("CME_APP_ENV")
    if not all(isinstance(value, str) and value for value in (database_url, redis_url, app_env)):
        report("BLOCKED", "runtime database or Redis configuration is missing")
        return 2

    network = compose_network()
    if not network:
        report("BLOCKED", "could not identify the current Compose network")
        return 2

    env = os.environ.copy()
    env.update(
        {
            "CME_APP_ENV": app_env,
            "CME_DATABASE_URL": database_url,
            "CME_REDIS_URL": redis_url,
        }
    )
    probe = run(
        [
            "docker",
            "run",
            "--rm",
            "--network",
            network,
            "--read-only",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges:true",
            "--env",
            "CME_APP_ENV",
            "--env",
            "CME_DATABASE_URL",
            "--env",
            "CME_REDIS_URL",
            "--entrypoint",
            "python",
            image_id,
            "-c",
            (
                "from sqlalchemy import text; from cme_api.db import SessionLocal; "
                "from cme_api.main import EXPECTED_SCHEMA_REVISION; "
                "db=SessionLocal(); revision=db.execute(text('SELECT version_num FROM alembic_version')).scalar_one(); "
                "db.close(); print(EXPECTED_SCHEMA_REVISION + '|' + revision)"
            ),
        ],
        env=env,
    )
    if probe.returncode != 0:
        report(
            "BLOCKED",
            "prior image could not read the current database schema; output was suppressed",
        )
        return 2
    revisions = probe.stdout.strip().split("|", 1)
    if len(revisions) != 2 or revisions[0] != revisions[1]:
        report(
            "FAIL",
            "prior application image is not compatible with the current database revision",
        )
        return 1
    report(
        "PASS",
        "prior image label, exact image ID, and current database revision are compatible",
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, subprocess.TimeoutExpired):
        report("BLOCKED", "a required Docker command or endpoint is unavailable")
        raise SystemExit(2) from None
