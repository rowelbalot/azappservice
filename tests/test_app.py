class TestHelloRoute:
    """Tests for the GET / route."""

    def test_status_code(self, client):
        """Root route returns 200 OK."""
        response = client.get("/")
        assert response.status_code == 200

    def test_response_body(self, client):
        """Root route returns the expected greeting."""
        response = client.get("/")
        assert response.data == b"Hello, Thomas and Andrew!"

    def test_content_type(self, client):
        """Root route returns text/html content type."""
        response = client.get("/")
        assert "text/html" in response.content_type

    def test_post_not_allowed(self, client):
        """POST to root route is not allowed."""
        response = client.post("/")
        assert response.status_code == 405

    def test_put_not_allowed(self, client):
        """PUT to root route is not allowed."""
        response = client.put("/")
        assert response.status_code == 405

    def test_delete_not_allowed(self, client):
        """DELETE to root route is not allowed."""
        response = client.delete("/")
        assert response.status_code == 405


class TestNotFound:
    """Tests for requests to unknown routes."""

    def test_unknown_route_returns_404(self, client):
        """Requests to unknown paths return 404 Not Found."""
        response = client.get("/nonexistent")
        assert response.status_code == 404

    def test_nested_unknown_route_returns_404(self, client):
        """Requests to unknown nested paths return 404 Not Found."""
        response = client.get("/some/nested/path")
        assert response.status_code == 404


class TestAppConfig:
    """Tests for Flask application configuration."""

    def test_testing_flag_is_set(self, app):
        """TESTING flag is enabled during tests."""
        assert app.config["TESTING"] is True

    def test_app_is_flask_instance(self, app):
        """The app object is a valid Flask application."""
        from flask import Flask
        assert isinstance(app, Flask)
