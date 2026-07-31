"""Web interface integration tests."""

from fastapi.testclient import TestClient

from linkdogger.config.settings import Settings
from linkdogger.web.app import create_app

client = TestClient(create_app(Settings(_env_file=None)))


def test_index_page_renders() -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert "LinkDogger" in response.text
    assert 'id="search-form"' in response.text


def test_static_css_and_js_are_served() -> None:
    assert client.get("/static/style.css").status_code == 200
    assert client.get("/static/app.js").status_code == 200


def test_api_search_returns_results() -> None:
    response = client.get("/api/search", params={"company": "Acme"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["schema_version"] == "1.0"
    assert payload["query"] == "Acme"
    assert payload["company"]["name"] == "Acme Corporation"
    assert payload["count"] == 3
    assert payload["results"][0]["networking"]["networking_score"] is not None


def test_api_search_unknown_company() -> None:
    response = client.get("/api/search", params={"company": "Nope Inc"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["company"] is None
    assert payload["count"] == 0


def test_api_search_sorts_by_followers() -> None:
    response = client.get(
        "/api/search", params={"company": "Acme", "sort": "followers-desc"}
    )
    payload = response.json()

    def max_followers(person: dict) -> int:
        counts = [
            profile["followers"]
            for profile in person["profiles"].values()
            if profile["followers"] is not None
        ]
        return max(counts, default=0)

    followers = [max_followers(p) for p in payload["results"]]
    assert followers == sorted(followers, reverse=True)


def test_api_search_invalid_sort_falls_back() -> None:
    response = client.get("/api/search", params={"company": "Acme", "sort": "bogus"})
    assert response.status_code == 200
    assert response.json()["count"] == 3


def test_api_search_filters_by_role() -> None:
    response = client.get("/api/search", params={"company": "Acme", "role": "engineer"})
    payload = response.json()
    assert payload["count"] == 1
    assert payload["results"][0]["position"] == "Software Engineer"


def test_api_search_respects_limit() -> None:
    response = client.get("/api/search", params={"company": "Acme", "limit": 2})
    assert response.json()["count"] == 2


def test_api_search_accepts_provider() -> None:
    response = client.get("/api/search", params={"company": "Acme", "provider": "mock"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] == 3
    assert payload["results"][0]["networking"]["networking_score"] is not None


def test_api_search_rejects_unknown_provider() -> None:
    response = client.get(
        "/api/search", params={"company": "Acme", "provider": "bogus"}
    )
    assert response.status_code == 400
    assert "invalid provider" in response.json()["detail"]
