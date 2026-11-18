"""Orquestrador CLI do Sistema de Auditoria Municipal — Palmópolis/MG (Prefeitura & Câmara)."""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any

from config import OUTPUT_DIR, ensure_dirs, load_raw, save_raw, settings, setup_logging
from connectors.camara_sigafi_client import SIGAFI_ENDPOINTS, CamaraSigafiClient
from connectors.memory_auth_playwright import capture_session, fallback_session
from connectors.memory_lai_client import ENDPOINTS, EXTRA_ENDPOINTS, MemoryLaiClient
from connectors.pncp_client import PNCPClient
from connectors.portal_scraper import PortalScraper
from engine.agente_juridico import AgenteJuridico, export_dossie_juridico
from engine.analise_critica import AnalisadorCritico
from engine.camara_normalizer import normalize_camara_to_canonical
from engine.diarias_pagamento import AnalisadorDiarias, export_diarias_pagamento
from engine.fiscal_contas import FiscalContasPublicas, export_relatorio_fiscal
from engine.fiscal_corretor import FiscalCorretor, export_plano_corretor
from engine.fornecedor_contratos import PesquisadorContratosRecebimentos, export_contratos_recebimentos
from engine.reconciliador import Reconciliador
from engine.report_builder import build_analise_critica_html, build_dashboard_html, build_excel_master


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Auditoria Municipal Automatizada — Palmópolis/MG (Prefeitura e Câmara Municipal)"
    )
    p.add_argument("--orgao", choices=["prefeitura", "camara", "todos"], default="prefeitura",
                   help="Órgão a auditar separadamente (padrão: prefeitura)")
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


def _load_pncp_raw(raw_source: str, exercicios: list[int]) -> dict[str, list[dict[str, Any]]]:
    pncp: dict[str, list[dict[str, Any]]] = {
        "contratacoes": [], "arquivos": [], "itens": [], "contratos": [], "atas": [],
        "busca_indice": load_raw(raw_source, "busca_indice") or [],
    }
    org = load_raw(raw_source, "orgao")
    pncp["orgao"] = [org] if org else []
    for ano in exercicios:
        for k in ("contratacoes", "arquivos", "itens", "contratos", "atas"):
            pncp[k].extend(load_raw(raw_source, f"{k}_{ano}") or [])
    return pncp


def _load_portal_raw(raw_source: str) -> dict[str, list[dict[str, Any]]]:
    return {
        "home_links": load_raw(raw_source, "home_links") or [],
        "publicacoes": load_raw(raw_source, "publicacoes") or [],
        "diario_oficial": load_raw(raw_source, "diario_oficial") or [],
        "noticias": load_raw(raw_source, "noticias") or [],
    }


def _load_from_raw(exercicios: list[int]) -> tuple[dict[str, list[dict[str, Any]]], dict[str, list[dict[str, Any]]], dict[str, list[dict[str, Any]]], list[dict[str, Any]]]:
    mem: dict[str, list[dict[str, Any]]] = {}
    for ep in ENDPOINTS + EXTRA_ENDPOINTS:
        mem[ep.key] = []
        for ano in exercicios:
            recs = load_raw("memory", f"{ep.key}_{ano}") or []
            for r in recs:
                r["exercicio"] = ano
            mem[ep.key].extend(recs)
    return mem, _load_pncp_raw("pncp", exercicios), _load_portal_raw("portal"), (load_raw("audit", "extraction_statuses") or [])


def _load_camara_from_raw(exercicios: list[int]) -> tuple[dict[str, list[dict[str, Any]]], dict[str, list[dict[str, Any]]], dict[str, list[dict[str, Any]]], list[dict[str, Any]]]:
    sigafi: dict[str, list[dict[str, Any]]] = {}
    for ep in SIGAFI_ENDPOINTS:
        sigafi[ep.key] = []
        for ano in exercicios:
            recs = load_raw("camara", f"{ep.key}_{ano}") or []
            for r in recs:
                r["exercicio"] = r.get("exercicio") or ano
            sigafi[ep.key].extend(recs)
    return (
        normalize_camara_to_canonical(sigafi),
        _load_pncp_raw("camara_pncp", exercicios),
        _load_portal_raw("camara_portal"),
        (load_raw("audit", "extraction_statuses_camara") or []),
    )


def _executar_pipeline_orgao(
    *,
    entidade_nome: str,
    cnpj: str,
    exercicios: list[int],
    mem_data: dict[str, list[dict[str, Any]]],
    pncp_data: dict[str, list[dict[str, Any]]],
    portal_data: dict[str, list[dict[str, Any]]],
    statuses_dicts: list[dict[str, Any]],
    out_dir: Path,
    excel_name: str,
    log: logging.Logger,
) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    orig_nome, orig_cnpj = settings.audit_entidade_nome, settings.audit_cnpj
    settings.audit_entidade_nome = entidade_nome
    settings.audit_cnpj = cnpj
    try:
        audit_result = Reconciliador(
            memory_data=mem_data,
            pncp_data=pncp_data,
            portal_data=portal_data,
            extraction_statuses=statuses_dicts,
            exercicios=exercicios,
        ).run()

        critica_result = AnalisadorCritico(
            memory_data=mem_data,
            pncp_data=pncp_data,
            cruzamento_lic=audit_result.dataframes.get("Cruzamento_Licitacoes"),
            exercicios=exercicios,
        ).run()
        audit_result.dataframes.update(critica_result.dataframes)

        rel_fiscal = FiscalContasPublicas(audit_result, critica_result).emitir_relatorio()
        fiscal_paths = export_relatorio_fiscal(rel_fiscal, out_dir=out_dir)

        plano_corretor = FiscalCorretor(rel_fiscal).gerar_plano()
        corretor_paths = export_plano_corretor(plano_corretor, out_dir=out_dir)

        dossie_jur = AgenteJuridico(rel_fiscal, plano_corretor).emitir_dossie()
        jur_paths = export_dossie_juridico(dossie_jur, out_dir=out_dir)

        pesq_bundle = PesquisadorContratosRecebimentos(mem_data).build()
        pesq_paths = export_contratos_recebimentos(pesq_bundle, out_dir=out_dir)

        diarias_bundle = AnalisadorDiarias(mem_data).build()
        diarias_paths = export_diarias_pagamento(diarias_bundle, out_dir=out_dir)

        xlsx_path = build_excel_master(audit_result, output_path=out_dir / excel_name)
        html_path = build_dashboard_html(audit_result, statuses_dicts, output_path=out_dir / "dashboard_executivo_palmopolis.html")
        critica_html_path = build_analise_critica_html(critica_result, output_path=out_dir / "painel_analise_critica.html")

        (out_dir / "analise_critica.json").write_text(
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
        (out_dir / "resumo_auditoria.json").write_text(
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

        log.info("=== AUDITORIA FINALIZADA (%s) ===", entidade_nome)
        log.info("Excel Master     : %s", xlsx_path)
        log.info("Dashboard HTML   : %s", html_path)
        log.info("Análise Crítica  : %s (%d variações)", critica_html_path, len(critica_result.anomalias))
        log.info("Fiscal de Contas : %s (%d apontamentos)", fiscal_paths["md"], rel_fiscal.total_apontamentos)
        log.info("Fiscal Corretor  : %s (%d roteiros)", corretor_paths["md"], plano_corretor.total_roteiros)
        log.info("Agente Jurídico  : %s (%d validações TCU)", jur_paths["html"], len(dossie_jur.validacoes_tcu))
        log.info("Contratos/Receb. : %s (%d contratos, %d recebimentos)", pesq_paths["xlsx"], len(pesq_bundle["contratos"]), len(pesq_bundle["recebimentos_cronologicos"]))
        log.info("Pagam. Diárias   : %s (%d servidores, %d pagamentos)", diarias_paths["xlsx"], len(diarias_bundle["servidores_resumo"]), len(diarias_bundle["pagamentos_diarias"]))
    finally:
        settings.audit_entidade_nome = orig_nome
        settings.audit_cnpj = orig_cnpj


def main() -> int:
    args = parse_args()
    log: logging.Logger = setup_logging(args.log_level)
    ensure_dirs()
    if args.no_itens:
        settings.pncp_fetch_itens = False

    exercicios: list[int] = sorted(set(args.exercicios))

    if args.orgao in ("prefeitura", "todos"):
        log.info("=== INICIANDO AUDITORIA: %s (CNPJ %s) | Exercícios: %s ===",
                 settings.audit_entidade_nome, settings.audit_cnpj, exercicios)
        if args.from_raw:
            mem_data, pncp_data, portal_data, statuses_dicts = _load_from_raw(exercicios)
        else:
            session = fallback_session() if (args.skip_playwright or not settings.memory_use_playwright) else capture_session(discover=True, headless=True)
            mem_data, mem_statuses = MemoryLaiClient(session).extract_all(exercicios, include_extra=True)
            pncp_client = PNCPClient(settings.audit_cnpj, raw_source="pncp")
            pncp_data = pncp_client.extract_all(exercicios)
            portal_scraper = PortalScraper(settings.portal_url, raw_source="portal")
            portal_data = portal_scraper.extract_all()
            statuses_dicts = [s.model_dump() for s in (mem_statuses + pncp_client.statuses + portal_scraper.statuses)]
            save_raw("audit", "extraction_statuses", statuses_dicts)

        _executar_pipeline_orgao(
            entidade_nome=settings.audit_entidade_nome,
            cnpj=settings.audit_cnpj,
            exercicios=exercicios,
            mem_data=mem_data,
            pncp_data=pncp_data,
            portal_data=portal_data,
            statuses_dicts=statuses_dicts,
            out_dir=OUTPUT_DIR,
            excel_name="auditoria_palmopolis_master.xlsx",
            log=log,
        )

    if args.orgao in ("camara", "todos"):
        log.info("=== INICIANDO AUDITORIA: %s (CNPJ %s) | Exercícios: %s ===",
                 settings.camara_nome, settings.camara_cnpj, exercicios)
        if args.from_raw:
            mem_c, pncp_c, portal_c, statuses_c = _load_camara_from_raw(exercicios)
        else:
            sigafi_raw, sigafi_statuses = CamaraSigafiClient().extract_all(exercicios)
            mem_c = normalize_camara_to_canonical(sigafi_raw)
            pncp_client_c = PNCPClient(settings.camara_cnpj, raw_source="camara_pncp")
            pncp_c = pncp_client_c.extract_all(exercicios)
            portal_scraper_c = PortalScraper(settings.camara_portal_url, raw_source="camara_portal")
            portal_c = portal_scraper_c.extract_all()
            statuses_c = [s.model_dump() for s in (sigafi_statuses + pncp_client_c.statuses + portal_scraper_c.statuses)]
            save_raw("audit", "extraction_statuses_camara", statuses_c)

        _executar_pipeline_orgao(
            entidade_nome=settings.camara_nome,
            cnpj=settings.camara_cnpj,
            exercicios=exercicios,
            mem_data=mem_c,
            pncp_data=pncp_c,
            portal_data=portal_c,
            statuses_dicts=statuses_c,
            out_dir=OUTPUT_DIR / "camara",
            excel_name="auditoria_camara_master.xlsx",
            log=log,
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
