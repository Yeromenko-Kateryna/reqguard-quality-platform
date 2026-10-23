from html.parser import HTMLParser

import pytest
from fastapi.testclient import TestClient

from reqguard.main import app


class Page(HTMLParser):
    def __init__(self):
        super().__init__()
        self.elements = []

    def handle_starttag(self, tag, attrs):
        self.elements.append((tag, dict(attrs)))


@pytest.fixture
def client(monkeypatch):
    def forbidden(*args):
        pytest.fail("Serving UI resources must not access persistence")

    monkeypatch.setattr("reqguard.main.save_analysis", forbidden)
    return TestClient(app)


def test_page_exposes_labelled_form_and_result_states(client):
    response = client.get("/")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    page = Page()
    page.feed(response.text)
    ids = {attrs["id"]: (tag, attrs) for tag, attrs in page.elements if "id" in attrs}
    assert ids["requirement"][0] == "textarea"
    assert ("label", {"for": "requirement"}) in page.elements
    assert ids["submit"][1]["type"] == "submit"
    assert "disabled" in ids["submit"][1]  # Enabled only after the module mounts.
    assert ids["notice"][1]["role"] == "status"
    assert ids["error"][1]["role"] == "alert"
    assert "hidden" in ids["error"][1] and "hidden" in ids["result"][1]
    assert {"run-id", "status", "provider", "analysis"} <= ids.keys()
    assert "deterministic fake" in response.text.lower()


def test_page_assets_are_local_and_served_without_persistence(client):
    page = Page()
    page.feed(client.get("/").text)
    resources = [attrs[key] for tag, attrs in page.elements
                 for key in ("src", "href") if key in attrs]
    assert set(resources) == {"/static/style.css", "/static/app.mjs"}
    for resource in resources:
        response = client.get(resource)
        assert response.status_code == 200
        assert response.content
    assert client.get("/static/style.css").headers["content-type"].startswith("text/css")
    assert "javascript" in client.get("/static/app.mjs").headers["content-type"]


def test_ui_routes_do_not_change_public_analysis_openapi(client):
    paths = client.get("/openapi.json").json()["paths"]
    assert set(paths) == {"/analyses"}
    assert set(paths["/analyses"]) == {"post"}


@pytest.mark.parametrize("text,expected_status", [
    ("The user can quickly reset their password", "completed"),
    ("  A different synthetic requirement  ", "unsupported_fixture"),
])
def test_ui_json_request_preserves_api_and_persistence_mapping(monkeypatch, text, expected_status):
    saved = []
    monkeypatch.setattr("reqguard.main.save_analysis", lambda original, result: saved.append((original, result)))
    client = TestClient(app)
    assert client.get("/").status_code == 200
    response = client.post("/analyses", json={"requirement_text": text}, headers={"Accept": "application/json"})
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"run_id", "status", "provider", "analysis"}
    assert body["status"] == expected_status and body["provider"] == "fake"
    assert saved == [(text, body)]
    assert (body["analysis"] is None) == (expected_status == "unsupported_fixture")


def test_blank_ui_json_request_returns_422_before_persistence(client):
    response = client.post("/analyses", json={"requirement_text": " \t\n"})
    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "requirement_text"]
