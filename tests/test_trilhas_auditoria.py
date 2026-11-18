"""Testes unitários e de integração por seleção de trilhas/itens de auditoria."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from engine.reconciliador import Reconciliador
from engine.report_builder import build_dashboard_html, build_excel_master


def _rodar_reconciliador(dados: dict[str, Any]) -> Any:
    return Reconciliador(
        memory_data=dados["memory"],
        pncp_data=dados["pncp"],
        portal_data=dados["portal"],
        extraction_statuses=dados["statuses"],
        exercicios=dados["exercicios"],
    ).run()


@pytest.mark.licitacoes
def test_reconciliacao_licitacoes_art54_94(dados_sinteticos: dict[str, Any]) -> None:
    res = _rodar_reconciliador(dados_sinteticos)
    df = res.dataframes["Cruzamento_Licitacoes"]
    assert not df.empty
    status_counts = df["status_conciliacao"].value_counts().to_dict()
    assert status_counts.get("CONCILIADO") == 1
    assert status_counts.get("SOMENTE_LOCAL_SEM_PNCP") == 2
    assert status_counts.get("SOMENTE_PNCP_SEM_LOCAL") == 1
    codigos = {a.codigo for a in res.achados}
    assert {"ACH-01", "ACH-02", "ACH-07"}.issubset(codigos)


@pytest.mark.contratos
def test_reconciliacao_contratos_e_tempestividade_art94(dados_sinteticos: dict[str, Any]) -> None:
    res = _rodar_reconciliador(dados_sinteticos)
    df = res.dataframes["Cruzamento_Contratos"]
    assert not df.empty
    status_counts = df["status_conciliacao"].value_counts().to_dict()
    assert status_counts.get("CONCILIADO") == 1
    assert status_counts.get("SOMENTE_LOCAL_SEM_PNCP") == 1
    codigos = {a.codigo for a in res.achados}
    assert {"ACH-03", "ACH-04", "ACH-05", "ACH-09"}.issubset(codigos)


@pytest.mark.dispensas
def test_auditoria_dispensas_art75(dados_sinteticos: dict[str, Any]) -> None:
    res = _rodar_reconciliador(dados_sinteticos)
    df = res.dataframes["Auditoria_Art75_Dispensas"]
    assert not df.empty
    alertas = set(df["alerta_art75"].dropna())
    assert "ACIMA_LIMITE_LEGAL" in alertas
    assert "RISCO_FRACIONAMENTO" in alertas
    assert any(a.codigo == "ACH-06" for a in res.achados)


@pytest.mark.fornecedores
def test_auditoria_fornecedores_art9_14(dados_sinteticos: dict[str, Any]) -> None:
    res = _rodar_reconciliador(dados_sinteticos)
    df = res.dataframes["Fornecedores_CurvaABC"]
    assert not df.empty
    vinc = df[df["possivel_vinculo_servidor_nome"] != "NAO"]
    assert len(vinc) == 1
    assert vinc.iloc[0]["fornecedor_nome"] == "SERVIDOR HOMONIMO DA SILVA"
    assert any(a.codigo == "ACH-08" for a in res.achados)


@pytest.mark.lai
def test_auditoria_transparencia_lai(dados_sinteticos: dict[str, Any]) -> None:
    res = _rodar_reconciliador(dados_sinteticos)
    df = res.dataframes["Transparencia_LAI"]
    assert not df.empty
    assert "DEFICIT_TRANSPARENCIA" in set(df["status"])
    assert any(a.codigo == "ACH-10" for a in res.achados)


@pytest.mark.relatorios
def test_geracao_relatorios_em_diretorio_isolado(dados_sinteticos: dict[str, Any], tmp_path: Path) -> None:
    res = _rodar_reconciliador(dados_sinteticos)
    xlsx = build_excel_master(res, output_path=tmp_path / "teste_master.xlsx")
    html = build_dashboard_html(res, dados_sinteticos["statuses"], output_path=tmp_path / "teste_dash.html")
    assert xlsx.exists() and xlsx.stat().st_size > 1000
    assert html.exists() and "Painel Executivo" in html.read_text(encoding="utf-8")
