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

### Session Management

Sessions are automatically created per directory and maintain:
- Conversation history
- Token usage tracking
- Project-specific context

### Configuration

Configuration files can be placed at:
- **Project level**: `.could-you-config.json` (in project root)
- **Global level**: `~/.config/could-you/config.json`

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

## Development

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup, coding standards, and contribution guidelines.

## License

MIT License - see LICENSE file for details.

## Links

- [Homepage](https://github.com/SimplyKnownAsG/could-you-ai-agent)
- [Repository](https://github.com/SimplyKnownAsG/could-you-ai-agent)
- [Model Context Protocol](https://modelcontextprotocol.io/)
