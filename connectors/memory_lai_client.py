"""Extrator dos 19 endpoints OData do Portal da Transparência iLAI (Memory).

Cada endpoint corresponde a uma tela do SPA. Os IDs de consulta foram mapeados por
engenharia reversa do tráfego (e são re-validados a cada execução via Playwright,
que pode sobrescrevê-los por entidade OData descoberta).
"""
from __future__ import annotations

import logging
from typing import Any

import httpx
from pydantic import BaseModel

from config import save_raw, settings
from connectors.http_utils import build_client, request
from connectors.memory_auth_playwright import MemorySession

log = logging.getLogger("memory.lai")


class MemoryEndpoint(BaseModel):
    key: str
    titulo: str
    query_id: str
    odata_entity: str
    rota_spa: str
    filtro_data: bool = False
    grupo: str = "Licitações e Contratos"


ENDPOINTS: list[MemoryEndpoint] = [
    MemoryEndpoint(key="editais", titulo="Editais", query_id="query995556", odata_entity="comprasedital", rota_spa="licitacoes/edital"),
    MemoryEndpoint(key="licitacoes", titulo="Licitações", query_id="query803469", odata_entity="compraslicitacoes", rota_spa="licitacoes/licitacao"),
    MemoryEndpoint(key="dispensas_valor", titulo="Dispensa por Valor / Compras Diretas", query_id="query371120", odata_entity="idcomprasdiretas", rota_spa="licitacoes/dispensaporvalor"),
    MemoryEndpoint(key="contratos", titulo="Contratos e Aditivos", query_id="query320084", odata_entity="comprascontratos", rota_spa="licitacoes/contratos"),
    MemoryEndpoint(key="naf", titulo="Notas de Autorização de Fornecimento", query_id="query426102", odata_entity="comprasnaf", rota_spa="licitacoes/naf"),
    MemoryEndpoint(key="fiscais_contrato", titulo="Fiscais de Contrato", query_id="query584729", odata_entity="wsfiscalcontrato", rota_spa="licitacoes/fiscaiscontrato"),
    MemoryEndpoint(key="empenhos", titulo="Despesa por Empenho", query_id="query774140", odata_entity="wsempenho", rota_spa="execucaodespesa/despesaempenho", filtro_data=True, grupo="Execução da Despesa"),
    MemoryEndpoint(key="liquidacoes", titulo="Despesa por Liquidação", query_id="query931434", odata_entity="wsdespesaliquidacao", rota_spa="execucaodespesa/despesaliquidacao", filtro_data=True, grupo="Execução da Despesa"),
    MemoryEndpoint(key="pagamentos", titulo="Despesa por Pagamento", query_id="query893375", odata_entity="wsdespesapagamento", rota_spa="execucaodespesa/despesapagamento", filtro_data=True, grupo="Execução da Despesa"),
    MemoryEndpoint(key="despesa_extra", titulo="Despesa Extraorçamentária", query_id="query388233", odata_entity="wsdespesaextra", rota_spa="execucaodespesa/despesaextra", filtro_data=True, grupo="Execução da Despesa"),
    MemoryEndpoint(key="despesa_unidade", titulo="Despesa por Unidade Orçamentária", query_id="query733663", odata_entity="wsdespesasecretaria", rota_spa="execucaodespesa/despesaunidadeorc", filtro_data=True, grupo="Execução da Despesa"),
    MemoryEndpoint(key="despesa_funcao", titulo="Despesa por Função", query_id="query881811", odata_entity="wsdespesafuncao", rota_spa="execucaodespesa/despesafuncao", filtro_data=True, grupo="Execução da Despesa"),
    MemoryEndpoint(key="despesa_natureza", titulo="Despesa por Natureza", query_id="query716254", odata_entity="wsdespesaelemento", rota_spa="execucaodespesa/despesanatureza", filtro_data=True, grupo="Execução da Despesa"),
    MemoryEndpoint(key="fornecedores", titulo="Despesa por Fornecedor", query_id="query163688", odata_entity="wsfornecedor", rota_spa="fornecedores/fornecedores", grupo="Fornecedores"),
    MemoryEndpoint(key="restos_pagar", titulo="Restos a Pagar", query_id="query665513", odata_entity="wsrestosapagar", rota_spa="fornecedores/restosapagar", grupo="Fornecedores"),
    MemoryEndpoint(key="receitas", titulo="Execução da Receita", query_id="query461831", odata_entity="contabilidadereceita", rota_spa="execucaoreceita/receita", grupo="Receita"),
    MemoryEndpoint(key="repasses", titulo="Repasses Recebidos", query_id="query520357", odata_entity="wsrepasserecebido", rota_spa="repasse/repasserecebido", grupo="Receita"),
    MemoryEndpoint(key="servidores", titulo="Servidores", query_id="query617490", odata_entity="pessoalservidores", rota_spa="pessoal/servidor", grupo="Pessoal"),
    MemoryEndpoint(key="diarias", titulo="Diárias de Viagem", query_id="query330699", odata_entity="wspessoaldiaria", rota_spa="pessoal/diarias", filtro_data=True, grupo="Pessoal"),
]

# Endpoints complementares (fora dos 19 principais), também extraídos
EXTRA_ENDPOINTS: list[MemoryEndpoint] = [
    MemoryEndpoint(key="obras", titulo="Obras Públicas", query_id="query525253", odata_entity="wsobraspublicas", rota_spa="obras/obraspublicas", grupo="Complementar"),
    MemoryEndpoint(key="convenios", titulo="Convênios", query_id="query926730", odata_entity="wscontabilidadeconvenios", rota_spa="home/convenios", grupo="Complementar"),
    MemoryEndpoint(key="terceirizados", titulo="Terceirizados", query_id="query307045", odata_entity="", rota_spa="pessoal/terceirizados", grupo="Complementar"),
]


class ExtractionStatus(BaseModel):
    fonte: str
    dataset: str
    exercicio: int | None
    registros: int
    total_declarado: int | None = None
    status: str
    detalhe: str = ""
    arquivo_raw: str = ""


class MemoryLaiClient:
    def __init__(self, session: MemorySession) -> None:
        self.session = session
        self.page_size = settings.memory_page_size
        # Reconciliar IDs descobertos dinamicamente (entidade OData -> query)
        for ep in ENDPOINTS + EXTRA_ENDPOINTS:
            disc = session.discovered_queries.get(ep.odata_entity) if ep.odata_entity else None
            if disc and disc != ep.query_id:
                log.warning("Query de %s mudou: %s -> %s (auto-descoberta)", ep.key, ep.query_id, disc)
                ep.query_id = disc

    def _client(self, exercicio: int) -> httpx.Client:
        return build_client(cookies=self.session.cookies_for(exercicio),
                            headers={"Referer": f"{self.session.base_url}/"})

    def fetch_endpoint(self, ep: MemoryEndpoint, exercicio: int) -> tuple[list[dict[str, Any]], ExtractionStatus]:
        url = f"{self.session.odata_base}{ep.query_id}"
        records: list[dict[str, Any]] = []
        pages: list[dict[str, Any]] = []
        total: int | None = None
        skip = 0
        extra: dict[str, str] = {}
        if ep.filtro_data:
            extra = {"dataInicial": f"datetimeoffset'{exercicio}-01-01T00:00:00.000Z'",
                     "dataFinal": f"datetimeoffset'{exercicio}-12-31T23:59:59.000Z'"}
        try:
            with self._client(exercicio) as cli:
                while True:
                    params = {"$format": "json", "$inlinecount": "allpages", "$skip": str(skip),
                              "$top": str(self.page_size), **extra}
                    resp = request(cli, "GET", url, params=params)
                    data = resp.json().get("d", {})
                    batch = data.get("results", [])
                    total = int(data.get("__count", 0) or 0)
                    pages.append({"skip": skip, "url": str(resp.url), "count": len(batch)})
                    for r in batch:
                        r.pop("__metadata", None)
                        records.append(r)
                    skip += len(batch)
                    log.debug("%s/%s: %d/%d", ep.key, exercicio, skip, total)
                    if not batch or skip >= total:
                        break
            raw = save_raw("memory", f"{ep.key}_{exercicio}", records,
                           {"endpoint": url, "query_id": ep.query_id, "titulo": ep.titulo, "exercicio": exercicio,
                            "filtros": extra, "total_declarado": total, "paginas": pages,
                            "cookies_contexto": self.session.cookies_for(exercicio)})
            status = "OK" if records else "VAZIO"
            log.info("[Memory] %-18s %s: %5d registros (declarado %s)", ep.key, exercicio, len(records), total)
            return records, ExtractionStatus(fonte="Memory iLAI", dataset=ep.key, exercicio=exercicio,
                                             registros=len(records), total_declarado=total, status=status,
                                             detalhe=ep.titulo, arquivo_raw=str(raw))
        except Exception as exc:
            log.error("[Memory] Falha em %s/%s: %s", ep.key, exercicio, exc)
            save_raw("memory", f"{ep.key}_{exercicio}_ERRO", {"erro": str(exc), "parcial": records}, {"endpoint": url})
            return records, ExtractionStatus(fonte="Memory iLAI", dataset=ep.key, exercicio=exercicio,
                                             registros=len(records), total_declarado=total, status="ERRO",
                                             detalhe=str(exc)[:300])

    def extract_all(self, exercicios: list[int], include_extra: bool = True
                    ) -> tuple[dict[str, list[dict[str, Any]]], list[ExtractionStatus]]:
        """Retorna {dataset: registros (com coluna 'exercicio')} e status por extração."""
        out: dict[str, list[dict[str, Any]]] = {}
        statuses: list[ExtractionStatus] = []
        eps = ENDPOINTS + (EXTRA_ENDPOINTS if include_extra else [])
        for ep in eps:
            for ano in exercicios:
                recs, st = self.fetch_endpoint(ep, ano)
                for r in recs:
                    r["exercicio"] = ano
                out.setdefault(ep.key, []).extend(recs)
                statuses.append(st)
        return out, statuses
