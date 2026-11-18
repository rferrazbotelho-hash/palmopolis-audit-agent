"""Orquestrador CLI do Sistema de Auditoria Municipal — Palmópolis/MG."""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any

from config import OUTPUT_DIR, ensure_dirs, load_raw, save_raw, settings, setup_logging
from connectors.memory_auth_playwright import capture_session, fallback_session
from connectors.memory_lai_client import ENDPOINTS, EXTRA_ENDPOINTS, MemoryLaiClient
from connectors.pncp_client import PNCPClient
from connectors.portal_scraper import PortalScraper
from engine.agente_juridico import AgenteJuridico, export_dossie_juridico
from engine.analise_critica import AnalisadorCritico
from engine.fiscal_contas import FiscalContasPublicas, export_relatorio_fiscal
from engine.fiscal_corretor import FiscalCorretor, export_plano_corretor
from engine.fornecedor_contratos import PesquisadorContratosRecebimentos, export_contratos_recebimentos
from engine.reconciliador import Reconciliador
from engine.report_builder import build_analise_critica_html, build_dashboard_html, build_excel_master


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Auditoria Municipal Automatizada — Prefeitura de Palmópolis/MG (CNPJ 66234345000118)"
    )
    p.add_argument("--exercicios", nargs="+", type=int, default=settings.audit_exercicios,
                   help="Exercícios financeiros a auditar (padrão: 2025 2026)")
    p.add_argument("--skip-playwright", action="store_true",
                   help="Usa sessão determinística da Memory sem abrir o Chromium")
    p.add_argument("--no-itens", action="store_true",
                   help="Não consulta itens individuais no PNCP (mais rápido)")
    p.add_argument("--from-raw", action="store_true",
                   help="Reprocessa auditoria e relatórios usando JSONs já salvos em data/raw/")
    p.add_argument("--log-level", default=settings.log_level, help="Nível de log (DEBUG, INFO, WARNING)")
    return p.parse_args()


def _load_from_raw(exercicios: list[int]) -> tuple[dict[str, list[dict[str, Any]]], dict[str, list[dict[str, Any]]], dict[str, list[dict[str, Any]]], list[dict[str, Any]]]:
    mem: dict[str, list[dict[str, Any]]] = {}
    for ep in ENDPOINTS + EXTRA_ENDPOINTS:
        mem[ep.key] = []
        for ano in exercicios:
            recs = load_raw("memory", f"{ep.key}_{ano}") or []
            for r in recs:
                r["exercicio"] = ano
            mem[ep.key].extend(recs)

    pncp: dict[str, list[dict[str, Any]]] = {
        "contratacoes": [], "arquivos": [], "itens": [], "contratos": [], "atas": [],
        "busca_indice": load_raw("pncp", "busca_indice") or [],
    }
    org = load_raw("pncp", "orgao")
    pncp["orgao"] = [org] if org else []
    for ano in exercicios:
        for k in ("contratacoes", "arquivos", "itens", "contratos", "atas"):
            pncp[k].extend(load_raw("pncp", f"{k}_{ano}") or [])

    portal = {
        "home_links": load_raw("portal", "home_links") or [],
        "publicacoes": load_raw("portal", "publicacoes") or [],
        "diario_oficial": load_raw("portal", "diario_oficial") or [],
        "noticias": load_raw("portal", "noticias") or [],
    }
    statuses = load_raw("audit", "extraction_statuses") or []
    return mem, pncp, portal, statuses


def main() -> int:
    args = parse_args()
    log: logging.Logger = setup_logging(args.log_level)
    ensure_dirs()
    if args.no_itens:
        settings.pncp_fetch_itens = False

    exercicios: list[int] = sorted(set(args.exercicios))
    log.info("=== INICIANDO AUDITORIA: %s (CNPJ %s) | Exercícios: %s ===",
             settings.audit_entidade_nome, settings.audit_cnpj, exercicios)

    if args.from_raw:
        log.info("Modo --from-raw ativado: carregando payloads de data/raw/...")
        mem_data, pncp_data, portal_data, statuses_dicts = _load_from_raw(exercicios)
    else:
        # 1. Sessão Memory iLAI
        if args.skip_playwright or not settings.memory_use_playwright:
            session = fallback_session()
            log.info("Sessão Memory (fallback determinístico) inicializada.")
        else:
            session = capture_session(discover=True, headless=True)

        # 2. Extração iLAI Memory (19 endpoints + complementares)
        mem_client = MemoryLaiClient(session)
        mem_data, mem_statuses = mem_client.extract_all(exercicios, include_extra=True)

        # 3. Extração PNCP
        pncp_client = PNCPClient(settings.audit_cnpj)
        pncp_data = pncp_client.extract_all(exercicios)

        # 4. Extração Portal Institucional
        portal_scraper = PortalScraper(settings.portal_url)
        portal_data = portal_scraper.extract_all()

        all_statuses = mem_statuses + pncp_client.statuses + portal_scraper.statuses
        statuses_dicts = [s.model_dump() for s in all_statuses]
        save_raw("audit", "extraction_statuses", statuses_dicts)

    # 5. Motor de Reconciliação e Trilhas da Lei 14.133/2021 e LAI
    reconciliador = Reconciliador(
        memory_data=mem_data,
        pncp_data=pncp_data,
        portal_data=portal_data,
        extraction_statuses=statuses_dicts,
        exercicios=exercicios,
    )
    audit_result = reconciliador.run()

    # 5b. Análise Crítica e Variações Inconsistentes
    critica_result = AnalisadorCritico(
        memory_data=mem_data,
        pncp_data=pncp_data,
        cruzamento_lic=audit_result.dataframes.get("Cruzamento_Licitacoes"),
        exercicios=exercicios,
    ).run()
    audit_result.dataframes.update(critica_result.dataframes)

    # 5c. Fiscal de Contas Públicas — Relatório Completo de Apontamentos
    rel_fiscal = FiscalContasPublicas(audit_result, critica_result).emitir_relatorio()
    fiscal_paths = export_relatorio_fiscal(rel_fiscal)

    # 5d. Fiscal Corretor — Melhor Condução e Plano Passo a Passo
    plano_corretor = FiscalCorretor(rel_fiscal).gerar_plano()
    corretor_paths = export_plano_corretor(plano_corretor)

    # 5e. Agente Jurídico — Parecer TCU + Minutas TCE-MG / MPMG
    dossie_jur = AgenteJuridico(rel_fiscal, plano_corretor).emitir_dossie()
    jur_paths = export_dossie_juridico(dossie_jur)

    # 5f. Pesquisador de Contratos por Fornecedor e Recebimentos Cronológicos
    pesq_bundle = PesquisadorContratosRecebimentos(mem_data).build()
    pesq_paths = export_contratos_recebimentos(pesq_bundle)

    # 6. Geração de Relatórios
    xlsx_path: Path = build_excel_master(audit_result)
    html_path: Path = build_dashboard_html(audit_result, statuses_dicts)
    critica_html_path: Path = build_analise_critica_html(critica_result)

    (OUTPUT_DIR / "analise_critica.json").write_text(
        json.dumps(
            {
                "resumo_eixos": critica_result.resumo_eixos,
                "total_anomalias": len(critica_result.anomalias),
                "anomalias": [a.model_dump() for a in critica_result.anomalias],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    resumo_json = OUTPUT_DIR / "resumo_auditoria.json"
    resumo_json.write_text(
        json.dumps(
            {
                "kpis": audit_result.kpis,
                "achados": [a.model_dump() for a in audit_result.achados],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    log.info("=== AUDITORIA FINALIZADA COM SUCESSO ===")
    log.info("Excel Master     : %s", xlsx_path)
    log.info("Dashboard HTML   : %s", html_path)
    log.info("Análise Crítica  : %s (%d variações/inconsistências)", critica_html_path, len(critica_result.anomalias))
    log.info("Fiscal de Contas : %s (%d apontamentos: %d graves, %d ressalvas)",
             fiscal_paths["md"], rel_fiscal.total_apontamentos, rel_fiscal.graves, rel_fiscal.ressalvas)
    log.info("Fiscal Corretor  : %s (%d roteiros, %d passos)",
             corretor_paths["md"], plano_corretor.total_roteiros, plano_corretor.total_passos)
    log.info("Agente Jurídico  : %s (%d validações TCU)", jur_paths["html"], len(dossie_jur.validacoes_tcu))
    log.info("Contratos/Receb. : %s (%d contratos, %d recebimentos)",
             pesq_paths["xlsx"], len(pesq_bundle["contratos"]), len(pesq_bundle["recebimentos_cronologicos"]))
    log.info("Resumo JSON      : %s", resumo_json)
    log.info("Achados gerados  : %d (Críticos=%d, Altos=%d, Médios=%d)",
             audit_result.kpis.get("achados_total", 0),
             audit_result.kpis.get("achados_criticos", 0),
             audit_result.kpis.get("achados_altos", 0),
             audit_result.kpis.get("achados_medios", 0))
    return 0


if __name__ == "__main__":
    sys.exit(main())
