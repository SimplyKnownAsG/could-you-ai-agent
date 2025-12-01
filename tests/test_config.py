from pathlib import Path

import pytest

from could_you.config import InvalidConfigError, load

MINIMAL_JSON = '{"llm": {"provider": "openai", "model": "gpt-4"}}'
MINIMAL_YAML = """
llm:
  provider: boto3
  model: us.anthropic.claude-sonnet-4-20250514-v1:0
"""


def test_load_workspace_json_config(tmp_cy_config_dir: Path, tmp_dir: Path):  # noqa: ARG001
    w_config_path = tmp_dir / ".could-you-config.json"
    w_config_path.write_text(MINIMAL_JSON)
    config = load()
    assert config.llm["provider"] == "openai"
    assert config.llm["model"] == "gpt-4"


def test_load_workspace_yaml_config(tmp_cy_config_dir: Path, tmp_dir: Path):  # noqa: ARG001
    w_config_path = tmp_dir / ".could-you-config.yaml"
    w_config_path.write_text(MINIMAL_YAML)
    config = load()
    assert config.llm["provider"] == "boto3"
    assert config.llm["model"] == "us.anthropic.claude-sonnet-4-20250514-v1:0"


def test_load_global_json_config(tmp_cy_config_dir: Path, tmp_dir: Path):
    g_config_path = tmp_cy_config_dir / "config.json"
    g_config_path.write_text(MINIMAL_JSON)
    w_config_path = tmp_dir / ".could-you-config.json"
    w_config_path.write_text("{}")  # empty
    config = load()
    assert config.llm["model"] == "gpt-4"


def test_load_global_yaml_config(tmp_cy_config_dir: Path, tmp_dir: Path):
    g_config_path = tmp_cy_config_dir / "config.yaml"
    g_config_path.write_text(MINIMAL_YAML)
    w_config_path = tmp_dir / ".could-you-config.yaml"
    w_config_path.write_text("{}")  # empty
    config = load()
    assert config.llm["model"] == "us.anthropic.claude-sonnet-4-20250514-v1:0"


def test_workspace_overide_global(tmp_cy_config_dir: Path, tmp_dir: Path):
    g_config_path = tmp_cy_config_dir / "config.json"
    g_config_path.write_text(MINIMAL_JSON)
    w_config_path = tmp_dir / ".could-you-config.json"
    w_config_path.write_text('{"llm": {"model": "gpt-99"} }')
    config = load()
    assert config.llm["provider"] == "openai"
    assert config.llm["model"] == "gpt-99"


def test_empty_fails(tmp_cy_config_dir: Path, tmp_dir: Path):  # noqa: ARG001
    w_config_path = tmp_dir / ".could-you-config.json"
    w_config_path.write_text("{}")
    with pytest.raises(InvalidConfigError, match="Must specify"):
        load()


def test_bad_provider(tmp_cy_config_dir: Path, tmp_dir: Path):  # noqa: ARG001
    w_config_path = tmp_dir / ".could-you-config.json"
    w_config_path.write_text('{"llm": {"provider": "human", "model": "m40"}}')
    with pytest.raises(InvalidConfigError, match="Invalid provider"):
        load()


def test_not_in_workspace(tmp_cy_config_dir: Path, tmp_dir: Path):  # noqa: ARG001
    with pytest.raises(InvalidConfigError, match="within a workspace"):
        load()


def test_load_config_invalid_json(tmp_cy_config_dir: Path, tmp_dir: Path):  # noqa: ARG001
    w_config_path = tmp_dir / ".could-you-config.json"
    w_config_path.write_text("not json")
    with pytest.raises(InvalidConfigError, match="Failed to load"):
        load()


def test_load_config_invalid_yaml(tmp_cy_config_dir: Path, tmp_dir: Path):  # noqa: ARG001
    w_config_path = tmp_dir / ".could-you-config.yaml"
    w_config_path.write_text("llm:\n  - 'invalid: [this is not valid: yaml")
    with pytest.raises(InvalidConfigError, match="Failed to load"):
        load()


def test_load_global_git_commit_script(tmp_cy_config_dir: Path, tmp_dir: Path):  # noqa: ARG001
    # Write a minimal valid global config
    g_config_path = tmp_cy_config_dir / "config.json"
    g_config_path.write_text(MINIMAL_JSON)

    config = load(script_name="git-commit")
    # Confirm query loaded from script, not from config
    assert config.query is not None
    assert "Conventional Commit message" in config.query
    # Should inherit llm from global config
    assert config.llm["provider"] == "openai"
    # Script should load mcpServers: expect the git-mcp tool config and that no "filesystem" tool is present
    git_mcp = [srv for srv in config.servers if srv.name == "git-mcp"]
    assert git_mcp, "Expected to find 'git-mcp' server loaded from script"
    # No workspace or user mcpServers should leak in:
    fs_servers = [srv for srv in config.servers if srv.name == "filesystem"]
    assert not fs_servers, "Should not merge filesystem mcpServers when running a script"


def test_load_nonexistent_script_raises(tmp_cy_config_dir: Path, tmp_dir: Path):  # noqa: ARG001
    g_config_path = tmp_cy_config_dir / "config.json"
    g_config_path.write_text(MINIMAL_JSON)
    # No workspace config

    # Enter workspace, expect failure
    with pytest.raises(InvalidConfigError, match="does not exist"):
        load(script_name="definitely-does-not-exist")


def test_load_workspace_script_overrides_global(tmp_cy_config_dir: Path, tmp_dir: Path):
    # Write a minimal valid global config for llm inheritance
    g_config_path = tmp_cy_config_dir / "config.json"
    g_config_path.write_text(MINIMAL_JSON)
    # Write a workspace-specific script
    w_script_path = tmp_dir / ".could-you-script.git-commit.json"
    custom_query = "Workspace script override commit message."
    w_script_path.write_text(
        f'{{"query": "{custom_query}", "llm": {{"provider": "openai", "model": "gpt-3.5-turbo"}}}}'
    )

    config = load(script_name="git-commit")
    # Should read the query from the workspace script, overriding the global script's
    assert config.query == custom_query
    # Should use llm specified in the workspace script, not the global config
    assert config.llm["model"] == "gpt-3.5-turbo"
