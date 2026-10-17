from bylaw.config import family


def test_family_handles_regional_and_bare_ids():
    assert family("us.anthropic.claude-sonnet-4-6") == "anthropic"
    assert family("global.anthropic.claude-haiku-4-5-20251001-v1:0") == "anthropic"
    assert family("mistral.mistral-large-3-675b-instruct") == "mistral"
    assert family("us.amazon.nova-pro-v1:0") == "amazon"
