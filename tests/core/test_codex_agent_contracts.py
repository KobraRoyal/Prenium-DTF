from pathlib import Path

from scripts.check_codex_agents import validate_agent_data, validate_repository


def test_project_codex_agent_contracts_are_valid():
    assert validate_repository() == []


def test_unknown_or_underpowered_sensitive_agent_is_rejected():
    errors = validate_agent_data(
        Path(".codex/agents/ids_security_reviewer.toml"),
        {
            "name": "ids_security_reviewer",
            "description": "Security review",
            "model": "gpt-5.6-terra",
            "model_reasoning_effort": "low",
            "sandbox_mode": "read-only",
            "developer_instructions": "Honor AGENTS.md and return a concise review.",
        },
    )

    assert any("model must be 'gpt-5.6-sol'" in error for error in errors)
    assert any("model_reasoning_effort must be 'high'" in error for error in errors)
    assert any("missing security invariant 'cross-tenant'" in error for error in errors)
