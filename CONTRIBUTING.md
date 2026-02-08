# Contributing to `could-you`

Thank you for your interest in contributing to `could-you`! This document provides guidelines for setting up your development environment, making changes, and submitting contributions.

## Development Setup

> **Note for Vibe Coders**: If you're vibing with an AI agent, make sure your agent reads both the README.md and CONTRIBUTING.md before making any changes. Trust us, it'll help!

### Prerequisites

- Python 3.11 or higher
- [uv](https://docs.astral.sh/uv/) (recommended) or pip
- Git

### Development Environment

1. **Fork and clone the repository**:

   ```bash
   git clone https://github.com/SimplyKnownAsG/could-you-ai-agent.git
   cd could-you-ai-agent
   ```

2. **Create and activate a virtual environment**:

   Using `uv` (recommended):

   ```bash
   uv venv
   source .venv/bin/activate
   ```

   Or, if you prefer Hatch (used in some older docs):

   ```bash
   hatch env create
   hatch shell
   ```

3. **Install dependencies**:

   With `uv` (recommended):

   ```bash
   uv pip install -e .[dev]
   ```

   Or with plain pip:

   ```bash
   python -m venv .venv
   source .venv/bin/activate
   pip install -e .[dev]
   ```

4. **Verify installation**:

   ```bash
   could-you --help
   ```

### Running Tests

Use `uv` or plain `pytest` to run tests and check coding style:

1. **Run all tests**:

   ```bash
   pytest
   ```

2. **Check code formatting and linting** (if configured in the project):

   ```bash
   hatch fmt
   ```

## Code Style and Standards

### Formatting

We use standard modern Python tooling (e.g. `ruff format`, `black`) as configured in `pyproject.toml`. Run the provided formatting commands before committing.

### Code Quality

- **Type hints**: Use type hints for all function parameters and return values.
- **Docstrings**: Add docstrings for all public functions and classes.
- **Error handling**: Use appropriate exception handling and meaningful error messages.
- **Async/await**: Follow async best practices for MCP operations and I/O.

### Project Structure

The core package layout currently looks like this (simplified):

```text
could_you/
├── __init__.py          # Package initialization
├── __main__.py          # CLI entry point
├── agent.py             # Main Agent implementation
├── attrs_patch.py       # Attrs helper for alias handling
├── config.py            # Configuration management
├── cy_error.py          # Error types
├── logging_config.py    # Logging setup
├── mcp_server.py        # MCP server connection handling
├── message.py           # Message data structures
├── message_history.py   # Conversation history management
├── prompt.py            # System prompt expansion helpers
├── resources/           # Packaged default configs
└── llm/                 # LLM provider abstractions
    ├── __init__.py
    ├── base_llm.py
    ├── boto3.py
    ├── ollama.py
    └── openai.py
```

There is also session management in `session.py`, which handles workspace discovery and the `.could-you/` directory.

### Key Design Principles

1. **Separation of Concerns**: Each module has a clear, single responsibility
2. **Async First**: All I/O operations should be async
3. **Configuration Flexibility**: Support both user and project-specific configs
4. **Error Resilience**: Graceful handling of network and MCP server failures
5. **User Experience**: Clear error messages and helpful feedback

## Workflow for Contributions

1. **Create a feature branch** from `main`:

   ```bash
   git checkout -b feature/your-feature-name
   ```

2. **Make your changes** following the coding standards above.

3. **Add tests** for new functionality:

   - Place tests in the `tests/` directory.
   - Use `pytest`.
   - Prefer in-memory or mocked I/O for unit tests rather than hitting the real filesystem or network.
   - Example pattern:

     ```python
     def test_should_do_x_when_y(monkeypatch):
         # Arrange (set up input/mocks)
         # Act
         # Assert
     ```

4. **Format and lint**:

   ```bash
   uv run ruff format .
   uv run ruff check .
   ```

5. **Commit your changes**:

   Use conventional commits where possible, e.g.:

   - `feat: add new MCP server configuration option`
   - `fix: handle missing workspace config gracefully`
   - `chore: update development dependencies`

6. **Push your branch** and open a Pull Request.

   In your PR description, include:

   - Summary of changes.
   - Rationale / motivation.
   - Reference to any related issues.
   - Screenshots or examples, if applicable.

7. **Ensure CI passes** (tests, formatting, etc.).

8. **Address review feedback** and update your branch as needed.

## Testing Guidelines

### Test Structure

- **Unit tests**: Test individual functions and classes.
- **Integration tests**: Test MCP server and LLM interactions.
- **End-to-end tests**: Test full CLI workflows where appropriate.

### Test Naming

```python
def test_should_do_something_when_condition():
    # Arrange
    # Act
    # Assert
```

### Mocking

Use appropriate mocking for:

- External API calls (e.g. OpenAI, Bedrock).
- File system operations.
- MCP server responses.

Prefer lightweight in-memory tests for fast feedback.

## Documentation

### Code Documentation

- Add docstrings to all public functions and classes.
- Use a consistent docstring style (Google- or Sphinx-style).
- Include examples for complex or non-obvious functions.

### README Updates

Update `README.md` when adding or significantly changing:

- Installation or setup steps.
- CLI flags or behavior.
- Configuration format or semantics.
- Supported MCP servers or LLM providers.

Include clear examples where useful.

## Release Process

Releases are generally managed by the maintainer(s). A typical release flow may include:

1. Bump version in `pyproject.toml`.
2. Update `CHANGELOG.md`.
3. Create a release PR.
4. Tag the release after merge.
5. GitHub Actions (if configured) will handle PyPI publishing.

## Getting Help

If you're unsure about anything:

- Open an issue describing your question or proposed change.
- Or start a draft PR early and mark it as "WIP" to get feedback.

Thank you for helping improve `could-you`!
