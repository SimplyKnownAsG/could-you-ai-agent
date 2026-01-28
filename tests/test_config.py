import os
from pathlib import Path

import pytest

from could_you.config import Config, InvalidConfigError, _find_workspace_config_dir, init
from could_you.config import load as real_load

MINIMAL_JSON = '{"llm": {"provider": "openai", "args": { "model": "gpt-4" } }}'
MINIMAL_YAML = """
llm:
  provider: boto3
  args:
      modelId: us.anthropic.claude-sonnet-4-20250514-v1:0
"""


def load(script_name: str | None = None) -> Config:
    return real_load(script_name)[0]


def test_load_workspace_json_config(tmp_workspace: Path):
    w_config_path = tmp_workspace / "config.json"
    w_config_path.write_text(MINIMAL_JSON)
    config = load()
    assert config.llm.provider == "openai"
    assert config.llm.args["model"] == "gpt-4"


def test_load_workspace_yaml_config(tmp_workspace: Path):
    w_config_path = tmp_workspace / "config.yaml"
    w_config_path.write_text(MINIMAL_YAML)
    config = load()
    assert config.llm.provider == "boto3"
    assert config.llm.args["modelId"] == "us.anthropic.claude-sonnet-4-20250514-v1:0"


@pytest.mark.parametrize("ext", ["json", "yaml", "yml"])
def test_empty_fails(tmp_workspace: Path, ext: str):
    w_config_path = tmp_workspace / f"config.{ext}"
    w_config_path.write_text("{}")
    with pytest.raises(InvalidConfigError, match="Must specify"):
        load()


def test_bad_provider(tmp_workspace: Path):
    w_config_path = tmp_workspace / "config.json"
    w_config_path.write_text('{"llm": {"provider": "human", "model": "m40"}}')
    with pytest.raises(InvalidConfigError, match="Invalid provider"):
        load()


def test_not_in_workspace(tmp_dir: Path):
    with pytest.raises(InvalidConfigError, match="within a workspace"):
        _find_workspace_config_dir(tmp_dir)

    with pytest.raises(InvalidConfigError, match="within a workspace"):
        load()


def test_load_config_invalid_json(tmp_workspace: Path):
    w_config_path = tmp_workspace / "config.json"
    w_config_path.write_text("not json")
    with pytest.raises(InvalidConfigError, match="Failed to load"):
        load()


def test_load_config_invalid_yaml(tmp_workspace: Path):
    w_config_path = tmp_workspace / "config.yaml"
    w_config_path.write_text("llm:\n  - 'invalid: [this is not valid: yaml")
    with pytest.raises(InvalidConfigError, match="Failed to load"):
        load()


def test_init(tmp_cy_config_dir: Path, tmp_dir: Path):  # noqa: ARG001
    config_dir = tmp_dir / ".could-you"
    assert not config_dir.exists()

    init()

    assert config_dir.exists()
    assert config_dir.is_dir()

    expected = {"script.summarize.yaml", "script.fix_build.json", "config.yaml", "script.git-commit.yaml"}
    assert expected == {os.path.basename(f) for f in config_dir.iterdir()}


def test_init_already_exists(tmp_workspace: Path):  # noqa: ARG001
    with pytest.raises(InvalidConfigError, match="already exists"):
        init()


def test_load_git_commit_script(tmp_cy_config_dir: Path, tmp_dir: Path):  # noqa: ARG001
    init()
    config = load(script_name="git-commit")
    # Confirm query loaded from script, not from config
    assert config.query is not None
    assert "Conventional Commit message" in config.query
    # Should inherit llm from global config
    assert config.llm.provider == "openai"
    # Script should load mcpServers: expect the git-mcp tool config and that no "filesystem" tool is present
    git_mcp = config.mcp_servers.get("git-mcp")
    assert git_mcp, f"Expected to find 'git-mcp' server loaded from script got {config.mcp_servers}"
    # No workspace or user mcpServers should leak in:
    fs_servers = config.mcp_servers.get("filesystem")
    assert not fs_servers, "Should not merge filesystem mcpServers when running a script"


def test_load_nonexistent_script_raises(tmp_workspace: Path):
    w_config_path = tmp_workspace / "config.json"
    w_config_path.write_text(MINIMAL_JSON)

    # Enter workspace, expect failure
    with pytest.raises(InvalidConfigError, match="Failed to find"):
        load(script_name="definitely-does-not-exist")
