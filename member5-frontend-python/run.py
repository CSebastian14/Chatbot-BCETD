"""
BCETD Flask Application — Entry Point.

Usage:
  Development:  python run.py
  Production:   gunicorn -w 4 -b 0.0.0.0:3000 "run:app"
"""

from app import create_app

app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=3000, debug=app.config.get("DEBUG", False))
