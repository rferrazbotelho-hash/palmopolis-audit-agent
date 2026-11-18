"""Sistema de Análise Crítica e Detecção de Variações Inconsistentes.

Avalia desvios quantitativos, inversões de estágios orçamentários, variações
interanuais abruptas, discrepâncias entre bases governamentais (Memory x PNCP)
e sinais de alerta para verificação documental aprofundada.
"""
from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd
from pydantic import BaseModel, Field

from engine.reconciliador import _norm_text, _only_digits, _to_df, _to_float

log = logging.getLogger("engine.analise_critica")


class AnomaliaCritica(BaseModel):
    codigo: str
    eixo: str
    criticidade: str  # CRITICA | ALTA | MEDIA
    score_risco: int  # 0..100
    base_governo_ref: str
    item_analisado: str
    esperado: str
    observado: str
    variacao_pct: float | None = None
    valor_exposto: float = 0.0
    acao_recomendada: str


class AnaliseCriticaResult(BaseModel):
    model_config = {"arbitrary_types_allowed": True}

    anomalias: list[AnomaliaCritica] = Field(default_factory=list)
    resumo_eixos: dict[str, int] = Field(default_factory=dict)
    dataframes: dict[str, pd.DataFrame] = Field(default_factory=dict)


class AnalisadorCritico:
    """Motor de detecção de variações inconsistentes e outliers."""

    def __init__(
        self,
        memory_data: dict[str, list[dict[str, Any]]],
        pncp_data: dict[str, list[dict[str, Any]]],
        cruzamento_lic: pd.DataFrame | None = None,
        exercicios: list[int] | None = None,
    ) -> None:
        self.mem = memory_data
        self.pncp = pncp_data
        self.cruz_lic = cruzamento_lic if cruzamento_lic is not None else pd.DataFrame()
        self.exercicios = exercicios or [2025, 2026]

    def run(self) -> AnaliseCriticaResult:
        anomalias: list[AnomaliaCritica] = []

        df_var_lic = self._analisar_variacao_licitacoes(anomalias)
        df_orc = self._analisar_estagios_orcamentarios(anomalias)
        df_inter = self._analisar_variacao_interanual(anomalias)
        df_ctr_naf = self._analisar_contratos_vs_naf(anomalias)
        df_itens = self._analisar_itens_pncp(anomalias)
        df_diarias = self._analisar_outliers_diarias(anomalias)

        anomalias.sort(key=lambda a: (a.score_risco, a.valor_exposto), reverse=True)
        df_ranking = pd.DataFrame([a.model_dump() for a in anomalias])

        resumo_eixos: dict[str, int] = {}
        for a in anomalias:
            resumo_eixos[a.eixo] = resumo_eixos.get(a.eixo, 0) + 1

        log.info("Análise crítica concluída: %d variações/inconsistências detectadas.", len(anomalias))
        return AnaliseCriticaResult(
            anomalias=anomalias,
            resumo_eixos=resumo_eixos,
            dataframes={
                "Critica_Ranking": df_ranking,
                "Critica_Var_Valores": df_var_lic,
                "Critica_Orcamentaria": df_orc,
                "Critica_Interanual": df_inter,
                "Critica_Contratos_NAF": df_ctr_naf,
                "Critica_Itens_PNCP": df_itens,
                "Critica_Outliers_Diarias": df_diarias,
            },
        )

    # 1. Variação de Valores (Memory Homologado vs Máximo Estimado e Memory vs PNCP)
    def _analisar_variacao_licitacoes(self, anomalias: list[AnomaliaCritica]) -> pd.DataFrame:
        rows: list[dict[str, Any]] = []
        df_lic = _to_df(self.mem.get("licitacoes", []))
        if not df_lic.empty:
            for r in df_lic.to_dict("records"):
                v_hom = _to_float(r.get("valor_homologado"))
                v_max = _to_float(r.get("valor_maximo_processo"))
                if v_hom > 0 and v_max > 0:
                    var_pct = round((v_hom - v_max) / v_max * 100.0, 2)
                    if var_pct > 15.0 or var_pct < -70.0:
                        tipo = "HOMOLOGADO_ACIMA_ESTIMADO" if var_pct > 15.0 else "DESCONTO_EXTREMO_INEXEQUIBILIDADE"
                        crit = "CRITICA" if var_pct > 50.0 else "ALTA"
                        score = 92 if var_pct > 50.0 else 76
                        rows.append({
                            "origem": "Memory_Interno",
                            "exercicio": r.get("exercicio"),
                            "processo": r.get("numero_licitacao"),
                            "modalidade": r.get("modalidade"),
                            "tipo_inconsistencia": tipo,
                            "valor_referencia": v_max,
                            "valor_observado": v_hom,
                            "variacao_pct": var_pct,
                            "objeto": str(r.get("descricao") or "")[:180],
                        })
                        anomalias.append(AnomaliaCritica(
                            codigo=f"VAR-LIC-{len(anomalias)+1:03d}",
                            eixo="Variação de Valores (Licitação)",
                            criticidade=crit,
                            score_risco=score,
                            base_governo_ref="Lei 14.133/2021, Art. 23 e Art. 59, III/IV",
                            item_analisado=f"Licitação {r.get('numero_licitacao')} ({r.get('modalidade')})",
                            esperado=f"Valor Máximo R$ {v_max:,.2f}",
                            observado=f"Homologado R$ {v_hom:,.2f}",
                            variacao_pct=var_pct,
                            valor_exposto=abs(v_hom - v_max),
                            acao_recomendada="Conferir mapa de apuração, termo de homologação e justificativa de preço/exequibilidade.",
                        ))

        if not self.cruz_lic.empty:
            conc = self.cruz_lic[self.cruz_lic["status_conciliacao"] == "CONCILIADO"]
            for r in conc.to_dict("records"):
                vm, vp = float(r.get("valor_memory") or 0), float(r.get("valor_pncp") or 0)
                if vm > 0 and vp > 0:
                    var_pct = round((vm - vp) / vp * 100.0, 2)
                    if abs(var_pct) > 20.0 and abs(vm - vp) > 10_000.0:
                        rows.append({
                            "origem": "Memory_x_PNCP",
                            "exercicio": r.get("exercicio"),
                            "processo": r.get("numero_memory"),
                            "modalidade": r.get("modalidade_memory"),
                            "tipo_inconsistencia": "DIVERGENCIA_MEMORY_PNCP",
                            "valor_referencia": vp,
                            "valor_observado": vm,
                            "variacao_pct": var_pct,
                            "objeto": str(r.get("objeto_memory") or "")[:180],
                        })
                        anomalias.append(AnomaliaCritica(
                            codigo=f"VAR-PNCP-{len(anomalias)+1:03d}",
                            eixo="Divergência entre Bases (Memory × PNCP)",
                            criticidade="ALTA",
                            score_risco=80,
                            base_governo_ref="PNCP (Gov.br) × Portal Transparência Local",
                            item_analisado=f"Processo {r.get('numero_memory')} | {r.get('numero_controle_pncp')}",
                            esperado=f"PNCP R$ {vp:,.2f}",
                            observado=f"Memory R$ {vm:,.2f}",
                            variacao_pct=var_pct,
                            valor_exposto=abs(vm - vp),
                            acao_recomendada="Verificar se houve retificação de homologação ou falha de integração com o PNCP.",
                        ))
        return pd.DataFrame(rows)

    # 2. Inconsistência Orçamentária e de Estágios da Despesa (Lei 4.320/1964)
    def _analisar_estagios_orcamentarios(self, anomalias: list[AnomaliaCritica]) -> pd.DataFrame:
        rows: list[dict[str, Any]] = []
        for dataset, nome_col in (
            ("despesa_unidade", "descricao_unidade"),
            ("despesa_funcao", "descricao_funcao"),
            ("despesa_natureza", "descricao"),
            ("fornecedores", "fornecedor_nome"),
        ):
            df = _to_df(self.mem.get(dataset, []))
            if df.empty:
                continue
            for r in df.to_dict("records"):
                dot = _to_float(r.get("dotacao_atualizada"))
                emp = _to_float(r.get("valor_empenhado"))
                liq = _to_float(r.get("valor_liquidado"))
                pag = _to_float(r.get("valor_pago"))
                ent = str(r.get(nome_col) or "-")[:80]
                ano = r.get("exercicio")

                if dot > 0 and emp > dot * 1.001:
                    var_pct = round((emp - dot) / dot * 100.0, 2)
                    rows.append({"dataset": dataset, "exercicio": ano, "item": ent, "anomalia": "EMPENHO_ACIMA_DOTACAO",
                                 "ref": dot, "obs": emp, "variacao_pct": var_pct})
                    anomalias.append(AnomaliaCritica(
                        codigo=f"ORC-DOT-{len(anomalias)+1:03d}",
                        eixo="Execução Orçamentária (Lei 4.320/64)",
                        criticidade="CRITICA",
                        score_risco=95,
                        base_governo_ref="Lei 4.320/1964, Art. 59 (Limite de Crédito Orçamentário)",
                        item_analisado=f"{dataset} ({ano}): {ent}",
                        esperado=f"Dotação Atualizada R$ {dot:,.2f}",
                        observado=f"Empenhado R$ {emp:,.2f}",
                        variacao_pct=var_pct,
                        valor_exposto=emp - dot,
                        acao_recomendada="Auditar decretos de créditos adicionais e abertura de suplementação no SICOM/TCE-MG.",
                    ))

                if liq > emp + 1.0 and emp > 0:
                    rows.append({"dataset": dataset, "exercicio": ano, "item": ent, "anomalia": "LIQUIDADO_ACIMA_EMPENHADO",
                                 "ref": emp, "obs": liq, "variacao_pct": round((liq - emp) / emp * 100, 2)})
                    anomalias.append(AnomaliaCritica(
                        codigo=f"ORC-LIQ-{len(anomalias)+1:03d}",
                        eixo="Estágios da Despesa (Lei 4.320/64)",
                        criticidade="ALTA",
                        score_risco=85,
                        base_governo_ref="Lei 4.320/1964, Arts. 60-63",
                        item_analisado=f"{dataset} ({ano}): {ent}",
                        esperado=f"Empenhado R$ {emp:,.2f}",
                        observado=f"Liquidado R$ {liq:,.2f}",
                        variacao_pct=round((liq - emp) / emp * 100, 2),
                        valor_exposto=liq - emp,
                        acao_recomendada="Verificar estornos de empenho ou inconsistência contábil na base de transparência.",
                    ))

                if pag > liq + 1.0 and liq > 0:
                    rows.append({"dataset": dataset, "exercicio": ano, "item": ent, "anomalia": "PAGO_ACIMA_LIQUIDADO",
                                 "ref": liq, "obs": pag, "variacao_pct": round((pag - liq) / liq * 100, 2)})
                    anomalias.append(AnomaliaCritica(
                        codigo=f"ORC-PAG-{len(anomalias)+1:03d}",
                        eixo="Estágios da Despesa (Lei 4.320/64)",
                        criticidade="CRITICA",
                        score_risco=93,
                        base_governo_ref="Lei 4.320/1964, Arts. 62-64 (Pagamento sem Liquidação)",
                        item_analisado=f"{dataset} ({ano}): {ent}",
                        esperado=f"Liquidado R$ {liq:,.2f}",
                        observado=f"Pago R$ {pag:,.2f}",
                        variacao_pct=round((pag - liq) / liq * 100, 2),
                        valor_exposto=pag - liq,
                        acao_recomendada="Apurar pagamento antecipado ou falha de registro de liquidação.",
                    ))
        return pd.DataFrame(rows)

    # 3. Variação Interanual Abrupta (2025 vs 2026)
    def _analisar_variacao_interanual(self, anomalias: list[AnomaliaCritica]) -> pd.DataFrame:
        if len(self.exercicios) < 2:
            return pd.DataFrame()
        ano_a, ano_b = min(self.exercicios), max(self.exercicios)
        rows: list[dict[str, Any]] = []

        for dataset, key_col, name_col in (
            ("despesa_funcao", "codigo_funcao", "descricao_funcao"),
            ("despesa_natureza", "id_elemento", "descricao"),
        ):
            df = _to_df(self.mem.get(dataset, []))
            if df.empty or key_col not in df.columns:
                continue
            df["emp_num"] = df["valor_empenhado"].apply(_to_float)
            piv = df.pivot_table(index=[key_col, name_col], columns="exercicio", values="emp_num", aggfunc="sum", fill_value=0.0).reset_index()
            if ano_a not in piv.columns or ano_b not in piv.columns:
                continue
            for r in piv.to_dict("records"):
                va, vb = float(r[ano_a]), float(r[ano_b])
                if va >= 50_000.0 and vb > 0:
                    var_pct = round((vb - va) / va * 100.0, 2)
                    if var_pct >= 150.0 or var_pct <= -80.0:
                        rows.append({
                            "dataset": dataset,
                            "codigo": r[key_col],
                            "descricao": r[name_col],
                            f"empenhado_{ano_a}": va,
                            f"empenhado_{ano_b}": vb,
                            "variacao_pct": var_pct,
                        })
                        anomalias.append(AnomaliaCritica(
                            codigo=f"INT-VAR-{len(anomalias)+1:03d}",
                            eixo=f"Variação Interanual ({ano_a} × {ano_b})",
                            criticidade="MEDIA" if var_pct < 300 else "ALTA",
                            score_risco=68 if var_pct < 300 else 82,
                            base_governo_ref="SICONFI / LOA Comparada (Execução Anual)",
                            item_analisado=f"{r[key_col]} - {str(r[name_col])[:60]}",
                            esperado=f"{ano_a}: R$ {va:,.2f}",
                            observado=f"{ano_b}: R$ {vb:,.2f}",
                            variacao_pct=var_pct,
                            valor_exposto=abs(vb - va),
                            acao_recomendada="Avaliar motivação orçamentária da variação abrupta entre exercícios.",
                        ))
        return pd.DataFrame(rows)

    # 4. Contratos x NAFs (Extrapolação > 25% — Art. 125 da Lei 14.133/2021)
    def _analisar_contratos_vs_naf(self, anomalias: list[AnomaliaCritica]) -> pd.DataFrame:
        df_ctr = _to_df(self.mem.get("contratos", []))
        df_naf = _to_df(self.mem.get("naf", []))
        if df_ctr.empty or df_naf.empty or "id_contrato" not in df_naf.columns:
            return pd.DataFrame()

        df_ctr["id_ctr_str"] = df_ctr["id_contrato"].astype(str)
        df_ctr["valor_ctr_num"] = df_ctr["valor_contrato"].apply(_to_float)
        df_naf["id_ctr_str"] = df_naf["id_contrato"].fillna("").astype(str)
        df_naf["valor_naf_num"] = df_naf["valor_total"].apply(_to_float)

        naf_grp = df_naf[df_naf["id_ctr_str"] != ""].groupby("id_ctr_str")["valor_naf_num"].agg(["count", "sum"]).reset_index()
        naf_grp.columns = ["id_ctr_str", "qtd_nafs", "soma_nafs"]

        merged = df_ctr.merge(naf_grp, on="id_ctr_str", how="inner")
        rows: list[dict[str, Any]] = []
        for r in merged.to_dict("records"):
            vc, vn = float(r["valor_ctr_num"]), float(r["soma_nafs"])
            if vc > 0 and vn > vc * 1.25:
                var_pct = round((vn - vc) / vc * 100.0, 2)
                rows.append({
                    "id_contrato": r["id_ctr_str"],
                    "numero_contrato": r.get("numero_contrato"),
                    "exercicio": r.get("exercicio"),
                    "valor_contrato": vc,
                    "qtd_nafs": int(r["qtd_nafs"]),
                    "soma_nafs": vn,
                    "excedente_pct": var_pct,
                    "objeto": str(r.get("objeto") or "")[:180],
                })
                anomalias.append(AnomaliaCritica(
                    codigo=f"CTR-NAF-{len(anomalias)+1:03d}",
                    eixo="Execução Contratual (Contrato × NAF)",
                    criticidade="CRITICA",
                    score_risco=90,
                    base_governo_ref="Lei 14.133/2021, Art. 125 (Limite de 25% de Acréscimo)",
                    item_analisado=f"Contrato {r.get('numero_contrato')} (ID {r['id_ctr_str']})",
                    esperado=f"Contrato R$ {vc:,.2f} (máx +25%: R$ {vc*1.25:,.2f})",
                    observado=f"{int(r['qtd_nafs'])} NAFs somando R$ {vn:,.2f}",
                    variacao_pct=var_pct,
                    valor_exposto=vn - vc,
                    acao_recomendada="Verificar termos aditivos publicados que justifiquem o excedente acima de 25%.",
                ))
        return pd.DataFrame(rows)

    # 5. Inconsistências em Itens do PNCP (preço zerado, homologado > estimado, desconto extremo)
    def _analisar_itens_pncp(self, anomalias: list[AnomaliaCritica]) -> pd.DataFrame:
        df_it = _to_df(self.pncp.get("itens", []))
        if df_it.empty:
            return df_it
        rows: list[dict[str, Any]] = []
        for r in df_it.to_dict("records"):
            v_est = _to_float(r.get("valorUnitarioEstimado"))
            v_hom = _to_float(r.get("valorUnitarioHomologado"))
            if v_est <= 0 and not r.get("orcamentoSigiloso", False):
                rows.append({
                    "numeroControlePNCP": r.get("numeroControlePNCP"),
                    "numeroItem": r.get("numeroItem"),
                    "inconsistencia": "VALOR_ESTIMADO_ZERO_SEM_SIGILO",
                    "valor_est": v_est,
                    "valor_hom": v_hom,
                    "variacao_pct": None,
                    "descricao": str(r.get("descricao") or "")[:150],
                })
            elif v_est > 0 and v_hom > 0:
                var_pct = round((v_hom - v_est) / v_est * 100.0, 2)
                if var_pct > 5.0 or var_pct < -75.0:
                    rows.append({
                        "numeroControlePNCP": r.get("numeroControlePNCP"),
                        "numeroItem": r.get("numeroItem"),
                        "inconsistencia": "HOMOLOGADO_ACIMA_ESTIMADO" if var_pct > 5.0 else "DESCONTO_EXTREMO_ITEM",
                        "valor_est": v_est,
                        "valor_hom": v_hom,
                        "variacao_pct": var_pct,
                        "descricao": str(r.get("descricao") or "")[:150],
                    })

        df_out = pd.DataFrame(rows)
        if not df_out.empty:
            acima = df_out[df_out["inconsistencia"] == "HOMOLOGADO_ACIMA_ESTIMADO"]
            if not acima.empty:
                anomalias.append(AnomaliaCritica(
                    codigo=f"PNCP-IT-{len(anomalias)+1:03d}",
                    eixo="Itens PNCP (Preço Homologado × Estimado)",
                    criticidade="ALTA",
                    score_risco=83,
                    base_governo_ref="Lei 14.133/2021, Art. 59, III (Sobrepreço em Item)",
                    item_analisado=f"{len(acima)} itens PNCP com valor unitário homologado > estimado",
                    esperado="Homologado <= Estimado",
                    observado=f"Máx variação: +{acima['variacao_pct'].max():.1f}%",
                    variacao_pct=float(acima["variacao_pct"].max()),
                    valor_exposto=float((acima["valor_hom"] - acima["valor_est"]).sum()),
                    acao_recomendada="Inspecionar atas de julgamento e aceitação de preço acima do orçamento de referência.",
                ))
            zero = df_out[df_out["inconsistencia"] == "VALOR_ESTIMADO_ZERO_SEM_SIGILO"]
            if not zero.empty:
                anomalias.append(AnomaliaCritica(
                    codigo=f"PNCP-IT-{len(anomalias)+1:03d}",
                    eixo="Itens PNCP (Integridade do Orçamento)",
                    criticidade="MEDIA",
                    score_risco=62,
                    base_governo_ref="Lei 14.133/2021, Art. 18, IV e Art. 24",
                    item_analisado=f"{len(zero)} itens no PNCP sem valor estimado e sem marcação de sigilo",
                    esperado="Valor estimado > 0 ou orçamento sigiloso declarado",
                    observado=f"{len(zero)} itens com valor estimado = 0",
                    acao_recomendada="Conferir se a pesquisa de preços foi publicada corretamente no PNCP.",
                ))
        return df_out

    # 6. Outliers Estatísticos em Diárias (IQR)
    def _analisar_outliers_diarias(self, anomalias: list[AnomaliaCritica]) -> pd.DataFrame:
        df_d = _to_df(self.mem.get("diarias", []))
        if df_d.empty or "nome_servidor" not in df_d.columns:
            return pd.DataFrame()
        df_d["valor_num"] = df_d["valor_pago"].apply(_to_float)
        grp = (
            df_d.groupby(["exercicio", "nome_servidor", "unidade_orcamentaria"], dropna=False)["valor_num"]
            .agg(["count", "sum"])
            .reset_index()
            .rename(columns={"count": "qtd_diarias", "sum": "total_pago"})
        )
        if len(grp) < 4:
            return grp
        q1, q3 = grp["total_pago"].quantile(0.25), grp["total_pago"].quantile(0.75)
        iqr = q3 - q1
        limite = q3 + 1.5 * iqr
        outliers = grp[grp["total_pago"] > max(limite, 3000.0)].sort_values("total_pago", ascending=False).copy()
        outliers["limite_iqr"] = round(limite, 2)
        if not outliers.empty:
            top = outliers.iloc[0]
            anomalias.append(AnomaliaCritica(
                codigo=f"DIA-OUT-{len(anomalias)+1:03d}",
                eixo="Concentração Estatística (Diárias)",
                criticidade="MEDIA",
                score_risco=65,
                base_governo_ref="Controle de Pessoal / Princípio da Economicidade",
                item_analisado=f"{len(outliers)} servidores acima do limite IQR (R$ {limite:,.2f})",
                esperado=f"Mediana/Limite IQR R$ {limite:,.2f}",
                observado=f"Maior acumulado: {top['nome_servidor']} (R$ {top['total_pago']:,.2f})",
                valor_exposto=float(outliers["total_pago"].sum()),
                acao_recomendada="Conferir comprovação de deslocamentos, portarias de concessão e relatórios de viagem.",
            ))
        return outliers
