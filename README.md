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
- **Message history**: Persisted per-workspace in `.could-you/messages.json` (opt-out with `--no-history`).

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

### Config loading and merging

Config loading works as follows (see `load()` in `could_you/config.py`):

1. Locate the nearest `.could-you/` directory from the current working directory.
2. Load the base config from `.could-you/config.(json|yaml|yml)`.
3. If `--script <name>` is provided, also load `.could-you/script.<name>.(json|yaml|yml)` and overlay its values on top of the base config.
4. Validate and normalize the config:
   - Ensure `llm.provider` is one of `"boto3"`, `"ollama"`, or `"openai"`.
   - Expand the `systemPrompt` via the prompt utilities (see below).
   - Apply environment variables from `env` to `os.environ`.
   - Expand `$COULD_YOU_WORKSPACE` in MCP server arguments to the parent of the workspace directory.

### Config schema

`could_you/config.py` defines the primary data structures using `attrs`:

- `LLMProps`:
  - `provider: str` – one of `"boto3"`, `"ollama"`, `"openai"`.
  - `init: dict[str, Any]` – provider-specific initialization args; e.g. for OpenAI: `{ "api_key": "..." }`.
  - `args: dict[str, Any]` – per-request arguments; e.g. `{ "model": "gpt-4.1-mini" }`.

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
    }
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

- The pattern is treated as a glob relative to the project root.
- For each matching file **inside** the current working directory tree, the content is loaded and wrapped in markers:

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
