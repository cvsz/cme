#!/usr/bin/env python3
"""Verify a live CMe release and write a no-clobber evidence manifest."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[2]
EXPECTED_SCHEMA_REVISION = "0004_accounting_journal"
SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$", re.IGNORECASE)
IMAGE_ID_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$", re.IGNORECASE)
CHECKSUM_PATTERN = re.compile(r"^[0-9a-f]{64}$", re.IGNORECASE)
checks: list[str] = []


def policy_target_configured(value: str) -> bool:
    normalized = value.strip().casefold()
    return bool(normalized) and not any(
        marker in normalized
        for marker in (
            "replace_me",
            "changeme",
            "change_me",
            "example",
            "your_",
            "owner_approved",
            "placeholder",
            "todo",
            "tbd",
        )
    )


def report(state: str, name: str, detail: str) -> None:
    checks.append(state)
    print(f"{state} - {name}: {detail}")


def run(command: list[str], *, timeout: int = 20) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, capture_output=True, text=True, check=False, timeout=timeout)


def compose_command(*arguments: str) -> list[str]:
    command = ["docker", "compose"]
    for env_file in os.environ.get("CME_COMPOSE_ENV_FILES", "").split(os.pathsep):
        if env_file:
            command.extend(["--env-file", env_file])
    return [*command, *arguments]


def parse_json_lines(output: str) -> list[dict[str, object]]:
    try:
        document = json.loads(output)
        if isinstance(document, dict):
            return [document]
        if isinstance(document, list):
            return [record for record in document if isinstance(record, dict)]
    except json.JSONDecodeError:
        pass
    records = []
    for line in output.splitlines():
        if line.strip():
            item = json.loads(line)
            if isinstance(item, dict):
                records.append(item)
    return records


def read_endpoint(base_url: str, path: str) -> dict[str, object] | None:
    try:
        with urlopen(f"{base_url.rstrip('/')}/{path.lstrip('/')}", timeout=5) as response:
            if response.status != 200:
                return None
            data = json.loads(response.read())
            return data if isinstance(data, dict) else None
    except (OSError, URLError, TimeoutError, json.JSONDecodeError):
        return None


def inspect_container(name: str) -> dict[str, object] | None:
    template = (
        '{{.RestartCount}}|{{.Image}}|{{index .Config.Labels "org.opencontainers.image.revision"}}|'
        "{{json .State}}|{{json .NetworkSettings.Ports}}"
    )
    result = run(["docker", "inspect", "--format", template, name])
    if result.returncode != 0:
        return None
    parts = result.stdout.strip().split("|", 4)
    if len(parts) != 5:
        return None
    try:
        return {
            "restart_count": int(parts[0]),
            "image_id": parts[1],
            "release_sha": parts[2],
            "state": json.loads(parts[3]),
            "ports": json.loads(parts[4]),
        }
    except (ValueError, json.JSONDecodeError):
        return None


def private_ports(service: str, ports: object) -> bool:
    if not isinstance(ports, dict):
        return False
    published = [bindings for bindings in ports.values() if bindings]
    if service in {"postgres", "redis"}:
        return not published
    if service == "api":
        return bool(published) and all(
            isinstance(binding, dict) and binding.get("HostIp") == "127.0.0.1"
            for bindings in published
            for binding in bindings
        )
    return True


def write_manifest(path_value: str, manifest: dict[str, object]) -> None:
    path = Path(path_value)
    if not path.is_absolute() or path.is_symlink():
        raise ValueError("evidence path must be absolute and must not be a symlink")
    resolved_parent = path.parent.resolve(strict=True)
    if resolved_parent == ROOT or ROOT in resolved_parent.parents:
        raise ValueError("evidence path must be outside the repository")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        json.dump(manifest, stream, indent=2, sort_keys=True)
        stream.write("\n")


def verified_backup(path_value: str) -> dict[str, object] | None:
    backup = Path(path_value)
    checksum_path = Path(f"{backup}.sha256")
    if (
        backup.is_symlink()
        or checksum_path.is_symlink()
        or not backup.is_file()
        or not checksum_path.is_file()
    ):
        return None
    try:
        checksum = checksum_path.read_text(encoding="ascii").strip()
        if not CHECKSUM_PATTERN.fullmatch(checksum):
            return None
        digest = hashlib.sha256()
        with backup.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        if digest.hexdigest().casefold() != checksum.casefold():
            return None
        archive = run(["pg_restore", "--list", str(backup)])
        if archive.returncode != 0:
            return None
        return {
            "path": str(backup),
            "sha256": checksum.casefold(),
            "size_bytes": backup.stat().st_size,
        }
    except OSError:
        return None


def dependency_probe(service: str, command: list[str], expected: str) -> bool:
    result = run(compose_command("exec", "-T", service, *command))
    return result.returncode == 0 and result.stdout.strip() == expected


def main() -> int:
    expected_sha = os.environ.get("CME_EXPECTED_RELEASE_SHA", "")
    expected_image_id = os.environ.get("CME_EXPECTED_IMAGE_ID", "")
    evidence_file = os.environ.get("CME_RELEASE_EVIDENCE_FILE", "")
    if SHA_PATTERN.fullmatch(expected_sha):
        report("PASS", "Expected Git SHA", "full commit SHA supplied")
    else:
        report(
            "BLOCKED",
            "Expected Git SHA",
            "set CME_EXPECTED_RELEASE_SHA to the deployed 40-character SHA",
        )
    if IMAGE_ID_PATTERN.fullmatch(expected_image_id):
        report("PASS", "Expected image ID", "immutable local SHA-256 image ID supplied")
    else:
        report(
            "BLOCKED",
            "Expected image ID",
            "set CME_EXPECTED_IMAGE_ID from the deployed image inspection",
        )
    if evidence_file:
        report("PASS", "Evidence destination", "release evidence path supplied")
    else:
        report(
            "BLOCKED",
            "Evidence destination",
            "set CME_RELEASE_EVIDENCE_FILE outside the repository",
        )

    rpo_target = os.environ.get("CME_RPO_TARGET", "").strip()
    rto_target = os.environ.get("CME_RTO_TARGET", "").strip()
    report(
        "PASS" if policy_target_configured(rpo_target) else "BLOCKED",
        "Configured RPO policy",
        "non-placeholder target is configured; release-owner approval is external"
        if policy_target_configured(rpo_target)
        else "set CME_RPO_TARGET from approved release policy",
    )
    report(
        "PASS" if policy_target_configured(rto_target) else "BLOCKED",
        "Configured RTO policy",
        "non-placeholder target is configured; release-owner approval is external"
        if policy_target_configured(rto_target)
        else "set CME_RTO_TARGET from approved release policy",
    )

    if shutil.which("docker") is None:
        report("BLOCKED", "Compose runtime", "Docker CLI is unavailable")
        return 2
    config_result = run(compose_command("config", "--format", "json"))
    if config_result.returncode != 0:
        report(
            "BLOCKED",
            "Compose runtime",
            "Docker Compose could not resolve the deployment",
        )
        return 2
    try:
        config = json.loads(config_result.stdout)
    except json.JSONDecodeError:
        report(
            "FAIL",
            "Compose configuration",
            "Docker Compose returned invalid structured configuration",
        )
        return 1
    services = config.get("services", {})
    service_definitions = {name: services.get(name, {}) for name in ("api", "postgres", "redis")}

    private = (
        bool(service_definitions["api"].get("ports"))
        and all(
            port.get("host_ip") == "127.0.0.1"
            for port in service_definitions["api"].get("ports", [])
        )
        and all(not service_definitions[name].get("ports") for name in ("postgres", "redis"))
    )
    report(
        "PASS" if private else "FAIL",
        "Private service exposure",
        "API is loopback-bound and PostgreSQL/Redis publish no host ports"
        if private
        else "API must be loopback-bound and PostgreSQL/Redis must publish no host ports",
    )

    ps_result = run(compose_command("ps", "--format", "json"))
    try:
        containers = parse_json_lines(ps_result.stdout) if ps_result.returncode == 0 else []
    except json.JSONDecodeError:
        containers = []
    runtime_services = {str(record.get("Service")): record for record in containers}
    required_services = {"api", "postgres", "redis"}
    present = required_services <= set(runtime_services)
    report(
        "PASS" if present else "BLOCKED",
        "Required containers",
        "API, PostgreSQL, and Redis are present"
        if present
        else "one or more required Compose containers are unavailable",
    )

    container_evidence: dict[str, dict[str, object]] = {}
    metadata_ok = present
    for service in sorted(required_services):
        record = runtime_services.get(service)
        if record is None:
            metadata_ok = False
            continue
        state = str(record.get("State", "")).casefold()
        health = str(record.get("Health", "")).casefold()
        name = str(record.get("Name", ""))
        inspected = inspect_container(name) if name else None
        if inspected is None:
            metadata_ok = False
            continue
        container_state = inspected["state"]
        health_info = container_state.get("Health") if isinstance(container_state, dict) else None
        health_status = str(
            health_info.get("Status", health) if isinstance(health_info, dict) else health
        ).casefold()
        if state != "running" or health_status != "healthy":
            metadata_ok = False
        if inspected["restart_count"] != 0:
            metadata_ok = False
        if not private_ports(service, inspected["ports"]):
            metadata_ok = False
        container_evidence[service] = {
            "state": state,
            "health": health_status,
            "restart_count": inspected["restart_count"],
            "image_id": inspected["image_id"],
            "release_sha": inspected["release_sha"],
        }
        if service == "api":
            if inspected["release_sha"] != expected_sha:
                metadata_ok = False
            if inspected["image_id"] != expected_image_id:
                metadata_ok = False
    report(
        "PASS" if metadata_ok else "FAIL",
        "Container health, identity, and restarts",
        "all required containers are healthy, have zero restarts, and the API image matches the expected SHA and image ID"
        if metadata_ok
        else "health, restart count, release label, image ID, or private port checks failed",
    )

    base_url = os.environ.get("CME_BASE_URL", "http://127.0.0.1:8000")
    health = read_endpoint(base_url, "/health")
    health_ok = health is not None and health.get("status") == "ok"
    report(
        "PASS" if health_ok else "FAIL",
        "HTTP liveness",
        "health endpoint returned HTTP 200" if health_ok else "health endpoint failed",
    )

    readiness = read_endpoint(base_url, "/ready")
    dependencies = readiness.get("dependencies") if readiness else None
    legacy_rollback = "--rollback-compatibility" in sys.argv[1:]
    modern_ready = (
        readiness is not None
        and readiness.get("schema_revision") == EXPECTED_SCHEMA_REVISION
        and dependencies == {"database": "ready", "redis": "ready"}
    )
    compatible_legacy_ready = (
        legacy_rollback
        and readiness is not None
        and dependencies is None
        and readiness.get("schema_revision") is None
        and dependency_probe("redis", ["redis-cli", "ping"], "PONG")
    )
    ready_ok = (
        readiness is not None
        and readiness.get("status") == "ready"
        and readiness.get("environment") == "production"
        and (modern_ready or compatible_legacy_ready)
    )
    report(
        "PASS" if ready_ok else "FAIL",
        "HTTP readiness, schema, and dependencies",
        "production readiness, schema compatibility, PostgreSQL, and Redis are ready"
        if ready_ok
        else "readiness response did not satisfy every production requirement",
    )

    logs_result = run(compose_command("logs", "--tail=100", "api"))
    log_text = f"{logs_result.stdout}\n{logs_result.stderr}".lower()
    error_markers = sum(
        log_text.count(marker) for marker in ("error", "exception", "traceback", "critical")
    )
    logs_ok = logs_result.returncode == 0 and error_markers == 0
    report(
        "PASS" if logs_ok else "FAIL",
        "Recent API logs",
        "last 100 lines contain no error markers"
        if logs_ok
        else "recent API logs contain errors or could not be read",
    )

    backup_value = os.environ.get("CME_BACKUP_FILE", "")
    backup_evidence = verified_backup(backup_value) if backup_value else None
    report(
        "PASS" if backup_evidence else "FAIL",
        "Verified backup evidence",
        "backup checksum matches and size is recorded"
        if backup_evidence
        else "set CME_BACKUP_FILE to a valid backup with a matching SHA-256 sidecar",
    )

    if all(state == "PASS" for state in checks):
        manifest = {
            "recorded_at_utc": datetime.now(UTC).isoformat(),
            "environment": "production",
            "git_sha": expected_sha,
            "schema_revision": readiness.get("schema_revision", EXPECTED_SCHEMA_REVISION),
            "image_id": expected_image_id,
            "backup": backup_evidence,
            "services": container_evidence,
            "checks": {"health": "PASS", "readiness": "PASS", "logs": "PASS"},
            "rpo_target": rpo_target,
            "rto_target": rto_target,
        }
        try:
            write_manifest(evidence_file, manifest)
            report(
                "PASS",
                "Release evidence manifest",
                "written with mode 0600 without overwriting an existing file",
            )
        except (OSError, ValueError):
            report(
                "FAIL",
                "Release evidence manifest",
                "destination was unsafe, unavailable, or already exists",
            )

    if all(state == "PASS" for state in checks):
        print("OVERALL - PASS")
        return 0
    print("OVERALL - BLOCKED" if "BLOCKED" in checks else "OVERALL - FAIL")
    return 2 if "BLOCKED" in checks else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, subprocess.TimeoutExpired):
        print(
            "BLOCKED - Production verification: a required local command or endpoint is unavailable"
        )
        raise SystemExit(2) from None
