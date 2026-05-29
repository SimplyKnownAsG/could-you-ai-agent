import re

from attrs import frozen


@frozen
class ModelTokenLimit:
    pattern: str
    token_limit: int
    note: str


# Boring, explicit, local defaults. Keep these best-effort and easy to audit.
# More specific patterns should appear before broader family patterns.
DEFAULT_MODEL_TOKEN_LIMITS = [
    # Anthropic docs, Models overview, retrieved 2026-05-17:
    # Claude Opus 4.7 and Sonnet 4.6 list 1M token context windows;
    # Claude Haiku 4.5 lists a 200k token context window.
    ModelTokenLimit(r"claude[-.]opus[-.]4[-.]7", 1_000_000, "Claude Opus 4.7 context window"),
    ModelTokenLimit(r"claude[-.]sonnet[-.]4[-.]6", 1_000_000, "Claude Sonnet 4.6 context window"),
    ModelTokenLimit(r"claude[-.]haiku[-.]4[-.]5", 200_000, "Claude Haiku 4.5 context window"),
    # Common recent/legacy Claude aliases and Bedrock model IDs.
    ModelTokenLimit(r"claude[-.]opus[-.]4[-.][0-5]", 200_000, "Claude Opus 4.x default context window"),
    ModelTokenLimit(r"claude[-.]sonnet[-.]4[-.][0-5]", 200_000, "Claude Sonnet 4.x default context window"),
    ModelTokenLimit(r"claude[-.]3[-.].*", 200_000, "Claude 3.x default context window"),
    # OpenAI docs were not fetchable without auth when these defaults were added.
    # These are intentionally conservative/common defaults plus the current known
    # workspace value for GPT-5.5. Explicit config always wins over these defaults.
    ModelTokenLimit(r"gpt[-.]5[-.]5", 1_050_000, "GPT-5.5 configured/default context window"),
    ModelTokenLimit(r"gpt[-.]4[-.]1", 1_047_576, "GPT-4.1 context window"),
    ModelTokenLimit(r"chatgpt[-.]4o[-.]latest", 128_000, "ChatGPT 4o latest context window"),
    ModelTokenLimit(r"gpt[-.]4o", 128_000, "GPT-4o context window"),
    ModelTokenLimit(r"gpt[-.]4[-.]turbo", 128_000, "GPT-4 Turbo context window"),
    # Google Gemini / Vertex AI best-effort defaults.
    ModelTokenLimit(r"gemini[-.]2[.].*", 1_048_576, "Gemini 2.x default context window"),
    ModelTokenLimit(r"gemini[-.]1[.]5[-.](pro|flash)", 1_048_576, "Gemini 1.5 Pro/Flash default context window"),
    # Alibaba Tongyi Qianwen, retrieved 2024-07-26 from:
    # https://help.aliyun.com/document_detail/2582584.html
    ModelTokenLimit(r"qwen-max-longcontext", 30_720, "Qwen Max Long Context window"),
    ModelTokenLimit(r"qwen-plus", 32_768, "Qwen Plus context window"),
    ModelTokenLimit(r"qwen-max$", 8_192, "Qwen Max context window"),
    ModelTokenLimit(r"qwen-turbo", 8_192, "Qwen Turbo context window"),
    # https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-qwen-qwen3-coder-480b-a35b-instruct.html
    ModelTokenLimit(r"qwen3-coder-480b-a35b", 128_000, "Qwen3 Coder 480B A35B Instruct"),
    # https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-qwen-qwen3-coder-30b-a3b-instruct.html
    ModelTokenLimit(r"qwen3-coder-30b-a3b", 256_000, "Qwen3 Coder 30B A3B Instruct"),
    # https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-qwen-qwen3-coder-next.html
    ModelTokenLimit(r"qwen3-coder-next", 256_000, "Qwen3 Coder Next"),
    # https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-qwen-qwen3-coder-next.html
    ModelTokenLimit(r"qwen3-coder-235b-a22b", 256_000, "Qwen3 235B A22B 2507"),
]


def infer_token_limit(llm_args: dict | None) -> int | None:
    model_name = _model_name_from_llm_args(llm_args or {})
    if not model_name:
        return None

    normalized_model_name = model_name.lower()
    for default in DEFAULT_MODEL_TOKEN_LIMITS:
        if re.search(default.pattern, normalized_model_name):
            return default.token_limit

    return None


def _model_name_from_llm_args(args: dict) -> str | None:
    for key in ("model", "modelId", "model_id"):
        value = args.get(key)
        if isinstance(value, str) and value:
            return value

    return None
