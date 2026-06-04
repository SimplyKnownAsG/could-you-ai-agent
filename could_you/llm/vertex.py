from google import genai

from .google_common import BaseGoogleLLM


class VertexLLM(BaseGoogleLLM):
    def _init_client(self):
        init_kwargs = dict(self.config.llm.init or {})
        return genai.Client(vertexai=True, **init_kwargs)
