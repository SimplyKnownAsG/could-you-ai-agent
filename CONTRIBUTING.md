# Contributing to Could You?

Thank you for your interest in contributing to `could-you`! This document provides guidelines for development setup, coding standards, and the contribution process.

## Development Setup

> **Note for Vibe Coders**: If you're vibing with an AI agent, make sure your agent reads both the README.md and CONTRIBUTING.md before making any changes. Trust us, it'll help! 🤖✨

### Prerequisites

- Python 3.11 or higher
- [uv](https://docs.astral.sh/uv/) (recommended) or pip
- Git

### Development Environment

1. **Clone the repository**:
   ```bash
   git clone https://github.com/SimplyKnownAsG/could-you-ai-agent.git
   cd could-you-ai-agent
   ```

2. **Create and activate a virtual environment**:
   Using Hatch, create and activate the environment for development:
   ```bash
   hatch env create
   hatch shell
   ```

3. **Install dependencies**:
   Dependencies are automatically synced via Hatch when you enter the environment.

4. **Verify installation**:
   ```bash
   could-you --help
   ```

### Running Tests

Utilize Hatch to run tests and check coding style:

1. **Run all tests**:
   ```bash
   hatch test
   ```

2. **Check code formatting**:
   ```bash
   hatch fmt
   ```

## Code Style and Standards

### Formatting

We use the default formatting in hatch through `hatch fmt`.

### Code Quality

- **Type hints**: Use type hints for all function parameters and return values
- **Docstrings**: Add docstrings for all public functions and classes
- **Error handling**: Use appropriate exception handling and meaningful error messages
- **Async/await**: Follow async best practices for MCP operations

### Project Structure

```
could_you/
├── __init__.py          # Package initialization
├── __main__.py          # CLI entry point
├── config.py            # Configuration management
├── llm.py               # LLM provider abstractions
├── agent.py             # Main Agent implementation
├── mcp_server.py        # MCP server connection handling
├── message.py           # Message data structures
├── message_history.py   # Conversation history management
├── session.py           # Session data structures
└── session_manager.py   # Session lifecycle management
```

### Key Design Principles

1. **Separation of Concerns**: Each module has a clear, single responsibility
2. **Async First**: All I/O operations should be async
3. **Configuration Flexibility**: Support both global and project-specific configs
4. **Error Resilience**: Graceful handling of network and MCP server failures
5. **User Experience**: Clear error messages and helpful feedback

## Development Workflow

### Making Changes

1. **Create a feature branch**:
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. **Make your changes** following the coding standards above

3. **Add tests** for new functionality:
   ```bash
   # Add tests in tests/ directory
   pytest tests/test_your_feature.py
   ```

4. **Format and lint**:
   ```bash
   black could_you/
   pytest --black
   ```

5. **Commit your changes**:
   ```bash
   git add .
   git commit -m "feat: add your feature description"
   ```

### Commit Message Format

Use conventional commit format:
- `feat:` for new features
- `fix:` for bug fixes
- `docs:` for documentation changes
- `style:` for formatting changes
- `refactor:` for code refactoring
- `test:` for adding tests
- `chore:` for maintenance tasks

### Pull Request Process

1. **Push your branch**:
   ```bash
   git push origin feature/your-feature-name
   ```

2. **Create a Pull Request** with:
   - Clear description of changes
   - Reference to any related issues
   - Screenshots/examples if applicable

3. **Address review feedback** and update your branch as needed

4. **Ensure CI passes** (tests, formatting, etc.)

## Testing Guidelines

### Test Structure

- **Unit tests**: Test individual functions and classes
- **Integration tests**: Test MCP server interactions
- **End-to-end tests**: Test full CLI workflows

### Test Naming

```python
def test_should_do_something_when_condition():
    # Arrange
    # Act  
    # Assert
```

### Mocking

Use appropriate mocking for:
- External API calls
- File system operations
- MCP server responses

## Documentation

### Code Documentation

- Add docstrings to all public functions and classes
- Use Google-style docstrings
- Include examples for complex functions

### README Updates

Update the README.md when adding:
- New features
- Configuration options
- Usage examples

## Release Process

1. Update version in `pyproject.toml`
2. Update CHANGELOG.md
3. Create release PR
4. Tag release after merge
5. GitHub Actions will handle PyPI publishing

## Getting Help

- **Issues**: Open GitHub issues for bugs or feature requests
- **Discussions**: Use GitHub Discussions for questions
- **Code Review**: Request reviews from maintainers

## Code of Conduct

- Be respectful and inclusive
- Focus on constructive feedback
- Help others learn and grow
- Follow the project's technical standards

Thank you for contributing to `could-you`!
