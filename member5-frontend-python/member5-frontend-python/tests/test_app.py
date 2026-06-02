"""
BCETD Python Frontend — Unit Tests.

Run: python -m pytest tests/ -v
"""

import json
import pytest
from unittest.mock import patch, MagicMock
from app import create_app
from app.config import TestingConfig
from app.services.session_manager import SessionManager
from app.services.n8n_client import N8nClient, N8nClientError


# ═══════════════════════════════════════════════════════════════
# FIXTURES
# ═══════════════════════════════════════════════════════════════


@pytest.fixture
def app():
    """Create a test Flask application."""
    application = create_app(config_class=TestingConfig)
    application.config["TESTING"] = True
    return application


@pytest.fixture
def client(app):
    """Create a test client."""
    return app.test_client()


@pytest.fixture
def session_mgr():
    """Create a fresh session manager."""
    return SessionManager(rotate_seconds=3600)


# ═══════════════════════════════════════════════════════════════
# TEST: Health Check
# ═══════════════════════════════════════════════════════════════


class TestHealthCheck:
    def test_health_endpoint_returns_200(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        data = response.get_json()
        assert data["status"] == "ok"
        assert data["service"] == "bcetd-frontend-python"


# ═══════════════════════════════════════════════════════════════
# TEST: Chat Page Route
# ═══════════════════════════════════════════════════════════════


class TestChatRoute:
    def test_index_returns_200(self, client):
        response = client.get("/")
        assert response.status_code == 200

    def test_index_contains_ulbs_branding(self, client):
        response = client.get("/")
        html = response.data.decode("utf-8")
        assert "ULBS" in html
        assert "Lucian Blaga" in html

    def test_index_contains_suggestions(self, client):
        response = client.get("/")
        html = response.data.decode("utf-8")
        assert "calendarul academic" in html
        assert "suggestion-chip" in html

    def test_index_loads_chat_js(self, client):
        response = client.get("/")
        html = response.data.decode("utf-8")
        assert "chat.js" in html

    def test_index_loads_chat_css(self, client):
        response = client.get("/")
        html = response.data.decode("utf-8")
        assert "chat.css" in html


# ═══════════════════════════════════════════════════════════════
# TEST: Admin Dashboard Route
# ═══════════════════════════════════════════════════════════════


class TestAdminRoute:
    def test_admin_returns_200(self, client):
        response = client.get("/admin/")
        assert response.status_code == 200

    def test_admin_contains_dashboard_title(self, client):
        response = client.get("/admin/")
        html = response.data.decode("utf-8")
        assert "Analytics Dashboard" in html

    def test_admin_loads_chartjs(self, client):
        response = client.get("/admin/")
        html = response.data.decode("utf-8")
        assert "chart.umd.min.js" in html

    def test_admin_loads_admin_js(self, client):
        response = client.get("/admin/")
        html = response.data.decode("utf-8")
        assert "admin.js" in html

    def test_admin_has_link_to_chat(self, client):
        response = client.get("/admin/")
        html = response.data.decode("utf-8")
        assert "Chat Interface" in html


# ═══════════════════════════════════════════════════════════════
# TEST: Session Manager
# ═══════════════════════════════════════════════════════════════


class TestSessionManager:
    def test_returns_uuid_string(self, session_mgr):
        sid = session_mgr.get_session_id()
        assert isinstance(sid, str)
        assert len(sid) == 36  # UUID format: 8-4-4-4-12

    def test_returns_same_id_within_interval(self, session_mgr):
        id1 = session_mgr.get_session_id()
        id2 = session_mgr.get_session_id()
        assert id1 == id2

    def test_reset_generates_new_id(self, session_mgr):
        id1 = session_mgr.get_session_id()
        id2 = session_mgr.reset()
        assert id1 != id2

    def test_rotates_after_interval(self):
        mgr = SessionManager(rotate_seconds=0)  # Rotate immediately
        id1 = mgr.get_session_id()
        import time
        time.sleep(0.01)
        id2 = mgr.get_session_id()
        assert id1 != id2


# ═══════════════════════════════════════════════════════════════
# TEST: Chat API Proxy
# ═══════════════════════════════════════════════════════════════


class TestChatAPI:
    def test_empty_query_returns_400(self, client):
        response = client.post(
            "/api/chat",
            data=json.dumps({"query": ""}),
            content_type="application/json",
        )
        assert response.status_code == 400
        data = response.get_json()
        assert "introduceți" in data["answer"]

    def test_missing_body_returns_400(self, client):
        response = client.post("/api/chat", content_type="application/json")
        assert response.status_code == 400

    def test_too_long_query_returns_400(self, client):
        response = client.post(
            "/api/chat",
            data=json.dumps({"query": "x" * 501}),
            content_type="application/json",
        )
        assert response.status_code == 400
        data = response.get_json()
        assert "lungă" in data["answer"]

    @patch("app.routes.api.N8nClient")
    def test_successful_chat_proxy(self, MockClient, client):
        """Test that a valid query is proxied to n8n and response returned."""
        mock_instance = MagicMock()
        mock_instance.send_query.return_value = {
            "answer": "Calendarul academic începe pe 1 octombrie.",
            "sources": ["calendar.pdf"],
            "confidence": 0.89,
        }
        MockClient.return_value = mock_instance

        response = client.post(
            "/api/chat",
            data=json.dumps({"query": "Care este calendarul?"}),
            content_type="application/json",
        )
        assert response.status_code == 200
        data = response.get_json()
        assert "octombrie" in data["answer"]
        assert data["sources"] == ["calendar.pdf"]
        assert data["confidence"] == 0.89

    @patch("app.routes.api.N8nClient")
    def test_n8n_timeout_returns_error(self, MockClient, client):
        """Test graceful handling of n8n timeout."""
        mock_instance = MagicMock()
        mock_instance.send_query.side_effect = N8nClientError("Timeout", 504)
        MockClient.return_value = mock_instance

        response = client.post(
            "/api/chat",
            data=json.dumps({"query": "Test question"}),
            content_type="application/json",
        )
        assert response.status_code == 504
        data = response.get_json()
        assert data["error"] is True

    @patch("app.routes.api.N8nClient")
    def test_n8n_connection_error(self, MockClient, client):
        """Test graceful handling of n8n being unreachable."""
        mock_instance = MagicMock()
        mock_instance.send_query.side_effect = N8nClientError("Connection refused", 503)
        MockClient.return_value = mock_instance

        response = client.post(
            "/api/chat",
            data=json.dumps({"query": "Test question"}),
            content_type="application/json",
        )
        assert response.status_code == 503


# ═══════════════════════════════════════════════════════════════
# TEST: Session Reset API
# ═══════════════════════════════════════════════════════════════


class TestSessionResetAPI:
    def test_reset_returns_new_session_id(self, client):
        response = client.post("/api/session/reset")
        assert response.status_code == 200
        data = response.get_json()
        assert data["status"] == "reset"
        assert len(data["session_id"]) == 36


# ═══════════════════════════════════════════════════════════════
# TEST: Analytics API Proxy
# ═══════════════════════════════════════════════════════════════


class TestAnalyticsAPI:
    @patch("app.routes.api.N8nClient")
    def test_analytics_summary(self, MockClient, client):
        mock_instance = MagicMock()
        mock_instance.get_analytics_summary.return_value = {"queries_7d": 150}
        MockClient.return_value = mock_instance

        response = client.get("/api/analytics/summary")
        assert response.status_code == 200

    @patch("app.routes.api.N8nClient")
    def test_analytics_daily(self, MockClient, client):
        mock_instance = MagicMock()
        mock_instance.get_analytics_daily.return_value = [{"day": "2026-03-27", "total_queries": 42}]
        MockClient.return_value = mock_instance

        response = client.get("/api/analytics/daily")
        assert response.status_code == 200

    @patch("app.routes.api.N8nClient")
    def test_analytics_categories(self, MockClient, client):
        mock_instance = MagicMock()
        mock_instance.get_analytics_categories.return_value = [{"category": "ACADEMIC", "count": 100}]
        MockClient.return_value = mock_instance

        response = client.get("/api/analytics/categories")
        assert response.status_code == 200

    @patch("app.routes.api.N8nClient")
    def test_analytics_documents(self, MockClient, client):
        mock_instance = MagicMock()
        mock_instance.get_analytics_documents.return_value = [{"document_name": "calendar.pdf"}]
        MockClient.return_value = mock_instance

        response = client.get("/api/analytics/documents")
        assert response.status_code == 200

    @patch("app.routes.api.N8nClient")
    def test_analytics_hourly(self, MockClient, client):
        mock_instance = MagicMock()
        mock_instance.get_analytics_hourly.return_value = [{"hour_of_day": 14, "query_count": 25}]
        MockClient.return_value = mock_instance

        response = client.get("/api/analytics/hourly")
        assert response.status_code == 200

    @patch("app.routes.api.N8nClient")
    def test_analytics_error_handling(self, MockClient, client):
        mock_instance = MagicMock()
        mock_instance.get_analytics_summary.side_effect = N8nClientError("Unavailable", 503)
        MockClient.return_value = mock_instance

        response = client.get("/api/analytics/summary")
        assert response.status_code == 503


# ═══════════════════════════════════════════════════════════════
# TEST: N8nClient
# ═══════════════════════════════════════════════════════════════


class TestN8nClient:
    def test_url_construction(self):
        c = N8nClient("http://n8n:5678")
        assert c._url("/webhook/chat") == "http://n8n:5678/webhook/chat"

    def test_trailing_slash_stripped(self):
        c = N8nClient("http://n8n:5678/")
        assert c._url("/webhook/chat") == "http://n8n:5678/webhook/chat"

    @patch("app.services.n8n_client.requests.Session.post")
    def test_send_query_success(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"answer": "Test answer", "sources": []}
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        c = N8nClient("http://n8n:5678")
        result = c.send_query("test", "session-123")
        assert result["answer"] == "Test answer"
        mock_post.assert_called_once()

    @patch("app.services.n8n_client.requests.Session.post")
    def test_send_query_timeout(self, mock_post):
        import requests
        mock_post.side_effect = requests.exceptions.Timeout()

        c = N8nClient("http://n8n:5678", timeout=1)
        with pytest.raises(N8nClientError) as exc_info:
            c.send_query("test", "session-123")
        assert exc_info.value.status_code == 504

    @patch("app.services.n8n_client.requests.Session.post")
    def test_send_query_connection_error(self, mock_post):
        import requests
        mock_post.side_effect = requests.exceptions.ConnectionError()

        c = N8nClient("http://n8n:5678")
        with pytest.raises(N8nClientError) as exc_info:
            c.send_query("test", "session-123")
        assert exc_info.value.status_code == 503


# ═══════════════════════════════════════════════════════════════
# TEST: Static Files Accessible
# ═══════════════════════════════════════════════════════════════


class TestStaticFiles:
    def test_chat_css_accessible(self, client):
        response = client.get("/static/css/chat.css")
        assert response.status_code == 200
        assert b"ulbs-navy" in response.data

    def test_chat_js_accessible(self, client):
        response = client.get("/static/js/chat.js")
        assert response.status_code == 200
        assert b"/api/chat" in response.data

    def test_admin_js_accessible(self, client):
        response = client.get("/static/js/admin.js")
        assert response.status_code == 200
        assert b"/api/analytics" in response.data
