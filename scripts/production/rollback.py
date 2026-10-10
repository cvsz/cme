#!/usr/bin/env python3
"""Run an explicitly approved API-only rollback after a read-only schema check."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[2]
APPROVAL_VALUE = "I_APPROVE_LIVE_APPLICATION_ROLLBACK"
SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$", re.IGNORECASE)
IMAGE_ID_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$", re.IGNORECASE)


def run(command: list[str], *, timeout: int = 60) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, capture_output=True, text=True, check=False, timeout=timeout)


def compose_command(*arguments: str) -> list[str]:
    command = ["docker", "compose"]
    for env_file in os.environ.get("CME_COMPOSE_ENV_FILES", "").split(os.pathsep):
        if env_file:
            command.extend(["--env-file", env_file])
    return [*command, *arguments]


def report(state: str, detail: str) -> None:
    print(f"{state} - Application rollback: {detail}")


def parse_compose_json(output: str) -> list[dict[str, object]]:
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
            record = json.loads(line)
            if isinstance(record, dict):
                records.append(record)
    return records


def write_record(path_value: str, record: dict[str, object]) -> None:
    path = Path(path_value)
    if not path.is_absolute() or path.is_symlink():
        raise ValueError
    parent = path.parent.resolve(strict=True)
    if parent == ROOT or ROOT in parent.parents:
        raise ValueError
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        json.dump(record, stream, indent=2, sort_keys=True)
        stream.write("\n")


def ready(base_url: str) -> bool:
    try:
        with urlopen(f"{base_url.rstrip('/')}/ready", timeout=3) as response:
            body = json.loads(response.read())
            return (
                response.status == 200
                and body.get("status") == "ready"
                and body.get("environment") == "production"
                and body.get("schema_revision", "0004_accounting_journal")
                == "0004_accounting_journal"
                and body.get("dependencies", {"database": "ready", "redis": "ready"})
                == {"database": "ready", "redis": "ready"}
            )
    except (OSError, URLError, TimeoutError, json.JSONDecodeError, AttributeError):
        return False


def api_health_is_stable() -> bool:
    result = run(compose_command("ps", "--format", "json"))
    if result.returncode != 0:
        return False
    try:
        api = next(
            record for record in parse_compose_json(result.stdout) if record.get("Service") == "api"
        )
        name = str(api.get("Name", ""))
    except (StopIteration, json.JSONDecodeError):
        return False
    if not name:
        return False
    inspected = run(
        [
            "docker",
            "inspect",
            "--format",
            "{{.RestartCount}}|{{.State.Health.Status}}",
            name,
        ]
    )
    return inspected.returncode == 0 and inspected.stdout.strip() == "0|healthy"


def prior_runtime_identity() -> tuple[str | None, str | None]:
    status = run(compose_command("ps", "--format", "json"))
    if status.returncode != 0:
        return None, None
    try:
        api = next(
            item for item in parse_compose_json(status.stdout) if item.get("Service") == "api"
        )
    except (StopIteration, json.JSONDecodeError):
        return None, None
    name = str(api.get("Name", ""))
    if not name:
        return None, None
    inspected = run(
        [
            "docker",
            "inspect",
            "--format",
            '{{.Image}}|{{index .Config.Labels "org.opencontainers.image.revision"}}',
            name,
        ]
    )
    if inspected.returncode != 0:
        return None, None
    parts = inspected.stdout.strip().split("|", 1)
    if len(parts) != 2:
        return None, None
    prior_sha = (
        parts[1] if SHA_PATTERN.fullmatch(parts[1]) else os.environ.get("CME_CURRENT_RELEASE_SHA")
    )
    return parts[0], prior_sha


def main() -> int:
    if os.environ.get("CME_APP_ENV") != "production":
        report("BLOCKED", "CME_APP_ENV must explicitly be production")
        return 2
    if os.environ.get("CME_ROLLBACK_APPROVAL") != APPROVAL_VALUE:
        report(
            "BLOCKED",
            "explicit CME_ROLLBACK_APPROVAL is required before a live service change",
        )
        return 2
    image_id = os.environ.get("CME_ROLLBACK_IMAGE_ID", "")
    release_sha = os.environ.get("CME_ROLLBACK_RELEASE_SHA", "")
    image_ref = os.environ.get("CME_ROLLBACK_IMAGE_REF", "")
    evidence_file = os.environ.get("CME_RELEASE_EVIDENCE_FILE", "")
    record_file = os.environ.get("CME_ROLLBACK_RECORD_FILE", "")
    if not IMAGE_ID_PATTERN.fullmatch(image_id) or not SHA_PATTERN.fullmatch(release_sha):
        report("BLOCKED", "supply the recorded prior image ID and full Git SHA")
        return 2
    if not image_ref or any(char.isspace() for char in image_ref):
        report(
            "BLOCKED",
            "supply the exact prior image reference already present in the release configuration",
        )
        return 2
    if not evidence_file or not record_file:
        report(
            "BLOCKED",
            "supply unique release and rollback evidence paths outside the repository",
        )
        return 2
    if shutil.which("docker") is None:
        report("BLOCKED", "Docker CLI is unavailable")
        return 2

    started = datetime.now(UTC)
    config = run(compose_command("config", "--format", "json"))
    if config.returncode != 0:
        report("BLOCKED", "deployment Compose configuration is unavailable")
        return 2
    try:
        services = json.loads(config.stdout)["services"]
        api_service = services["api"]
        configured_ref = api_service.get("image")
        configured_env = api_service.get("environment", {})
        configured_sha = api_service.get("build", {}).get("args", {}).get("CME_RELEASE_SHA")
    except (json.JSONDecodeError, KeyError, TypeError):
        report("BLOCKED", "deployment image configuration could not be read")
        return 2
    if (
        configured_ref != image_ref
        or configured_sha != release_sha
        or configured_env.get("CME_APP_ENV") != "production"
    ):
        report(
            "FAIL",
            "Compose does not select the approved prior image reference and Git SHA",
        )
        return 1

    image = run(
        [
            "docker",
            "image",
            "inspect",
            "--format",
            '{{.Id}}|{{index .Config.Labels "org.opencontainers.image.revision"}}',
            image_ref,
        ]
    )
    if image.returncode != 0 or image.stdout.strip() != f"{image_id}|{release_sha}":
        report(
            "FAIL",
            "prior image reference, exact image ID, and embedded SHA did not match",
        )
        return 1

    compatibility = run(
        [sys.executable, str(ROOT / "scripts" / "production" / "rollback-check.py")]
    )
    if compatibility.returncode != 0:
        report(
            "BLOCKED",
            "prior image schema compatibility check failed; API service was not changed",
        )
        return 2

    previous_image_id, previous_sha = prior_runtime_identity()
    if previous_image_id is None or previous_sha is None or not SHA_PATTERN.fullmatch(previous_sha):
        report(
            "BLOCKED",
            "current API release identity could not be recorded before rollback",
        )
        return 2

    changed = run(compose_command("up", "-d", "--no-deps", "api"), timeout=120)
    if changed.returncode != 0:
        report(
            "FAIL",
            "Compose could not recreate only the API service; command output was suppressed",
        )
        return 1

    base_url = os.environ.get("CME_BASE_URL", "http://127.0.0.1:8000")
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline and not (ready(base_url) and api_health_is_stable()):
        time.sleep(2)

    verify_env = os.environ.copy()
    verify_env.update(
        {
            "CME_EXPECTED_RELEASE_SHA": release_sha,
            "CME_EXPECTED_IMAGE_ID": image_id,
            "CME_RELEASE_EVIDENCE_FILE": evidence_file,
        }
    )
    verification = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "production" / "verify.py"),
            "--rollback-compatibility",
        ],
        capture_output=True,
        text=True,
        check=False,
        env=verify_env,
        timeout=180,
    )
    ended = datetime.now(UTC)
    record = {
        "attempt_started_at_utc": started.isoformat(),
        "attempt_completed_at_utc": ended.isoformat(),
        "prior_release_sha_before_rollback": previous_sha,
        "prior_image_id_before_rollback": previous_image_id,
        "restored_release_sha": release_sha,
        "restored_image_id": image_id,
        "compatibility": "PASS",
        "post_rollback_verification": "PASS" if verification.returncode == 0 else "FAIL",
        "release_evidence_file": evidence_file if verification.returncode == 0 else None,
    }
    try:
        write_record(record_file, record)
    except (OSError, ValueError):
        report(
            "FAIL",
            "rollback completed but no-clobber audit record could not be written",
        )
        return 1

    if verification.returncode != 0:
        report(
            "FAIL",
            "API rollback ran but live verification failed; keep the database unchanged and investigate",
        )
        return 1
    report(
        "PASS",
        "prior API image restored and live verification passed; database was not modified",
    )
    report("PASS", f"rollback audit record written with mode 0600 to {record_file}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, subprocess.TimeoutExpired):
        report(
            "BLOCKED",
            "a required Docker command, endpoint, or evidence location is unavailable",
        )
        raise SystemExit(2) from None
