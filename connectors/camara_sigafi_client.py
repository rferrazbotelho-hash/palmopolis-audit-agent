"""Extrator dos 19 endpoints Sigafi da Câmara Municipal de Palmópolis/MG.

Portal: https://cmpalmopolis.sigafi.com.br/portal/main
Salva todos os payloads JSON brutos em data/raw/camara/.
"""
from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel

from config import save_raw, settings
from connectors.http_utils import build_client, request
from connectors.memory_lai_client import ExtractionStatus

log = logging.getLogger("camara.sigafi")


class SigafiEndpoint(BaseModel):
    key: str
    modulo: str
    titulo: str
    path: str
    fallback_path: str | None = None
    mode: str = "date_range"  # date_range | exercicio | mensal | medicoes
    extra_params: dict[str, str] = {}


SIGAFI_ENDPOINTS: list[SigafiEndpoint] = [
    SigafiEndpoint(key="empenhos", modulo="Despesa", titulo="Empenhos", path="/Despesa/ajaxEmpenho/"),
    SigafiEndpoint(key="liquidacoes", modulo="Despesa", titulo="Liquidações", path="/Despesa/ajaxLiquidacao/"),
    SigafiEndpoint(key="pagamentos", modulo="Despesa", titulo="Pagamentos Efetuados", path="/Despesa/ajaxPagamento/", extra_params={"tipo": "efetuado"}),
    SigafiEndpoint(key="repasse_concedido", modulo="Despesa", titulo="Repasse Concedido", path="/Despesa/ajaxConcedido/"),
    SigafiEndpoint(
        key="diarias",
        modulo="Despesa",
        titulo="Diárias",
        path="/Despesa/ajaxPagamentoDiaria/",
        fallback_path="/Despesa/ajaxPagamento/",
        extra_params={"tipo": "diaria"},
    ),
    SigafiEndpoint(key="loa_receita", modulo="Receita", titulo="LOA Receita", path="/Receita/ajaxLoaReceita/", mode="exercicio"),
    SigafiEndpoint(key="previsao_repasse", modulo="Receita", titulo="Previsão de Repasse", path="/Receita/ajaxPrevisaoRepasse/", mode="exercicio"),
    SigafiEndpoint(key="receita_orc", modulo="Receita", titulo="Receita Orçamentária", path="/Receita/ajaxOrcamentaria/"),
    SigafiEndpoint(key="folha", modulo="Folha", titulo="Folha de Pagamento", path="/Folha/ajaxFolha/", mode="mensal", extra_params={"tipo": "mensal"}),
    SigafiEndpoint(key="servidores", modulo="Folha", titulo="Remuneração Nominal / Servidores", path="/Folha/ajaxServidores/", mode="mensal"),
    SigafiEndpoint(key="ordem_compras", modulo="Compras", titulo="Ordem de Compras", path="/Compra/ajaxOrdemCompras/"),
    SigafiEndpoint(key="ordem_fornecimento", modulo="Compras", titulo="Ordem de Fornecimento", path="/Compra/ajaxOrdemFornecimento/"),
    SigafiEndpoint(key="contratos", modulo="Contratos", titulo="Contratos", path="/Contrato/ajaxContratos/"),
    SigafiEndpoint(key="licitacoes", modulo="Licitações", titulo="Licitações", path="/Licitacao/ajaxLicitacoes/"),
    SigafiEndpoint(key="obras", modulo="Obras", titulo="Obras", path="/Obras/ajaxObras/"),
    SigafiEndpoint(key="medicoes", modulo="Obras", titulo="Medições de Obras", path="/Obras/ajaxMedicao/", mode="medicoes"),
    SigafiEndpoint(key="bens", modulo="Patrimônio", titulo="Bens Patrimoniais", path="/Patrimonio/ajaxBens/"),
    SigafiEndpoint(key="concursos", modulo="Concursos", titulo="Concursos", path="/Concurso/ajaxConcurso/"),
    SigafiEndpoint(key="divida_ativa", modulo="Tributário", titulo="Dívida Ativa", path="/Tributario/ajaxDividaAtiva/"),
]


class CamaraSigafiClient:
    def __init__(self, base_url: str | None = None, raw_source: str = "camara") -> None:
        self.base_url = (base_url or settings.camara_sigafi_url).rstrip("/")
        self.raw_source = raw_source

    @staticmethod
    def _parse_payload(raw_data: Any) -> list[dict[str, Any]]:
        if isinstance(raw_data, list):
            return [x for x in raw_data if isinstance(x, dict)]
        if isinstance(raw_data, dict):
            vals = list(raw_data.values())
            if vals and all(isinstance(v, dict) for v in vals):
                return vals
            return [raw_data] if raw_data else []
        return []

    def _get_json(self, client: Any, path: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        url = f"{self.base_url}{path}"
        resp = request(client, "GET", url, params={"json": "true", **params})
        try:
            data = resp.json()
        except ValueError as exc:
            raise ValueError(f"Resposta não-JSON em {url}: {resp.text[:160]}") from exc
        return self._parse_payload(data)

    def fetch_endpoint(
        self,
        ep: SigafiEndpoint,
        ano: int,
        obra_ids: list[str] | None = None,
    ) -> tuple[list[dict[str, Any]], ExtractionStatus]:
        records: list[dict[str, Any]] = []
        try:
            with build_client() as cli:
                if ep.mode == "exercicio":
                    records = self._get_json(cli, ep.path, {"exercicio": str(ano), **ep.extra_params})
                elif ep.mode == "mensal":
                    # Tenta mês mais recente disponível (outubro/dezembro) ou varre meses
                    for mes in ("10", "12", "09", "06", "01"):
                        batch = self._get_json(cli, ep.path, {"ano": str(ano), "mes": mes, **ep.extra_params})
                        if batch:
                            records = batch
                            break
                elif ep.mode == "medicoes":
                    for oid in obra_ids or []:
                        try:
                            batch = self._get_json(
                                cli,
                                ep.path,
                                {"obra_id": oid, "data_inicio": f"01/01/{ano}", "data_fim": f"31/12/{ano}"},
                            )
                            records.extend(batch)
                        except Exception:
                            continue
                else:
                    params = {"data_inicio": f"01/01/{ano}", "data_fim": f"31/12/{ano}", **ep.extra_params}
                    try:
                        records = self._get_json(cli, ep.path, params)
                    except ValueError:
                        if ep.fallback_path:
                            records = self._get_json(cli, ep.fallback_path, params)
                        else:
                            raise

            for r in records:
                r["exercicio"] = r.get("exercicio") or ano

            raw = save_raw(
                self.raw_source,
                f"{ep.key}_{ano}",
                records,
                {"endpoint": f"{self.base_url}{ep.path}", "modulo": ep.modulo, "exercicio": ano},
            )
            st = "OK" if records else "VAZIO"
            log.info("[Câmara Sigafi] %-20s %s: %5d registros", ep.key, ano, len(records))
            return records, ExtractionStatus(
                fonte="Câmara Sigafi",
                dataset=ep.key,
                exercicio=ano,
                registros=len(records),
                status=st,
                detalhe=f"{ep.modulo} - {ep.titulo}",
                arquivo_raw=str(raw),
            )
        except Exception as exc:
            log.warning("[Câmara Sigafi] Falha em %s/%s: %s", ep.key, ano, exc)
            save_raw(self.raw_source, f"{ep.key}_{ano}_ERRO", {"erro": str(exc)}, {"endpoint": ep.path})
            return [], ExtractionStatus(
                fonte="Câmara Sigafi",
                dataset=ep.key,
                exercicio=ano,
                registros=0,
                status="ERRO",
                detalhe=str(exc)[:240],
            )

    def extract_all(self, exercicios: list[int]) -> tuple[dict[str, list[dict[str, Any]]], list[ExtractionStatus]]:
        out: dict[str, list[dict[str, Any]]] = {}
        statuses: list[ExtractionStatus] = []
        obra_ids_by_ano: dict[int, list[str]] = {}

        for ep in SIGAFI_ENDPOINTS:
            for ano in exercicios:
                recs, st = self.fetch_endpoint(ep, ano, obra_ids=obra_ids_by_ano.get(ano))
                if ep.key == "obras" and recs:
                    obra_ids_by_ano[ano] = [str(r.get("id")) for r in recs if r.get("id")]
                out.setdefault(ep.key, []).extend(recs)
                statuses.append(st)
        return out, statuses
