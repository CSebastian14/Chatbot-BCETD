"""
Chat Routes — Student-facing chatbot interface.
Replaces the static index.html with a Flask-rendered template.
"""
import os
from flask import Blueprint, render_template, send_from_directory, abort

chat_bp = Blueprint("chat", __name__)


# ── Suggested questions for the welcome screen ──
SUGGESTIONS = [
    "Care este calendarul academic?",
    "Cum mă pot înscrie la master?",
    "Care sunt taxele de școlarizare?",
    "Unde găsesc regulamentul de licență?",
    "What are the library hours?",
    "How do I apply for a scholarship?",
]


@chat_bp.route("/")
def index():
    """Render the student chat interface."""
    return render_template("chat.html", suggestions=SUGGESTIONS)


@chat_bp.route("/documents/<path:filename>")
def serve_document(filename):
    """Serve documents from data/documents/ folder."""
    documents_dir = "/app/data/documents"
    
    # Securitate: blochează path traversal
    requested_path = os.path.abspath(os.path.join(documents_dir, filename))
    if not requested_path.startswith(documents_dir):
        abort(403)
    
    if not os.path.exists(requested_path):
        abort(404)
    
    return send_from_directory(documents_dir, filename, as_attachment=False)