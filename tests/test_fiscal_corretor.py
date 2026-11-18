"""Testes unitários do Fiscal Corretor."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from engine.analise_critica import AnalisadorCritico
from engine.fiscal_contas import FiscalContasPublicas
from engine.fiscal_corretor import FiscalCorretor, export_plano_corretor
from engine.reconciliador import Reconciliador


def test_fiscal_corretor_gera_plano_passo_a_passo(dados_sinteticos: dict[str, Any], tmp_path: Path) -> None:
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
    rel_fiscal = FiscalContasPublicas(audit, critica).emitir_relatorio()
    plano = FiscalCorretor(rel_fiscal).gerar_plano()

    assert plano.total_roteiros == rel_fiscal.total_apontamentos
    assert plano.total_passos >= plano.total_roteiros
    assert any(r.prioridade_execucao == "IMEDIATA_0_5D" for r in plano.roteiros)

    paths = export_plano_corretor(plano, out_dir=tmp_path)
    assert paths["md"].exists() and "PASSO A PASSO" in paths["md"].read_text(encoding="utf-8")
    assert paths["html"].exists()
    assert paths["json"].exists()
