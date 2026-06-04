from google import genai

from .google_common import BaseGoogleLLM


class GoogleLLM(BaseGoogleLLM):
    def __init__(self, *args, **kwargs):
        super().__init__(api_name="Google AI Developer API", *args, **kwargs)

    def _init_client(self):
        init_kwargs = dict(self.config.llm.init or {})
        return genai.Client(**init_kwargs)
