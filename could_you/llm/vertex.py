from google import genai

from .google_common import BaseGoogleLLM


class VertexLLM(BaseGoogleLLM):
    def __init__(self, *args, **kwargs):
        super().__init__(api_name="Vertex AI", *args, **kwargs)

    def _init_client(self):
        init_kwargs = dict(self.config.llm.init or {})
        return genai.Client(vertexai=True, **init_kwargs)
