"""Small HTTP helper: GET with retries and a size cap, standard library only."""

from __future__ import annotations

import time
import urllib.error
import urllib.request

from . import config

RETRY_STATUS = {429, 500, 502, 503, 504}


def get(url: str, *, timeout: float = 30, retries: int = 3, max_bytes: int = 5_000_000) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": config.USER_AGENT})
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.read(max_bytes)
        except urllib.error.HTTPError as error:
            if error.code not in RETRY_STATUS or attempt == retries - 1:
                raise
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            if attempt == retries - 1:
                raise
        time.sleep(3 * (attempt + 1))
    raise AssertionError("unreachable")
