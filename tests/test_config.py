import os
import subprocess
from pathlib import Path

import pytest

from could_you.config import (
    Config,
    DialogueProps,
    InvalidConfigError,
    _find_workspace_config_dir,
    _is_git_repo,
    init,
    load,
    sync_workspace,
)

MINIMAL_JSON = '{"llm": {"provider": "openai", "args": { "model": "gpt-4" } }}'
MINIMAL_YAML = """
llm:
  provider: boto3
  args:
      modelId: us.anthropic.claude-sonnet-4-20250514-v1:0
"""


def test_load_workspace_json_config(tmp_workspace: Path):
    w_config_path = tmp_workspace / "config.json"
    w_config_path.write_text(MINIMAL_JSON)
    config, _ = load()
    assert config.llm.provider == "openai"
    assert config.llm.args["model"] == "gpt-4"


def test_load_workspace_token_limit(tmp_workspace: Path):
    w_config_path = tmp_workspace / "config.json"
    w_config_path.write_text('{"llm": {"provider": "openai", "tokenLimit": 128000}}')
    config, _ = load()
    assert config.llm.token_limit == 128000


def test_load_workspace_infers_token_limit(tmp_workspace: Path):
    w_config_path = tmp_workspace / "config.json"
    w_config_path.write_text('{"llm": {"provider": "openai", "args": {"model": "gpt-4o"}}}')
    config, _ = load()
    assert config.llm.token_limit == 128000


def test_load_workspace_memory_thresholds(tmp_workspace: Path):
    w_config_path = tmp_workspace / "config.yaml"
    w_config_path.write_text("""
llm:
  provider: openai
memory:
  warningThresholdPercent: 60
  rejectionThresholdPercent: 85
""")
    config, _ = load()
    assert config.memory.warning_threshold_percent == 60
    assert config.memory.rejection_threshold_percent == 85


def test_load_workspace_dialogue_defaults(tmp_workspace: Path):
    w_config_path = tmp_workspace / "config.yaml"
    w_config_path.write_text("""
llm:
  provider: openai
""")
    config, _ = load()
    assert config.dialogue == DialogueProps(load=True, store=True)


def test_load_workspace_dialogue_config(tmp_workspace: Path):
    w_config_path = tmp_workspace / "config.yaml"
    w_config_path.write_text("""
llm:
  provider: openai
dialogue:
  load: false
  store: true
""")
    config, _ = load()
    assert config.dialogue == DialogueProps(load=False, store=True)


def test_load_workspace_yaml_config(tmp_workspace: Path):
    w_config_path = tmp_workspace / "config.yaml"
    w_config_path.write_text(MINIMAL_YAML)
    config, _ = load()
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
    assert _is_git_repo(config_dir)

    expected = {
        ".git",
        "config.yaml",
        "SYSTEM_PROMPT.md",
        "script.compact-history.any-script.yaml",
        "script.compact-history.yaml",
        "script.git-commit.yaml",
    }
    assert expected == {os.path.basename(f) for f in config_dir.iterdir()}


def test_init_already_exists(tmp_workspace: Path):  # noqa: ARG001
    with pytest.raises(InvalidConfigError, match="already exists"):
        init()


def test_init_rejects_non_directory_workspace_path(tmp_dir: Path):
    workspace_path = tmp_dir / ".could-you"
    workspace_path.write_text("not a directory")

    with pytest.raises(InvalidConfigError, match="already exists"):
        init()


def test_sync_workspace_overwrites_managed_files(tmp_workspace: Path):
    config_path = tmp_workspace / "config.yaml"
    config_path.write_text("llm:\n  provider: openai\n")
    subprocess.run(["git", "-C", str(tmp_workspace), "init"], check=True)
    subprocess.run(["git", "-C", str(tmp_workspace), "config", "user.name", "could-you"], check=True)
    subprocess.run(["git", "-C", str(tmp_workspace), "config", "user.email", "could-you@localhost"], check=True)
    subprocess.run(["git", "-C", str(tmp_workspace), "add", "."], check=True)
    subprocess.run(["git", "-C", str(tmp_workspace), "commit", "-m", "seed workspace"], check=True)

    sync_workspace()

    assert "COULD_YOU_DEFAULT_PROMPT" in config_path.read_text()
    assert _is_git_repo(tmp_workspace)


def test_sync_workspace_skips_protected_files_from_user_templates(tmp_workspace: Path, monkeypatch):
    (tmp_workspace / "MEMORY.md").write_text("WORKSPACE MEMORY")
    (tmp_workspace / "TODO.md").write_text("WORKSPACE TODO")
    subprocess.run(["git", "-C", str(tmp_workspace), "init"], check=True)
    subprocess.run(["git", "-C", str(tmp_workspace), "config", "user.name", "could-you"], check=True)
    subprocess.run(["git", "-C", str(tmp_workspace), "config", "user.email", "could-you@localhost"], check=True)
    subprocess.run(["git", "-C", str(tmp_workspace), "add", "."], check=True)
    subprocess.run(["git", "-C", str(tmp_workspace), "commit", "-m", "seed workspace"], check=True)

    user_workspace_templates = tmp_workspace.parent / "user-templates"
    user_workspace_templates.mkdir()
    (user_workspace_templates / "MEMORY.md").write_text("USER TEMPLATE MEMORY")
    (user_workspace_templates / "TODO.md").write_text("USER TEMPLATE TODO")
    (user_workspace_templates / "custom.md").write_text("CUSTOM")
    conversations_dir = user_workspace_templates / "conversations"
    conversations_dir.mkdir(parents=True, exist_ok=True)
    (conversations_dir / "old.jsonl").write_text("archived")

    monkeypatch.setattr("could_you.config._get_user_config_dir_path", lambda: user_workspace_templates)

    sync_workspace()

    assert (tmp_workspace / "MEMORY.md").read_text() == "WORKSPACE MEMORY"
    assert (tmp_workspace / "TODO.md").read_text() == "WORKSPACE TODO"
    assert (tmp_workspace / "custom.md").read_text() == "CUSTOM"
    assert not (tmp_workspace / "conversations" / "old.jsonl").exists()


def test_sync_workspace_requires_existing_directory(tmp_dir: Path, monkeypatch):
    monkeypatch.chdir(tmp_dir)

    with pytest.raises(InvalidConfigError, match="does not exist"):
        sync_workspace()


def test_sync_workspace_creates_git_repo_for_legacy_workspace(tmp_dir: Path, monkeypatch):
    workspace_root = tmp_dir
    w_config_dir = workspace_root / ".could-you"
    w_config_dir.mkdir()
    (w_config_dir / "config.yaml").write_text("llm:\n  provider: openai\n")
    monkeypatch.chdir(workspace_root)

    with pytest.raises(InvalidConfigError, match="uncommitted changes"):
        sync_workspace()

    assert _is_git_repo(w_config_dir)


def test_load_git_commit_script(tmp_cy_config_dir: Path, tmp_dir: Path):  # noqa: ARG001
    init()
    (tmp_dir / ".could-you" / "MEMORY.md").write_text("WORKSPACE MEMORY")
    config, _ = load(script_name="git-commit")
    # Confirm query loaded from script, not from config
    assert config.query is not None
    assert "Conventional Commit message" in config.query
    # Should inherit llm from global config
    assert config.llm.provider == "openai"
    assert "WORKSPACE MEMORY" in config.system_prompt
    # Script should load mcpServers: expect the git-mcp tool config and that no "filesystem" tool is present
    git_mcp = config.mcp_servers.get("git-mcp")
    assert git_mcp, f"Expected to find 'git-mcp' server loaded from script got {config.mcp_servers}"
    # No workspace or user mcpServers should leak in:
    fs_servers = config.mcp_servers.get("filesystem")
    assert not fs_servers, "Should not merge filesystem mcpServers when running a script"


def test_load_compact_history_script_dialogue_settings(tmp_cy_config_dir: Path, tmp_dir: Path):  # noqa: ARG001
    init()
    config, _ = load(script_name="compact-history")

    assert config.dialogue == DialogueProps(load=True, store=False)


def test_load_nonexistent_script_raises(tmp_workspace: Path):
    w_config_path = tmp_workspace / "config.json"
    w_config_path.write_text(MINIMAL_JSON)

    # Enter workspace, expect failure
    with pytest.raises(InvalidConfigError, match="Failed to find"):
        load(script_name="definitely-does-not-exist")


def test_load_sets_workspace_env_and_chdir(tmp_path: Path, tmp_dir: Path, monkeypatch):  # noqa: ARG001
    """Ensure load() infers workspace root, sets COULD_YOU_WORKSPACE, and chdirs."""
    project_root = tmp_path / "project"
    project_root.mkdir()
    w_config_dir = project_root / ".could-you"
    w_config_dir.mkdir()

    config_path = w_config_dir / "config.yaml"
    config_path.write_text(MINIMAL_YAML)

    # Start in a subdirectory under the project
    subdir = project_root / "subdir"
    subdir.mkdir()
    monkeypatch.chdir(subdir)

    # Clear any preexisting env var to be explicit
    monkeypatch.delenv("COULD_YOU_WORKSPACE", raising=False)

    config, returned_w_config_dir = load()

    # w_config_dir should be the .could-you directory we created
    assert returned_w_config_dir == w_config_dir

    # COULD_YOU_WORKSPACE should be the parent (project root)
    assert os.environ.get("COULD_YOU_WORKSPACE") == str(project_root)

    # cwd should have been changed to the workspace root
    assert Path.cwd() == project_root

    # A minimal sanity check that config still parsed correctly
    assert isinstance(config, Config)
