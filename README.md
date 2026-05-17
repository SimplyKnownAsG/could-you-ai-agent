# could-you

A CLI wrapper around [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) that makes it easier to:

- Talk to MCP servers and tools through a conversational LLM interface
- Use a project-local workspace configuration (`.could-you/`)
- Run one-off, stateless "scripts" powered by LLM + tools

The project name is `could-you`, and the primary CLI entry point is typically installed as `could-you` (or `cy`, depending on your environment/packaging).

---

## Features

- **Workspace-aware**: Looks for a `.could-you/` directory from the current working directory upward.
- **Config merging**: Merges user-level configuration (from `$XDG_CONFIG_HOME/could-you`) with project-local configuration (from `.could-you/`).
- **Multiple LLM providers**:
  - AWS Bedrock via `boto3`
  - OpenAI-compatible providers via `openai`
  - Ollama via its OpenAI-compatible API
- **MCP server integration**: Spawns and manages MCP servers via stdio and exposes their tools to the LLM.
- **Script mode**: Run ephemeral scripts with their own config overlays using `--script`.
- **Message history**: Persisted per-workspace in `.could-you/messages.json` (opt-out with `--no-history`), including provider token usage on assistant messages when available.
- **Private memory backups**: Copy message history into the private `.could-you/` git repo with `--backup-memory`.
- **Permission inspection**: Print an observational OS-user/filesystem permission report with `--inspect-permissions`.

---

## Installation

### From source

Clone the repo and install in editable mode (development setup is described in more detail in `CONTRIBUTING.md`):

```bash
git clone https://github.com/SimplyKnownAsG/could-you-ai-agent.git
cd could-you-ai-agent

# Recommended: use uv
uv venv
source .venv/bin/activate
uv pip install -e .[dev]

# Or with plain pip
python -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
```

This will install the `could-you` (and/or `cy`) CLI entrypoint, depending on packaging.

---

## Basic Usage

Inside a project where you've initialized a workspace (see below), you can run:

```bash
could-you "Refactor the config loading logic to support environment overlays."
```

Without a direct query, `could-you` will open your `$EDITOR` (default `vim`) on a temporary `query.md`, showing previous messages and a marker for you to type after.

### CLI options

From `could_you/__main__.py`:

- Logging verbosity (mutually exclusive):
  - `-v`, `--verbose` – DEBUG level logging
  - `-q`, `--quiet` – WARNING level logging only
- History:
  - `-H`, `--no-history` – Do not load or persist message history for this run
- Config inspection:
  - `-C`, `--dump-config [json|yaml]` – Print the effective config (after overlays) then exit
- Session / workspace helpers:
  - `-l`, `--list-sessions` – List existing sessions from the cache
  - `-i`, `--init-session` – Initialize a `.could-you/` workspace in the current directory
  - `-d`, `--delete-session PATH` – Delete a specific session from the sessions cache
  - `-p`, `--print-history` – Print the message history for the current workspace
- Connectivity:
  - `-t`, `--test-connect [MESSAGE]` – Test MCP + LLM connectivity with a simple message, then exit
- Memory:
  - `--backup-memory [TOPIC]` – Back up `.could-you/messages.json` to the private memory git repo
- Permissions:
  - `--inspect-permissions` – Print an observational report about the current OS-user/filesystem permission boundary
- Scripts:
  - `-s`, `--script SCRIPT` – Run an ephemeral, stateless script config (see **Script Mode** below)

You can also run `could-you` with no `query` argument; in that case, it may fall back to `config.query` or launch `$EDITOR` as described above.

---

## Configuration

Configuration is primarily managed by `could_you/config.py` and resolved via `SessionManager` in `could_you/session.py`.

### Workspace discovery

`could-you` expects to run **inside a workspace**. It walks upward from the current directory looking for a `.could-you/` directory:

```text
project-root/
  .could-you/
    config.json (or .yaml / .yml)
    script.<name>.json (or .yaml / .yml)
    messages.json        # created automatically as you interact
  src/
  README.md
```

Use:

```bash
could-you --init-session
```

from your project root to create `.could-you/` using any global templates shipped in `could_you.resources`.

`could-you` treats `.could-you/` as private workspace state. Initialization ensures `.could-you/` is listed in the workspace `.gitignore` so conversation history, config, and future memories are not accidentally committed to the project repository.

### Config loading and merging

Config loading works as follows (see `load()` in `could_you/config.py`):

1. Locate the nearest `.could-you/` directory from the current working directory.
2. Load the base config from `.could-you/config.(json|yaml|yml)`.
3. If `--script <name>` is provided, also load `.could-you/script.<name>.(json|yaml|yml)` and overlay its values on top of the base config.
4. Validate and normalize the config:
   - Ensure `llm.provider` is one of `"boto3"`, `"ollama"`, or `"openai"`.
   - Expand the `systemPrompt` via the prompt utilities (see below).
   - Infer the workspace root as the parent directory of `.could-you/` and:
     - Set `COULD_YOU_WORKSPACE` in `os.environ` to that path.
     - Change the process working directory to `COULD_YOU_WORKSPACE` so all relative paths are evaluated from the workspace root.
   - Apply environment variables from `env` to `os.environ`.
   - Expand `$COULD_YOU_WORKSPACE` in MCP server arguments and environment variables to the workspace root.

### Config schema

`could_you/config.py` defines the primary data structures using `attrs`:

- `LLMProps`:
  - `provider: str` – one of `"boto3"`, `"ollama"`, `"openai"`.
  - `init: dict[str, Any]` – provider-specific initialization args; e.g. for OpenAI: `{ "api_key": "..." }`.
  - `args: dict[str, Any]` – per-request arguments; e.g. `{ "model": "gpt-4.1-mini" }`.
  - `tokenLimit: int | null` – optional configured context/token limit for the selected model. Providers generally report tokens used, but not the model limit, so could-you stores this explicit configured value alongside each assistant response. If omitted, could-you tries a best-effort local lookup from the configured model name (`model`, `modelId`, or `model_id`).

- `MCPServerProps` (keyed by server name in `mcpServers`):
  - `command: str` – the executable to launch (e.g. `"npx"`).
  - `args: list[str]` – command arguments; `"$COULD_YOU_WORKSPACE"` is expanded to your workspace root.
  - `disabledTools: list[str]` – MCP tool names that should be advertised but disabled for the LLM.
  - `env: dict[str, str]` – environment variables for that server process.
  - `enabled: bool` – whether to spawn the server at all.

- `Config`:
  - `llm: LLMProps`
  - `systemPrompt: str | null` – system prompt or prompt pattern (see below). Defaults to `"COULD_YOU_DEFAULT_PROMPT"`.
  - `mcpServers: dict[str, MCPServerProps]`
  - `env: dict[str, str]` – environment variables applied to the current process.
  - `query: str | null` – default query used in script mode when no CLI query is provided.

### Example configuration

A complete example using OpenAI and the official filesystem MCP server:

```json
{
  "llm": {
    "provider": "openai",
    "init": {
      "api_key": "your-api-key"
    },
    "args": {
      "model": "gpt-4.1-mini"
    },
    "tokenLimit": 1047576
  },
  "mcpServers": {
    "filesystem": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "$COULD_YOU_WORKSPACE"],
      "enabled": true,
      "disabledTools": ["write_file", "create_directory"]
    }
  },
  "systemPrompt": "COULD_YOU_DEFAULT_PROMPT"
}
```

---

## System Prompt & Prompt Expansion

Prompt expansion is handled by `could_you/prompt.py`. It supports two main patterns:

### 1. Default System Prompt Pattern

To use the built-in default system prompt for the agent, set in your config:

```json
{
  "systemPrompt": "COULD_YOU_DEFAULT_PROMPT"
}
```

At runtime, this pattern is expanded to a longer text equivalent to:

```text
Your name is Cy.

You are an agent responsible for helping a software developer perform tasks.

DO ASSUME file content is correct.

DO NOT ASSUME any file edits you have previously made will be persisted, or were correct.

DO NOT ASSUME that you should make file edits, only make file changes if asked. For example, if asked to "show" or
"tell" only provide an answer.

COULD_YOU_LOAD_FILE(*.md)
```

This expansion happens **before** any `COULD_YOU_LOAD_FILE(...)` directives are resolved.

### 2. `COULD_YOU_LOAD_FILE(...)` directives

You can embed file-loading directives in your system prompt. They are expanded at runtime to include the contents of matching files in the current workspace.

- Syntax:

  ```text
  COULD_YOU_LOAD_FILE(relative/pattern/*.md)
  ```

- The pattern is treated as a glob relative to the workspace root (the parent directory of `.could-you/`).
- For each matching file **inside** the workspace tree, the content is loaded and wrapped in markers:

  ```text
  <could-you-prompt-expanded-file "/absolute/path/to/file.ext">
  ... file contents ...
  </could-you-prompt-expanded-file "/absolute/path/to/file.ext">
  ```

- Non-file paths or files outside the workspace root are ignored, with a log message.

This allows you to create powerful prompts like:

```text
COULD_YOU_LOAD_FILE(README.md)
COULD_YOU_LOAD_FILE(docs/*.md)
```

---

## MCP Servers and Tools

MCP integration is implemented in `could_you/mcp_server.py`.

### Server lifecycle

For each entry in `config.mcpServers`:

1. `Agent.__aenter__` constructs an `MCPServer` with its `MCPServerProps`.
2. If the server is `enabled`, it starts the process using stdio (`mcp.client.stdio.stdio_client`).
3. It initializes a `ClientSession` and calls `list_tools()`.
4. Each tool is wrapped in an `MCPTool` object that knows whether it is enabled or disabled via `disabledTools`.

Enabled tools are registered in a global `tools` map on the agent and advertised to the LLM.

### Tool usage

- When the LLM returns a message with tool calls (`Content.tool_use`), the agent invokes the matching `MCPTool`.
- Tool results are wrapped into `ToolResultContent` objects and sent back to the LLM as a follow-up user message.
- The conversation continues until the LLM stops emitting any tool calls.

---

## LLM Providers

LLM abstraction lives under `could_you/llm/` and is built around `BaseLLM`.

### Common base

`BaseLLM` exposes:

- `config: Config`
- `message_history: MessageHistory`
- `tools: dict[str, MCPTool]`
- Abstract method `async def converse(self) -> Message`.

### Boto3 / Bedrock

`Boto3LLM` (
`could_you/llm/boto3.py`) uses `bedrock-runtime`'s `converse` API.

- It converts MCP tools into Bedrock `toolConfig.tools` structures.
- Serializes message history via `MessageHistory.to_dict()`.
- On error, raises `CYError` with `FaultOwner.LLM`.

### OpenAI-compatible providers

`OpenAILLM` (`could_you/llm/openai.py`) supports OpenAI and OpenAI-compatible APIs.

- Uses `openai.OpenAI(**config.llm.init)` to create a client.
- Sends chat completions with:
  - `messages` – converted from internal `Message`/`Content` model.
  - `tools` – converted from MCP tools to OpenAI function-calling schema.
  - Additional args from `config.llm.args` (e.g. `model` name).
- Handles `tool_calls` in responses and converts them back into internal `ToolUse` content.

`OllamaLLM` simply subclasses `OpenAILLM` but uses `openai.OpenAI(**self.config.init)` to point at an Ollama-compatible endpoint (see `could_you/llm/ollama.py`).

---

## Script Mode

Script mode lets you run one-off, stateless operations using custom configs.

### How it works

- A script config file is named:
  - `$XDG_CONFIG_HOME/could-you/script.<script-name>.json` (user-global), or
  - `.could-you/script.<script-name>.json` (project-local workspace).
- When `--script <script-name>` is used:
  - The base workspace config is loaded.
  - The script config is loaded and merged over it.
  - Message history is **disabled** for that run.
  - The query is resolved as:
    1. CLI `query` argument, if provided.
    2. `config.query` from the merged config, if set.
    3. Otherwise, fall back to the editor-based `query.md` flow (though script runs generally avoid history).

### Examples

#### 1. Minimal script for Conventional Commits

`$XDG_CONFIG_HOME/could-you/script.git-commit.json`:

```json
{
  "query": "Format the current staged changes as a Conventional Commit message",
  "llm": {
    "provider": "openai",
    "init": {
      "api_key": "your-api-key"
    },
    "args": {
      "model": "gpt-4.1-mini"
    }
  }
}
```

Run with:

```bash
could-you --script git-commit
```

#### 2. Script with workspace-local config

`.could-you/script.git-commit.json` in your project:

```json
{
  "query": "Format the current staged changes as a Conventional Commit message",
  "llm": {
    "provider": "openai",
    "init": {
      "api_key": "your-api-key"
    },
    "args": {
      "model": "gpt-4.1-mini"
    }
  }
}
```

Run with:

```bash
could-you --script git-commit
```

In both cases, the system prompt is resolved as described in **System Prompt & Prompt Expansion**.

---

## Private Memory Backups

Private memory backup is implemented in `could_you/memory.py`.

Run:

```bash
could-you --backup-memory "conversation about memory design"
```

This copies `.could-you/messages.json` into a private git repository and commits it. By default, the repo is the workspace `.could-you/` directory:

```text
.could-you/
```

Override the location with:

```bash
export COULD_YOU_MEMORY_REPO=/path/to/private/memory/repo
```

Backups are plain files under:

```text
workspaces/<workspace-name-and-hash>/conversations/<timestamp>.messages.json
workspaces/<workspace-name-and-hash>/conversations/<timestamp>.metadata.json
```

No remote is configured or pushed by `could-you`; the user owns that repo.

When the memory repo is `.could-you/`, the backup commit also stages existing explicit prompt and memory files:

```text
config.yaml / config.yml / config.json
SYSTEM_PROMPT.md
TODO.md
MEMORY.md
```

### History compaction script

The default resources include an optional script-mode memory compaction workflow:

```bash
could-you --script compact-history
```

The script loads `.could-you/messages.json`, generates a durable memory update, calls `could-you --backup-memory`, replaces `MEMORY.md`, removes the live message history, and commits the updated private memory state.

This is intended as a starter template. Users should review and customize it before relying on it.

---

## Permission Boundary

`could-you` does not currently create an OS sandbox. MCP servers normally run as the same OS user as the `could-you` process. The preferred least-privilege boundary is therefore explicit and external: run `could-you` as a constrained user, and let normal filesystem ownership/mode bits decide what that user can read and write.

You can inspect the current boundary with:

```bash
could-you --inspect-permissions
```

The report includes:

- the current process user / uid / gid,
- workspace root and `.could-you/` paths,
- readability/writability/executability for key paths,
- ownership and mode strings,
- warnings for obvious risk signals such as root, world-readable `.could-you/`, or world-writable `.could-you/`.

This command is observational only. It does not change permissions, switch users, or sandbox tools.

### Boring Linux dedicated-user recipe

For a stronger local boundary, run `could-you` as a dedicated OS user and put only the intended workspaces under that user's access. This is useful, but it is not magic: the dedicated user still needs a working `could-you` installation, Python environment, model credentials, Node/`npx` if your MCP servers need them, and any other tool dependencies.

Example shape:

```text
human user:       owns normal home, browser profile, work credentials, SSH keys
agent user:       owns agent home, selected workspaces, .could-you state
remote services:  separate trust boundary; local filesystem permissions do not constrain them
```

One possible Linux setup:

```bash
# Create a dedicated user with its own home.
sudo useradd --create-home --shell /bin/bash could-you-agent

# Create a workspace owned by that user.
sudo -u could-you-agent mkdir -p /home/could-you-agent/workspaces
sudo -u could-you-agent git clone <repo-url> /home/could-you-agent/workspaces/my-project

# Initialize private workspace state as the agent user.
sudo -u could-you-agent bash -lc 'cd /home/could-you-agent/workspaces/my-project && could-you --init-session'

# Keep private state private.
sudo -u could-you-agent chmod 700 /home/could-you-agent/workspaces/my-project/.could-you

# Inspect what the agent process can see.
sudo -u could-you-agent bash -lc 'cd /home/could-you-agent/workspaces/my-project && could-you --inspect-permissions'
```

Then run normal agent work as that user:

```bash
sudo -u could-you-agent bash -lc 'cd /home/could-you-agent/workspaces/my-project && could-you "summarize this repository"'
```

This is intentionally boring. It relies on the operating system boundary instead of asking the model or prompt to enforce filesystem secrecy. It may take normal system-administration work to make the agent user's PATH, Python environment, credentials, and MCP server dependencies usable.

### Human-user tools vs agent-user tools

Some tools may need the human user's credentials or desktop session, such as a browser profile, company CLI, password manager integration, or local app automation. Treat those tools as explicit privileged exceptions.

Rules of thumb:

- Tools launched by `could-you` usually inherit the same OS user as `could-you`.
- A filesystem MCP server launched as the agent user should only see files that the agent user can access.
- A browser or work-app tool launched as the human user can usually act as that human user.
- Remote MCP servers or remote APIs are their own trust boundary; local OS permissions do not automatically constrain what they can access.
- If an MCP server can execute arbitrary commands as a user, it can usually access whatever that user can access.

Important limitations:

- OS-user isolation protects files outside the agent user's permissions.
- Subpath restrictions inside a readable/writable workspace still need tool-level controls.
- If a configured MCP server can execute arbitrary commands as the same user, it can usually access whatever that user can access.
- `.could-you/` contains private workspace state and should usually be readable/writable only by the intended owner/agent user.
- A shared remote `could-you` process should not be treated as isolation between mutually untrusted users. Use separate OS users, containers, VMs, hosts, or equivalent isolation for separate trust boundaries.

---

## FAQ / Comparisons

### How does could-you compare to OpenClaw?

OpenClaw is a broad personal-assistant platform: a long-running gateway, many messaging channels, apps/nodes, browser/device integrations, tool policy, and sandboxing options.

`could-you` is intentionally smaller. It is a local-first agent kernel around:

- MCP server composition,
- explicit workspace configuration,
- private project-local state in `.could-you/`,
- user-owned git-backed memory backups,
- scriptable one-off workflows,
- inspectable permission boundaries.

Choose OpenClaw if you want an integrated always-on assistant platform with many channels. Choose `could-you` if you want a small, inspectable CLI/runtime that you can compose with your own MCP servers, prompts, private memory files, and OS-level boundaries.

### How does could-you compare to Claude Code, Cline, and other coding agents?

Those tools are often better if you want a polished coding-agent experience out of the box, especially inside a specific editor, model provider, or product workflow.

`could-you` focuses on a different center:

- the open kernel is small and forkable,
- private memories are local workspace state owned by the user,
- behavior is driven by explicit config and prompt files,
- tool access comes through MCP servers,
- trust boundaries should be visible and boring rather than hidden behind product defaults.

The goal is not to replace every specialized coding assistant. The goal is to make the agent runtime, private state, and permission boundary easy to inspect, move, and change.

---

## Message History

`MessageHistory` (`could_you/message_history.py`) manages reading and writing the conversation log for a workspace:

- File: `.could-you/messages.json` in the discovered workspace.
- Automatically loaded and saved when used as a context manager.
- You can print history with:

  ```bash
  could-you --print-history
  ```

- Disable history for a single run with:

  ```bash
  could-you --no-history "One-off question without saving context"
  ```

The history file distinguishes between:

- `user` messages – human input.
- `assistant` messages – LLM replies.
- `tool` messages – MCP tool outputs.

Each message also has a `type` field:

- `"normal"` – regular conversational turns.
- `"tool_call"` – assistant turns that request tools.
- `"tool_result"` – messages containing tool output.

Example `messages.json` snippet:

```json
[
  { "role": "user", "type": "normal", "content": [{ "type": "text", "text": "What files are here?" }] },
  { "role": "assistant", "type": "tool_call", "content": [{ "toolUse": { "toolUseId": "1", "name": "filesystem.read_directory", "input": { "path": "." } } }] },
  { "role": "tool", "type": "tool_result", "content": [{ "toolResult": { "status": "success", "toolUseId": "1", "content": [{ "text": "main.py\nREADME.md" }] } }] },
  { "role": "assistant", "type": "normal", "content": [{ "type": "text", "text": "You have main.py and README.md in this directory." }] }
]
```

---

## Project Structure

The core package layout (simplified) is:

```text
could_you/
├── __init__.py
├── __main__.py          # CLI entry point and orchestration
├── agent.py             # Main Agent implementation
├── attrs_patch.py       # Attrs helper for alias handling
├── config.py            # Configuration loading & validation
├── cy_error.py          # Error types and fault ownership
├── llm/                 # LLM provider abstractions
│   ├── __init__.py
│   ├── base_llm.py
│   ├── boto3.py
│   ├── ollama.py
│   └── openai.py
├── logging_config.py    # Logging setup
├── mcp_server.py        # MCP server connection & tool wrappers
├── message.py           # Message/content data structures
├── memory.py            # Private message-history backup helpers
├── message_history.py   # Conversation history management
├── prompt.py            # System prompt expansion (patterns + file loading)
├── resources/           # Default config templates
└── session.py           # Workspace + session management
```

There is also `could_you/resources/__init__.py` which marks the package resource directory for default configs.

---

## Contributing

See [`CONTRIBUTING.md`](CONTRIBUTING.md) for full contributor guidelines, coding style, and testing instructions.

---

## License

MIT License - see `LICENSE` file for details.

---

## Links

- [Homepage](https://github.com/SimplyKnownAsG/could-you-ai-agent)
- [Repository](https://github.com/SimplyKnownAsG/could-you-ai-agent)
- [Model Context Protocol](https://modelcontextprotocol.io/)
