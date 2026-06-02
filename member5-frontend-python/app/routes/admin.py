"""
Admin Routes — Analytics dashboard for administrators.
Replaces the static admin.html with a Flask-rendered template.

PASSWORD SETUP:
  Set the ADMIN_PASSWORD environment variable (default: admin1234).
  The hash is computed at startup and passed to the template.
  For proper security, consider adding a server-side session check.
"""

import os
from flask import Blueprint, render_template

admin_bp = Blueprint("admin", __name__)


def _djb2_hash(s: str) -> str:
    """Same djb2-style hash used in the browser JS — keeps client/server in sync."""
    h = 5381
    for ch in s:
        h = ((h << 5) + h) ^ ord(ch)
        h &= 0xFFFFFFFF
    return format(h, "x")


# Compute once at import time — read from env, fallback to dev default
_ADMIN_PW_HASH = _djb2_hash(os.environ.get("ADMIN_PASSWORD", "admin1234"))


@admin_bp.route("/")
def dashboard():
    """Render the admin analytics dashboard."""
    return render_template("admin.html", admin_pw_hash=_ADMIN_PW_HASH)
