import json
from unittest.mock import AsyncMock

import pytest

from could_you.agent import Agent
from could_you.config import Config, DialogueProps, LLMProps
from could_you.cy_error import CYError, FaultOwner
from could_you.dialogue import Dialogue
from could_you.message import Message, MessageMetadata, MessageType, TextContent, ToolUse, ToolUseContent


def tool_call(name: str, arguments: dict, tool_use_id: str = "call_1") -> ToolUseContent:
    return ToolUseContent(tool_use=ToolUse(name=name, input=arguments, toolUseId=tool_use_id))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("text", "arguments", "expected"),
    [
        ([], {"message": "Done."}, ["Done."]),
        ([], {"message": ""}, []),
        ([], {}, []),
        (["Done."], {}, ["Done."]),
        (["Done."], {"message": ""}, ["Done."]),
        (["Done."], {"message": "Done."}, ["Done."]),
        (["Working.", "Done."], {"message": "Done."}, ["Working.", "Done."]),
        (["Working."], {"message": "Done."}, ["Working.", "Done."]),
        (["Done!"], {"message": "Done."}, ["Done!", "Done."]),
    ],
)
async def test_stop_turn_does_not_store_tool_calls_or_results(tmp_path, text, arguments, expected):
    config = Config(llm=LLMProps(provider="openai"))
    props = DialogueProps(load=False, store=True)
    content = [*[TextContent(text=item) for item in text], tool_call("__stop_turn__", arguments)]
    metadata = MessageMetadata(inputTokens=12)

    with Dialogue(tmp_path, props=props) as dialogue:
        agent = Agent(session_manager=AsyncMock(), config=config, dialogue=dialogue)
        agent.llm = AsyncMock()
        agent.llm.converse.return_value = Message(role="assistant", content=content, metadata=metadata)

        await agent.orchestrate("hello")

        assistant_messages = [entry for entry in dialogue.messages if entry.role == "assistant"]
        assert assistant_messages == (
            [Message(role="assistant", content=[TextContent(text=item) for item in expected], metadata=metadata)]
            if expected
            else []
        )
        assert not any(entry.role == "tool" for entry in dialogue.messages)
        agent.llm.converse.assert_awaited_once()

    persisted = [json.loads(line) for line in (tmp_path / "dialogue.jsonl").read_text().splitlines()]
    assert not any(entry.get("type") in ("tool_call", "tool_result") for entry in persisted)
    assert len(persisted) == 2 + bool(expected)  # date, user, optional assistant text


@pytest.mark.asyncio
async def test_stop_turn_rejects_mixed_tool_calls_before_persisting_or_executing(tmp_path):
    config = Config(llm=LLMProps(provider="openai"))
    with Dialogue(tmp_path, props=DialogueProps(load=False, store=True)) as dialogue:
        agent = Agent(session_manager=AsyncMock(), config=config, dialogue=dialogue)
        agent.llm = AsyncMock()
        agent.llm.converse.return_value = Message(
            role="assistant",
            content=[tool_call("other_tool", {}, "call_1"), tool_call("__stop_turn__", {}, "call_2")],
        )
        other_tool = AsyncMock()
        agent.tools["other_tool"] = other_tool

        with pytest.raises(CYError, match="must be the only tool call") as exc:
            await agent.orchestrate("hello")

        assert exc.value.fault_owner is FaultOwner.LLM
        other_tool.assert_not_awaited()
        assert [entry.role for entry in dialogue.messages] == ["system", "user"]

    assert len((tmp_path / "dialogue.jsonl").read_text().splitlines()) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("arguments", [{"message": 42}, {"message": "ok", "extra": 1}, []])
async def test_stop_turn_rejects_invalid_arguments(tmp_path, arguments):
    config = Config(llm=LLMProps(provider="openai"))
    with Dialogue(tmp_path, props=DialogueProps(load=False, store=True)) as dialogue:
        agent = Agent(session_manager=AsyncMock(), config=config, dialogue=dialogue)
        agent.llm = AsyncMock()
        agent.llm.converse.return_value = Message(role="assistant", content=[tool_call("__stop_turn__", arguments)])

        with pytest.raises(CYError, match="optional string 'message'"):
            await agent.orchestrate("hello")

        assert [entry.role for entry in dialogue.messages] == ["system", "user"]


@pytest.mark.asyncio
async def test_normal_tool_calls_still_receive_results(tmp_path):
    config = Config(llm=LLMProps(provider="openai"))
    with Dialogue(tmp_path, props=DialogueProps(load=False, store=True)) as dialogue:
        agent = Agent(session_manager=AsyncMock(), config=config, dialogue=dialogue)
        agent.llm = AsyncMock()
        agent.llm.converse.side_effect = [
            Message(role="assistant", content=[tool_call("missing_tool", {})]),
            Message(role="assistant", content=[TextContent(text="done")], type=MessageType.NORMAL),
        ]

        await agent.orchestrate("hello")

        assert [entry.role for entry in dialogue.messages] == ["system", "user", "assistant", "tool", "assistant"]
        assert agent.llm.converse.await_count == 2
