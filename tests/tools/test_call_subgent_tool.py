from unittest.mock import AsyncMock, patch

import pytest

from could_you.config import Config, DialogueProps, LLMProps
from could_you.cy_error import CYError
from could_you.llm.openai import OpenAILLM
from could_you.message import Message, TextContent, ToolResultInnerTextContent, ToolUse
from could_you.session import Session
from could_you.tools.subagent_tools import CallSubagentTool


class DummyOpenAILLM(OpenAILLM):
    def _init_client(self):
        return None


@pytest.mark.asyncio
async def test_call_could_you_returns_final_text_as_provider_compatible_tool_result(tmp_path):
    config = Config(llm=LLMProps(provider="openai"), dialogue=DialogueProps(load=False, store=False))
    config_dir = tmp_path / ".could-you"
    config_dir.mkdir()
    session = Session(config_dir, None, config)
    manager = AsyncMock()

    def load_session(_name, override, *, depth):
        assert depth == session.depth + 1
        override(config)
        return session

    manager.load_session = load_session
    tool = CallSubagentTool(session.subagent_server, manager)

    async def orchestrate(agent, _query):
        assert agent.session.workspace_dir == tmp_path
        agent.dialogue.add(Message(role="assistant", content=[TextContent(text="Hello"), TextContent(text="there")]))

    async def enter(agent):
        return agent

    with (
        patch("could_you.agent.Agent.__aenter__", new=enter),
        patch("could_you.agent.Agent.__aexit__", new=AsyncMock()),
        patch("could_you.agent.Agent.orchestrate", new=orchestrate),
    ):
        result = await tool(
            ToolUse(toolUseId="call_1", name=tool.name, input={}),
            {"dialogue_name": "temp", "message": "say hello"},
        )

    assert session.config.dialogue.name == "temp"
    assert session.config.tools.subagent.enabled is True
    assert result.tool_result.content == [ToolResultInnerTextContent(text="Hello\n\nthere")]
    assert result.tool_result.tool_use_id == "call_1"
    llm = DummyOpenAILLM(
        session.config, type("History", (), {"messages": [Message(role="tool", content=[result])]})(), {}
    )
    assert llm._convert_messages()[-1] == {  # noqa: SLF001
        "role": "tool",
        "tool_call_id": "call_1",
        "content": "Hello\n\nthere",
    }


@pytest.mark.asyncio
async def test_call_could_you_without_final_answer_reports_error(tmp_path):
    config = Config(llm=LLMProps(provider="openai"), dialogue=DialogueProps(load=False, store=False))
    config_dir = tmp_path / ".could-you"
    config_dir.mkdir()
    session = Session(config_dir, None, config)
    manager = AsyncMock()

    def load_session(_name, override, *, depth):
        assert depth == session.depth + 1
        override(config)
        return session

    manager.load_session = load_session
    tool = CallSubagentTool(session.subagent_server, manager)

    async def enter(agent):
        return agent

    with (
        patch("could_you.agent.Agent.__aenter__", new=enter),
        patch("could_you.agent.Agent.__aexit__", new=AsyncMock()),
        patch("could_you.agent.Agent.orchestrate", new=AsyncMock()),
        pytest.raises(CYError, match="without a final assistant message"),
    ):
        await tool(
            ToolUse(toolUseId="call_1", name=tool.name, input={}),
            {"dialogue_name": "temp", "message": "say hello"},
        )
