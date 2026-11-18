"""Testes unitários do Pesquisador de Contratos por Fornecedor e Recebimentos Cronológicos."""
from __future__ import annotations

from pathlib import Path

from engine.fornecedor_contratos import PesquisadorContratosRecebimentos, export_contratos_recebimentos


def test_pesquisador_contratos_e_recebimentos_cronologicos(tmp_path: Path) -> None:
    mem = {
        "contratos": [
            {
                "id_contrato": 10,
                "numero_contrato": "15/2026",
                "exercicio": 2026,
                "fornecedor": None,
                "cpf_cnpj": None,
                "modalidade": "Pregão",
                "situacao": "Ativo",
                "valor_contrato": 50000.0,
                "objeto": "FORNECIMENTO DE MEDICAMENTOS",
            }
        ],
        "naf": [
            {
                "id_contrato": "10",
                "numero_contrato": "15/2026",
                "id_empenho": "12026100",
                "fornecedor_nome": "FARMACIA MODELO LTDA",
                "fornecedor_cpf_cnpj": "12.345.678/0001-99",
                "valor_total": 12000.0,
            }
        ],
        "pagamentos": [
            {
                "id_empenho": "12026100",
                "empenho_ano": "100/2026",
                "data_pagamento": "15/03/2026",
                "data_pagamento_format": "2026-03-15T00:00:00Z",
                "fornecedor_nome": "FARMACIA MODELO LTDA",
                "cpf_cnpj": "12.345.678/0001-99",
                "valor_pago": 8000.0,
                "exercicio": 2026,
                "nota_fiscal": "NF-200",
            },
            {
                "id_empenho": "12026999",
                "empenho_ano": "999/2026",
                "data_pagamento": "02/01/2026",
                "data_pagamento_format": "2026-01-02T00:00:00Z",
                "fornecedor_nome": "ENERGIA MG",
                "cpf_cnpj": "99.999.999/0001-99",
                "valor_pago": 1500.0,
                "des_despesa": "Energia Elétrica",
                "exercicio": 2026,
            },
        ],
    }

    bundle = PesquisadorContratosRecebimentos(mem).build()
    assert bundle["contratos"][0]["fornecedor_nome"] == "FARMACIA MODELO LTDA"
    assert bundle["contratos"][0]["valor_pago_vinculado"] == 8000.0

    recs = bundle["recebimentos_cronologicos"]
    assert len(recs) == 2
    # Ordem cronológica: 2026-01-02 vem antes de 2026-03-15
    assert recs[0]["data_iso"] == "2026-01-02"
    assert recs[1]["data_iso"] == "2026-03-15"
    assert recs[1]["contrato"] == "15/2026"
    assert recs[1]["objeto"] == "FORNECIMENTO DE MEDICAMENTOS"
    assert recs[1]["empenho"] == "100/2026"

    paths = export_contratos_recebimentos(bundle, out_dir=tmp_path)
    assert paths["xlsx"].exists() and paths["json"].exists()
