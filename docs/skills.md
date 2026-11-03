# Agent Skills

could-you supports [Agent Skills](https://agentskills.io/specification) via explicitly configured scan directories. There are no default scan locations: configure each source under root-level `skills.sources` in `.could-you/config.yaml` (or its JSON equivalent).

```yaml
skills:
  sources:
    - directory: "$COULD_YOU_WORKSPACE/.agents/skills"
      include: ["*"]
      exclude: ["experimental-*"]
    - directory: "~/shared-skills"
      include: ["code-review"]
```

Each source has a required `directory` and optional `include` (defaults to `["*"]`) and `exclude` (defaults to `[]`) lists. Patterns are case-sensitive shell-style wildcards matched against the skill **name** from `SKILL.md`; exclude wins. Relative directory paths are resolved against the workspace root. `$COULD_YOU_WORKSPACE`, other environment variables, and `~` are expanded in directory paths. The directory contains skill subdirectories, each with a `SKILL.md`. Discovery is bounded and recursive (six levels, 2,000 directories per source). First configured source wins on name collisions; warnings identify shadowed skills and invalid `SKILL.md` files. Missing source directories produce warnings and are skipped.

When valid skills are found, could-you gives the model only their names and descriptions. Three tools are exposed:

- `load_skill(skill_name)` loads instructions from `SKILL.md`.
- `load_skill_resource(skill_name, path)` reads a UTF-8 relative path under the skill's `references/` or `assets/` directory. Binary assets are not supported by this text-only tool.
- `run_skill_script(skill_name, script_name, args)` runs an executable script under the skill's `scripts/` directory (with a shebang and executable bit). `args` is a list of strings, not a shell command. Runs from the skill directory with no interactive stdin; times out after 60 seconds and caps returned stdout and stderr at 128 KiB each. It reports exit code, stdout, and stderr.

Scripts and MCP tools run with the same OS-user permissions as could-you. **There is no sandbox or additional execution confirmation.** Only configure skill directories you trust. A skill can also contain instructions that affect model behavior; inspect skills from newly cloned repositories before enabling them. `allowed-tools` in skill frontmatter is experimental and does not confer or limit OS permissions in could-you.

`could-you script <name>` is an older, separate feature for running a could-you config overlay, not an Agent Skill script.
