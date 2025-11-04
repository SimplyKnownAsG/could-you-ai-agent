# Could You?

A powerful command-line assistant that integrates with Model Context Protocol (MCP) servers to provide AI-powered help for software development tasks.

## Overview

`could-you` is an Agent that connects to various MCP servers to provide contextual assistance for developers. It maintains conversation history, supports multiple LLM providers, and can be configured per-project or globally.

## Features

- **MCP Integration**: Connect to multiple MCP servers for extended functionality
- **Session Management**: Maintain conversation history per project/directory
- **Multiple LLM Support**: Works with various language models (OpenAI, AWS Bedrock, etc.)
- **Interactive Editor**: Open your preferred editor for complex queries
- **Flexible Configuration**: Per-project and global configuration support
- **Command Aliases**: Use `could-you` or the shorter `cy` command
- **Ephemeral Script Mode**: Run one-off, stateless scripts with `--script` (see below)

## Installation

```bash
pip install could-you-ai-agent
```

## Quick Start

1. **Initialize a session** in your project directory:
   ```bash
   could-you --init-session
   ```

2. **Ask a question**:
   ```bash
   could-you "How do I fix this Python import error?"
   ```

3. **Use the interactive editor** (opens when no query provided):
   ```bash
   could-you
   ```

## Usage

### Basic Commands

```bash
# Ask a direct question
could-you "What does this code do?"

# List all sessions
could-you --list-sessions

# Initialize session in current directory
could-you --init-session

# Print conversation history
could-you --print-history

# Test MCP server connections
could-you --test-connect

# Delete a specific session
could-you --delete-session /path/to/session
```

### Ephemeral Script Mode (--script / -s)

**Run single-use, stateless scripts with their its own config!**

- Place a script config at `$XDG_CONFIG_HOME/could-you/<script-name>.script.json`.
- Run with:
  ```bash
  could-you --script <script-name> ["your query"]
  ```
- There is **no history loaded or saved**; only the input and the script config, and inherited configs, are used for a single turn.
- Perfect for batch jobs, automation, git hooks, custom codegen/check flows, etc.
- Example script (`$XDG_CONFIG_HOME/could-you/git-commit.script.json`):
  ```json
  {
    "systemPrompt": "Format the current staged changes as a Conventional Commit message",
    "query": "Use git diff origin/HEAD to determine the staged changes, and write a git commit message.",
    "mcpServers": {
      "git": {
        "command": "uvx",
        "args": ["mcp-server-git"],
        "enabled": true,
        "disabledTools": ["git_reset", "git_create_branch"]
      }
    },
    "llm": {
      "provider": "openai",
      "model": "gpt-4"
    }
  }
  ```
- Minimal example, loading system prompt from `$XDG_CONFIG_HOME/could-you/config.json` or nearest `.could-you-config.json`. 
  ```json
  {
    "query": "Format the current staged changes as a Conventional Commit message",
    "mcpServers": {
      "git": {
        "command": "uvx",
        "args": ["mcp-server-git"],
        "enabled": true,
        "disabledTools": ["git_reset", "git_create_branch"]
      }
    }
  }
  ```

#### How it works
- Load configuration:
  1. Load global `$XDG_CONFIG_HOME/could-you/config.json`, remove `mcpServers`
  2. Overwrite global with local `.could-you-config.json`, remove `mcpServers`.
  3. Overwrite local config with `$XDG_CONFIG_HOME/could-you/<script>.script.json`
- No message history files are loaded or written.

#### Example use cases
- **Git commit message generation**
- **Update documentation for the staged changes**
- **CI/CD custom checks with AI**
- **Linting/code transformation flows**
- **Batch QA/code review flows**

---

### Session Management

Sessions are automatically created per directory and maintain:
- Conversation history
- Token usage tracking
- Project-specific context

### Configuration

Configuration files can be placed at:
- **Project level**: `.could-you-config.json` (in project root)
- **Global level**: `$XDG_CONFIG_HOME/could-you/config.json`

Example configuration:
```json
{
  "llm": {
    "provider": "openai",
    "model": "gpt-4",
    "api_key": "your-api-key"
  },
  "servers": [
    {
      "name": "filesystem",
      "command": "mcp-server-filesystem",
      "args": ["/path/to/workspace"]
    }
  ],
  "editor": "code",
  "prompt": "Custom system prompt for the assistant"
}
```

#### COULD_YOU_LOAD_FILE: File & Glob Expansion in Prompts

You can instruct the assistant to dynamically include the contents of files in your prompts using the special COULD_YOU_LOAD_FILE directive. This directive supports glob patterns, so you can auto-load several files at once.

**Syntax:**

```
COULD_YOU_LOAD_FILE(<relative-glob-pattern>)
```
- The pattern is always interpreted relative to your current working directory.
- Glob syntax (`*`, `?`, `[abc]`, etc.) is supported to match one or more files.
- Matched files must reside within your project directory for security.
- If no files match, nothing is injected (but an info log entry is created).

**Examples:**

- Inject one file:  
  `COULD_YOU_LOAD_FILE(README.md)`
- Inject all markdown files in docs/:  
  `COULD_YOU_LOAD_FILE(docs/*.md)`
- Inject all Python files in the src directory and subdirectories:  
  `COULD_YOU_LOAD_FILE(src/**/*.py)`

Matched file contents appear in the prompt wrapped in block tags for clarity:

```text
<could-you-prompt-expanded-file "path/to/file.ext">
...file contents...
</could-you-prompt-expanded-file "path/to/file.ext">
```

#### Server Configuration Options

Each MCP server in the `mcpServers` section supports the following options:

- **`command`** (required): The command to execute the MCP server
- **`args`** (required): Array of arguments to pass to the command
- **`env`** (optional): Environment variables to set for the server process
- **`enabled`** (optional, default: `true`): Whether to enable this server
- **`disabledTools`** (optional): Array of tool names to disable from this server

Example configuration with tool disabling:
```json
{
  "llm": {
    "provider": "openai",
    "model": "gpt-4"
  },
  "mcpServers": {
    "filesystem": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "/workspace"],
      "enabled": true,
      "disabledTools": ["write_file", "create_directory"]
    },
    "git": {
      "command": "mcp-server-git",
      "args": ["/workspace"],
      "env": {
        "GIT_AUTHOR_NAME": "AI Assistant"
      }
    },
    "experimental-server": {
      "command": "experimental-mcp-server",
      "args": [],
      "enabled": false
    }
  }
}
```

**Tool Disabling**: Use `disabledTools` to prevent specific dangerous operations while keeping the server enabled. Tools listed here are filtered out during server connection and reported in logs for transparency.

## MCP Server Integration

`could-you` acts as an agent, connecting to various MCP servers to extend functionality. Popular MCP servers include:

- **Filesystem**: File operations and code analysis
- **Git**: Version control operations
- **Database**: SQL query assistance
- **Web**: HTTP requests and API interactions

Each connected server provides tools that the AI assistant can use to help with your tasks.

---

## Change Log: Ephemeral Script Mode via --script Flag

### Background

Previously, `could-you` only supported running as an interactive CLI with project-aware or global config files. There was no stateless "script" mode where a one-off config/script could be loaded from the user config directory for batch-style invocation. This change introduces such an ephemeral command mode.

### Changes

* Add `--script` (`-s`) CLI argument to `could_you/__main__.py` to support running a stateless script
* Update argument parser to use `cmd_group` for improved mutual exclusion
* Update config loading logic in `config.py` to support merging a `<script>.script.json` from the user config directory (under `$XDG_CONFIG_HOME/could-you/`)
* Add support for an optional `query` field in the script config
* Refactor query/editor-input logic for script flows
* Pass merged config and ephemeral message history to the agent when running in script mode
* Update code to use `agent` (not `host`) for var naming consistency

### Testing

* Ran CLI script mode with various `.script.json` files in `$XDG_CONFIG_HOME/could-you/`, with and without the `query` set
* Validated that history was not persisted when using the `--script` flag
* Confirmed mutual exclusivity of CLI args, and that legacy project config still works
* Inspected logs for error handling if script config doesn't exist

---

## Development

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup, coding standards, and contribution guidelines.

## License

MIT License - see LICENSE file for details.

## Links

- [Homepage](https://github.com/SimplyKnownAsG/could-you-ai-agent)
- [Repository](https://github.com/SimplyKnownAsG/could-you-ai-agent)
- [Model Context Protocol](https://modelcontextprotocol.io/)
