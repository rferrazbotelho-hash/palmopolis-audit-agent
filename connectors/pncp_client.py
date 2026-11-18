"""Extrator do Portal Nacional de Contratações Públicas (PNCP).

Coleta, para o CNPJ auditado e exercícios informados:
- Contratações (compras/editais/avisos) por modalidade - API de Consulta;
- Arquivos (documentos) e itens de cada contratação - API PNCP;
- Atas de Registro de Preços e Contratos - API de Consulta;
- Índice de busca do PNCP (editais/atas/contratos) como verificação cruzada.

Todos os payloads brutos são salvos em data/raw/pncp/.
"""
from __future__ import annotations

import logging
import threading
import time
from datetime import date
from typing import Any

import httpx

from config import save_raw, settings
from connectors.http_utils import build_client, request
from connectors.memory_lai_client import ExtractionStatus

log = logging.getLogger("pncp")

# Tabela de domínio "Modalidade de Contratação" (Manual PNCP / Lei 14.133)
MODALIDADES: dict[int, str] = {
    1: "Leilão - Eletrônico", 2: "Diálogo Competitivo", 3: "Concurso", 4: "Concorrência - Eletrônica",
    5: "Concorrência - Presencial", 6: "Pregão - Eletrônico", 7: "Pregão - Presencial",
    8: "Dispensa de Licitação", 9: "Inexigibilidade", 10: "Manifestação de Interesse",
    11: "Pré-qualificação", 12: "Credenciamento", 13: "Leilão - Presencial",
}


class _Throttle:
    """Limita a taxa de requisições ao PNCP (que responde 429 em rajadas)."""

    def __init__(self, min_interval: float = 0.7) -> None:
        self.min_interval = min_interval
        self._last = 0.0
        self._lock = threading.Lock()

    def wait(self) -> None:
        with self._lock:
            delta = time.monotonic() - self._last
            if delta < self.min_interval:
                time.sleep(self.min_interval - delta)
            self._last = time.monotonic()


class PNCPClient:
    def __init__(self, cnpj: str | None = None, raw_source: str = "pncp") -> None:
        self.cnpj = cnpj or settings.audit_cnpj
        self.raw_source = raw_source
        self.base = settings.pncp_base_url.rstrip("/")
        self.page_size = settings.pncp_page_size
        self.throttle = _Throttle()
        self.client: httpx.Client = build_client()
        self.statuses: list[ExtractionStatus] = []

    # ------------------------------------------------------------------ utils
    def _get(self, path: str, params: dict[str, Any] | None = None, accept: set[int] | None = None) -> httpx.Response:
        self.throttle.wait()
        url = path if path.startswith("http") else f"{self.base}{path}"
        return request(self.client, "GET", url, params=params, accept_status=accept or {200, 204})

    @staticmethod
    def _json(resp: httpx.Response) -> Any:
        if resp.status_code == 204 or not resp.content:
            return None
        try:
            return resp.json()
        except ValueError:
            return None

    def _period(self, ano: int) -> tuple[str, str]:
        fim = min(date(ano, 12, 31), date.today())
        return f"{ano}0101", fim.strftime("%Y%m%d")

    def _status(self, dataset: str, ano: int | None, n: int, st: str, detalhe: str = "", raw: str = "") -> None:
        self.statuses.append(ExtractionStatus(fonte="PNCP", dataset=dataset, exercicio=ano, registros=n,
                                              status=st, detalhe=detalhe, arquivo_raw=raw))

    def _paginate_consulta(self, path: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        pagina = 1
        while True:
            resp = self._get(path, {**params, "pagina": pagina, "tamanhoPagina": self.page_size})
            data = self._json(resp)
            if not data or not data.get("data"):
                break
            out.extend(data["data"])
            total_pag = int(data.get("totalPaginas") or 1)
            if pagina >= total_pag:
                break
            pagina += 1
        return out

    # ------------------------------------------------------------- endpoints
    def orgao(self) -> dict[str, Any] | None:
        try:
            data = self._json(self._get(f"/pncp/v1/orgaos/{self.cnpj}"))
            raw = save_raw(self.raw_source, "orgao", data)
            self._status("orgao", None, 1 if data else 0, "OK" if data else "VAZIO", raw=str(raw))
            return data
        except Exception as exc:
            log.error("Falha ao consultar órgão: %s", exc)
            self._status("orgao", None, 0, "ERRO", str(exc))
            return None

    def contratacoes(self, ano: int) -> list[dict[str, Any]]:
        di, df = self._period(ano)
        todas: list[dict[str, Any]] = []
        for cod, nome in MODALIDADES.items():
            try:
                regs = self._paginate_consulta("/consulta/v1/contratacoes/publicacao",
                                               {"dataInicial": di, "dataFinal": df,
                                                "codigoModalidadeContratacao": cod, "cnpj": self.cnpj})
                for r in regs:
                    r["_modalidade_consulta"] = cod
                todas.extend(regs)
                if regs:
                    log.info("[PNCP] contratações %s modalidade %-26s: %d", ano, nome, len(regs))
            except Exception as exc:
                log.error("[PNCP] Falha contratações %s mod %s: %s", ano, cod, exc)
                self._status(f"contratacoes_mod{cod}", ano, 0, "ERRO", str(exc)[:300])
        # Deduplicar por numeroControlePNCP
        uniq = {r.get("numeroControlePNCP") or id(r): r for r in todas}
        todas = list(uniq.values())
        raw = save_raw(self.raw_source, f"contratacoes_{ano}", todas,
                       {"endpoint": "/consulta/v1/contratacoes/publicacao", "periodo": [di, df]})
        self._status("contratacoes", ano, len(todas), "OK" if todas else "VAZIO", raw=str(raw))
        return todas

    def arquivos_e_itens(self, contratacoes: list[dict[str, Any]], ano: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        arquivos: list[dict[str, Any]] = []
        itens: list[dict[str, Any]] = []
        for c in contratacoes:
            a, s = c.get("anoCompra"), c.get("sequencialCompra")
            ctrl = c.get("numeroControlePNCP")
            if not a or not s:
                continue
            try:
                arqs = self._json(self._get(f"/pncp/v1/orgaos/{self.cnpj}/compras/{a}/{s}/arquivos", accept={200, 204, 404})) or []
                for x in arqs:
                    x["numeroControlePNCP"] = ctrl
                arquivos.extend(arqs)
            except Exception as exc:
                log.warning("[PNCP] arquivos %s/%s: %s", a, s, exc)
            if settings.pncp_fetch_itens:
                try:
                    pagina = 1
                    while True:
                        its = self._json(self._get(f"/pncp/v1/orgaos/{self.cnpj}/compras/{a}/{s}/itens",
                                                   {"pagina": pagina, "tamanhoPagina": 500}, accept={200, 204, 404})) or []
                        for x in its:
                            x["numeroControlePNCP"] = ctrl
                        itens.extend(its)
                        if len(its) < 500:
                            break
                        pagina += 1
                except Exception as exc:
                    log.warning("[PNCP] itens %s/%s: %s", a, s, exc)
        r1 = save_raw(self.raw_source, f"arquivos_{ano}", arquivos, {"endpoint": "/pncp/v1/orgaos/{cnpj}/compras/{ano}/{seq}/arquivos"})
        r2 = save_raw(self.raw_source, f"itens_{ano}", itens, {"endpoint": "/pncp/v1/orgaos/{cnpj}/compras/{ano}/{seq}/itens"})
        self._status("arquivos", ano, len(arquivos), "OK" if arquivos else "VAZIO", raw=str(r1))
        self._status("itens", ano, len(itens), "OK" if itens else "VAZIO", raw=str(r2))
        log.info("[PNCP] %s: %d arquivos, %d itens", ano, len(arquivos), len(itens))
        return arquivos, itens

    def contratos(self, ano: int) -> list[dict[str, Any]]:
        di, df = self._period(ano)
        try:
            regs = self._paginate_consulta("/consulta/v1/contratos", {"dataInicial": di, "dataFinal": df, "cnpjOrgao": self.cnpj})
            raw = save_raw(self.raw_source, f"contratos_{ano}", regs, {"endpoint": "/consulta/v1/contratos", "periodo": [di, df]})
            self._status("contratos", ano, len(regs), "OK" if regs else "VAZIO", raw=str(raw))
            log.info("[PNCP] contratos %s: %d", ano, len(regs))
            return regs
        except Exception as exc:
            log.error("[PNCP] contratos %s: %s", ano, exc)
            self._status("contratos", ano, 0, "ERRO", str(exc)[:300])
            return []

    def atas(self, ano: int) -> list[dict[str, Any]]:
        di, df = self._period(ano)
        try:
            regs = self._paginate_consulta("/consulta/v1/atas", {"dataInicial": di, "dataFinal": df, "cnpj": self.cnpj})
            raw = save_raw(self.raw_source, f"atas_{ano}", regs, {"endpoint": "/consulta/v1/atas", "periodo": [di, df]})
            self._status("atas", ano, len(regs), "OK" if regs else "VAZIO", raw=str(raw))
            log.info("[PNCP] atas %s: %d", ano, len(regs))
            return regs
        except Exception as exc:
            log.error("[PNCP] atas %s: %s", ano, exc)
            self._status("atas", ano, 0, "ERRO", str(exc)[:300])
            return []

    def busca_indice(self, termo: str = "palmopolis") -> list[dict[str, Any]]:
        """Índice de busca do PNCP (mesma base do site) - verificação cruzada de editais/atas/contratos."""
        out: list[dict[str, Any]] = []
        for tipo in ("edital", "ata", "contrato"):
            pagina = 1
            try:
                while True:
                    data = self._json(self._get("/search/", {"q": termo, "tipos_documento": tipo, "ordenacao": "-data",
                                                             "pagina": pagina, "tam_pagina": 100, "status": "todos"})) or {}
                    items = data.get("items") or []
                    out.extend(i for i in items if i.get("orgao_cnpj") == self.cnpj)
                    if len(items) < 100 or pagina * 100 >= int(data.get("total") or 0):
                        break
                    pagina += 1
            except Exception as exc:
                log.warning("[PNCP] busca %s: %s", tipo, exc)
                self._status(f"busca_{tipo}", None, 0, "ERRO", str(exc)[:300])
        raw = save_raw(self.raw_source, "busca_indice", out, {"endpoint": "/search/", "termo": termo})
        self._status("busca_indice", None, len(out), "OK" if out else "VAZIO", raw=str(raw))
        log.info("[PNCP] índice de busca: %d documentos do órgão", len(out))
        return out

    # --------------------------------------------------------------- facade
    def extract_all(self, exercicios: list[int]) -> dict[str, list[dict[str, Any]]]:
        out: dict[str, list[dict[str, Any]]] = {"contratacoes": [], "arquivos": [], "itens": [],
                                                "contratos": [], "atas": [], "busca_indice": []}
        org = self.orgao()
        out["orgao"] = [org] if org else []
        for ano in exercicios:
            comp = self.contratacoes(ano)
            out["contratacoes"].extend(comp)
            arqs, its = self.arquivos_e_itens(comp, ano)
            out["arquivos"].extend(arqs)
            out["itens"].extend(its)
            out["contratos"].extend(self.contratos(ano))
            out["atas"].extend(self.atas(ano))
        out["busca_indice"] = self.busca_indice()
        return out
