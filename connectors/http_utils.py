"""Cliente HTTP resiliente compartilhado (retry exponencial com jitter + logs)."""
from __future__ import annotations

import logging
from typing import Any

import httpx
from tenacity import (
    RetryCallState,
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential_jitter,
)

from config import USER_AGENT, settings

log = logging.getLogger("http")

RETRY_STATUS = {408, 425, 429, 500, 502, 503, 504}


class RetryableHTTPError(Exception):
    def __init__(self, status: int, url: str, body: str = "") -> None:
        super().__init__(f"HTTP {status} em {url} :: {body[:200]}")
        self.status = status
        self.url = url


def _is_retryable(exc: BaseException) -> bool:
    return isinstance(exc, (RetryableHTTPError, httpx.TransportError, httpx.TimeoutException))


def _before_sleep(state: RetryCallState) -> None:
    exc = state.outcome.exception() if state.outcome else None
    log.warning("Tentativa %s falhou (%s). Novo retry em %.1fs",
                state.attempt_number, type(exc).__name__ if exc else "?", state.next_action.sleep if state.next_action else 0)


def build_client(base_url: str = "", cookies: dict[str, str] | None = None,
                 headers: dict[str, str] | None = None) -> httpx.Client:
    h = {"User-Agent": USER_AGENT, "Accept": "application/json, text/plain, */*"}
    h.update(headers or {})
    return httpx.Client(base_url=base_url, cookies=cookies, headers=h, timeout=settings.http_timeout,
                        follow_redirects=True, verify=True)


def request(client: httpx.Client, method: str, url: str, *, accept_status: set[int] | None = None,
            **kwargs: Any) -> httpx.Response:
    """Executa requisição com retry/backoff exponencial para erros transitórios."""
    accept = accept_status or {200, 204}

    @retry(reraise=True, stop=stop_after_attempt(settings.http_max_retries),
           wait=wait_exponential_jitter(initial=1.5, max=45, jitter=2),
           retry=retry_if_exception(_is_retryable), before_sleep=_before_sleep)
    def _do() -> httpx.Response:
        resp = client.request(method, url, **kwargs)
        if resp.status_code in RETRY_STATUS:
            raise RetryableHTTPError(resp.status_code, str(resp.url), resp.text)
        if resp.status_code not in accept:
            resp.raise_for_status()
        log.debug("%s %s -> %s (%d bytes)", method, resp.url, resp.status_code, len(resp.content))
        return resp

    return _do()
