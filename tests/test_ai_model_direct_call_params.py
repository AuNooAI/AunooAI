"""AIModel calls litellm.completion directly, bypassing the Router, so it must
pass the yaml's drop list itself. Without it Claude 5 on Bedrock rejected the
default temperature and every get_ai_model() caller of it failed."""
from unittest.mock import patch

from app import ai_models
from app.ai_models import AIModel

CLAUDE5 = {
    "model": "bedrock/us.anthropic.claude-sonnet-5",
    "api_key": "test-key",
    "aws_region_name": "us-east-1",
    "thinking": {"type": "disabled"},
    "additional_drop_params": ["reasoning_effort", "response_format", "temperature", "top_p", "top_k"],
}


class _Msg:
    content = "OK"


class _Choice:
    message = _Msg()


class _Resp:
    choices = [_Choice()]


def _captured_kwargs(call):
    with patch.object(ai_models, "completion", return_value=_Resp()) as fake:
        call()
    return fake.call_args.kwargs


def test_generate_response_passes_the_drop_list():
    kw = _captured_kwargs(lambda: AIModel(dict(CLAUDE5)).generate_response([{"role": "user", "content": "hi"}]))
    assert "temperature" in kw["additional_drop_params"]
    assert kw["thinking"] == {"type": "disabled"}
    assert kw["api_key"] == "test-key"


def test_generate_sync_passes_the_drop_list():
    kw = _captured_kwargs(lambda: AIModel(dict(CLAUDE5)).generate_sync("hi"))
    assert "temperature" in kw["additional_drop_params"]


def test_model_without_drop_list_is_unchanged():
    cfg = {"model": "bedrock/amazon.nova-lite-v1:0", "api_key": "k", "aws_region_name": "us-east-1"}
    kw = _captured_kwargs(lambda: AIModel(cfg).generate_response([{"role": "user", "content": "hi"}]))
    assert "additional_drop_params" not in kw and "thinking" not in kw
    assert kw["temperature"] == 0.7
