# Could You?

A powerful command-line assistant that integrates with Model Context Protocol (MCP) servers to provide AI-powered help for software development tasks.

## Overview

`could-you` is an Agent that connects to various MCP servers to provide contextual assistance for developers. It maintains conversation history, supports multiple LLM providers, and can be configured for each user and per-project.

## Features

- **MCP Integration**: Connect to multiple MCP servers for extended functionality
- **Session Management**: Maintain conversation history per project/directory
- **Multiple LLM Support**: Works with various language models (OpenAI, AWS Bedrock, etc.)
- **Interactive Editor**: Open your preferred editor for complex queries
- **Flexible Configuration**: User and per-project configuration support
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

# Dump the effective configuration as JSON (the default)
could-you --dump-config

# Dump config as YAML
could-you --dump-config yaml

# Dump config for a specific script
could-you --dump-config --script <script-name>

# Delete a specific session
could-you --delete-session /path/to/session
```

### CLI Configuration Dump

- `-C`, `--dump-config [yaml]`: Load and print the effective resolved configuration and exit. Defaults to JSON output; provide `yaml` to output as YAML. No agent/session/etc is run.
- Works with `--script` to show script configs after merging inheritance.

### Session Management

Sessions are automatically created per directory and maintain:
- Conversation history
- Token usage tracking
- Project-specific context

### Configuration

Configuration directory and files:
- **Workspace level**: All config is now located in the `.could-you/` directory in your workspace root
    - The main config: `.could-you/config.json` (or `config.yaml`, `config.yml`)
- **User level**: `$XDG_CONFIG_HOME/could-you/config.json` (or `config.yaml`, `config.yml`)

> **NOTE**: All configuration files (project, user and script) support `.json`, `.yaml`, and `.yml` extensions in that preferred order.

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

Example configuration with tool disabling (in `.could-you/config.json` or `.could-you/config.yaml`):
```json
{
  "llm": {
    "provider": "openai",
    "model": "gpt-4"
  },
  "mcpServers": {
    "filesystem": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "$CY_WORKSPACE"],
      "enabled": true,
      "disabledTools": ["write_file", "create_directory"]
    },
    "git": {
      "command": "mcp-server-git",
      "args": ["$CY_WORKSPACE"],
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
> Note: Arguments like `$CY_WORKSPACE` are automatically replaced with the root path by the agent when launching MCP servers.

**Tool Disabling**: Use `disabledTools` to prevent specific dangerous operations while keeping the server enabled. Tools listed here are filtered out during server connection and reported in logs for transparency.

## MCP Server Integration

`could-you` acts as an agent, connecting to various MCP servers to extend functionality. Popular MCP servers include:

- **Filesystem**: File operations and code analysis
- **Git**: Version control operations
- **Database**: SQL query assistance
- **Web**: HTTP requests and API interactions

Each connected server provides tools that the AI assistant can use to help with your tasks.

### Ephemeral Script Mode (--script / -s)

**Run single-use, stateless scripts with its own config**

- Place a script config at `$XDG_CONFIG_HOME/could-you/script.<script-name>.json` or in the project-local workspace as `.could-you-script.<script>.json`.
- Run with:
  ```bash
  could-you --script <script-name> ["your query"]
  ```
- There is **no history loaded or saved**; only the input and the script config, and inherited configs, are used for a single turn.
- Perfect for batch jobs, automation, git hooks, custom codegen/check flows, etc.
- Example script (`$XDG_CONFIG_HOME/could-you/script.git-commit.json`):

  Run with: `cy --script git-commit`.

  ```json
  {
    "systemPrompt": "Format the current staged changes as a Conventional Commit message",
    "query": "Use git diff origin/HEAD to determine the staged changes, and write a git commit message.",
    "mcpServers": {
      "mcp-git": {
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
- Minimal example, loading system prompt from `$XDG_CONFIG_HOME/could-you/config.json` or nearest `.could-you-config.json`. No default query.

  Run with: `cy --script git-commit "Format the current staged changes as a Conventional Commit message"`

  ```json
  {
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
- Minimal example, loading system prompt from `$XDG_CONFIG_HOME/could-you/config.json` or nearest `.could-you-config.json`, with a default query.

  Run with: `cy --script git-commit`.

  ```json
  {
    "query": "Use git diff origin/HEAD to determine the staged changes, and write a git commit message.",
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

1. Load configuration:
   1. Load per-project workspace config from `.could-you/config.json` (or `.yaml`/`.yml`)
2. Find and load script, and overwrite configuration. Search path is:
   1. Workspace: `.could-you/script.<script>.json|yaml|yml`
3. No message history files are loaded or written.

#### Example use cases
- **Git commit message generation**
- **Update documentation for the staged changes**
- **CI/CD custom checks with AI**
- **Linting/code transformation flows**
- **Batch QA/code review flows**

---

## Development

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup, coding standards, and contribution guidelines.

## License

MIT License - see LICENSE file for details.

## Links

- [Homepage](https://github.com/SimplyKnownAsG/could-you-ai-agent)
- [Repository](https://github.com/SimplyKnownAsG/could-you-ai-agent)
- [Model Context Protocol](https://modelcontextprotocol.io/)
