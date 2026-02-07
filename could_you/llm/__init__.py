from .base_llm import BaseLLM
from .boto3 import Boto3LLM
from .ollama import OllamaLLM
from .openai import OpenAILLM

# Factory for LLM


def create_llm(config, message_history, tools) -> BaseLLM:
    provider = config.llm.provider
    providers = {
        "boto3": Boto3LLM,
        "ollama": OllamaLLM,
        "openai": OpenAILLM,
    }

    if provider in providers:
        return providers[provider](config, message_history, tools)
    raise ValueError(f"Unsupported LLM provider: {provider}")


__all__ = ["BaseLLM", "create_llm"]
