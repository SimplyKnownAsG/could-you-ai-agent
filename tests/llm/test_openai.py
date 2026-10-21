from types import SimpleNamespace

from could_you.config import Config, LLMProps
from could_you.llm.openai import OpenAILLM
from could_you.message import Message, MessageType, TextContent, TokenUsage, ToolUseContent


class DummyOpenAILLM(OpenAILLM):
    def _init_client(self):
        return None


class DummyHistory:
    def __init__(self, messages: list[Message] | None = None):
        self.messages = messages or []


def test_openai_extracts_token_usage_from_response():
    llm = DummyOpenAILLM(
        Config(llm=LLMProps(provider="openai", tokenLimit=128000)),
        DummyHistory(),
        {},
    )
    response = SimpleNamespace(
        usage=SimpleNamespace(prompt_tokens=12, completion_tokens=7, total_tokens=19),
        choices=[SimpleNamespace(message=SimpleNamespace(content="hi", tool_calls=None))],
    )

    message = llm._transform_response(response)  # noqa: SLF001

    assert message.metadata == TokenUsage(
        inputTokens=12,
        outputTokens=7,
        totalTokens=19,
        tokenLimit=128000,
        provider="openai",
        model=None,
    )


def test_openai_transform_response_preserves_text_and_tool_calls():
    llm = DummyOpenAILLM(Config(llm=LLMProps(provider="openai")), DummyHistory(), {})
    response = SimpleNamespace(
        usage=None,
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    content="I'll list the files.",
                    tool_calls=[
                        SimpleNamespace(
                            id="call_1",
                            function=SimpleNamespace(name="list_directory", arguments='{"path": "/tmp"}'),
                        ),
                        SimpleNamespace(
                            id="call_2",
                            function=SimpleNamespace(name="read_file", arguments='{"path": "/tmp/a"}'),
                        ),
                    ],
                )
            )
        ],
    )

    message = llm._transform_response(response)  # noqa: SLF001

    assert message.type is MessageType.TOOL_CALL
    assert isinstance(message.content[0], TextContent)
    assert message.content[0].text == "I'll list the files."
    assert len(message.content) == 3
    assert all(isinstance(item, ToolUseContent) for item in message.content[1:])
    assert [(item.tool_use.tool_use_id, item.tool_use.name, item.tool_use.input) for item in message.content[1:]] == [
        ("call_1", "list_directory", {"path": "/tmp"}),
        ("call_2", "read_file", {"path": "/tmp/a"}),
    ]


def test_openai_convert_messages_ignores_token_usage():
    llm = DummyOpenAILLM(
        Config(llm=LLMProps(provider="openai")),
        DummyHistory(
            messages=[
                Message(
                    role="assistant",
                    content=[TextContent(text="hi")],
                    metadata=TokenUsage(inputTokens=12, outputTokens=7, totalTokens=19, tokenLimit=128000),
                )
            ]
        ),
        {},
    )

    assert llm._convert_messages() == [  # noqa: SLF001
        {"role": "system", "content": "COULD_YOU_DEFAULT_PROMPT"},
        {"role": "assistant", "content": "hi"},
    ]
