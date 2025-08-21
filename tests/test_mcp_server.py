import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from contextlib import AsyncExitStack

from could_you.mcp_server import MCPServer, MCPTool

def test_mcp_tool_wrapper():
    """Test MCPTool wrapper functionality."""
    # Create a mock MCP Tool
    server = MCPServer(name="test-server", command="test-command", args=["arg1", "arg2"])
    mock_tool = MagicMock()
    mock_tool.name = "test_tool"
    mock_tool.description = "A test tool"
    mock_tool.inputSchema = {"type": "object"}

    # Test enabled tool
    enabled_tool = MCPTool(server, mock_tool, enabled=True)
    assert enabled_tool.name == "test_tool"
    assert enabled_tool.description == "A test tool"
    assert enabled_tool.inputSchema == {"type": "object"}
    assert enabled_tool.enabled is True

    # Test disabled tool
    disabled_tool = MCPTool(server, mock_tool, enabled=False)
    assert disabled_tool.name == "test_tool"
    assert disabled_tool.enabled is False

    # Test default enabled
    default_tool = MCPTool(server, mock_tool)
    assert default_tool.enabled is True


def test_mcp_server_init():
    """Test MCPServer initialization with default values."""
    server = MCPServer(name="test-server", command="test-command", args=["arg1", "arg2"])

    assert server.name == "test-server"
    assert server.command == "test-command"
    assert server.args == ["arg1", "arg2"]
    assert server.env == {}
    assert server.enabled is True
    assert server.disabled_tools == set()


def test_mcp_server_init_with_disabled_tools():
    """Test MCPServer initialization with disabled tools."""
    server = MCPServer(
        name="test-server",
        command="test-command",
        args=["arg1"],
        disabled_tools=["tool1", "tool2", "tool3"],
    )

    assert server.disabled_tools == {"tool1", "tool2", "tool3"}


def test_mcp_server_init_with_all_options():
    """Test MCPServer initialization with all options."""
    server = MCPServer(
        name="test-server",
        command="test-command",
        args=["arg1"],
        env={"TEST_VAR": "test_value"},
        enabled=False,
        disabled_tools=["unwanted_tool"],
    )

    assert server.name == "test-server"
    assert server.command == "test-command"
    assert server.args == ["arg1"]
    assert server.env == {"TEST_VAR": "test_value"}
    assert server.enabled is False
    assert server.disabled_tools == {"unwanted_tool"}


@pytest.mark.asyncio
async def test_connect_disabled_server():
    """Test that disabled servers don't connect and have empty tools."""
    server = MCPServer(name="disabled-server", command="test-command", args=["arg1"], enabled=False)

    exit_stack = AsyncExitStack()

    with patch("could_you.mcp_server.LOGGER") as mock_logger:
        result = await server.connect(exit_stack=exit_stack)

    assert result is True
    assert server.tools == []
    mock_logger.info.assert_called_once_with("Server disabled-server is not enabled.")


@pytest.mark.asyncio
async def test_connect_enabled_server_with_tool_filtering():
    """Test that enabled servers filter out disabled tools."""
    # Create mock tools
    mock_tool1 = MagicMock()
    mock_tool1.name = "allowed_tool"

    mock_tool2 = MagicMock()
    mock_tool2.name = "disabled_tool"

    mock_tool3 = MagicMock()
    mock_tool3.name = "another_allowed_tool"

    all_tools = [mock_tool1, mock_tool2, mock_tool3]

    # Create server with one disabled tool
    server = MCPServer(
        name="test-server", command="test-command", args=["arg1"], disabled_tools=["disabled_tool"]
    )

    exit_stack = AsyncExitStack()

    # Mock the MCP client and session
    mock_session = AsyncMock()
    mock_list_tools_response = MagicMock()
    mock_list_tools_response.tools = all_tools
    mock_session.list_tools.return_value = mock_list_tools_response

    with (
        patch("could_you.mcp_server.stdio_client") as mock_stdio_client,
        patch("could_you.mcp_server.ClientSession") as mock_client_session,
    ):

        # Setup mocks
        mock_stdio_client.return_value.__aenter__ = AsyncMock(
            return_value=(MagicMock(), MagicMock())
        )
        mock_client_session.return_value.__aenter__ = AsyncMock(return_value=mock_session)

        # Mock the exit_stack context managers
        exit_stack.enter_async_context = AsyncMock(
            side_effect=[
                (MagicMock(), MagicMock()),  # stdio_client result
                mock_session,  # ClientSession result
            ]
        )

        result = await server.connect(exit_stack=exit_stack)

    assert result is True
    assert len(server.tools) == 3  # Should have all tools as MCPTool wrappers

    # Check that tools are properly wrapped
    enabled_tools = [tool for tool in server.tools if tool.enabled]
    disabled_tools = [tool for tool in server.tools if not tool.enabled]

    assert len(enabled_tools) == 2  # allowed_tool and another_allowed_tool
    assert len(disabled_tools) == 1  # disabled_tool

    # Check specific tools
    tool_names = {tool.name: tool.enabled for tool in server.tools}
    assert tool_names["allowed_tool"] is True
    assert tool_names["another_allowed_tool"] is True
    assert tool_names["disabled_tool"] is False


@pytest.mark.asyncio
async def test_connect_enabled_server_no_disabled_tools():
    """Test that enabled servers work normally when no tools are disabled."""
    # Create mock tools
    mock_tool1 = MagicMock()
    mock_tool1.name = "tool1"

    mock_tool2 = MagicMock()
    mock_tool2.name = "tool2"

    all_tools = [mock_tool1, mock_tool2]

    # Create server with no disabled tools
    server = MCPServer(name="test-server", command="test-command", args=["arg1"])

    exit_stack = AsyncExitStack()

    # Mock the MCP client and session
    mock_session = AsyncMock()
    mock_list_tools_response = MagicMock()
    mock_list_tools_response.tools = all_tools
    mock_session.list_tools.return_value = mock_list_tools_response

    with (
        patch("could_you.mcp_server.stdio_client") as mock_stdio_client,
        patch("could_you.mcp_server.ClientSession") as mock_client_session,
    ):

        # Setup mocks
        mock_stdio_client.return_value.__aenter__ = AsyncMock(
            return_value=(MagicMock(), MagicMock())
        )
        mock_client_session.return_value.__aenter__ = AsyncMock(return_value=mock_session)

        # Mock the exit_stack context managers
        exit_stack.enter_async_context = AsyncMock(
            side_effect=[
                (MagicMock(), MagicMock()),  # stdio_client result
                mock_session,  # ClientSession result
            ]
        )

        result = await server.connect(exit_stack=exit_stack)

    assert result is True
    assert len(server.tools) == 2  # Should have all tools as MCPTool wrappers

    # Check that all tools are enabled
    for tool in server.tools:
        assert tool.enabled is True

    # Check specific tools
    tool_names = [tool.name for tool in server.tools]
    assert "tool1" in tool_names
    assert "tool2" in tool_names


@pytest.mark.asyncio
async def test_call_tool():
    """Test that call_tool delegates to the session."""
    server = MCPServer(name="test-server", command="test-command", args=["arg1"])

    # Mock session
    mock_session = AsyncMock()
    mock_session.call_tool.return_value = "tool_result"
    server.session = mock_session

    result = await server.call_tool("test_tool", {"arg": "value"})

    assert result == "tool_result"
    mock_session.call_tool.assert_called_once_with("test_tool", {"arg": "value"})
