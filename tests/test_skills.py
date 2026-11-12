import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from could_you.agent import Agent
from could_you.config import Config, LLMProps, SkillSourceProps, SkillsProps
from could_you.message import ToolUse
from could_you.session import Session
from could_you.skills import MAX_FRONTMATTER_CHARS, SkillError, SkillRegistry, _read_skill
from could_you.tools.skill_tools import LoadSkillResourceTool, LoadSkillTool, RunSkillScriptTool


def create_skill(root: Path, name: str = "pdf-tools", description: str = "Extract PDF text") -> Path:
    skill = root / name
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text(f"---\nname: {name}\ndescription: {description}\n---\n# Instructions\n")
    return skill


def registry(root: Path, **kwargs) -> SkillRegistry:
    return SkillRegistry.discover([SkillSourceProps(directory=str(root), **kwargs)])


def test_discovery_filter_collision_and_nested(tmp_path, caplog):
    first, second = tmp_path / "first", tmp_path / "second"
    skill = create_skill(first / "team")
    create_skill(first, "excluded")
    create_skill(second, description="Shadowing version")
    result = SkillRegistry.discover(
        [SkillSourceProps(directory=str(first), exclude=["excl*"]), SkillSourceProps(directory=str(second))]
    )
    assert list(result.skills) == ["pdf-tools"]
    assert result.skills["pdf-tools"].description == "Extract PDF text"
    assert "shadowed" in caplog.text
    description = result.load_skill_description()
    assert "- pdf-tools: Extract PDF text" in description
    assert "# Instructions" not in description
    content = result.load_skill("pdf-tools")
    assert content == (skill / "SKILL.md").read_text()
    assert "# Instructions" in content
    assert str(skill) not in content


def test_bad_frontmatter_and_symlink_are_skipped(tmp_path, caplog):
    root = tmp_path / "skills"
    create_skill(root, "bad-name")
    (root / "bad-name" / "SKILL.md").write_text("---\nname: WRONG\ndescription: nope\n---\n")
    create_skill(root, "empty")
    (root / "empty" / "SKILL.md").write_text("---\nname: empty\n---\n")
    external = create_skill(tmp_path / "other", "outside")
    (root / "linked").symlink_to(external, target_is_directory=True)
    assert not registry(root).skills
    assert "Skipping invalid skill" in caplog.text


def test_read_skill_uses_provided_path(tmp_path):
    skill = create_skill(tmp_path, "actual-skill", "From the requested file")
    result = _read_skill(skill / "SKILL.md", tmp_path)
    assert result.name == "actual-skill"
    assert result.description == "From the requested file"
    assert result.root == skill


@pytest.mark.parametrize(
    ("frontmatter", "diagnostic"),
    [
        ("---\nname: missing\ndescription: valid\n", "closing"),
        ("---\nname: malformed\ndescription: [oops\n---\n", "YAML"),
        ("---\nname: oversized\ndescription: " + "x" * MAX_FRONTMATTER_CHARS, "size limit"),
    ],
)
def test_invalid_frontmatter_does_not_crash_discovery(tmp_path, caplog, frontmatter, diagnostic):
    name = frontmatter.split("name: ", 1)[1].split("\n", 1)[0]
    skill = create_skill(tmp_path, name)
    (skill / "SKILL.md").write_text(frontmatter)
    assert not registry(tmp_path).skills
    assert diagnostic in caplog.text
    assert "Skipping invalid skill" in caplog.text


def test_discovery_stops_reading_at_second_exact_delimiter(tmp_path):
    skill = create_skill(tmp_path, "body-unread")
    path = skill / "SKILL.md"
    path.write_bytes(b"---\nname: body-unread\ndescription: valid\n---\n" + b"\xff" * 1_000_000)
    assert registry(tmp_path).skills["body-unread"].description == "valid"


def test_non_exact_delimiter_is_not_accepted(tmp_path, caplog):
    skill = create_skill(tmp_path, "non-exact")
    (skill / "SKILL.md").write_text("---\nname: non-exact\ndescription: valid\n --- \n")
    assert not registry(tmp_path).skills
    assert "missing closing" in caplog.text


def test_resources_require_safe_relative_path(tmp_path):
    skill = create_skill(tmp_path)
    (skill / "references").mkdir()
    (skill / "assets").mkdir()
    (skill / "references" / "guide.md").write_text("Guide")
    (skill / "assets" / "image.svg").write_text("<svg />")
    outside = tmp_path / "secret.txt"
    outside.write_text("secret")
    (skill / "assets" / "escape.txt").symlink_to(outside)
    skills = registry(tmp_path)
    assert skills.load_resource("pdf-tools", "references/guide.md") == "Guide"
    assert skills.load_resource("pdf-tools", "assets/image.svg") == "<svg />"
    # Symlinks that escape the skill root are allowed (spec does not restrict them).
    assert skills.load_resource("pdf-tools", "assets/escape.txt") == "secret"
    for path in ("../secret.txt", str(outside), "SKILL.md", "scripts/anything"):
        with pytest.raises(SkillError):
            skills.load_resource("pdf-tools", path)
    with pytest.raises(SkillError, match="Unknown"):
        skills.load_skill("missing")


@pytest.mark.asyncio
async def test_script_execution_arguments_errors_and_tools(tmp_path):
    skill = create_skill(tmp_path)
    scripts = skill / "scripts"
    scripts.mkdir()
    script = scripts / "echo.py"
    script.write_text("#!/usr/bin/env python3\nimport json, sys\nprint(json.dumps(sys.argv[1:]))\n")
    script.chmod(0o755)
    skills = registry(tmp_path)
    result = json.loads(await skills.run_script("pdf-tools", "scripts/echo.py", ["a b", "$(touch /tmp/no)"]))
    assert json.loads(result["stdout"]) == ["a b", "$(touch /tmp/no)"]
    assert result["exit_code"] == 0
    with pytest.raises(SkillError):
        await skills.run_script("pdf-tools", "scripts/../SKILL.md", [])
    with pytest.raises(SkillError, match="list of strings"):
        await skills.run_script("pdf-tools", "scripts/echo.py", [42])
    tool_use = ToolUse(toolUseId="id", name="load_skill", input={})
    assert (await LoadSkillTool(skills)(tool_use, {"skill_name": "pdf-tools"})).tool_result.status == "success"
    assert (
        await LoadSkillResourceTool(skills)(tool_use, {"skill_name": "pdf-tools", "path": "no"})
    ).tool_result.status == "error"
    assert (
        await RunSkillScriptTool(skills)(
            tool_use, {"skill_name": "pdf-tools", "script_name": "scripts/echo.py", "args": []}
        )
    ).tool_result.status == "success"


@pytest.mark.asyncio
async def test_agent_registers_skills_in_tool_description_not_system_prompt(tmp_path):
    create_skill(tmp_path)
    config = Config(
        llm=LLMProps(provider="openai"),
        systemPrompt="base",
        skills=SkillsProps(sources=[SkillSourceProps(directory=str(tmp_path))]),
    )
    session = Session(tmp_path, None, config)
    with patch("could_you.agent.create_llm", return_value=AsyncMock()) as create_llm:
        async with Agent(session_manager=AsyncMock(), session=session) as agent:
            assert {"load_skill", "load_skill_resource", "run_skill_script"} <= agent.tools.keys()
            description = agent.tools["load_skill"].description
            assert "- pdf-tools: Extract PDF text" in description
            assert "<available_skills>" not in description
            assert "# Instructions" not in description
            assert create_llm.call_args.args[0].system_prompt == "base"
    assert config.system_prompt == "base"
