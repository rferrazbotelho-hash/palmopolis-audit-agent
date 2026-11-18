"""Captura automática de sessão/URL base do SPA iLAI (Memory) via Playwright.

O portal iLAI é um SPA CronApp/AngularJS. Ao acessar a URL de login da entidade, o
frontend grava cookies de contexto (codigo_auxiliar, codigo_entidade, exercicio,
codigo_ibge...) que o backend OData (``/api/cronapi/odata/v2/app/queryNNNNNN``) usa
para filtrar a entidade/exercício. Este módulo:

1. abre a URL de login em Chromium headless;
2. intercepta o tráfego XHR para capturar a URL base da API REST
   (``Util:returnApiUrl``), os cookies e os IDs de consulta OData de cada tela;
3. persiste a sessão em ``data/raw/memory/session.json``.

Caso o Playwright não esteja disponível, há fallback determinístico baseado nos
parâmetros públicos da entidade (os cookies são definidos pelo próprio cliente).
"""
from __future__ import annotations

import logging
import re
from typing import Any
from urllib.parse import parse_qs, urlparse

from pydantic import BaseModel, Field

from config import save_raw, settings

log = logging.getLogger("memory.auth")

# Telas do SPA visitadas para auto-descoberta dos IDs de consulta OData
DISCOVERY_ROUTES: list[str] = [
    "licitacoes/edital", "licitacoes/licitacao", "licitacoes/contratos", "licitacoes/naf",
    "licitacoes/fiscaiscontrato", "execucaodespesa/despesaempenho", "execucaodespesa/despesaliquidacao",
    "execucaodespesa/despesapagamento", "execucaodespesa/despesaextra", "execucaodespesa/despesaunidadeorc",
    "execucaodespesa/despesafuncao", "execucaodespesa/despesanatureza", "fornecedores/fornecedores",
    "fornecedores/restosapagar", "execucaoreceita/receita", "repasse/repasserecebido", "pessoal/servidor",
    "pessoal/diarias", "obras/obraspublicas", "home/convenios", "pessoal/terceirizados",
]


class MemorySession(BaseModel):
    base_url: str
    odata_base: str
    api_url: str | None = None
    cookies: dict[str, str]
    discovered_queries: dict[str, str] = Field(default_factory=dict)  # entidade OData -> queryID
    entidade: dict[str, Any] | None = None
    source: str = "fallback"

    def cookies_for(self, exercicio: int) -> dict[str, str]:
        c = dict(self.cookies)
        c["exercicio"] = str(exercicio)
        return c


def fallback_session() -> MemorySession:
    base = settings.memory_base_url.rstrip("/")
    return MemorySession(
        base_url=base,
        odata_base=f"{base}/api/cronapi/odata/v2/app/",
        cookies={
            "codigo_auxiliar": settings.memory_cod_cliente,
            "codigo_entidade": settings.memory_unidade,
            "codigo_entidade_p": settings.memory_unidade,
            "codigo_ibge": settings.audit_codigo_ibge,
        },
        source="fallback",
    )


def capture_session(discover: bool = True, headless: bool = True, timeout_ms: int = 90_000) -> MemorySession:
    """Abre o SPA, captura cookies/URL da API e (opcionalmente) descobre IDs de consulta."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        log.warning("Playwright não instalado - usando sessão fallback.")
        return fallback_session()

    sess = fallback_session()
    discovered: dict[str, str] = {}
    api_url: dict[str, str] = {}
    entidades: list[Any] = []

    def on_response(resp: Any) -> None:
        url = resp.url
        try:
            if "Util:returnApiUrl" in url:
                api_url["v"] = resp.json()
            elif url.endswith("/lai/portal/entidades"):
                entidades.extend(resp.json())
            m = re.search(r"/odata/v2/app/(query\d+)", url)
            if m and resp.status == 200:
                body = resp.text()
                ent = re.search(r'"type"\s*:\s*"app\.(\w+)"', body)
                if ent:
                    discovered[ent.group(1)] = m.group(1)
                    log.debug("Descoberto %s -> %s (%s)", ent.group(1), m.group(1),
                              {k: v for k, v in parse_qs(urlparse(url).query).items() if not k.startswith("$")})
        except Exception as exc:  # pragma: no cover - captura defensiva
            log.debug("Falha ao inspecionar %s: %s", url, exc)

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=headless)
            ctx = browser.new_context(locale="pt-BR")
            page = ctx.new_page()
            page.on("response", on_response)
            log.info("Abrindo SPA Memory: %s", settings.memory_login_url)
            page.goto(settings.memory_login_url, wait_until="networkidle", timeout=timeout_ms)
            page.wait_for_timeout(4000)
            log.info("SPA redirecionou para %s", page.url)
            if discover:
                for route in DISCOVERY_ROUTES:
                    try:
                        page.goto(f"{sess.base_url}/#/public/{route}", wait_until="networkidle", timeout=timeout_ms)
                        page.wait_for_timeout(2500)
                    except Exception as exc:
                        log.warning("Rota %s não carregou: %s", route, exc)
            cookies = {c["name"]: c["value"] for c in ctx.cookies() if "memory.com.br" in c.get("domain", "")}
            browser.close()
    except Exception as exc:
        log.error("Playwright falhou (%s) - usando sessão fallback.", exc)
        return fallback_session()

    cookies.pop("exercicio", None)
    if cookies.get("codigo_auxiliar"):
        sess.cookies.update(cookies)
    sess.api_url = api_url.get("v")
    sess.discovered_queries = discovered
    ent = next((e for e in entidades if e.get("codigo_auxiliar") == settings.memory_cod_cliente), None)
    sess.entidade = ent
    sess.source = "playwright"
    save_raw("memory", "session", sess.model_dump(), {"login_url": settings.memory_login_url})
    log.info("Sessão capturada: api_url=%s, cookies=%s, %d consultas descobertas",
             sess.api_url, list(sess.cookies), len(discovered))
    return sess
