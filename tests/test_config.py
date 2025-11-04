import textwrap
import json
import os
import shutil
import tempfile
from pathlib import Path

import pytest

from could_you.config import load, InvalidConfigError
from .dir_changer import DirChanger

MINIMAL_JSON = '{"llm": {"provider": "openai", "model": "gpt-4"}}'
MINIMAL_YAML = """
llm:
  provider: boto3
  model: us.anthropic.claude-sonnet-4-20250514-v1:0
"""

def test_load_workspace_json_config(tmp_cy_config_dir: Path, tmp_dir: Path):
    w_config_path = tmp_dir / ".could-you-config.json"
    w_config_path.write_text(MINIMAL_JSON)
    config = load()
    assert config.llm["provider"] == "openai"
    assert config.llm["model"] == "gpt-4"

def test_load_workspace_yaml_config(tmp_cy_config_dir: Path, tmp_dir: Path):
    w_config_path = tmp_dir / ".could-you-config.yaml"
    w_config_path.write_text(MINIMAL_YAML)
    config = load()
    assert config.llm["provider"] == "boto3"
    assert config.llm["model"] == "us.anthropic.claude-sonnet-4-20250514-v1:0"

def test_load_global_json_config(tmp_cy_config_dir: Path, tmp_dir: Path):
    g_config_path = tmp_cy_config_dir / "config.json"
    g_config_path.write_text(MINIMAL_JSON)
    w_config_path = tmp_dir / ".could-you-config.json"
    w_config_path.write_text('{}') # empty
    config = load()
    assert config.llm["model"] == "gpt-4"

def test_load_global_yaml_config(tmp_cy_config_dir: Path, tmp_dir: Path):
    g_config_path = tmp_cy_config_dir / "config.yaml"
    g_config_path.write_text(MINIMAL_YAML)
    w_config_path = tmp_dir / ".could-you-config.yaml"
    w_config_path.write_text('{}') # empty
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

def test_missing_data(tmp_cy_config_dir: Path, tmp_dir: Path):
    w_config_path = tmp_dir / ".could-you-config.json"
    w_config_path.write_text('{}')
    with pytest.raises(InvalidConfigError):
        config = load()

def test_not_in_workspace(tmp_cy_config_dir: Path, tmp_dir: Path):
    with pytest.raises(InvalidConfigError):
        config = load()

def test_load_config_invalid_json(tmp_cy_config_dir: Path, tmp_dir: Path):
    w_config_path = tmp_dir / ".could-you-config.json"
    w_config_path.write_text("not json")
    with pytest.raises(InvalidConfigError):
        load()

def test_load_config_invalid_yaml(tmp_cy_config_dir: Path, tmp_dir: Path):
    w_config_path = tmp_dir / ".could-you-config.yaml"
    w_config_path.write_text("llm:\n  - 'invalid: [this is not valid: yaml")
    with pytest.raises(InvalidConfigError):
        load()
