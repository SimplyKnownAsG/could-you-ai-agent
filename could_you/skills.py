"""Agent Skills discovery and bounded access to bundled resources and scripts."""

import asyncio
import fnmatch
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path

import yaml

from .config import SkillSourceProps
from .logging_config import LOGGER

MAX_SCAN_DEPTH = 6
MAX_SCAN_DIRS = 2000
MAX_SKILL_BYTES = 512_000
MAX_FRONTMATTER_CHARS = 16_384
MAX_RESOURCE_BYTES = 1_000_000
MAX_SCRIPT_OUTPUT_BYTES = 128_000
SCRIPT_TIMEOUT_SECONDS = 60
MAX_NAME_LENGTH = 64
MAX_DESCRIPTION_LENGTH = 1024
MAX_COMPATIBILITY_LENGTH = 500
NAME_PATTERN = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z")
SKIP_DIRS = {".git", ".venv", "node_modules", "__pycache__", "scripts", "references", "assets"}


class SkillError(ValueError):
    """A user-actionable skill discovery or invocation error."""


@dataclass(frozen=True)
class Skill:
    name: str
    description: str
    root: Path


class SkillRegistry:
    def __init__(self, skills: dict[str, Skill] | None = None):
        self.skills = skills or {}

    @classmethod
    def discover(cls, sources: list[SkillSourceProps]) -> "SkillRegistry":
        skills: dict[str, Skill] = {}
        for source in sources:
            root = Path(source.directory)
            if not root.is_dir():
                LOGGER.warning("Skill scan directory is missing or not a directory: %s", root)
                continue
            root = root.resolve()
            todo = [(root, 0)]
            scanned = 0
            while todo:
                directory, depth = todo.pop()
                scanned += 1
                if scanned > MAX_SCAN_DIRS:
                    LOGGER.warning("Skill scan limit reached (%s directories): %s", MAX_SCAN_DIRS, root)
                    break
                try:
                    entries = sorted(directory.iterdir(), key=lambda item: item.name)
                    skill_file = directory / "SKILL.md"
                    if depth and skill_file.is_file():
                        try:
                            skill = _read_skill(skill_file, root)
                        except (SkillError, OSError, UnicodeError) as exc:
                            LOGGER.warning("Skipping invalid skill %s: %s", skill_file, exc)
                        else:
                            if any(fnmatch.fnmatchcase(skill.name, p) for p in source.include) and not any(
                                fnmatch.fnmatchcase(skill.name, p) for p in source.exclude
                            ):
                                if skill.name in skills:
                                    LOGGER.warning(
                                        "Skill %s at %s is shadowed by %s",
                                        skill.name,
                                        skill.root,
                                        skills[skill.name].root,
                                    )
                                else:
                                    skills[skill.name] = skill
                    if depth < MAX_SCAN_DEPTH:
                        for entry in reversed(entries):
                            if entry.name not in SKIP_DIRS and not entry.is_symlink() and entry.is_dir():
                                todo.append((entry, depth + 1))
                except OSError as exc:
                    LOGGER.warning("Cannot scan skill directory %s: %s", directory, exc)

        LOGGER.info(f"Discovered {len(skills)} skills:")

        for skill in skills.values():
            short = skill.description.replace("\n", " ")[:30] + " ..."
            LOGGER.info(f"    {skill.name}: {short}")

        return cls(skills)

    def load_skill_description(self) -> str:
        lines = [
            "You have access to [Agent Skills](https://agentskills.io/specification), which are reusable capability packs. Use skill",
            "names/descriptions to choose the most relevant skill. If matched, load it and follow its instructions; otherwise",
            "continue normally. Use only the most specific skill and do not activate unrelated ones.",
            "Use load_skill_resource for references/assets and run_skill_script for bundled scripts as needed.",
            "The following skills are available provided as a list `- <skill_name>: <skill_description>`:",
            "",
        ]

        for name, skill in sorted(self.skills.items()):
            lines.append(f"- {name}: {skill.description}")

        return "\n".join(lines)

    def _get(self, name: str) -> Skill:
        try:
            return self.skills[name]
        except (KeyError, TypeError) as exc:
            raise SkillError(f"Unknown or disabled skill: {name!r}") from exc

    def load_skill(self, name: str) -> str:
        skill = self._get(name)
        path = _contained_file(skill.root, "SKILL.md", allowed={"SKILL.md"})
        return _read_bounded(path, MAX_SKILL_BYTES)

    def load_resource(self, name: str, path: str) -> str:
        skill = self._get(name)
        resource = _contained_file(skill.root, path, allowed={"references", "assets"})
        try:
            return _read_bounded(resource, MAX_RESOURCE_BYTES)
        except UnicodeError as exc:
            raise SkillError(f"Resource is not UTF-8 text: {path!r}") from exc

    async def run_script(self, name: str, script_name: str, args: list[str]) -> str:
        skill = self._get(name)
        if not isinstance(args, list) or any(not isinstance(arg, str) or "\x00" in arg for arg in args):
            raise SkillError("args must be a list of strings without NUL bytes")
        script = _contained_file(skill.root, script_name, allowed={"scripts"})
        # Scripts are invoked directly using their shebang and executable bit.
        if not os.access(script, os.X_OK):
            raise SkillError(f"Script is not executable: {script_name!r}; add a shebang and chmod +x")
        try:
            process = await asyncio.create_subprocess_exec(
                str(script),
                *args,
                cwd=skill.root,
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except OSError as exc:
            raise SkillError(f"Could not start script {script_name!r}: {exc}") from exc
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=SCRIPT_TIMEOUT_SECONDS)
        except (TimeoutError, asyncio.CancelledError):
            process.kill()
            await process.communicate()
            raise
        if len(stdout) > MAX_SCRIPT_OUTPUT_BYTES or len(stderr) > MAX_SCRIPT_OUTPUT_BYTES:
            raise SkillError("Script output exceeded 128 KiB per stream")
        result = json.dumps(
            {
                "exit_code": process.returncode,
                "stdout": stdout.decode("utf-8", errors="replace"),
                "stderr": stderr.decode("utf-8", errors="replace"),
            }
        )
        if process.returncode:
            raise SkillError(f"Script failed: {result}")
        return result


def _read_bounded(path: Path, limit: int) -> str:
    try:
        with path.open("rb") as stream:
            data = stream.read(limit + 1)
    except OSError as exc:
        raise SkillError(f"Cannot read {path}: {exc}") from exc
    if len(data) > limit:
        raise SkillError(f"File exceeds size limit ({limit} bytes): {path}")
    return data.decode("utf-8")


def _read_skill(path: Path, scan_root: Path) -> Skill:
    front_matter_lines = []
    frontmatter_bytes = 0
    with path.open("rb") as stream:
        if stream.readline(MAX_FRONTMATTER_CHARS + 1) != b"---\n":
            raise SkillError("SKILL.md must begin with --- frontmatter marker")

        while True:
            line = stream.readline(MAX_FRONTMATTER_CHARS - frontmatter_bytes + 1)
            if not line:
                raise SkillError("SKILL.md is missing closing --- frontmatter marker")
            if line.rstrip(b"\r\n") == b"---":
                break
            frontmatter_bytes += len(line)
            if frontmatter_bytes > MAX_FRONTMATTER_CHARS:
                raise SkillError("SKILL.md frontmatter exceeds size limit")
            front_matter_lines.append(line)

    try:
        frontmatter = yaml.safe_load(b"".join(front_matter_lines).decode("utf-8"))
    except yaml.YAMLError as exc:
        raise SkillError(f"Invalid SKILL.md YAML frontmatter: {exc}") from exc
    if not isinstance(frontmatter, dict):
        raise SkillError("SKILL.md frontmatter must be a mapping")

    name = frontmatter.get("name")
    description = frontmatter.get("description")

    if (
        not isinstance(name, str)
        or not NAME_PATTERN.fullmatch(name)
        or len(name) > MAX_NAME_LENGTH
        or name != path.parent.name
    ):
        raise SkillError(f"Invalid skill name {name!r}; must match directory and Agent Skills naming rules")

    if (
        not isinstance(description, str)
        or not 1 <= len(description) <= MAX_DESCRIPTION_LENGTH
        or not description.strip()
    ):
        raise SkillError("description must be nonempty text of at most 1024 characters")

    if path.parent.resolve() != path.parent or not path.parent.resolve().is_relative_to(scan_root.resolve()):
        raise SkillError("Skill directory must be inside scan directory without symlinks")

    return Skill(name, description, path.parent)


def _contained_file(root: Path, name: str, *, allowed: set[str]) -> Path:
    if not isinstance(name, str) or not name or "\x00" in name:
        raise SkillError("Path must be a nonempty relative path")
    relative = Path(name)
    if relative.is_absolute() or ".." in relative.parts or not relative.parts or relative.parts[0] not in allowed:
        raise SkillError(f"Path must be relative to one of {sorted(allowed)} without traversal: {name!r}")
    target = root / relative
    if not target.is_file():
        raise SkillError(f"File does not exist inside skill directory: {name!r}")
    return target
