from types import SimpleNamespace

from could_you.config import Config, LLMProps
from could_you.llm.openai import OpenAILLM
from could_you.message import Message, TextContent, TokenUsage


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

    assert message.token_usage == TokenUsage(
        inputTokens=12,
        outputTokens=7,
        totalTokens=19,
        tokenLimit=128000,
        provider="openai",
        model=None,
    )


def test_openai_convert_messages_ignores_token_usage():
    llm = DummyOpenAILLM(
        Config(llm=LLMProps(provider="openai")),
        DummyHistory(
            messages=[
                Message(
                    role="assistant",
                    content=[TextContent(text="hi")],
                    tokenUsage=TokenUsage(inputTokens=12, outputTokens=7, totalTokens=19, tokenLimit=128000),
                )
            ]
        ),
        {},
    )

    assert llm._convert_messages() == [  # noqa: SLF001
        {"role": "system", "content": "COULD_YOU_DEFAULT_PROMPT"},
        {"role": "assistant", "content": "hi"},
    ]
