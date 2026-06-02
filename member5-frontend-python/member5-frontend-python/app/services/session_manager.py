"""
Rotating Session Manager.
Generates a new UUID every hour for privacy-preserving session grouping.
Replaces the JavaScript sessionStorage implementation.
"""

import uuid
import time
import threading


class SessionManager:
    """Manages rotating hourly session IDs."""

    def __init__(self, rotate_seconds=3600):
        self._rotate_seconds = rotate_seconds
        self._current_id = str(uuid.uuid4())
        self._created_at = time.time()
        self._lock = threading.Lock()

    def get_session_id(self):
        """Return the current session ID, rotating if the interval has passed."""
        with self._lock:
            now = time.time()
            if now - self._created_at >= self._rotate_seconds:
                self._current_id = str(uuid.uuid4())
                self._created_at = now
            return self._current_id

    def reset(self):
        """Force a new session ID (used when user clicks 'new conversation')."""
        with self._lock:
            self._current_id = str(uuid.uuid4())
            self._created_at = time.time()
            return self._current_id


# Singleton instance
session_manager = SessionManager()
