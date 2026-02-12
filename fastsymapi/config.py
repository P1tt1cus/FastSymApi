"""Application configuration loaded from environment variables.

Single Responsibility: This module is solely responsible for defining
and loading configuration values used across the application.
"""

import os

CHUNK_SIZE = int(os.environ.get("FASTSYM_CHUNK_SIZE", 1024 * 1024 * 2))
MAX_RETRY_ATTEMPTS = int(os.environ.get("FASTSYM_MAX_RETRIES", 3))
RETRY_BACKOFF_FACTOR = float(os.environ.get("FASTSYM_RETRY_BACKOFF", 0.3))
MAX_MEMORY_USAGE = int(os.environ.get("FASTSYM_MAX_MEMORY_MB", 100)) * 1024 * 1024

SYMBOL_PATH = os.path.join(os.path.dirname(__file__), "symbols")

SYM_URLS = [
    "http://msdl.microsoft.com/download/symbols",
    "http://chromium-browser-symsrv.commondatastorage.googleapis.com",
    "http://symbols.mozilla.org",
    "http://symbols.mozilla.org/try",
]
