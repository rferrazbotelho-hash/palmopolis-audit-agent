"""Fiscal de Contas Públicas — Especialista em Irregularidades Governamentais e Procedimentais.

Consolida os achados de conformidade legal (Lei 14.133/2021, LAI 12.527/2011) e as
variações inconsistentes (Lei 4.320/1964, PNCP x Memory, Contrato x NAF, Diárias)
em um Relatório Técnico Completo de Apontamentos de Controle Externo, com
enquadramento normativo, risco ao erário e determinações corretivas ao gestor.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
from jinja2 import Template
from pydantic import BaseModel, Field

from config import OUTPUT_DIR, settings
from engine.analise_critica import AnaliseCriticaResult
from engine.reconciliador import AuditResult

log = logging.getLogger("engine.fiscal_contas")


class ApontamentoControleExterno(BaseModel):
    codigo: str
    categoria: str
    gravidade: str  # IRREGULARIDADE_GRAVE | RESSALVA_RELEVANTE | RECOMENDACAO_CONTROLE
    base_legal: str
    titulo: str
    situacao_encontrada: str
    risco_procedimental: str
    quantidade_ocorrencias: int = 0
    valor_envolvido: float = 0.0
    evidencias_principais: list[str] = Field(default_factory=list)
    determinacao_ao_gestor: str
    prazo_sugerido_dias: int = 15


class RelatorioFiscalContas(BaseModel):
    entidade: str
    cnpj: str
    exercicios: list[int]
    gerado_em: str
    parecer_sintese: str
    total_apontamentos: int
    graves: int
    ressalvas: int
    recomendacoes: int
    valor_total_envolvido: float
    apontamentos: list[ApontamentoControleExterno] = Field(default_factory=list)


def _brl(v: float) -> str:
    return "R$ " + f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


class FiscalContasPublicas:
    """Agente especialista que transforma achados e anomalias em apontamentos formais de Controle Externo."""

    def __init__(self, audit: AuditResult, critica: AnaliseCriticaResult) -> None:
        self.audit = audit
        self.critica = critica

    def emitir_relatorio(self) -> RelatorioFiscalContas:
        apontamentos: list[ApontamentoControleExterno] = []
        ach_map = {a.codigo: a for a in self.audit.achados}

        # 1. Eficácia contratual e publicidade no PNCP (Art. 94 - Contratos)
        if "ACH-03" in ach_map:
            a = ach_map["ACH-03"]
            apontamentos.append(ApontamentoControleExterno(
                codigo="AP-001",
                categoria="Licitações, Contratos e Publicidade (PNCP)",
                gravidade="IRREGULARIDADE_GRAVE",
                base_legal="Lei Federal nº 14.133/2021, Art. 94, caput e incisos I e II; CF/88, Art. 37, caput",
                titulo="Ausência de divulgação de contratos no PNCP (condição legal de eficácia)",
                situacao_encontrada=(
                    f"Identificados {a.quantidade} contratos/aditivos no Portal da Transparência local (Memory) "
                    f"sem registro correspondente na API de consulta de contratos do PNCP."
                ),
                risco_procedimental=(
                    "Nos termos expressos do Art. 94 da Lei nº 14.133/2021, a divulgação no PNCP é condição "
                    "indispensável para a eficácia do contrato e de seus aditamentos. Pagamentos executados sem "
                    "essa publicação sujeitam-se à glosa e responsabilização do ordenador de despesas."
                ),
                quantidade_ocorrencias=a.quantidade,
                valor_envolvido=a.valor_envolvido,
                evidencias_principais=[x.strip() for x in a.evidencia.split(";") if x.strip()][:10],
                determinacao_ao_gestor=(
                    "Providenciar a imediata integração/envio dos instrumentos contratuais ao PNCP, comprovar as "
                    "justificativas técnicas de eventual regime anterior (Lei 8.666/93) e apresentar planilha de "
                    "enquadramento por contrato."
                ),
                prazo_sugerido_dias=15,
            ))

        # 2. Ausência de divulgação de licitações no PNCP (Arts. 54 e 94)
        if "ACH-01" in ach_map:
            a = ach_map["ACH-01"]
            apontamentos.append(ApontamentoControleExterno(
                codigo="AP-002",
                categoria="Licitações, Contratos e Publicidade (PNCP)",
                gravidade="IRREGULARIDADE_GRAVE",
                base_legal="Lei Federal nº 14.133/2021, Arts. 54 e 174; Lei nº 12.527/2011, Art. 8º",
                titulo="Processos licitatórios locais sem publicação no Portal Nacional de Contratações Públicas",
                situacao_encontrada=(
                    f"{a.quantidade} processos registrados no sistema Memory não possuem publicação localizada no PNCP "
                    f"(taxa de aderência atual de {self.audit.kpis.get('taxa_aderencia_pncp_lic_pct', 0)}% nas licitações)."
                ),
                risco_procedimental=(
                    "Restrição à competitividade, déficit de controle social e descumprimento da publicidade "
                    "nacional obrigatória dos atos convocatórios."
                ),
                quantidade_ocorrencias=a.quantidade,
                valor_envolvido=a.valor_envolvido,
                evidencias_principais=[x.strip() for x in a.evidencia.split(";") if x.strip()][:10],
                determinacao_ao_gestor=(
                    "Apresentar relação dos processos regidos pela Lei 14.133/2021 com seus respectivos "
                    "números de controle PNCP e corrigir a rotina de exportação da plataforma de compras."
                ),
                prazo_sugerido_dias=15,
            ))

        # 3. Estouro de Dotação Orçamentária (Lei 4.320/1964, Art. 59)
        orc_dot = [x for x in self.critica.anomalias if x.codigo.startswith("ORC-DOT")]
        if orc_dot:
            apontamentos.append(ApontamentoControleExterno(
                codigo="AP-003",
                categoria="Execução Orçamentária e Financeira",
                gravidade="IRREGULARIDADE_GRAVE",
                base_legal="Lei Federal nº 4.320/1964, Art. 59; CF/88, Art. 167, II; LRF (LC 101/2000), Art. 16",
                titulo="Realização de despesa empenhada acima do limite da dotação orçamentária atualizada",
                situacao_encontrada=(
                    f"Detectadas {len(orc_dot)} ocorrências em que o valor empenhado supera a dotação "
                    f"atualizada publicada no portal de transparência."
                ),
                risco_procedimental=(
                    "Realização de despesa sem crédito orçamentário suficiente configura ilegalidade financeira "
                    "grave e pode ensejar rejeição de contas e crime contra as finanças públicas."
                ),
                quantidade_ocorrencias=len(orc_dot),
                valor_envolvido=sum(x.valor_exposto for x in orc_dot),
                evidencias_principais=[f"{x.item_analisado} ({x.esperado} vs {x.observado})" for x in orc_dot[:8]],
                determinacao_ao_gestor=(
                    "Encaminhar os decretos de abertura de créditos adicionais (suplementares/especiais) e "
                    "balancetes do SICOM/TCE-MG que comprovem lastro orçamentário prévio aos empenhos."
                ),
                prazo_sugerido_dias=10,
            ))

        # 4. Inversão de estágios da despesa (Liquidado > Empenhado / Pago > Liquidado)
        orc_est = [x for x in self.critica.anomalias if x.codigo.startswith(("ORC-LIQ", "ORC-PAG"))]
        if orc_est:
            apontamentos.append(ApontamentoControleExterno(
                codigo="AP-004",
                categoria="Execução Orçamentária e Financeira",
                gravidade="IRREGULARIDADE_GRAVE",
                base_legal="Lei Federal nº 4.320/1964, Arts. 60 a 64",
                titulo="Inversão dos estágios legais da despesa pública",
                situacao_encontrada=(
                    f"Identificadas {len(orc_est)} ocorrências com valor liquidado superior ao empenhado ou "
                    f"valor pago superior ao liquidado."
                ),
                risco_procedimental=(
                    "Pagamento sem prévia liquidação regular viola a ordem cronológica e a comprovação de "
                    "entrega do bem ou prestação do serviço."
                ),
                quantidade_ocorrencias=len(orc_est),
                valor_envolvido=sum(x.valor_exposto for x in orc_est),
                evidencias_principais=[f"{x.item_analisado}: {x.observado}" for x in orc_est[:8]],
                determinacao_ao_gestor=(
                    "Auditar os lançamentos contábeis e comprovar notas fiscais/atestos de recebimento para "
                    "todas as unidades/fornecedores listados."
                ),
                prazo_sugerido_dias=10,
            ))

        # 5. Variações extremas entre valor máximo estimado e valor homologado (sobrepreço/erro)
        var_lic = [x for x in self.critica.anomalias if x.codigo.startswith("VAR-LIC")]
        if var_lic:
            crit_lic = [x for x in var_lic if x.variacao_pct and x.variacao_pct > 50.0]
            alvo = crit_lic or var_lic
            apontamentos.append(ApontamentoControleExterno(
                codigo="AP-005",
                categoria="Planejamento e Formação de Preços",
                gravidade="IRREGULARIDADE_GRAVE" if crit_lic else "RESSALVA_RELEVANTE",
                base_legal="Lei Federal nº 14.133/2021, Arts. 18, IV, 23 e 59, III e IV",
                titulo="Distorções severas entre orçamento máximo estimado e valor homologado",
                situacao_encontrada=(
                    f"{len(var_lic)} licitações apresentaram variação anômala entre o valor máximo do processo "
                    f"e o valor homologado ({len(crit_lic)} com homologação > 50% acima do máximo registrado)."
                ),
                risco_procedimental=(
                    "Forte indício de falha grave na pesquisa de preços, erro de registro cadastral em "
                    "transparência ou adjudicação acima do preço de referência."
                ),
                quantidade_ocorrencias=len(alvo),
                valor_envolvido=sum(x.valor_exposto for x in alvo),
                evidencias_principais=[
                    f"{x.item_analisado}: {x.esperado} vs {x.observado} ({x.variacao_pct:+.1f}%)"
                    for x in alvo[:8]
                ],
                determinacao_ao_gestor=(
                    "Apresentar pesquisa de preços (Art. 23), parecer jurídico e ata de julgamento/homologação "
                    "dos processos críticos, especialmente Pregão 90/2025, Concorrência 105/2025 e Adesão 105/2026."
                ),
                prazo_sugerido_dias=15,
            ))

        # 6. Extrapolação de Contratos via NAFs (> 25% - Art. 125)
        ctr_naf = [x for x in self.critica.anomalias if x.codigo.startswith("CTR-NAF")]
        if ctr_naf:
            apontamentos.append(ApontamentoControleExterno(
                codigo="AP-006",
                categoria="Gestão e Execução Contratual",
                gravidade="IRREGULARIDADE_GRAVE",
                base_legal="Lei Federal nº 14.133/2021, Arts. 124, 125 e 132",
                titulo="Execução por NAFs superior a 125% do valor contratual registrado",
                situacao_encontrada=(
                    f"{len(ctr_naf)} contratos apresentam somatório de Notas de Autorização de Fornecimento (NAFs) "
                    f"superior ao limite legal de acréscimo de 25% sobre o valor contratado."
                ),
                risco_procedimental=(
                    "Execução contratual sem cobertura de termo aditivo formalizado ou burla ao limite legal "
                    "de alteração quantitativa (Art. 125)."
                ),
                quantidade_ocorrencias=len(ctr_naf),
                valor_envolvido=sum(x.valor_exposto for x in ctr_naf),
                evidencias_principais=[f"{x.item_analisado}: {x.esperado} | {x.observado}" for x in ctr_naf[:8]],
                determinacao_ao_gestor=(
                    "Apresentar todos os termos aditivos e apostilamentos vinculados aos contratos apontados ou "
                    "justificar eventual vínculo cruzado de NAFs em sistema."
                ),
                prazo_sugerido_dias=15,
            ))

        # 7. Contratação Direta / Art. 75 (acima do limite ou risco de fracionamento)
        if "ACH-06" in ach_map:
            a = ach_map["ACH-06"]
            apontamentos.append(ApontamentoControleExterno(
                codigo="AP-007",
                categoria="Contratação Direta e Fracionamento",
                gravidade="IRREGULARIDADE_GRAVE",
                base_legal="Lei Federal nº 14.133/2021, Art. 75, I, II e §1º; Decreto 12.343/2024 e Decreto 12.807/2025",
                titulo="Dispensas por valor ou acumulados anuais acima do limite legal (risco de fracionamento)",
                situacao_encontrada=(
                    f"Identificados {a.quantidade} processos ou acumulados anuais por fornecedor em compra direta "
                    f"que excedem o teto vigente do Art. 75."
                ),
                risco_procedimental=(
                    "Fuga ao procedimento licitatório obrigatório e fracionamento indevido de despesa da mesma "
                    "natureza/ramo de atividade no exercício."
                ),
                quantidade_ocorrencias=a.quantidade,
                valor_envolvido=a.valor_envolvido,
                evidencias_principais=[x.strip() for x in a.evidencia.split(";") if x.strip()][:10],
                determinacao_ao_gestor=(
                    "Justificar o enquadramento legal específico (ex.: emergência/calamidade vs baixo valor) e "
                    "apresentar controle de fracionamento por subelemento/ramo de atividade."
                ),
                prazo_sugerido_dias=15,
            ))

        # 8. Divergência de valores entre bases governamentais (Memory x PNCP)
        var_pncp = [x for x in self.critica.anomalias if x.codigo.startswith("VAR-PNCP")]
        if var_pncp or "ACH-02" in ach_map:
            qtd = len(var_pncp) + (ach_map["ACH-02"].quantidade if "ACH-02" in ach_map else 0)
            val = sum(x.valor_exposto for x in var_pncp) + (ach_map["ACH-02"].valor_envolvido if "ACH-02" in ach_map else 0.0)
            apontamentos.append(ApontamentoControleExterno(
                codigo="AP-008",
                categoria="Integridade entre Bases Governamentais",
                gravidade="RESSALVA_RELEVANTE",
                base_legal="Lei nº 12.527/2011 (LAI), Art. 8º, §3º, II; Lei 14.133/2021, Art. 174",
                titulo="Divergências de valores e espelhamento entre Portal Memory e PNCP",
                situacao_encontrada=(
                    f"{len(var_pncp)} processos conciliados exibem diferença financeira > 20% entre Memory e PNCP, "
                    f"além de processos no PNCP sem espelhamento local."
                ),
                risco_procedimental=(
                    "Inconsistência informacional entre bases oficiais prejudica a rastreabilidade e a "
                    "confiabilidade das demonstrações enviadas aos órgãos de controle."
                ),
                quantidade_ocorrencias=qtd,
                valor_envolvido=val,
                evidencias_principais=[f"{x.item_analisado}: {x.esperado} vs {x.observado}" for x in var_pncp[:8]],
                determinacao_ao_gestor=(
                    "Conciliar os valores homologados entre o sistema de gestão municipal, o Portal iLAI e o PNCP."
                ),
                prazo_sugerido_dias=20,
            ))

        # 9. Moralidade e Impedimentos (Fornecedor x Servidor - Arts. 9º e 14)
        if "ACH-08" in ach_map:
            a = ach_map["ACH-08"]
            apontamentos.append(ApontamentoControleExterno(
                codigo="AP-009",
                categoria="Moralidade Administrativa e Impedimentos",
                gravidade="RESSALVA_RELEVANTE",
                base_legal="Lei Federal nº 14.133/2021, Art. 9º, §1º e Art. 14, IV; CF/88, Art. 37, caput",
                titulo="Homonímia exata entre fornecedores pagos e servidores municipais",
                situacao_encontrada=(
                    f"Cruzamento nominal apontou {a.quantidade} fornecedores com nome idêntico ao de servidores "
                    f"constantes na folha municipal (CPFs parcialmente mascarados na LAI)."
                ),
                risco_procedimental=(
                    "Possível contratação ou pagamento comercial a agente público em exercício, vedada pelo "
                    "Art. 9º, §1º e Art. 14, IV da Lei 14.133/2021 (ou eventual registro de diária/indenização na base de fornecedores)."
                ),
                quantidade_ocorrencias=a.quantidade,
                valor_envolvido=a.valor_envolvido,
                evidencias_principais=[x.strip() for x in a.evidencia.split(";") if x.strip()][:8],
                determinacao_ao_gestor=(
                    "Realizar batimento de CPF completo em folha e contabilidade, segregando eventuais reembolsos/diárias "
                    "de fornecimentos vedados."
                ),
                prazo_sugerido_dias=20,
            ))

        # 10. Opacidade contratual (Fornecedor/CNPJ nulo) e Déficit LAI
        if "ACH-05" in ach_map or "ACH-10" in ach_map:
            a5 = ach_map.get("ACH-05")
            a10 = ach_map.get("ACH-10")
            qtd = (a5.quantidade if a5 else 0) + (a10.quantidade if a10 else 0)
            val = a5.valor_envolvido if a5 else 0.0
            evs = []
            if a5:
                evs.append(f"Contratos sem fornecedor/CPF-CNPJ: {a5.quantidade} ({a5.evidencia[:120]})")
            if a10:
                evs.append(f"Lacunas LAI/Portal: {a10.quantidade} ({a10.evidencia[:140]})")
            apontamentos.append(ApontamentoControleExterno(
                codigo="AP-010",
                categoria="Transparência Ativa e Controle Social (LAI)",
                gravidade="RESSALVA_RELEVANTE",
                base_legal="Lei nº 12.527/2011, Art. 8º, §1º, IV e §3º; LC 131/2009; Lei 14.133/2021, Art. 54",
                titulo="Omissão de identificação de contratados em contratos e lacunas de transparência ativa",
                situacao_encontrada=(
                    "Todos os contratos retornados no endpoint Memory estão com campos 'fornecedor' e 'cpf_cnpj' nulos; "
                    "adicionalmente, há endpoints de 2025 vazios/erro (servidores/2025 HTTP 500) e seções vazias no portal institucional "
                    "(Licitações, Decretos, Leis e Diário Oficial)."
                ),
                risco_procedimental=(
                    "Impede a fiscalização cidadã e o controle de impedimentos cadastrais (CEIS/CNEP) por ausência de CNPJ/CPF."
                ),
                quantidade_ocorrencias=qtd,
                valor_envolvido=val,
                evidencias_principais=evs,
                determinacao_ao_gestor=(
                    "Habilitar a exibição integral de razão social e CNPJ/CPF nos contratos do iLAI e regularizar "
                    "as publicações de Diário Oficial, Decretos, Leis e Licitações no portal institucional."
                ),
                prazo_sugerido_dias=15,
            ))

        # 11. Variação Interanual e Diárias (Recomendações de Controle)
        inter = [x for x in self.critica.anomalias if x.codigo.startswith("INT-VAR")]
        diarias = [x for x in self.critica.anomalias if x.codigo.startswith("DIA-OUT")]
        if inter or diarias:
            apontamentos.append(ApontamentoControleExterno(
                codigo="AP-011",
                categoria="Gestão Orçamentária e Pessoal",
                gravidade="RECOMENDACAO_CONTROLE",
                base_legal="CF/88, Art. 37 (Eficiência/Economicidade); LRF Art. 1º, §1º",
                titulo="Variações interanuais abruptas (2025 × 2026) e concentração atípica de diárias",
                situacao_encontrada=(
                    f"{len(inter)} dotações/naturezas com variação >= +150% ou <= -80% entre 2025 e 2026; "
                    f"{len(diarias)} alerta estatístico de concentração de diárias por servidor."
                ),
                risco_procedimental="Necessidade de monitoramento contínuo de planejamento orçamentário e despesas com viagens.",
                quantidade_ocorrencias=len(inter) + len(diarias),
                valor_envolvido=sum(x.valor_exposto for x in inter + diarias),
                evidencias_principais=[f"{x.item_analisado}: {x.observado}" for x in (inter + diarias)[:8]],
                determinacao_ao_gestor="Documentar motivação técnica das variações orçamentárias e relatórios de viagem.",
                prazo_sugerido_dias=30,
            ))

        graves = sum(1 for x in apontamentos if x.gravidade == "IRREGULARIDADE_GRAVE")
        ressalvas = sum(1 for x in apontamentos if x.gravidade == "RESSALVA_RELEVANTE")
        recs = sum(1 for x in apontamentos if x.gravidade == "RECOMENDACAO_CONTROLE")

        parecer = (
            f"CONCLUSÃO TÉCNICA PRELIMINAR: Diante das {graves} irregularidade(s) grave(s) e {ressalvas} "
            f"ressalva(s) relevante(s) apuradas nos exercícios de {', '.join(map(str, self.audit.kpis.get('exercicios', [])))}, "
            f"recomenda-se a INSTAURAÇÃO DE DILIGÊNCIA / CITAÇÃO DO GESTOR para saneamento documental "
            f"e regularização imediata dos registros no PNCP, no Portal iLAI e no SICOM/TCE-MG."
            if graves > 0
            else "CONCLUSÃO TÉCNICA PRELIMINAR: Sem irregularidades graves detectadas no recorte analisado."
        )

        return RelatorioFiscalContas(
            entidade=settings.audit_entidade_nome,
            cnpj=settings.audit_cnpj,
            exercicios=self.audit.kpis.get("exercicios", [2025, 2026]),
            gerado_em=datetime.now().strftime("%d/%m/%Y %H:%M"),
            parecer_sintese=parecer,
            total_apontamentos=len(apontamentos),
            graves=graves,
            ressalvas=ressalvas,
            recomendacoes=recs,
            valor_total_envolvido=round(sum(x.valor_envolvido for x in apontamentos), 2),
            apontamentos=apontamentos,
        )


def export_relatorio_fiscal(rel: RelatorioFiscalContas, out_dir: Path | None = None) -> dict[str, Path]:
    """Exporta o Relatório Completo do Fiscal de Contas em Markdown, HTML e JSON."""
    dest = out_dir or OUTPUT_DIR
    dest.mkdir(parents=True, exist_ok=True)

    # 1. JSON
    json_path = dest / "apontamentos_fiscal_contas.json"
    json_path.write_text(json.dumps(rel.model_dump(), ensure_ascii=False, indent=2), encoding="utf-8")

    # 2. Markdown Formal
    md_lines = [
        f"# RELATÓRIO TÉCNICO DE FISCALIZAÇÃO DE CONTAS PÚBLICAS",
        f"**Entidade:** {rel.entidade} | **CNPJ:** `{rel.cnpj}`  ",
        f"**Exercícios Auditados:** {', '.join(map(str, rel.exercicios))} | **Emissão:** {rel.gerado_em}",
        "",
        f"> **Parecer Síntese:** {rel.parecer_sintese}",
        "",
        "## Quadro Resumo dos Apontamentos",
        "| Indicador | Quantidade |",
        "|---|---|",
        f"| Total de Apontamentos | {rel.total_apontamentos} |",
        f"| Irregularidades Graves | {rel.graves} |",
        f"| Ressalvas Relevantes | {rel.ressalvas} |",
        f"| Recomendações de Controle | {rel.recomendacoes} |",
        f"| Soma de Valores Envolvidos (não cumulativa entre trilhas) | {_brl(rel.valor_total_envolvido)} |",
        "",
        "---",
        "## Detalhamento dos Apontamentos",
    ]
    for ap in rel.apontamentos:
        md_lines.extend([
            f"### {ap.codigo} — {ap.titulo}",
            f"- **Categoria:** {ap.categoria} | **Gravidade:** `{ap.gravidade}` | **Prazo Sugerido:** {ap.prazo_sugerido_dias} dias",
            f"- **Enquadramento Legal:** {ap.base_legal}",
            f"- **Ocorrências:** {ap.quantidade_ocorrencias} | **Valor Envolvido:** {_brl(ap.valor_envolvido)}",
            f"- **Situação Encontrada:** {ap.situacao_encontrada}",
            f"- **Risco Procedimental / ao Erário:** {ap.risco_procedimental}",
            "- **Evidências Principais:**",
        ])
        for ev in ap.evidencias_principais:
            md_lines.append(f"  - {ev}")
        md_lines.extend([
            f"- **Determinação ao Gestor:** {ap.determinacao_ao_gestor}",
            "",
        ])
    md_path = dest / "relatorio_fiscal_contas_palmopolis.md"
    md_path.write_text("\n".join(md_lines), encoding="utf-8")

    # 3. HTML para leitura executiva e impressão
    tpl = Template("""<!DOCTYPE html>
<html lang="pt-BR"><head><meta charset="utf-8"/>
<title>Relatório do Fiscal de Contas — {{ rel.entidade }}</title>
<style>
  body { font-family: 'Segoe UI', Arial, sans-serif; margin: 0; background: #f5f7fa; color: #1a202c; }
  header { background: #1a202c; color: #fff; padding: 26px 34px; border-bottom: 4px solid #c53030; }
  main { max-width: 1120px; margin: 24px auto; padding: 0 20px 40px; }
  .parecer { background: #fff5f5; border-left: 5px solid #c53030; padding: 14px 18px; border-radius: 6px; margin-bottom: 20px; }
  .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; margin-bottom: 22px; }
  .kpi { background: #fff; border: 1px solid #e2e8f0; border-radius: 8px; padding: 14px; }
  .kpi .v { font-size: 24px; font-weight: 700; color: #1b365d; }
  .ap { background: #fff; border: 1px solid #e2e8f0; border-radius: 8px; padding: 18px; margin-bottom: 16px; }
  .badge { display: inline-block; padding: 3px 9px; border-radius: 999px; font-size: 11px; font-weight: 700; }
  .IRREGULARIDADE_GRAVE { background: #fde2e1; color: #9b2c2c; }
  .RESSALVA_RELEVANTE { background: #fef0d9; color: #9c4221; }
  .RECOMENDACAO_CONTROLE { background: #e7f5ff; color: #1864ab; }
  @media print { body { background: #fff; } .ap { break-inside: avoid; } }
</style></head><body>
<header>
  <h1 style="margin:0 0 6px;font-size:21px;">Relatório Técnico de Fiscalização de Contas Públicas</h1>
  <p style="margin:0;font-size:13px;opacity:.9;">{{ rel.entidade }} | CNPJ {{ rel.cnpj }} | Exercícios: {{ rel.exercicios|join(', ') }} | {{ rel.gerado_em }}</p>
</header>
<main>
  <div class="parecer"><strong>{{ rel.parecer_sintese }}</strong></div>
  <div class="grid">
    <div class="kpi"><div>Total de Apontamentos</div><div class="v">{{ rel.total_apontamentos }}</div></div>
    <div class="kpi"><div>Irregularidades Graves</div><div class="v" style="color:#c53030">{{ rel.graves }}</div></div>
    <div class="kpi"><div>Ressalvas Relevantes</div><div class="v" style="color:#dd6b20">{{ rel.ressalvas }}</div></div>
    <div class="kpi"><div>Recomendações</div><div class="v">{{ rel.recomendacoes }}</div></div>
  </div>
  {% for ap in rel.apontamentos %}
  <div class="ap">
    <span class="badge {{ ap.gravidade }}">{{ ap.gravidade }}</span>
    <span style="font-size:12px;color:#64748b;margin-left:8px;">{{ ap.categoria }} | Prazo: {{ ap.prazo_sugerido_dias }}d</span>
    <h2 style="margin:8px 0 6px;font-size:17px;color:#1b365d;">{{ ap.codigo }} — {{ ap.titulo }}</h2>
    <p style="margin:4px 0;"><strong>Base Legal:</strong> {{ ap.base_legal }}</p>
    <p style="margin:4px 0;"><strong>Ocorrências:</strong> {{ ap.quantidade_ocorrencias }} | <strong>Valor Envolvido:</strong> {{ brl(ap.valor_envolvido) }}</p>
    <p style="margin:6px 0;"><strong>Situação Encontrada:</strong> {{ ap.situacao_encontrada }}</p>
    <p style="margin:6px 0;"><strong>Risco Procedimental:</strong> {{ ap.risco_procedimental }}</p>
    {% if ap.evidencias_principais %}
    <p style="margin:6px 0 2px;"><strong>Evidências:</strong></p>
    <ul style="margin:0 0 8px 18px;font-size:13px;">{% for e in ap.evidencias_principais %}<li>{{ e }}</li>{% endfor %}</ul>
    {% endif %}
    <p style="margin:6px 0;background:#f8fafc;padding:8px 10px;border-left:3px solid #2b6cb0;"><strong>Determinação ao Gestor:</strong> {{ ap.determinacao_ao_gestor }}</p>
  </div>
  {% endfor %}
</main></body></html>""")
    html_path = dest / "relatorio_fiscal_contas_palmopolis.html"
    html_path.write_text(tpl.render(rel=rel, brl=_brl), encoding="utf-8")

    log.info("Relatório do Fiscal de Contas exportado em %s", dest)
    return {"json": json_path, "md": md_path, "html": html_path}
