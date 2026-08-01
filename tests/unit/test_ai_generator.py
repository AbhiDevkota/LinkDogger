"""AI draft generation (OpenAI-compatible chat completions, NVIDIA NIM)."""

import httpx
import pytest

from linkdogger.ai.generator import DraftGenerator, EmailDraft
from linkdogger.config.settings import Settings
from linkdogger.errors import AIError


class FakeResponse:
    def __init__(self, payload: object, status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code

    def json(self) -> object:
        return self._payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            request = httpx.Request("POST", "https://integrate.api.nvidia.com/v1")
            raise httpx.HTTPStatusError(
                "error",
                request=request,
                response=httpx.Response(self.status_code, request=request),
            )


class FakeClient:
    """Records requests and replays canned responses."""

    instances: list["FakeClient"] = []
    responses: list[FakeResponse] = []

    def __init__(self, *args: object, **kwargs: object) -> None:
        self.args = args
        self.kwargs = kwargs
        FakeClient.instances.append(self)

    def __enter__(self) -> "FakeClient":
        return self

    def __exit__(self, *args: object) -> None:
        pass

    def post(self, url: str, json: object | None = None) -> FakeResponse:
        self.last_url = url
        self.last_payload = json
        return FakeClient.responses.pop(0)

    def get(self, url: str) -> FakeResponse:
        self.last_url = url
        return FakeClient.responses.pop(0)


@pytest.fixture(autouse=True)
def fake_client(monkeypatch: pytest.MonkeyPatch) -> None:
    FakeClient.instances = []
    FakeClient.responses = []
    monkeypatch.setattr("linkdogger.ai.generator.httpx.Client", FakeClient)


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("linkdogger.ai.generator.time.sleep", lambda s: None)


def _settings(**overrides: object) -> Settings:
    return Settings(
        _env_file=None,
        ai_api_key="nvapi-test-key",
        ai_model="deepseek-ai/deepseek-v4-flash",
        ai_base_url="https://integrate.api.nvidia.com/v1",
        **overrides,
    )


def _completion(content: str) -> object:
    return {
        "choices": [{"message": {"role": "assistant", "content": content}}],
        "model": "deepseek-ai/deepseek-v4-flash",
    }


def test_generate_template_returns_draft() -> None:
    FakeClient.responses.append(
        FakeResponse(
            _completion(
                '{"subject": "Quick question for {name}", '
                '"body": "Dear {name},\\n\\nHello."}'
            )
        )
    )
    draft = DraftGenerator(_settings()).generate_template()
    assert draft == EmailDraft(
        subject="Quick question for {name}",
        body="Dear {name},\n\nHello.",
    )

    client = FakeClient.instances[0]
    assert client.last_url == "/chat/completions"
    assert client.kwargs["base_url"] == "https://integrate.api.nvidia.com/v1"
    assert client.kwargs["headers"] == {"Authorization": "Bearer nvapi-test-key"}
    assert client.last_payload is not None
    payload = client.last_payload
    assert payload["model"] == "deepseek-ai/deepseek-v4-flash"
    assert payload["temperature"] == 0.7
    user_message = payload["messages"][1]["content"]
    assert "{name}" in user_message
    assert "{company}" in user_message
    assert "{position}" in user_message
    assert "{from_name}" in user_message
    assert "professional" in user_message


def test_generate_template_parses_fenced_and_prose_json() -> None:
    FakeClient.responses.append(
        FakeResponse(_completion('```json\n{"subject": "S", "body": "B"}\n```'))
    )
    assert DraftGenerator(_settings()).generate_template() == EmailDraft("S", "B")

    FakeClient.responses.append(
        FakeResponse(_completion('Here you go: {"subject": "S2", "body": "B2"}.'))
    )
    assert DraftGenerator(_settings()).generate_template() == EmailDraft("S2", "B2")


def test_generate_template_requires_api_key() -> None:
    with pytest.raises(AIError, match="AI_API_KEY"):
        DraftGenerator(Settings(_env_file=None, ai_api_key=None)).generate_template()


def test_generate_template_raises_on_http_error() -> None:
    FakeClient.responses.append(FakeResponse({"error": "bad key"}, status_code=401))
    with pytest.raises(AIError, match="HTTP 401"):
        DraftGenerator(_settings()).generate_template()
    assert not FakeClient.responses  # single attempt, non-transient errors don't retry


def test_generate_template_retries_transient_errors_then_succeeds() -> None:
    FakeClient.responses.append(FakeResponse({"error": "overloaded"}, status_code=529))
    FakeClient.responses.append(FakeResponse({"error": "slow"}, status_code=503))
    FakeClient.responses.append(
        FakeResponse(_completion('{"subject": "S", "body": "B"}'))
    )
    assert DraftGenerator(_settings()).generate_template() == EmailDraft("S", "B")


def test_generate_template_gives_up_after_retries() -> None:
    for _ in range(3):
        FakeClient.responses.append(
            FakeResponse({"error": "overloaded"}, status_code=529)
        )
    with pytest.raises(AIError, match="after 3 attempts"):
        DraftGenerator(_settings()).generate_template()


def test_generate_template_raises_on_unexpected_shape() -> None:
    FakeClient.responses.append(FakeResponse({"unexpected": True}))
    with pytest.raises(AIError, match="unexpected response shape"):
        DraftGenerator(_settings()).generate_template()


def test_generate_template_raises_on_non_json_content() -> None:
    FakeClient.responses.append(FakeResponse(_completion("Sorry, I cannot do that.")))
    with pytest.raises(AIError, match="did not contain"):
        DraftGenerator(_settings()).generate_template()


def test_generate_template_raises_on_missing_fields() -> None:
    FakeClient.responses.append(FakeResponse(_completion('{"subject": "only"}')))
    with pytest.raises(AIError, match="missing 'subject' or 'body'"):
        DraftGenerator(_settings()).generate_template()


def test_check_reports_model_count() -> None:
    FakeClient.responses.append(
        FakeResponse(
            {
                "data": [
                    {"id": "deepseek-ai/deepseek-v4-flash"},
                    {"id": "nvidia/nemotron-3-super-120b"},
                ]
            }
        )
    )
    generator = DraftGenerator(_settings())
    assert generator.check() == "ok (2 models)"
    assert FakeClient.instances[1].last_url == "/models"


def test_check_warns_when_configured_model_not_listed() -> None:
    FakeClient.responses.append(FakeResponse({"data": [{"id": "other/model"}]}))
    result = DraftGenerator(_settings()).check()
    assert "ok (1 models)" in result
    assert "not listed" in result


def test_check_raises_on_http_error() -> None:
    FakeClient.responses.append(FakeResponse({"error": "bad key"}, status_code=401))
    with pytest.raises(AIError, match="HTTP 401"):
        DraftGenerator(_settings()).check()


def test_check_requires_api_key() -> None:
    with pytest.raises(AIError, match="AI_API_KEY"):
        DraftGenerator(Settings(_env_file=None, ai_api_key=None)).check()
