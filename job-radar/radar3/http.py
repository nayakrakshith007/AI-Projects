"""One polite HTTP client for every reader: at most one request per host per second, a few retries, honest User-Agent.
Readers take an object with get_json / get_text / post_json, so tests can pass a fake that returns saved samples."""
import threading
import time
from urllib.parse import urlparse

import requests

from . import config


class Http:
    def __init__(self, min_interval: float = config.MIN_SECONDS_PER_HOST) -> None:
        self.min_interval = min_interval
        self._locks: dict[str, threading.Lock] = {}
        self._last: dict[str, float] = {}
        self._guard = threading.Lock()
        self._local = threading.local()

    def _session(self) -> requests.Session:
        if not hasattr(self._local, "s"):
            self._local.s = requests.Session()
            self._local.s.headers.update({"User-Agent": config.USER_AGENT, "Accept-Language": "en"})
        return self._local.s

    def _wait(self, host: str) -> None:
        with self._guard:
            lock = self._locks.setdefault(host, threading.Lock())
        with lock:
            gap = self.min_interval - (time.monotonic() - self._last.get(host, 0.0))
            if gap > 0:
                time.sleep(gap)
            self._last[host] = time.monotonic()

    def request(self, method: str, url: str, **kw) -> requests.Response:
        host = urlparse(url).netloc
        last: Exception | None = None
        for attempt in range(config.HTTP_RETRIES + 1):
            self._wait(host)
            try:
                r = self._session().request(method, url, timeout=config.HTTP_TIMEOUT, **kw)
                if r.status_code in (429, 500, 502, 503, 504) and attempt < config.HTTP_RETRIES:
                    time.sleep(2 * (attempt + 1))
                    continue
                r.raise_for_status()
                return r
            except requests.RequestException as e:
                last = e
                if attempt < config.HTTP_RETRIES and not (isinstance(e, requests.HTTPError) and e.response is not None and e.response.status_code < 500 and e.response.status_code != 429):
                    time.sleep(2 * (attempt + 1))
                    continue
                raise
        raise last or RuntimeError("request failed")

    def get_json(self, url: str, **kw):
        return self.request("GET", url, **kw).json()

    def get_text(self, url: str, **kw) -> str:
        return self.request("GET", url, **kw).text

    def post_json(self, url: str, payload: dict, **kw):
        return self.request("POST", url, json=payload, **kw).json()

    def post_form(self, url: str, data: dict, **kw):
        return self.request("POST", url, data=data, **kw).json()
