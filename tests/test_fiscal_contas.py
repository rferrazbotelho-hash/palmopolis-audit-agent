"""Testes unitários do Fiscal de Contas Públicas."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from engine.analise_critica import AnalisadorCritico
from engine.fiscal_contas import FiscalContasPublicas, export_relatorio_fiscal
from engine.reconciliador import Reconciliador


def test_fiscal_contas_emite_e_exporta_relatorio(dados_sinteticos: dict[str, Any], tmp_path: Path) -> None:
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
    assert rel.total_apontamentos >= 4
    assert rel.graves >= 1
    assert "INSTAURAÇÃO DE DILIGÊNCIA" in rel.parecer_sintese

    paths = export_relatorio_fiscal(rel, out_dir=tmp_path)
    assert paths["md"].exists() and "AP-001" in paths["md"].read_text(encoding="utf-8")
    assert paths["html"].exists()
    assert paths["json"].exists()
