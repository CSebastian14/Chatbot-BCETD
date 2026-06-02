"""
n8n Webhook Client.

Handles all HTTP communication with the n8n workflow engine.
The browser never talks to n8n directly — Flask proxies everything.

Features:
  - Verbose, actionable error messages (URL is logged + included on exception)
  - Single retry on transient connection errors
  - Centralized endpoint catalog (no string duplication)
  - Health-check ping() for the /api/health diagnostic endpoint
"""

import logging
import time
import requests

logger = logging.getLogger(__name__)


class N8nClientError(Exception):
    """Raised when n8n communication fails."""

    def __init__(self, message, status_code=None, attempted_url=None):
        super().__init__(message)
        self.status_code = status_code
        self.attempted_url = attempted_url


class N8nClient:
    """HTTP client for n8n webhook endpoints."""

    PATHS = {
        "chat": "/webhook/chat",
        "analytics_summary": "/webhook/analytics/summary",
        "analytics_daily": "/webhook/analytics/daily",
        "analytics_categories": "/webhook/analytics/categories",
        "analytics_documents": "/webhook/analytics/documents",
        "analytics_hourly": "/webhook/analytics/hourly",
    }

    def __init__(self, base_url, timeout=30, retries=1):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.retries = max(0, retries)
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})

    def _url(self, path_key):
        return f"{self.base_url}{self.PATHS[path_key]}"

    def _request(self, method, path_key, payload=None):
        """Unified request handler with retry on connection errors."""
        url = self._url(path_key)

        for attempt in range(self.retries + 1):
            try:
                if method == "GET":
                    response = self.session.get(url, timeout=self.timeout)
                else:
                    response = self.session.post(url, json=payload, timeout=self.timeout)
                response.raise_for_status()
                return response.json()

            except requests.exceptions.Timeout:
                logger.warning(f"Timeout {attempt + 1}/{self.retries + 1}: {url}")
                if attempt < self.retries:
                    time.sleep(0.5)
                    continue
                raise N8nClientError(
                    "Conexiunea cu serverul a expirat. Vă rugăm încercați din nou.",
                    504, url,
                )

            except requests.exceptions.ConnectionError:
                logger.warning(f"Connection error {attempt + 1}/{self.retries + 1}: {url}")
                if attempt < self.retries:
                    time.sleep(0.5)
                    continue
                logger.error(
                    f"Cannot reach n8n at {url}. "
                    f"Check N8N_BASE_URL env var (currently base={self.base_url})."
                )
                raise N8nClientError(
                    "Serviciul de asistență nu este disponibil momentan. "
                    "Vă rugăm încercați peste câteva momente.",
                    503, url,
                )

            except requests.exceptions.HTTPError as e:
                code = e.response.status_code if e.response is not None else 500
                logger.error(f"n8n HTTP {code} from {url}")
                if code == 404:
                    raise N8nClientError(
                        f"Endpoint n8n inexistent: {self.PATHS[path_key]}. "
                        "Verificați dacă workflow-ul n8n este activ.",
                        404, url,
                    )
                raise N8nClientError(f"Eroare server n8n: {code}", code, url)

            except ValueError as e:
                logger.error(f"n8n returned non-JSON from {url}: {e}")
                raise N8nClientError(
                    "Răspuns invalid de la server.", 502, url,
                )

            except Exception as e:
                logger.exception(f"Unexpected error calling {url}")
                raise N8nClientError(f"Eroare neașteptată: {str(e)}", 500, url)

        raise N8nClientError("Eroare necunoscută", 500, url)

    # ── Chat API ──

    def send_query(self, query, session_id):
        """Send a student query to the n8n chat webhook."""
        return self._request("POST", "chat", {"query": query, "session_id": session_id})

    # ── Analytics API ──

    def get_analytics_summary(self):
        return self._request("GET", "analytics_summary")

    def get_analytics_daily(self):
        return self._request("GET", "analytics_daily")

    def get_analytics_categories(self):
        return self._request("GET", "analytics_categories")

    def get_analytics_documents(self):
        return self._request("GET", "analytics_documents")

    def get_analytics_hourly(self):
        return self._request("GET", "analytics_hourly")

    # ── Health check ──

    def ping(self):
        """Quick connectivity check to the n8n base URL."""
        try:
            response = self.session.get(self.base_url, timeout=5)
            return True, {"status_code": response.status_code, "url": self.base_url}
        except requests.exceptions.ConnectionError:
            return False, {"error": "connection_refused", "url": self.base_url}
        except requests.exceptions.Timeout:
            return False, {"error": "timeout", "url": self.base_url}
        except Exception as e:
            return False, {"error": str(e), "url": self.base_url}