import openai

from .openai import OpenAILLM


class OllamaLLM(OpenAILLM):
    """
    OllamaLLM is compliant with OpenAILLM [1].
    [1] https://ollama.com/blog/tool-support
    """

    def _init_client(self):
        return openai.OpenAI(**{"base_url": "http://localhost:11434/v1", "api_key": "ollama", **self.config.llm.init})
