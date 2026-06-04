from google import genai

from .google_common import BaseGoogleLLM


class GoogleLLM(BaseGoogleLLM):
    def _init_client(self):
        init_kwargs = dict(self.config.llm.init or {})
        return genai.Client(**init_kwargs)
