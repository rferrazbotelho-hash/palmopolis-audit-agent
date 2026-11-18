"""Motor de reconciliação Local (Memory) x PNCP e trilhas da Lei 14.133/2021 e LAI."""
from __future__ import annotations

import logging
import re
import unicodedata
from datetime import date, datetime
from difflib import SequenceMatcher
from typing import Any

import numpy as np
import pandas as pd
from pydantic import BaseModel, Field

from config import (
    LIMITES_DISPENSA,
    PRAZO_PNCP_CONTRATACAO_DIRETA_DU,
    PRAZO_PNCP_LICITACAO_DU,
)

log = logging.getLogger("engine.reconciliador")


class AchadoAuditoria(BaseModel):
    codigo: str
    severidade: str  # CRITICO | ALTO | MEDIO | INFO
    base_legal: str
    titulo: str
    descricao: str
    quantidade: int = 0
    valor_envolvido: float = 0.0
    evidencia: str = ""


class AuditResult(BaseModel):
    model_config = {"arbitrary_types_allowed": True}

    achados: list[AchadoAuditoria] = Field(default_factory=list)
    kpis: dict[str, Any] = Field(default_factory=dict)
    dataframes: dict[str, pd.DataFrame] = Field(default_factory=dict)


# --------------------------------------------------------------------- helpers
def _norm_text(val: Any) -> str:
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return ""
    s = unicodedata.normalize("NFKD", str(val))
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", s).strip().upper()


def _only_digits(val: Any) -> str:
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return ""
    return re.sub(r"\D", "", str(val))


def _to_float(val: Any) -> float:
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return 0.0
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val).strip()
    if not s:
        return 0.0
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".")
    elif "," in s:
        s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return 0.0


def _parse_date(val: Any) -> date | None:
    if not val:
        return None
    s = str(val).strip()
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(s[:19] if "T" in fmt else s[:10], fmt).date()
        except ValueError:
            continue
    return None


def _business_days(d1: date | None, d2: date | None) -> int | None:
    if not d1 or not d2:
        return None
    return int(np.busday_count(d1.isoformat(), d2.isoformat()))


def _extract_num_ano(val: Any, fallback_ano: Any = None) -> tuple[str, str]:
    """Normaliza '001/2026' ou '1' + 2026 -> ('1', '2026')."""
    s = str(val or "").strip()
    m = re.search(r"0*(\d+)\s*/\s*(20\d{2})", s)
    if m:
        return m.group(1), m.group(2)
    m2 = re.search(r"0*(\d+)", s)
    ano = str(fallback_ano or "").strip()
    return (m2.group(1) if m2 else ""), ano


def _to_df(records: list[dict[str, Any]]) -> pd.DataFrame:
    if not records:
        return pd.DataFrame()
    return pd.DataFrame(records)


def _similaridade(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, _norm_text(a)[:180], _norm_text(b)[:180]).ratio()


# ------------------------------------------------------------------ engine
class Reconciliador:
    def __init__(
        self,
        memory_data: dict[str, list[dict[str, Any]]],
        pncp_data: dict[str, list[dict[str, Any]]],
        portal_data: dict[str, list[dict[str, Any]]],
        extraction_statuses: list[dict[str, Any]],
        exercicios: list[int],
    ) -> None:
        self.mem = memory_data
        self.pncp = pncp_data
        self.portal = portal_data
        self.statuses = extraction_statuses
        self.exercicios = exercicios

    def run(self) -> AuditResult:
        res = AuditResult()

        # DataFrames base tratados
        df_lic_mem = self._prep_memory_licitacoes()
        df_ctr_mem = self._prep_memory_contratos()
        df_disp_mem = self._prep_memory_dispensas()
        df_naf_mem = self._prep_memory_naf()
        df_emp_mem = self._prep_memory_empenhos()
        df_forn_mem = self._prep_memory_fornecedores()
        df_serv_mem = _to_df(self.mem.get("servidores", []))
        df_fisc_mem = _to_df(self.mem.get("fiscais_contrato", []))
        df_obras_mem = _to_df(self.mem.get("obras", []))
        df_conv_mem = _to_df(self.mem.get("convenios", []))

        df_pncp_comp = self._prep_pncp_contratacoes()
        df_pncp_ctr = self._prep_pncp_contratos()
        df_pncp_arqs = _to_df(self.pncp.get("arquivos", []))
        df_pncp_itens = _to_df(self.pncp.get("itens", []))
        df_pncp_atas = _to_df(self.pncp.get("atas", []))

        # Cruzamentos principais
        df_cruz_lic = self._reconciliar_licitacoes(df_lic_mem, df_pncp_comp)
        df_cruz_ctr = self._reconciliar_contratos(df_ctr_mem, df_pncp_ctr)
        df_disp_audit = self._auditar_dispensas_art75(df_disp_mem, df_lic_mem, df_naf_mem)
        df_forn_abc = self._auditar_fornecedores_art9_14(df_forn_mem, df_naf_mem, df_serv_mem)
        df_lai = self._auditar_transparencia_lai()

        # Gerar achados consolidados
        achados = self._gerar_achados(
            df_cruz_lic=df_cruz_lic,
            df_cruz_ctr=df_cruz_ctr,
            df_ctr_mem=df_ctr_mem,
            df_disp_audit=df_disp_audit,
            df_forn_abc=df_forn_abc,
            df_pncp_comp=df_pncp_comp,
            df_pncp_arqs=df_pncp_arqs,
            df_fisc_mem=df_fisc_mem,
            df_lai=df_lai,
        )

        df_achados = pd.DataFrame([a.model_dump() for a in achados])
        df_status = pd.DataFrame(self.statuses)

        # KPIs executivos
        kpis = self._compute_kpis(
            df_lic_mem=df_lic_mem,
            df_ctr_mem=df_ctr_mem,
            df_disp_mem=df_disp_mem,
            df_naf_mem=df_naf_mem,
            df_emp_mem=df_emp_mem,
            df_forn_mem=df_forn_mem,
            df_serv_mem=df_serv_mem,
            df_pncp_comp=df_pncp_comp,
            df_pncp_ctr=df_pncp_ctr,
            df_pncp_arqs=df_pncp_arqs,
            df_cruz_lic=df_cruz_lic,
            df_cruz_ctr=df_cruz_ctr,
            achados=achados,
        )

        res.achados = achados
        res.kpis = kpis
        res.dataframes = {
            "Achados_Auditoria": df_achados,
            "Cruzamento_Licitacoes": df_cruz_lic,
            "Cruzamento_Contratos": df_cruz_ctr,
            "Auditoria_Art75_Dispensas": df_disp_audit,
            "Fornecedores_CurvaABC": df_forn_abc,
            "Transparencia_LAI": df_lai,
            "Memory_Licitacoes": df_lic_mem,
            "Memory_Contratos": df_ctr_mem,
            "Memory_Dispensas": df_disp_mem,
            "Memory_NAF": df_naf_mem,
            "Memory_Empenhos": df_emp_mem,
            "Memory_Obras": df_obras_mem,
            "Memory_Convenios": df_conv_mem,
            "PNCP_Contratacoes": df_pncp_comp,
            "PNCP_Contratos": df_pncp_ctr,
            "PNCP_Atas": df_pncp_atas,
            "PNCP_Arquivos": df_pncp_arqs,
            "PNCP_Itens": df_pncp_itens,
            "Log_Extracoes": df_status,
        }
        log.info("Auditoria concluída: %d achados gerados.", len(achados))
        return res

    # ------------------------------------------------------------ preparadores
    def _prep_memory_licitacoes(self) -> pd.DataFrame:
        df = _to_df(self.mem.get("licitacoes", []))
        if df.empty:
            return df
        df["valor_homologado_num"] = df.get("valor_homologado", pd.Series(dtype=object)).apply(_to_float)
        df["valor_maximo_num"] = df.get("valor_maximo_processo", pd.Series(dtype=object)).apply(_to_float)
        nums = df.apply(lambda r: _extract_num_ano(r.get("numero_licitacao"), r.get("exercicio")), axis=1)
        df["num_norm"] = [n[0] for n in nums]
        df["ano_norm"] = [n[1] for n in nums]
        df["chave_proc"] = df["num_norm"] + "/" + df["ano_norm"]
        return df

    def _prep_memory_contratos(self) -> pd.DataFrame:
        df = _to_df(self.mem.get("contratos", []))
        if df.empty:
            return df
        df["valor_contrato_num"] = df.get("valor_contrato", pd.Series(dtype=object)).apply(_to_float)
        df["cpf_cnpj_limpo"] = df.get("cpf_cnpj", pd.Series(dtype=object)).apply(_only_digits)
        nums = df.apply(lambda r: _extract_num_ano(r.get("numero_contrato"), r.get("exercicio")), axis=1)
        df["num_norm"] = [n[0] for n in nums]
        df["ano_norm"] = [n[1] for n in nums]
        df["chave_ctr"] = df["num_norm"] + "/" + df["ano_norm"]
        return df

    def _prep_memory_dispensas(self) -> pd.DataFrame:
        df = _to_df(self.mem.get("dispensas_valor", []))
        if df.empty:
            return df
        nums = df.apply(lambda r: _extract_num_ano(r.get("numero_direta"), r.get("exercicio")), axis=1)
        df["num_norm"] = [n[0] for n in nums]
        df["ano_norm"] = [n[1] for n in nums]
        return df

    def _prep_memory_naf(self) -> pd.DataFrame:
        df = _to_df(self.mem.get("naf", []))
        if df.empty:
            return df
        df["valor_total_num"] = df.get("valor_total", pd.Series(dtype=object)).apply(_to_float)
        df["cpf_cnpj_limpo"] = df.get("fornecedor_cpf_cnpj", pd.Series(dtype=object)).apply(_only_digits)
        return df

    def _prep_memory_empenhos(self) -> pd.DataFrame:
        df = _to_df(self.mem.get("empenhos", []))
        if df.empty:
            return df
        df["valor_empenho_num"] = df.get("valor_empenho", pd.Series(dtype=object)).apply(_to_float)
        df["cpf_cnpj_limpo"] = df.get("fornecedor_cpf_cnpj", pd.Series(dtype=object)).apply(_only_digits)
        return df

    def _prep_memory_fornecedores(self) -> pd.DataFrame:
        df = _to_df(self.mem.get("fornecedores", []))
        if df.empty:
            return df
        for col in ("valor_empenhado", "valor_liquidado", "valor_pago", "valor_apagar"):
            if col in df.columns:
                df[f"{col}_num"] = df[col].apply(_to_float)
        df["cpf_cnpj_limpo"] = df.get("fornecedor_cpf_cnpj", pd.Series(dtype=object)).apply(_only_digits)
        return df

    def _prep_pncp_contratacoes(self) -> pd.DataFrame:
        df = _to_df(self.pncp.get("contratacoes", []))
        if df.empty:
            return df
        df["valor_estimado_num"] = df.get("valorTotalEstimado", pd.Series(dtype=object)).apply(_to_float)
        df["valor_homologado_num"] = df.get("valorTotalHomologado", pd.Series(dtype=object)).apply(_to_float)
        nums = df.apply(lambda r: _extract_num_ano(r.get("numeroCompra"), r.get("anoCompra")), axis=1)
        df["num_norm"] = [n[0] for n in nums]
        df["ano_norm"] = [n[1] for n in nums]
        df["chave_comp"] = df["num_norm"] + "/" + df["ano_norm"]
        pnums = df.apply(lambda r: _extract_num_ano(r.get("processo"), r.get("anoCompra")), axis=1)
        df["chave_proc"] = [n[0] + "/" + n[1] for n in pnums]
        return df

    def _prep_pncp_contratos(self) -> pd.DataFrame:
        df = _to_df(self.pncp.get("contratos", []))
        if df.empty:
            return df
        df["valor_global_num"] = df.get("valorGlobal", pd.Series(dtype=object)).apply(_to_float)
        df["cpf_cnpj_limpo"] = df.get("niFornecedor", pd.Series(dtype=object)).apply(_only_digits)
        nums = df.apply(lambda r: _extract_num_ano(r.get("numeroContratoEmpenho"), r.get("anoContrato")), axis=1)
        df["chave_ctr"] = [n[0] + "/" + n[1] for n in nums]
        df["dias_uteis_pub"] = df.apply(
            lambda r: _business_days(_parse_date(r.get("dataAssinatura")), _parse_date(r.get("dataPublicacaoPncp"))),
            axis=1,
        )
        return df

    # ------------------------------------------------------------ cruzamentos
    def _reconciliar_licitacoes(self, df_mem: pd.DataFrame, df_pncp: pd.DataFrame) -> pd.DataFrame:
        """Cruza licitações/compras do Memory com contratações publicadas no PNCP."""
        rows: list[dict[str, Any]] = []
        matched_pncp_idx: set[int] = set()

        pncp_records = df_pncp.to_dict("records") if not df_pncp.empty else []

        if not df_mem.empty:
            for r in df_mem.to_dict("records"):
                chave = r.get("chave_proc", "")
                desc = str(r.get("descricao") or "")
                best_idx = None
                best_sim = 0.0
                metodo = ""

                for idx, p in enumerate(pncp_records):
                    if idx in matched_pncp_idx:
                        continue
                    sim = _similaridade(desc, str(p.get("objetoCompra") or ""))
                    if chave and (chave == p.get("chave_proc") or chave == p.get("chave_comp")) and sim >= 0.35:
                        best_idx, best_sim, metodo = idx, sim, "Chave+Objeto"
                        break
                    if str(r.get("exercicio")) == str(p.get("anoCompra")) and sim > best_sim and sim >= 0.72:
                        best_idx, best_sim, metodo = idx, sim, "Similaridade_Objeto"

                if best_idx is not None:
                    matched_pncp_idx.add(best_idx)
                    p = pncp_records[best_idx]
                    v_mem = float(r.get("valor_homologado_num") or 0)
                    v_pncp = float(p.get("valor_homologado_num") or p.get("valor_estimado_num") or 0)
                    rows.append({
                        "status_conciliacao": "CONCILIADO",
                        "metodo_match": metodo,
                        "similaridade": round(best_sim, 2),
                        "exercicio": r.get("exercicio"),
                        "numero_memory": r.get("numero_licitacao"),
                        "modalidade_memory": r.get("modalidade"),
                        "situacao_memory": str(r.get("situacao") or "").strip(),
                        "valor_memory": v_mem,
                        "objeto_memory": desc[:220],
                        "numero_controle_pncp": p.get("numeroControlePNCP"),
                        "numero_pncp": f"{p.get('numeroCompra')}/{p.get('anoCompra')} (proc {p.get('processo')})",
                        "modalidade_pncp": p.get("modalidadeNome"),
                        "valor_pncp": v_pncp,
                        "diferenca_valor": round(v_mem - v_pncp, 2),
                        "data_publicacao_pncp": p.get("dataPublicacaoPncp"),
                    })
                else:
                    rows.append({
                        "status_conciliacao": "SOMENTE_LOCAL_SEM_PNCP",
                        "metodo_match": "-",
                        "similaridade": 0.0,
                        "exercicio": r.get("exercicio"),
                        "numero_memory": r.get("numero_licitacao"),
                        "modalidade_memory": r.get("modalidade"),
                        "situacao_memory": str(r.get("situacao") or "").strip(),
                        "valor_memory": float(r.get("valor_homologado_num") or r.get("valor_maximo_num") or 0),
                        "objeto_memory": desc[:220],
                        "numero_controle_pncp": None,
                        "numero_pncp": None,
                        "modalidade_pncp": None,
                        "valor_pncp": 0.0,
                        "diferenca_valor": 0.0,
                        "data_publicacao_pncp": None,
                    })

        for idx, p in enumerate(pncp_records):
            if idx in matched_pncp_idx:
                continue
            rows.append({
                "status_conciliacao": "SOMENTE_PNCP_SEM_LOCAL",
                "metodo_match": "-",
                "similaridade": 0.0,
                "exercicio": p.get("anoCompra"),
                "numero_memory": None,
                "modalidade_memory": None,
                "situacao_memory": None,
                "valor_memory": 0.0,
                "objeto_memory": None,
                "numero_controle_pncp": p.get("numeroControlePNCP"),
                "numero_pncp": f"{p.get('numeroCompra')}/{p.get('anoCompra')} (proc {p.get('processo')})",
                "modalidade_pncp": p.get("modalidadeNome"),
                "valor_pncp": float(p.get("valor_homologado_num") or p.get("valor_estimado_num") or 0),
                "diferenca_valor": 0.0,
                "data_publicacao_pncp": p.get("dataPublicacaoPncp"),
            })

        return pd.DataFrame(rows)

    def _reconciliar_contratos(self, df_mem: pd.DataFrame, df_pncp: pd.DataFrame) -> pd.DataFrame:
        rows: list[dict[str, Any]] = []
        matched_pncp: set[int] = set()
        pncp_recs = df_pncp.to_dict("records") if not df_pncp.empty else []

        if not df_mem.empty:
            for r in df_mem.to_dict("records"):
                chave = r.get("chave_ctr", "")
                cnpj = r.get("cpf_cnpj_limpo", "")
                val = float(r.get("valor_contrato_num") or 0)
                best = None
                for idx, p in enumerate(pncp_recs):
                    if idx in matched_pncp:
                        continue
                    if chave and chave == p.get("chave_ctr"):
                        best = idx
                        break
                    if cnpj and cnpj == p.get("cpf_cnpj_limpo") and abs(val - float(p.get("valor_global_num") or 0)) < 1.0:
                        best = idx
                        break
                if best is not None:
                    matched_pncp.add(best)
                    p = pncp_recs[best]
                    rows.append({
                        "status_conciliacao": "CONCILIADO",
                        "exercicio": r.get("exercicio"),
                        "numero_contrato_memory": r.get("numero_contrato"),
                        "tipo_ato": r.get("tipo_ato"),
                        "modalidade": r.get("modalidade"),
                        "fornecedor_memory": r.get("fornecedor"),
                        "cpf_cnpj_memory": r.get("cpf_cnpj"),
                        "valor_memory": val,
                        "numero_controle_pncp": p.get("numeroControlePNCP"),
                        "valor_pncp": float(p.get("valor_global_num") or 0),
                        "dias_uteis_pub_pncp": p.get("dias_uteis_pub"),
                        "objeto": str(r.get("objeto") or "")[:200],
                    })
                else:
                    rows.append({
                        "status_conciliacao": "SOMENTE_LOCAL_SEM_PNCP",
                        "exercicio": r.get("exercicio"),
                        "numero_contrato_memory": r.get("numero_contrato"),
                        "tipo_ato": r.get("tipo_ato"),
                        "modalidade": r.get("modalidade"),
                        "fornecedor_memory": r.get("fornecedor"),
                        "cpf_cnpj_memory": r.get("cpf_cnpj"),
                        "valor_memory": val,
                        "numero_controle_pncp": None,
                        "valor_pncp": 0.0,
                        "dias_uteis_pub_pncp": None,
                        "objeto": str(r.get("objeto") or "")[:200],
                    })

        for idx, p in enumerate(pncp_recs):
            if idx in matched_pncp:
                continue
            rows.append({
                "status_conciliacao": "SOMENTE_PNCP_SEM_LOCAL",
                "exercicio": p.get("anoContrato"),
                "numero_contrato_memory": None,
                "tipo_ato": (p.get("tipoContrato") or {}).get("nome") if isinstance(p.get("tipoContrato"), dict) else None,
                "modalidade": None,
                "fornecedor_memory": p.get("nomeRazaoSocialFornecedor"),
                "cpf_cnpj_memory": p.get("niFornecedor"),
                "valor_memory": 0.0,
                "numero_controle_pncp": p.get("numeroControlePNCP"),
                "valor_pncp": float(p.get("valor_global_num") or 0),
                "dias_uteis_pub_pncp": p.get("dias_uteis_pub"),
                "objeto": str(p.get("objetoContrato") or "")[:200],
            })
        return pd.DataFrame(rows)

    def _auditar_dispensas_art75(
        self, df_disp: pd.DataFrame, df_lic: pd.DataFrame, df_naf: pd.DataFrame
    ) -> pd.DataFrame:
        """Consolida dispensas/inexigibilidades e verifica limites do Art. 75, I e II."""
        rows: list[dict[str, Any]] = []

        if not df_lic.empty:
            mask = df_lic["modalidade"].astype(str).str.contains("Dispensa|Inexigibilidade", case=False, na=False)
            for r in df_lic[mask].to_dict("records"):
                ano = int(r.get("exercicio") or 2025)
                lim = LIMITES_DISPENSA.get(ano, LIMITES_DISPENSA[2026])
                val = float(r.get("valor_homologado_num") or r.get("valor_maximo_num") or 0)
                desc = str(r.get("descricao") or "")
                eh_obra = any(k in _norm_text(desc) for k in ("OBRA", "ENGENHARIA", "REFORMA", "CONSTRUCAO", "PAVIMENTACAO"))
                teto = lim["inciso_I"] if eh_obra else lim["inciso_II"]
                eh_dispensa = "DISPENSA" in _norm_text(r.get("modalidade"))
                excede = eh_dispensa and val > teto
                rows.append({
                    "origem": "Memory_Licitacoes",
                    "exercicio": ano,
                    "numero": r.get("numero_licitacao"),
                    "modalidade": r.get("modalidade"),
                    "situacao": str(r.get("situacao") or "").strip(),
                    "valor": val,
                    "teto_art75": teto if eh_dispensa else None,
                    "enquadramento_teto": "Inciso I (Obra/Eng)" if eh_obra else "Inciso II (Compras/Serv)",
                    "alerta_art75": "ACIMA_LIMITE_LEGAL" if excede else "REGULAR_OU_INEXIG",
                    "objeto": desc[:220],
                })

        if not df_disp.empty:
            for r in df_disp.to_dict("records"):
                rows.append({
                    "origem": "Memory_DispensaValor",
                    "exercicio": r.get("exercicio"),
                    "numero": r.get("numero_direta"),
                    "modalidade": r.get("modalidade"),
                    "situacao": str(r.get("situacao") or "").strip(),
                    "valor": 0.0,
                    "teto_art75": LIMITES_DISPENSA.get(int(r.get("exercicio") or 2026), LIMITES_DISPENSA[2026])["inciso_II"],
                    "enquadramento_teto": "Dispensa por Valor",
                    "alerta_art75": "VERIFICAR_VALOR_NA_NAF",
                    "objeto": str(r.get("objeto") or "")[:220],
                })

        # Se houver NAFs vinculadas a compras diretas (sem licitação ou id_compradireta preenchido)
        if not df_naf.empty and "id_compradireta" in df_naf.columns:
            diretas = df_naf[df_naf["id_compradireta"].notna()]
            if not diretas.empty:
                grp = diretas.groupby(["exercicio", "fornecedor_cpf_cnpj", "fornecedor_nome"], dropna=False)[
                    "valor_total_num"
                ].sum().reset_index()
                for g in grp.to_dict("records"):
                    ano = int(g.get("exercicio") or 2026)
                    teto = LIMITES_DISPENSA.get(ano, LIMITES_DISPENSA[2026])["inciso_II"]
                    val = float(g.get("valor_total_num") or 0)
                    rows.append({
                        "origem": "NAF_CompraDireta_Fornecedor",
                        "exercicio": ano,
                        "numero": g.get("fornecedor_cpf_cnpj"),
                        "modalidade": "Compra Direta (NAF acumulada)",
                        "situacao": "Acumulado Anual",
                        "valor": val,
                        "teto_art75": teto,
                        "enquadramento_teto": "Inciso II (Fracionamento)",
                        "alerta_art75": "RISCO_FRACIONAMENTO" if val > teto else "ABAIXO_TETO",
                        "objeto": f"Fornecedor: {g.get('fornecedor_nome')}",
                    })

        return pd.DataFrame(rows)

    def _auditar_fornecedores_art9_14(
        self, df_forn: pd.DataFrame, df_naf: pd.DataFrame, df_serv: pd.DataFrame
    ) -> pd.DataFrame:
        """Curva ABC de fornecedores e cruzamento com quadro de servidores (Art. 9º / 14)."""
        serv_nomes: set[str] = set()
        if not df_serv.empty and "nome_servidor" in df_serv.columns:
            serv_nomes = {_norm_text(n) for n in df_serv["nome_servidor"].dropna() if len(_norm_text(n)) > 5}

        base = pd.DataFrame()
        if not df_forn.empty:
            base = df_forn.copy()
            base["valor_ref"] = base.get("valor_empenhado_num", 0.0)
        elif not df_naf.empty:
            base = (
                df_naf.groupby(["cpf_cnpj_limpo", "fornecedor_nome", "fornecedor_cpf_cnpj"], dropna=False)["valor_total_num"]
                .sum()
                .reset_index()
                .rename(columns={"valor_total_num": "valor_ref"})
            )
        if base.empty:
            return base

        base = base.sort_values("valor_ref", ascending=False).reset_index(drop=True)
        total = float(base["valor_ref"].sum()) or 1.0
        base["participacao_pct"] = (base["valor_ref"] / total * 100).round(2)
        base["acumulado_pct"] = base["participacao_pct"].cumsum().round(2)
        base["possivel_vinculo_servidor_nome"] = base["fornecedor_nome"].apply(
            lambda n: "SIM (VERIFICAR CPF)" if _norm_text(n) in serv_nomes else "NAO"
        )
        base["eh_proprio_municipio"] = base["cpf_cnpj_limpo"].apply(lambda c: c == "66234345000118")
        return base

    def _auditar_transparencia_lai(self) -> pd.DataFrame:
        """Avalia aderência à LAI (Lei 12.527/2011) nos portais Memory e Institucional."""
        rows: list[dict[str, Any]] = []
        # Status dos endpoints
        for st in self.statuses:
            rows.append({
                "camada": st.get("fonte"),
                "item": st.get("dataset"),
                "exercicio": st.get("exercicio"),
                "registros": st.get("registros"),
                "status": st.get("status"),
                "observacao": st.get("detalhe"),
            })

        # Checagem específica de categorias vazias no portal institucional
        for pub in self.portal.get("publicacoes", []):
            if pub.get("vazio_declarado") or pub.get("qtd_documentos", 0) == 0:
                rows.append({
                    "camada": "Portal Institucional (LAI)",
                    "item": f"publicacao/{pub.get('categoria')}",
                    "exercicio": "Todos",
                    "registros": pub.get("qtd_documentos", 0),
                    "status": "DEFICIT_TRANSPARENCIA",
                    "observacao": f"Página sem publicações disponíveis ({pub.get('url')})",
                })
        return pd.DataFrame(rows)

    # -------------------------------------------------------------- achados
    def _gerar_achados(
        self,
        *,
        df_cruz_lic: pd.DataFrame,
        df_cruz_ctr: pd.DataFrame,
        df_ctr_mem: pd.DataFrame,
        df_disp_audit: pd.DataFrame,
        df_forn_abc: pd.DataFrame,
        df_pncp_comp: pd.DataFrame,
        df_pncp_arqs: pd.DataFrame,
        df_fisc_mem: pd.DataFrame,
        df_lai: pd.DataFrame,
    ) -> list[AchadoAuditoria]:
        achados: list[AchadoAuditoria] = []

        # 1. Licitações locais ausentes no PNCP (Art. 54 e 94)
        if not df_cruz_lic.empty:
            sem_pncp = df_cruz_lic[df_cruz_lic["status_conciliacao"] == "SOMENTE_LOCAL_SEM_PNCP"]
            if not sem_pncp.empty:
                achados.append(AchadoAuditoria(
                    codigo="ACH-01",
                    severidade="CRITICO",
                    base_legal="Lei 14.133/2021, Arts. 54 e 94",
                    titulo="Licitações/processos no Portal Memory sem correspondência no PNCP",
                    descricao=(
                        "Foram identificados processos no Portal da Transparência local (Memory) que não "
                        "possuem publicação correspondente localizada na API do PNCP para o CNPJ do Município."
                    ),
                    quantidade=len(sem_pncp),
                    valor_envolvido=float(sem_pncp["valor_memory"].sum()),
                    evidencia="; ".join(sem_pncp["numero_memory"].dropna().astype(str).head(10)),
                ))

            sem_local = df_cruz_lic[df_cruz_lic["status_conciliacao"] == "SOMENTE_PNCP_SEM_LOCAL"]
            if not sem_local.empty:
                achados.append(AchadoAuditoria(
                    codigo="ACH-02",
                    severidade="ALTO",
                    base_legal="Lei 12.527/2011 (LAI), Art. 8º, §1º, IV",
                    titulo="Contratações publicadas no PNCP sem espelhamento localizado no Portal Memory",
                    descricao="Processos publicados no PNCP sem correspondência direta nos registros do Portal Memory.",
                    quantidade=len(sem_local),
                    valor_envolvido=float(sem_local["valor_pncp"].sum()),
                    evidencia="; ".join(sem_local["numero_controle_pncp"].dropna().astype(str).head(8)),
                ))

        # 2. Contratos locais ausentes no PNCP (Art. 94) + Dados nulos no Memory
        if not df_cruz_ctr.empty:
            ctr_sem_pncp = df_cruz_ctr[df_cruz_ctr["status_conciliacao"] == "SOMENTE_LOCAL_SEM_PNCP"]
            if not ctr_sem_pncp.empty:
                achados.append(AchadoAuditoria(
                    codigo="ACH-03",
                    severidade="CRITICO",
                    base_legal="Lei 14.133/2021, Art. 94 (Condição de Eficácia)",
                    titulo="Contratos registrados no Portal Memory sem divulgação localizada no PNCP",
                    descricao=(
                        "O Art. 94 da Lei 14.133/2021 estabelece a divulgação no PNCP como condição "
                        "indispensável para eficácia do contrato e de seus aditivos."
                    ),
                    quantidade=len(ctr_sem_pncp),
                    valor_envolvido=float(ctr_sem_pncp["valor_memory"].sum()),
                    evidencia="; ".join(ctr_sem_pncp["numero_contrato_memory"].dropna().astype(str).head(10)),
                ))

            # Tempestividade no PNCP
            if "dias_uteis_pub_pncp" in df_cruz_ctr.columns:
                atraso = df_cruz_ctr[df_cruz_ctr["dias_uteis_pub_pncp"].fillna(0) > PRAZO_PNCP_LICITACAO_DU]
                if not atraso.empty:
                    achados.append(AchadoAuditoria(
                        codigo="ACH-04",
                        severidade="ALTO",
                        base_legal="Lei 14.133/2021, Art. 94, I e II",
                        titulo="Contratos divulgados no PNCP fora do prazo legal",
                        descricao=f"Publicação no PNCP superior a {PRAZO_PNCP_LICITACAO_DU} dias úteis da assinatura.",
                        quantidade=len(atraso),
                        valor_envolvido=float(atraso["valor_pncp"].sum()),
                        evidencia="; ".join(atraso["numero_controle_pncp"].dropna().astype(str).head(8)),
                    ))

        if not df_ctr_mem.empty:
            sem_forn = df_ctr_mem[df_ctr_mem["fornecedor"].isna() | (df_ctr_mem["cpf_cnpj_limpo"] == "")]
            if not sem_forn.empty:
                achados.append(AchadoAuditoria(
                    codigo="ACH-05",
                    severidade="ALTO",
                    base_legal="Lei 12.527/2011, Art. 8º, §1º, IV e §3º",
                    titulo="Contratos no Portal Memory com fornecedor ou CPF/CNPJ ausente",
                    descricao="Registros de contratos publicados no portal sem identificação de contratado ou CNPJ/CPF.",
                    quantidade=len(sem_forn),
                    valor_envolvido=float(sem_forn["valor_contrato_num"].sum()),
                    evidencia="; ".join(sem_forn["numero_contrato"].dropna().astype(str).head(10)),
                ))

        # 3. Art. 75 - Dispensas acima do teto ou risco de fracionamento
        if not df_disp_audit.empty:
            acima = df_disp_audit[df_disp_audit["alerta_art75"].isin(["ACIMA_LIMITE_LEGAL", "RISCO_FRACIONAMENTO"])]
            if not acima.empty:
                achados.append(AchadoAuditoria(
                    codigo="ACH-06",
                    severidade="CRITICO",
                    base_legal="Lei 14.133/2021, Art. 75, I, II e §1º",
                    titulo="Dispensas por valor ou acumulados anuais acima do limite legal",
                    descricao="Processos ou acumulados por fornecedor em compra direta superam o teto atualizado do Art. 75.",
                    quantidade=len(acima),
                    valor_envolvido=float(acima["valor"].sum()),
                    evidencia="; ".join(acima["numero"].dropna().astype(str).head(10)),
                ))

        # 4. Art. 54 - Contratações no PNCP sem arquivos anexados
        if not df_pncp_comp.empty:
            com_arq = set(df_pncp_arqs["numeroControlePNCP"].dropna()) if not df_pncp_arqs.empty else set()
            sem_arq = df_pncp_comp[~df_pncp_comp["numeroControlePNCP"].isin(com_arq)]
            if not sem_arq.empty:
                achados.append(AchadoAuditoria(
                    codigo="ACH-07",
                    severidade="MEDIO",
                    base_legal="Lei 14.133/2021, Art. 54, caput",
                    titulo="Contratações no PNCP sem inteiro teor de edital/anexos publicados",
                    descricao="Art. 54 exige divulgação e manutenção do inteiro teor do ato convocatório e anexos no PNCP.",
                    quantidade=len(sem_arq),
                    valor_envolvido=float(sem_arq["valor_estimado_num"].sum()),
                    evidencia="; ".join(sem_arq["numeroControlePNCP"].dropna().astype(str).head(8)),
                ))

        # 5. Art. 9º e 14 - Possível vínculo fornecedor x servidor
        if not df_forn_abc.empty:
            vinc = df_forn_abc[df_forn_abc["possivel_vinculo_servidor_nome"] != "NAO"]
            if not vinc.empty:
                achados.append(AchadoAuditoria(
                    codigo="ACH-08",
                    severidade="ALTO",
                    base_legal="Lei 14.133/2021, Art. 9º, §1º e Art. 14, IV",
                    titulo="Fornecedores com homonímia exata no quadro de servidores municipais",
                    descricao=(
                        "Cruzamento nominal entre fornecedores e servidores ativos/contratados identificou "
                        "coincidência exata de nome completo (CPF parcialmente mascarado pela LAI exige conferência documental)."
                    ),
                    quantidade=len(vinc),
                    valor_envolvido=float(vinc["valor_ref"].sum()),
                    evidencia="; ".join(vinc["fornecedor_nome"].dropna().astype(str).head(8)),
                ))

        # 6. Fiscais de contrato (Art. 117)
        if not df_ctr_mem.empty and df_fisc_mem.empty:
            achados.append(AchadoAuditoria(
                codigo="ACH-09",
                severidade="MEDIO",
                base_legal="Lei 14.133/2021, Art. 117 e LAI",
                titulo="Ausência de fiscais de contrato publicados para o exercício",
                descricao="Há contratos registrados, mas a consulta de Fiscais de Contrato retornou 0 registros.",
                quantidade=len(df_ctr_mem),
                valor_envolvido=float(df_ctr_mem["valor_contrato_num"].sum()),
            ))

        # 7. Déficit de transparência no Portal Institucional (LAI)
        if not df_lai.empty:
            deficits = df_lai[df_lai["status"].isin(["DEFICIT_TRANSPARENCIA", "VAZIO"])]
            if not deficits.empty:
                achados.append(AchadoAuditoria(
                    codigo="ACH-10",
                    severidade="MEDIO",
                    base_legal="Lei 12.527/2011 (LAI), Art. 8º",
                    titulo="Lacunas de publicação em endpoints do iLAI ou seções do Portal Institucional",
                    descricao="Endpoints sem registros em 2025/2026 ou seções institucionais (ex.: Licitações/Decretos/Diário) vazias.",
                    quantidade=len(deficits),
                    evidencia="; ".join(
                        f"{r.get('item', '-')}({'-' if pd.isna(r.get('exercicio')) else r.get('exercicio')})"
                        for r in deficits.head(12).to_dict("records")
                    ),
                ))

        return achados

    # ------------------------------------------------------------------ KPIs
    def _compute_kpis(
        self,
        *,
        df_lic_mem: pd.DataFrame,
        df_ctr_mem: pd.DataFrame,
        df_disp_mem: pd.DataFrame,
        df_naf_mem: pd.DataFrame,
        df_emp_mem: pd.DataFrame,
        df_forn_mem: pd.DataFrame,
        df_serv_mem: pd.DataFrame,
        df_pncp_comp: pd.DataFrame,
        df_pncp_ctr: pd.DataFrame,
        df_pncp_arqs: pd.DataFrame,
        df_cruz_lic: pd.DataFrame,
        df_cruz_ctr: pd.DataFrame,
        achados: list[AchadoAuditoria],
    ) -> dict[str, Any]:
        conc_lic = int((df_cruz_lic["status_conciliacao"] == "CONCILIADO").sum()) if not df_cruz_lic.empty else 0
        sem_pncp_lic = int((df_cruz_lic["status_conciliacao"] == "SOMENTE_LOCAL_SEM_PNCP").sum()) if not df_cruz_lic.empty else 0
        conc_ctr = int((df_cruz_ctr["status_conciliacao"] == "CONCILIADO").sum()) if not df_cruz_ctr.empty else 0
        sem_pncp_ctr = int((df_cruz_ctr["status_conciliacao"] == "SOMENTE_LOCAL_SEM_PNCP").sum()) if not df_cruz_ctr.empty else 0

        total_lic_mem = len(df_lic_mem)
        taxa_pncp_lic = round((conc_lic / total_lic_mem * 100), 1) if total_lic_mem else 0.0

        return {
            "exercicios": self.exercicios,
            "memory_licitacoes_qtd": total_lic_mem,
            "memory_licitacoes_valor": round(float(df_lic_mem["valor_homologado_num"].sum()), 2) if not df_lic_mem.empty else 0.0,
            "memory_contratos_qtd": len(df_ctr_mem),
            "memory_contratos_valor": round(float(df_ctr_mem["valor_contrato_num"].sum()), 2) if not df_ctr_mem.empty else 0.0,
            "memory_dispensas_qtd": len(df_disp_mem),
            "memory_naf_qtd": len(df_naf_mem),
            "memory_naf_valor": round(float(df_naf_mem["valor_total_num"].sum()), 2) if not df_naf_mem.empty else 0.0,
            "memory_empenhos_qtd": len(df_emp_mem),
            "memory_empenhos_valor": round(float(df_emp_mem["valor_empenho_num"].sum()), 2) if not df_emp_mem.empty else 0.0,
            "memory_fornecedores_qtd": len(df_forn_mem),
            "memory_servidores_qtd": len(df_serv_mem),
            "pncp_contratacoes_qtd": len(df_pncp_comp),
            "pncp_contratacoes_valor_est": round(float(df_pncp_comp["valor_estimado_num"].sum()), 2) if not df_pncp_comp.empty else 0.0,
            "pncp_contratos_qtd": len(df_pncp_ctr),
            "pncp_arquivos_qtd": len(df_pncp_arqs),
            "conciliadas_lic_qtd": conc_lic,
            "sem_pncp_lic_qtd": sem_pncp_lic,
            "taxa_aderencia_pncp_lic_pct": taxa_pncp_lic,
            "conciliados_ctr_qtd": conc_ctr,
            "sem_pncp_ctr_qtd": sem_pncp_ctr,
            "achados_total": len(achados),
            "achados_criticos": sum(1 for a in achados if a.severidade == "CRITICO"),
            "achados_altos": sum(1 for a in achados if a.severidade == "ALTO"),
            "achados_medios": sum(1 for a in achados if a.severidade == "MEDIO"),
        }
