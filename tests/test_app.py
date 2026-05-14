import json
import os
from unittest.mock import MagicMock, patch

import pytest

from app import app as flask_app


@pytest.fixture
def app():
    flask_app.config.update({"TESTING": True})
    yield flask_app


@pytest.fixture
def client(app):
    return app.test_client()


class TestIndexRoute:
    def test_status_code(self, client):
        response = client.get("/")
        assert response.status_code == 200

    def test_content_type_html(self, client):
        response = client.get("/")
        assert "text/html" in response.content_type

    def test_post_not_allowed(self, client):
        assert client.post("/").status_code == 405

    def test_put_not_allowed(self, client):
        assert client.put("/").status_code == 405

    def test_delete_not_allowed(self, client):
        assert client.delete("/").status_code == 405


class TestModelsRoute:
    def test_status_code(self, client):
        assert client.get("/api/models").status_code == 200

    def test_returns_models_list(self, client):
        data = json.loads(client.get("/api/models").data)
        assert "models" in data
        assert isinstance(data["models"], list)
        assert len(data["models"]) > 0

    def test_each_model_has_id_and_name(self, client):
        data = json.loads(client.get("/api/models").data)
        for model in data["models"]:
            assert "id" in model
            assert "name" in model


class TestChatRoute:
    def test_missing_messages_returns_400(self, client):
        assert client.post("/api/chat", json={}).status_code == 400

    def test_empty_messages_returns_400(self, client):
        assert client.post("/api/chat", json={"messages": []}).status_code == 400

    def test_no_api_key_returns_500(self, client):
        env = {k: v for k, v in os.environ.items() if k != "OPENROUTER_API_KEY"}
        with patch.dict("os.environ", env, clear=True):
            response = client.post("/api/chat", json={"messages": [{"role": "user", "content": "hi"}]})
            assert response.status_code == 500
            assert "OPENROUTER_API_KEY" in json.loads(response.data)["error"]

    def test_successful_response(self, client):
        mock_result = {
            "choices": [{"message": {"role": "assistant", "content": "Hello!"}, "finish_reason": "stop"}]
        }
        with patch.dict("os.environ", {"OPENROUTER_API_KEY": "test-key"}):
            with patch("requests.post") as mock_post:
                r = MagicMock()
                r.json.return_value = mock_result
                r.raise_for_status.return_value = None
                mock_post.return_value = r

                response = client.post("/api/chat", json={"messages": [{"role": "user", "content": "Hello"}]})
                assert response.status_code == 200
                data = json.loads(response.data)
                assert data["content"] == "Hello!"
                assert data["tool_calls"] == []

    def test_tool_call_loop(self, client):
        tool_resp = {
            "choices": [{
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [{"id": "c1", "function": {"name": "web_search", "arguments": '{"query":"test"}'}}],
                },
                "finish_reason": "tool_calls",
            }]
        }
        final_resp = {
            "choices": [{"message": {"role": "assistant", "content": "Found it!"}, "finish_reason": "stop"}]
        }
        with patch.dict("os.environ", {"OPENROUTER_API_KEY": "test-key"}):
            with patch("requests.post") as mock_post:
                r1, r2 = MagicMock(), MagicMock()
                r1.json.return_value = tool_resp
                r1.raise_for_status.return_value = None
                r2.json.return_value = final_resp
                r2.raise_for_status.return_value = None
                mock_post.side_effect = [r1, r2]

                with patch("tools.web_search", return_value="Search results here"):
                    response = client.post("/api/chat", json={"messages": [{"role": "user", "content": "Search"}]})
                    assert response.status_code == 200
                    data = json.loads(response.data)
                    assert data["content"] == "Found it!"
                    assert len(data["tool_calls"]) == 1
                    assert data["tool_calls"][0]["name"] == "web_search"

    def test_tool_call_invalid_json_args(self, client):
        tool_resp = {
            "choices": [{
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [{"id": "c1", "function": {"name": "web_search", "arguments": "INVALID"}}],
                },
                "finish_reason": "tool_calls",
            }]
        }
        final_resp = {
            "choices": [{"message": {"role": "assistant", "content": "Done"}, "finish_reason": "stop"}]
        }
        with patch.dict("os.environ", {"OPENROUTER_API_KEY": "test-key"}):
            with patch("requests.post") as mock_post:
                r1, r2 = MagicMock(), MagicMock()
                r1.json.return_value = tool_resp
                r1.raise_for_status.return_value = None
                r2.json.return_value = final_resp
                r2.raise_for_status.return_value = None
                mock_post.side_effect = [r1, r2]

                with patch("tools.execute_tool", return_value="result"):
                    response = client.post("/api/chat", json={"messages": [{"role": "user", "content": "hi"}]})
                    assert response.status_code == 200

    def test_openrouter_network_error_returns_502(self, client):
        import requests as req
        with patch.dict("os.environ", {"OPENROUTER_API_KEY": "test-key"}):
            with patch("requests.post", side_effect=req.RequestException("timeout")):
                response = client.post("/api/chat", json={"messages": [{"role": "user", "content": "hi"}]})
                assert response.status_code == 502
                assert "OpenRouter API error" in json.loads(response.data)["error"]

    def test_openrouter_error_response_returns_502(self, client):
        with patch.dict("os.environ", {"OPENROUTER_API_KEY": "test-key"}):
            with patch("requests.post") as mock_post:
                r = MagicMock()
                r.json.return_value = {"error": {"message": "Invalid API key"}}
                r.raise_for_status.return_value = None
                mock_post.return_value = r

                response = client.post("/api/chat", json={"messages": [{"role": "user", "content": "hi"}]})
                assert response.status_code == 502
                assert "Invalid API key" in json.loads(response.data)["error"]

    def test_max_iterations_returns_500(self, client):
        always_tool = {
            "choices": [{
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [{"id": "c1", "function": {"name": "web_search", "arguments": '{"query":"x"}'}}],
                },
                "finish_reason": "tool_calls",
            }]
        }
        with patch.dict("os.environ", {"OPENROUTER_API_KEY": "test-key"}):
            with patch("requests.post") as mock_post:
                r = MagicMock()
                r.json.return_value = always_tool
                r.raise_for_status.return_value = None
                mock_post.return_value = r

                with patch("tools.web_search", return_value="result"):
                    response = client.post("/api/chat", json={"messages": [{"role": "user", "content": "hi"}]})
                    assert response.status_code == 500
                    assert "Max tool call" in json.loads(response.data)["error"]


class TestNotFound:
    def test_unknown_route_returns_404(self, client):
        assert client.get("/nonexistent").status_code == 404

    def test_nested_unknown_route_returns_404(self, client):
        assert client.get("/some/nested/path").status_code == 404


class TestAppConfig:
    def test_testing_flag_is_set(self, app):
        assert app.config["TESTING"] is True

    def test_app_is_flask_instance(self, app):
        from flask import Flask
        assert isinstance(app, Flask)
