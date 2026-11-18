"""Testes unitários do Agente Jurídico (TCE-MG, MPMG e Matriz TCU)."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from engine.agente_juridico import AgenteJuridico, export_dossie_juridico
from engine.analise_critica import AnalisadorCritico
from engine.fiscal_contas import FiscalContasPublicas
from engine.reconciliador import Reconciliador


def test_agente_juridico_gera_parecer_tcu_e_minutas(dados_sinteticos: dict[str, Any], tmp_path: Path) -> None:
    audit = Reconciliador(
        memory_data=dados_sinteticos["memory"],
        pncp_data=dados_sinteticos["pncp"],
        portal_data=dados_sinteticos["portal"],
        extraction_statuses=dados_sinteticos["statuses"],
        exercicios=dados_sinteticos["exercicios"],
    ).run()
    critica = AnalisadorCritico(
        memory_data=dados_sinteticos["memory"],
        pncp_data=dados_sinteticos["pncp"],
        cruzamento_lic=audit.dataframes.get("Cruzamento_Licitacoes"),
        exercicios=dados_sinteticos["exercicios"],
    ).run()
    rel = FiscalContasPublicas(audit, critica).emitir_relatorio()
    dossie = AgenteJuridico(rel).emitir_dossie()

    assert len(dossie.validacoes_tcu) == rel.total_apontamentos
    assert "TCE-MG" in dossie.nota_competencia_tce_tcm_mg
    assert "TRIBUNAL DE CONTAS DO ESTADO DE MINAS GERAIS" in dossie.minuta_tce_mg
    assert "MINISTÉRIO PÚBLICO DO ESTADO DE MINAS GERAIS" in dossie.minuta_mpmg

    paths = export_dossie_juridico(dossie, out_dir=tmp_path)
    for k in ("json", "tce_mg", "mpmg", "parecer_md", "html"):
        assert paths[k].exists() and paths[k].stat().st_size > 200
