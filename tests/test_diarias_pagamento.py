"""Testes unitários da aba/módulo Pagamento de Diárias (Nome/CPF e cronologia)."""
from __future__ import annotations

from pathlib import Path

from engine.diarias_pagamento import AnalisadorDiarias, export_diarias_pagamento


def test_pagamento_diarias_recupera_cpf_e_ordena(tmp_path: Path) -> None:
    mem = {
        "diarias": [
            {
                "nome_servidor": "JOAO DA SILVA",
                "unidade_orcamentaria": "SAUDE",
                "numero_empenho": 20,
                "data_empenho": "10/02/2026",
                "data_pagamento": "10/02/2026",
                "valor_empenho": 120.0,
                "valor_pago": 120.0,
                "numero_pagamento": 5,
                "id_empenho": 1202620,
                "descricao_empenho": "DIARIA VIAGEM",
                "exercicio": 2026,
            },
            {
                "nome_servidor": "MARIA SOUZA",
                "unidade_orcamentaria": "GABINETE",
                "numero_empenho": 2,
                "data_empenho": "05/01/2026",
                "data_pagamento": "05/01/2026",
                "valor_empenho": 300.0,
                "valor_pago": 300.0,
                "numero_pagamento": 1,
                "id_empenho": 1202602,
                "descricao_empenho": "DIARIA BH",
                "exercicio": 2026,
            },
        ],
        "pagamentos": [
            {"id_empenho": "1202620", "cpf_cnpj": "***.111.222-**"},
        ],
        "empenhos": [
            {"id_empenho": "1202602", "fornecedor_cpf_cnpj": "***.999.888-**"},
        ],
        "servidores": [
            {"nome_servidor": "JOAO DA SILVA", "funcao": "MOTORISTA"},
            {"nome_servidor": "MARIA SOUZA", "funcao": "ASSESSORA"},
        ],
    }

    bundle = AnalisadorDiarias(mem).build()
    pags = bundle["pagamentos_diarias"]
    assert len(pags) == 2
    assert pags[0]["data_iso"] == "2026-01-05"
    assert pags[0]["cpf"] == "***.999.888-**"
    assert pags[0]["funcao"] == "ASSESSORA"
    assert pags[1]["cpf"] == "***.111.222-**"
    assert bundle["total_pago"] == 420.0

    paths = export_diarias_pagamento(bundle, out_dir=tmp_path)
    assert paths["xlsx"].exists() and paths["json"].exists()
