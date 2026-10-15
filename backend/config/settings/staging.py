"""Staging: production hardening with sandbox provider keys and API docs for testing."""

import os

os.environ.setdefault("ENVIRONMENT", "staging")  # read by production.py (Sentry environment tag)

from .base import env  # noqa: E402
from .production import *  # noqa: E402, F403

API_DOCS_ENABLED = env.bool("API_DOCS_ENABLED", default=True)
