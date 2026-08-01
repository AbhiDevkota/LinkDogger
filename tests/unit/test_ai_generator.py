"""AI draft generation (OpenAI-compatible chat completions, NVIDIA NIM)."""

import httpx
import pytest

from linkdogger.ai.generator import DraftGenerator, EmailDraft
from linkdogger.config.settings import Settings
from linkdogger.errors import AIError
from linkdogger.mail.contacts import Contact


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

    def post(self, url: str, json: object | None = None) -> FakeResponse:
        self.last_url = url
        self.last_payload = json
        return FakeClient.responses.pop(0)


@pytest.fixture(autouse=True)
def fake_client(monkeypatch: pytest.MonkeyPatch) -> None:
    FakeClient.instances = []
    FakeClient.responses = []
    monkeypatch.setattr("linkdogger.ai.generator.httpx.Client", FakeClient)


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


def _contact() -> Contact:
    return Contact(
        email="alice@example.com",
        name="Alice",
        company="Acme",
        position="Engineer",
    )


def test_generate_returns_personalized_draft() -> None:
    FakeClient.responses.append(
        FakeResponse(
            _completion('{"subject": "Hi Alice", "body": "Hello Alice, Acme!"}')
        )
    )
    draft = DraftGenerator(_settings()).generate(_contact())
    assert draft == EmailDraft(subject="Hi Alice", body="Hello Alice, Acme!")

    client = FakeClient.instances[0]
    assert client.last_url == "/chat/completions"
    assert client.kwargs["base_url"] == "https://integrate.api.nvidia.com/v1"
    assert client.kwargs["headers"] == {"Authorization": "Bearer nvapi-test-key"}
    assert client.last_payload is not None
    payload = client.last_payload
    assert payload["model"] == "deepseek-ai/deepseek-v4-flash"
    assert payload["temperature"] == 0.7
    user_message = payload["messages"][1]["content"]
    assert "Alice" in user_message
    assert "Acme" in user_message
    assert "Engineer" in user_message


def test_generate_parses_fenced_and_prose_json() -> None:
    FakeClient.responses.append(
        FakeResponse(_completion('```json\n{"subject": "S", "body": "B"}\n```'))
    )
    assert DraftGenerator(_settings()).generate(_contact()) == EmailDraft("S", "B")

    FakeClient.responses.append(
        FakeResponse(_completion('Here you go: {"subject": "S2", "body": "B2"}.'))
    )
    assert DraftGenerator(_settings()).generate(_contact()) == EmailDraft("S2", "B2")


def test_generate_requires_api_key() -> None:
    with pytest.raises(AIError, match="AI_API_KEY"):
        DraftGenerator(Settings(_env_file=None, ai_api_key=None)).generate(_contact())


def test_generate_raises_on_http_error() -> None:
    FakeClient.responses.append(FakeResponse({"error": "bad key"}, status_code=401))
    with pytest.raises(AIError, match="HTTP 401"):
        DraftGenerator(_settings()).generate(_contact())


def test_generate_raises_on_unexpected_shape() -> None:
    FakeClient.responses.append(FakeResponse({"unexpected": True}))
    with pytest.raises(AIError, match="unexpected response shape"):
        DraftGenerator(_settings()).generate(_contact())


def test_generate_raises_on_non_json_content() -> None:
    FakeClient.responses.append(FakeResponse(_completion("Sorry, I cannot do that.")))
    with pytest.raises(AIError, match="did not contain"):
        DraftGenerator(_settings()).generate(_contact())


def test_generate_raises_on_missing_fields() -> None:
    FakeClient.responses.append(FakeResponse(_completion('{"subject": "only"}')))
    with pytest.raises(AIError, match="missing 'subject' or 'body'"):
        DraftGenerator(_settings()).generate(_contact())
