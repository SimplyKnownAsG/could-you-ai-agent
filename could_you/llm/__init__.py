from .base_llm import BaseLLM
from .boto3 import Boto3LLM
from .google import GoogleLLM
from .ollama import OllamaLLM
from .openai import OpenAILLM
from .vertex import VertexLLM

# Factory for LLM


def create_llm(config, dialogue, tools) -> BaseLLM:
    provider = config.llm.provider
    providers = {
        "boto3": Boto3LLM,
        "ollama": OllamaLLM,
        "openai": OpenAILLM,
        "vertex": VertexLLM,
        "google": GoogleLLM,
    }

    if provider in providers:
        return providers[provider](config, dialogue, tools)
    raise ValueError(f"Unsupported LLM provider: {provider}")


__all__ = ["BaseLLM", "create_llm"]
