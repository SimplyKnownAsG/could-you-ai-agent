from types import SimpleNamespace

from could_you.config import Config, LLMProps
from could_you.llm.vertex import VertexLLM
from could_you.message import (
    Message,
    TextContent,
    TokenUsage,
    ToolResult,
    ToolResultContent,
    ToolResultInnerTextContent,
    ToolUseContent,
)


class DummyVertexLLM(VertexLLM):
    def _init_client(self):
        return None


class DummyHistory:
    def __init__(self, messages: list[Message] | None = None):
        self.messages = messages or []


def test_vertex_extracts_token_usage_from_response():
    llm = DummyVertexLLM(
        Config(llm=LLMProps(provider="vertex", tokenLimit=1_000_000, args={"model": "gemini-2.5-pro"})),
        DummyHistory(),
        {},
    )
    response = SimpleNamespace(
        usage_metadata=SimpleNamespace(
            prompt_token_count=12,
            candidates_token_count=7,
            total_token_count=19,
        ),
        candidates=[SimpleNamespace(content=SimpleNamespace(parts=[SimpleNamespace(text="hi", function_call=None)]))],
    )

    message = llm._transform_response(response)  # noqa: SLF001

    assert message.metadata == TokenUsage(
        inputTokens=12,
        outputTokens=7,
        totalTokens=19,
        tokenLimit=1_000_000,
        provider="vertex",
        model="gemini-2.5-pro",
    )


def test_vertex_convert_messages_maps_text_roles():
    llm = DummyVertexLLM(
        Config(llm=LLMProps(provider="vertex", args={"model": "gemini-2.5-pro"}), systemPrompt="sys"),
        DummyHistory(
            messages=[
                Message(role="user", content=[TextContent(text="hello")]),
                Message(role="assistant", content=[TextContent(text="hi")]),
            ]
        ),
        {},
    )

    contents = llm._convert_messages()  # noqa: SLF001

    assert len(contents) == 2
    assert contents[0].role == "user"
    assert contents[0].parts[0].text == "hello"
    assert contents[1].role == "model"
    assert contents[1].parts[0].text == "hi"


def test_vertex_convert_messages_maps_tool_result():
    llm = DummyVertexLLM(
        Config(llm=LLMProps(provider="vertex", args={"model": "gemini-2.5-pro"})),
        DummyHistory(
            messages=[
                Message(
                    role="tool",
                    content=[
                        ToolResultContent(
                            toolResult=ToolResult(
                                status="success",
                                toolUseId="call-1",
                                content=[ToolResultInnerTextContent(text="done")],
                            )
                        )
                    ],
                )
            ]
        ),
        {},
    )

    contents = llm._convert_messages()  # noqa: SLF001

    assert len(contents) == 1
    assert contents[0].role == "user"
    function_response = contents[0].parts[0].function_response
    assert function_response.name == "call-1"
    assert function_response.response == {"result": "done", "status": "success"}


def test_vertex_sanitize_schema_removes_zod_metadata():
    llm = DummyVertexLLM(
        Config(llm=LLMProps(provider="vertex", args={"model": "gemini-2.5-pro"})),
        DummyHistory(),
        {},
    )

    schema = {
        "type": "object",
        "properties": {
            "duration_seconds": {
                "type": "integer",
                "description": "Number of seconds to wait",
                "_def": {"checks": [{"kind": "min", "value": 0}]},
                "~standard": {"version": 1, "vendor": "zod"},
            }
        },
        "required": ["duration_seconds"],
    }

    cleaned = llm._sanitize_schema(schema)  # noqa: SLF001

    assert cleaned == {
        "type": "object",
        "properties": {
            "duration_seconds": {
                "type": "integer",
                "description": "Number of seconds to wait",
            }
        },
        "required": ["duration_seconds"],
    }
    assert "_def" in schema["properties"]["duration_seconds"]
    assert "~standard" in schema["properties"]["duration_seconds"]
    schema["properties"]["duration_seconds"]["$schema"] = "http://json-schema.org/draft-07/schema#"
    schema["properties"]["duration_seconds"]["title"] = "Duration"
    schema["properties"]["duration_seconds"]["default"] = 1
    schema["properties"]["duration_seconds"]["examples"] = [1, 2]

    cleaned = llm._sanitize_schema(schema)  # noqa: SLF001

    assert cleaned == {
        "type": "object",
        "properties": {
            "duration_seconds": {
                "type": "integer",
                "description": "Number of seconds to wait",
            }
        },
        "required": ["duration_seconds"],
    }
    assert "_def" in schema["properties"]["duration_seconds"]
    assert "~standard" in schema["properties"]["duration_seconds"]
    assert "$schema" in schema["properties"]["duration_seconds"]
    assert "title" in schema["properties"]["duration_seconds"]
    assert "default" in schema["properties"]["duration_seconds"]
    assert "examples" in schema["properties"]["duration_seconds"]


def test_vertex_transform_response_maps_function_call_to_tool_use():
    llm = DummyVertexLLM(
        Config(llm=LLMProps(provider="vertex", args={"model": "gemini-2.5-pro"})),
        DummyHistory(),
        {},
    )
    response = SimpleNamespace(
        usage_metadata=None,
        candidates=[
            SimpleNamespace(
                content=SimpleNamespace(
                    parts=[
                        SimpleNamespace(
                            text=None,
                            function_call=SimpleNamespace(name="search", args={"query": "x"}, id="call-1"),
                        )
                    ]
                )
            )
        ],
    )

    message = llm._transform_response(response)  # noqa: SLF001

    assert message.type.value == "tool_call"
    assert isinstance(message.content[0], ToolUseContent)
    assert message.content[0].tool_use.name == "search"
    assert message.content[0].tool_use.input == {"query": "x"}
    assert message.content[0].tool_use.tool_use_id == "call-1"
