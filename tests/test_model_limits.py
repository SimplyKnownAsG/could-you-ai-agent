from could_you.model_limits import infer_token_limit


def test_infer_openai_token_limit():
    assert infer_token_limit({"model": "gpt-5.5"}) == 1_050_000
    assert infer_token_limit({"model": "gpt-4.1-mini"}) == 1_047_576
    assert infer_token_limit({"model": "gpt-4o"}) == 128_000


def test_infer_anthropic_token_limit_from_bedrock_model_id():
    assert infer_token_limit({"modelId": "us.anthropic.claude-opus-4-7-v1:0"}) == 1_000_000
    assert infer_token_limit({"modelId": "us.anthropic.claude-sonnet-4-6-v1:0"}) == 1_000_000
    assert infer_token_limit({"modelId": "anthropic.claude-haiku-4-5-20251001-v1:0"}) == 200_000
    assert infer_token_limit({"modelId": "us.anthropic.claude-sonnet-4-20250514-v1:0"}) == 200_000


def test_infer_google_gemini_token_limit():
    assert infer_token_limit({"model": "gemini-2.5-pro"}) == 1_048_576
    assert infer_token_limit({"model": "gemini-1.5-flash"}) == 1_048_576


def test_infer_token_limit_returns_none_when_unknown():
    assert infer_token_limit({"model": "some-new-model"}) is None
    assert infer_token_limit(None) is None
    assert infer_token_limit({}) is None


def test_infer_token_limit_reads_supported_model_name_keys():
    assert infer_token_limit({"model": "gpt-4o"}) == 128_000
    assert infer_token_limit({"modelId": "anthropic.claude-sonnet-4-6"}) == 1_000_000
    assert infer_token_limit({"model_id": "gpt-4o"}) == 128_000
