#!/usr/bin/env python3
"""Validate project-scoped Codex orchestration contracts with stdlib only."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10 pre-commit fallback
    import tomli as tomllib

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = Path(".codex/config.toml")
AGENTS_DIR = Path(".codex/agents")
POLICY_PATH = Path("docs/architecture/CODEX_AGENT_ORCHESTRATION.md")

REQUIRED_FIELDS = {
    "name",
    "description",
    "model",
    "model_reasoning_effort",
    "developer_instructions",
}
ALLOWED_FIELDS = REQUIRED_FIELDS | {"nickname_candidates", "sandbox_mode"}
EXPECTED_ROUTING = {
    "ids_explorer": ("gpt-5.6-terra", "low", "read-only"),
    "ids_qa": ("gpt-5.6-terra", "medium", None),
    "ids_backend_worker": ("gpt-5.6-sol", "medium", None),
    "ids_ui_worker": ("gpt-5.6-sol", "medium", None),
    "ids_security_reviewer": ("gpt-5.6-sol", "high", "read-only"),
    "ids_domain_architect": ("gpt-5.6-sol", "high", "read-only"),
}
SENSITIVE_INVARIANTS = {
    "ids_backend_worker": ("customer", "public_id", "audit", "cross-tenant"),
    "ids_security_reviewer": ("customer", "public_id", "audit", "cross-tenant"),
    "ids_domain_architect": ("customer", "public_id", "audit", "cross-tenant"),
    "ids_ui_worker": ("business rules", "permissions"),
}


def _read_toml(path: Path, errors: list[str]) -> dict[str, Any]:
    try:
        with path.open("rb") as handle:
            return tomllib.load(handle)
    except FileNotFoundError:
        errors.append(f"missing file: {path}")
    except tomllib.TOMLDecodeError as exc:
        errors.append(f"invalid TOML in {path}: {exc}")
    return {}


def _validate_project_config(root: Path, errors: list[str]) -> None:
    path = root / CONFIG_PATH
    config = _read_toml(path, errors)
    agents = config.get("agents")
    if not isinstance(agents, dict):
        errors.append(f"{CONFIG_PATH}: missing [agents] table")
        return

    expected = {"max_threads": 3, "max_depth": 1, "interrupt_message": True}
    for key, value in expected.items():
        if agents.get(key) != value:
            errors.append(f"{CONFIG_PATH}: agents.{key} must be {value!r}")


def validate_agent_data(path: Path, data: dict[str, Any]) -> list[str]:
    """Return semantic contract errors for one custom agent definition."""

    errors: list[str] = []
    relative_path = path.as_posix()
    missing = REQUIRED_FIELDS - data.keys()
    unknown = data.keys() - ALLOWED_FIELDS
    if missing:
        errors.append(f"{relative_path}: missing fields {sorted(missing)}")
    if unknown:
        errors.append(f"{relative_path}: unsupported fields {sorted(unknown)}")

    name = data.get("name")
    if name != path.stem:
        errors.append(f"{relative_path}: name must match filename stem {path.stem!r}")
    if name not in EXPECTED_ROUTING:
        errors.append(f"{relative_path}: unregistered agent name {name!r}")
        return errors

    model, effort, sandbox = EXPECTED_ROUTING[name]
    if data.get("model") != model:
        errors.append(f"{relative_path}: model must be {model!r}")
    if data.get("model_reasoning_effort") != effort:
        errors.append(f"{relative_path}: model_reasoning_effort must be {effort!r}")
    if sandbox is not None and data.get("sandbox_mode") != sandbox:
        errors.append(f"{relative_path}: sandbox_mode must be {sandbox!r}")

    for field in ("description", "developer_instructions"):
        value = data.get(field)
        if not isinstance(value, str) or not value.strip():
            errors.append(f"{relative_path}: {field} must be a non-empty string")

    nicknames = data.get("nickname_candidates")
    if nicknames is not None:
        if not isinstance(nicknames, list) or not nicknames:
            errors.append(f"{relative_path}: nickname_candidates must be a non-empty list")
        elif len(nicknames) != len(set(nicknames)):
            errors.append(f"{relative_path}: nickname_candidates must be unique")

    instructions = str(data.get("developer_instructions", "")).lower()
    for phrase in ("agents.md", "concise"):
        if phrase not in instructions:
            errors.append(f"{relative_path}: developer_instructions must mention {phrase!r}")
    for phrase in SENSITIVE_INVARIANTS.get(name, ()):
        if phrase not in instructions:
            errors.append(f"{relative_path}: missing security invariant {phrase!r}")
    return errors


def validate_repository(root: Path = ROOT) -> list[str]:
    """Validate all repository orchestration files."""

    errors: list[str] = []
    _validate_project_config(root, errors)

    agents_dir = root / AGENTS_DIR
    paths = sorted(agents_dir.glob("*.toml")) if agents_dir.is_dir() else []
    if not paths:
        errors.append(f"missing agent definitions in {AGENTS_DIR}")
    discovered = {path.stem for path in paths}
    expected = set(EXPECTED_ROUTING)
    if discovered != expected:
        errors.append(
            f"{AGENTS_DIR}: expected agents {sorted(expected)}, found {sorted(discovered)}"
        )

    for path in paths:
        data = _read_toml(path, errors)
        relative_path = path.relative_to(root)
        errors.extend(validate_agent_data(relative_path, data))

    policy_path = root / POLICY_PATH
    if not policy_path.is_file():
        errors.append(f"missing policy: {POLICY_PATH}")
    else:
        policy = policy_path.read_text(encoding="utf-8")
        for name in EXPECTED_ROUTING:
            if f"`{name}`" not in policy:
                errors.append(f"{POLICY_PATH}: missing routing entry for {name}")

    return errors


def main() -> int:
    errors = validate_repository()
    if errors:
        print("Codex agent contract validation failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print(f"Codex agent contracts valid: {len(EXPECTED_ROUTING)} agents")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
