"""Testes unitários do Sistema de Análise Crítica e Variações Inconsistentes."""
from __future__ import annotations

import pandas as pd

from engine.analise_critica import AnalisadorCritico


def test_analise_critica_detecta_variacoes_e_inconsistencias() -> None:
    mem = {
        "licitacoes": [
            {
                "numero_licitacao": "105/2025",
                "modalidade": "Concorrência",
                "valor_homologado": "26.618.359,93",
                "valor_maximo_processo": "1.407.694,88",
                "descricao": "OBRA HABITACIONAL",
                "exercicio": 2025,
            }
        ],
        "despesa_unidade": [
            {
                "descricao_unidade": "Secretaria Teste",
                "dotacao_atualizada": 100000.0,
                "valor_empenhado": 130000.0,
                "valor_liquidado": 135000.0,
                "valor_pago": 140000.0,
                "exercicio": 2026,
            }
        ],
        "despesa_funcao": [
            {"codigo_funcao": "10", "descricao_funcao": "Saúde", "valor_empenhado": 100000.0, "exercicio": 2025},
            {"codigo_funcao": "10", "descricao_funcao": "Saúde", "valor_empenhado": 350000.0, "exercicio": 2026},
        ],
        "contratos": [
            {"id_contrato": 500, "numero_contrato": "50/2026", "valor_contrato": 100000.0, "objeto": "SERVICOS", "exercicio": 2026}
        ],
        "naf": [
            {"id_contrato": "500", "valor_total": 145000.0, "exercicio": 2026}
        ],
        "diarias": [
            {"exercicio": 2026, "nome_servidor": "SERVIDOR A", "unidade_orcamentaria": "SEC", "valor_pago": 200.0},
            {"exercicio": 2026, "nome_servidor": "SERVIDOR B", "unidade_orcamentaria": "SEC", "valor_pago": 250.0},
            {"exercicio": 2026, "nome_servidor": "SERVIDOR C", "unidade_orcamentaria": "SEC", "valor_pago": 300.0},
            {"exercicio": 2026, "nome_servidor": "SERVIDOR OUTLIER", "unidade_orcamentaria": "SEC", "valor_pago": 12000.0},
        ],
    }
    pncp = {
        "itens": [
            {
                "numeroControlePNCP": "66234345000118-1-000001/2026",
                "numeroItem": 1,
                "valorUnitarioEstimado": 100.0,
                "valorUnitarioHomologado": 150.0,
                "orcamentoSigiloso": False,
                "descricao": "ITEM COM SOBREPRECO",
            },
            {
                "numeroControlePNCP": "66234345000118-1-000001/2026",
                "numeroItem": 2,
                "valorUnitarioEstimado": 0.0,
                "valorUnitarioHomologado": 50.0,
                "orcamentoSigiloso": False,
                "descricao": "ITEM SEM ESTIMATIVA",
            },
        ]
    }
    cruz_lic = pd.DataFrame([
        {
            "status_conciliacao": "CONCILIADO",
            "exercicio": 2026,
            "numero_memory": "1/2026",
            "modalidade_memory": "Pregão",
            "numero_controle_pncp": "66234345000118-1-000001/2026",
            "valor_memory": 500000.0,
            "valor_pncp": 300000.0,
            "objeto_memory": "COMBUSTIVEIS",
        }
    ])

    res = AnalisadorCritico(mem, pncp, cruz_lic, exercicios=[2025, 2026]).run()
    prefixes = {a.codigo.rsplit("-", 1)[0] for a in res.anomalias}
    assert "VAR-LIC" in prefixes
    assert "VAR-PNCP" in prefixes
    assert "ORC-DOT" in prefixes
    assert "ORC-LIQ" in prefixes
    assert "ORC-PAG" in prefixes
    assert "INT-VAR" in prefixes
    assert "CTR-NAF" in prefixes
    assert "PNCP-IT" in prefixes
    assert "DIA-OUT" in prefixes
    assert not res.dataframes["Critica_Ranking"].empty
