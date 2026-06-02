"""
API Proxy Routes — Browser ↔ Flask ↔ n8n.

DESIGN:
  1. Normalize n8n responses into a stable contract for the browser.
  2. Errors are returned with HTTP 200 + `error: true` so the chat UI
     renders them inline (no browser-level fetch failures).
  3. /api/health is a diagnostic endpoint.
  4. EVERY endpoint wraps logic in try/except so a bug never produces 500.
     Full tracebacks are logged via `logger.exception()` for debugging.

Frontend contract returned by /api/chat:
  {
    "answer":    str,
    "sources":   list[{label, url, type}],
    "used_tool": bool,
    "rejected":  bool,
    "fallback":  bool,
    "error":     bool
  }
"""

import logging
import re
import traceback

from flask import Blueprint, request, jsonify, current_app

from app.services.n8n_client import N8nClient, N8nClientError
from app.services.session_manager import session_manager

logger = logging.getLogger(__name__)
api_bp = Blueprint("api", __name__)


# ─────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────

def _get_client():
    return N8nClient(
        base_url=current_app.config["N8N_BASE_URL"],
        timeout=current_app.config.get("N8N_TIMEOUT", 30),
        retries=1,
    )


_SOURCE_LINE_RE = re.compile(
    r"\U0001F4C4\s*\*{0,2}\s*Surs[aăe]?\s*\*{0,2}\s*:?\s*(.+?)(?:\n|$)",
    re.IGNORECASE,
)
_MARKDOWN_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")


def _extract_sources_from_text(text):
    """Extract sources from raw markdown. Returns (clean_text, sources)."""
    if not isinstance(text, str):
        return "", []

    sources = []
    seen = set()

    try:
        for match in _SOURCE_LINE_RE.finditer(text):
            line_content = (match.group(1) or "").strip()

            links = _MARKDOWN_LINK_RE.findall(line_content)
            if links:
                for label, url in links:
                    url = (url or "").strip()
                    label = (label or "").strip() or "Sursă oficială"
                    if url and url not in seen:
                        seen.add(url)
                        sources.append({"label": label, "url": url, "type": "link"})
            else:
                items = [
                    s.replace("*", "").strip()
                    for s in re.split(r"[,;]", line_content)
                ]
                for item in items:
                    if not item or len(item) < 3 or item in seen:
                        continue
                    seen.add(item)
                    if item.startswith(("http://", "https://")):
                        sources.append({"label": "Pagină oficială", "url": item, "type": "link"})
                    else:
                        sources.append({"label": item, "url": None, "type": "file"})

        clean_text = _SOURCE_LINE_RE.sub("", text).strip()
        clean_text = re.sub(r"\n{3,}", "\n\n", clean_text)
        return clean_text, sources

    except Exception:
        logger.exception("Failed to extract sources from text — returning text unchanged")
        return text, []


def _normalize_sources(raw_sources):
    """Coerce whatever n8n sent into list[{label, url, type}]."""
    if not raw_sources:
        return []
    if isinstance(raw_sources, str):
        raw_sources = [raw_sources]
    if not isinstance(raw_sources, list):
        return []

    normalized = []
    seen = set()
    for item in raw_sources:
        try:
            if isinstance(item, dict):
                label = str(item.get("label") or "").strip()
                url = str(item.get("url") or "").strip() or None
                stype = item.get("type") or ("link" if url else "file")
                key = url or label
                if key and key not in seen:
                    seen.add(key)
                    normalized.append({"label": label or "Sursă", "url": url, "type": stype})
            elif isinstance(item, str):
                s = item.strip()
                if not s or s in seen:
                    continue
                seen.add(s)
                if s.startswith(("http://", "https://")):
                    normalized.append({"label": "Pagină oficială", "url": s, "type": "link"})
                else:
                    normalized.append({"label": s, "url": None, "type": "file"})
        except Exception:
            logger.exception(f"Skipping malformed source item: {item!r}")
            continue
    return normalized


def _unwrap_n8n_payload(raw):
    """n8n may return a single object or a list — pick the chat response."""
    if isinstance(raw, list):
        for item in raw:
            if isinstance(item, dict) and ("answer" in item or "output" in item):
                return item
        if raw and isinstance(raw[0], dict):
            return raw[0]
        return {}
    if isinstance(raw, dict):
        return raw
    return {}


def _normalize_response(raw):
    """Shape n8n's response into the stable frontend contract. Never raises."""
    try:
        payload = _unwrap_n8n_payload(raw)
        if not isinstance(payload, dict):
            payload = {}

        answer_raw = payload.get("answer") or payload.get("output") or ""
        answer = str(answer_raw).strip() if answer_raw else ""

        raw_sources = payload.get("sources")

        if not raw_sources and answer:
            answer, parsed = _extract_sources_from_text(answer)
            sources = parsed
        else:
            sources = _normalize_sources(raw_sources)
            if answer and "\U0001F4C4" in answer:
                answer, _unused = _extract_sources_from_text(answer)

        if not answer:
            answer = "Nu am primit un răspuns. Vă rugăm reformulați întrebarea."

        used_tool = payload.get("used_tool")
        if used_tool is None:
            used_tool = len(sources) > 0

        return {
            "answer": answer,
            "sources": sources,
            "used_tool": bool(used_tool),
            "rejected": bool(payload.get("rejected", False)),
            "fallback": bool(payload.get("fallback", False)),
            "error": False,
        }

    except Exception:
        logger.exception(f"Normalization failed for n8n payload: {raw!r}")
        # Return whatever string we can extract, plus the error flag
        fallback_answer = "Răspunsul de la server nu a putut fi procesat corect."
        if isinstance(raw, dict):
            for key in ("answer", "output", "text", "message"):
                val = raw.get(key)
                if isinstance(val, str) and val.strip():
                    fallback_answer = val.strip()
                    break
        return {
            "answer": fallback_answer,
            "sources": [],
            "used_tool": False,
            "rejected": False,
            "fallback": True,
            "error": True,
        }


def _error_response(message, status=200):
    """Friendly inline-renderable error."""
    return jsonify({
        "answer": message,
        "sources": [],
        "used_tool": False,
        "rejected": False,
        "fallback": False,
        "error": True,
    }), status


# ─────────────────────────────────────────────────────────────────────
# Health check
# ─────────────────────────────────────────────────────────────────────

@api_bp.route("/health", methods=["GET"])
def api_health():
    try:
        client = _get_client()
        ok, info = client.ping()
        return jsonify({
            "flask": "ok",
            "n8n_reachable": ok,
            "n8n_info": info,
            "n8n_base_url_config": current_app.config["N8N_BASE_URL"],
        }), 200 if ok else 503
    except Exception:
        logger.exception("Health check crashed")
        return jsonify({"flask": "error", "n8n_reachable": False}), 500


# ─────────────────────────────────────────────────────────────────────
# Chat endpoint — bulletproof: never returns 500
# ─────────────────────────────────────────────────────────────────────

@api_bp.route("/chat", methods=["POST"])
def chat():
    try:
        data = request.get_json(silent=True) or {}
        query = (data.get("query") or "").strip()
        max_len = current_app.config.get("MAX_QUERY_LENGTH", 500)

        if not query:
            return _error_response("Vă rog să introduceți o întrebare.", 400)
        if len(query) > max_len:
            return _error_response(
                f"Întrebarea este prea lungă (maximum {max_len} caractere).", 400,
            )

        sid = session_manager.get_session_id()

        try:
            client = _get_client()
            raw = client.send_query(query=query, session_id=sid)
        except N8nClientError as e:
            logger.warning(
                f"n8n call failed: {e} | url={e.attempted_url} | code={e.status_code}"
            )
            return _error_response(str(e), 200)

        # Log what n8n actually returned (helps debug response-shape issues)
        logger.info(f"n8n raw response type={type(raw).__name__}")
        if isinstance(raw, (dict, list)):
            try:
                preview = str(raw)[:500]
                logger.info(f"n8n raw preview: {preview}")
            except Exception:
                pass

        normalized = _normalize_response(raw)
        return jsonify(normalized), 200

    except Exception as e:
        # Last-resort safety net — log full traceback, return friendly error
        logger.exception(f"Unhandled error in /api/chat: {e}")
        return _error_response(
            "A apărut o eroare la procesarea cererii. Vă rugăm încercați din nou.",
            200,
        )


@api_bp.route("/session/reset", methods=["POST"])
def reset_session():
    try:
        new_id = session_manager.reset()
        return jsonify({"session_id": new_id, "status": "reset"}), 200
    except Exception:
        logger.exception("Session reset failed")
        return jsonify({"status": "error"}), 200


# ─────────────────────────────────────────────────────────────────────
# Analytics endpoints — DRY pattern
# ─────────────────────────────────────────────────────────────────────

def _analytics_proxy(method_name):
    try:
        client = _get_client()
        return jsonify(getattr(client, method_name)()), 200
    except N8nClientError as e:
        logger.warning(f"Analytics {method_name} failed: {e}")
        return jsonify({"error": str(e)}), 200
    except Exception:
        logger.exception(f"Unhandled error in analytics: {method_name}")
        return jsonify({"error": "internal"}), 200


@api_bp.route("/analytics/summary")
def analytics_summary():
    return _analytics_proxy("get_analytics_summary")


@api_bp.route("/analytics/daily")
def analytics_daily():
    return _analytics_proxy("get_analytics_daily")


@api_bp.route("/analytics/categories")
def analytics_categories():
    return _analytics_proxy("get_analytics_categories")


@api_bp.route("/analytics/documents")
def analytics_documents():
    return _analytics_proxy("get_analytics_documents")


@api_bp.route("/analytics/hourly")
def analytics_hourly():
    return _analytics_proxy("get_analytics_hourly")