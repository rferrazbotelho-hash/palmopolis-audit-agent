"""Testes unitários do conector e normalizador da Câmara Municipal de Palmópolis/MG."""
from __future__ import annotations

from engine.camara_normalizer import normalize_camara_to_canonical
from engine.diarias_pagamento import AnalisadorDiarias
from engine.fornecedor_contratos import PesquisadorContratosRecebimentos


def test_camara_normalizer_separa_contratos_diarias_e_fornecedores() -> None:
    sigafi = {
        "contratos": [
            {
                "id": "7112",
                "codigo": "0001-2026",
                "tipo": "nao_licitado",
                "exercicio": "2026",
                "objeto": "HOSPEDAGEM WEBSITE CAMARA",
                "fornecedor": "A E T DEVELOPMENT LTDA.",
                "data_inicio_vigencia": "2026-01-02",
                "data_fim_vigencia": "2026-12-31",
                "valor": "4800.0000",
                "data": "02/01/2026",
                "status": "finalizado",
                "fiscal_nome": "LYVIA COSTA COELHO",
            }
        ],
        "licitacoes": [
            {
                "id": "610",
                "exercicio": "2025",
                "codigo": "1",
                "data": "2025-03-07",
                "tipo_processo": "dispensa",
                "objeto": "ASSESSORIA JURIDICA",
            }
        ],
        "pagamentos": [
            {
                "id": "130545",
                "codigo": "4",
                "data": "20/01/2026",
                "valor": "5734.30",
                "nome": "EXUPERIO FERREIRA PIRES",
                "cnpj_cpf": "22253648000102",
                "historico": "CONSULTORIA LEGISLATIVA",
                "exercicio": 2026,
            }
        ],
        "diarias": [
            {
                "id": "132327",
                "codigo": "1",
                "data": "20/01/2026",
                "valor": "4000.00",
                "num_empenho": "00024/2026",
                "nome": "ALEXANDRE PEREIRA DA ROCHA",
                "data_diaria": "15/01/2026",
                "cargo": "PRESIDENTE DA CAMARA",
                "motivo_afastamento": "VIAGEM BH",
                "cnpj_cpf": "01300000000",
                "exercicio": 2026,
            }
        ],
        "servidores": [{"nome": "ALEXANDRE PEREIRA DA ROCHA", "cargo": "VEREADOR", "exercicio": 2026}],
        "empenhos": [],
        "liquidacoes": [],
        "obras": [],
    }

    canon = normalize_camara_to_canonical(sigafi)
    assert len(canon["contratos"]) == 1
    assert canon["contratos"][0]["numero_contrato"] == "0001/2026"
    assert canon["contratos"][0]["fornecedor_nome"] == "A E T DEVELOPMENT LTDA."
    assert len(canon["fiscais_contrato"]) == 1

    pesq = PesquisadorContratosRecebimentos(canon).build()
    assert pesq["contratos"][0]["fornecedor_nome"] == "A E T DEVELOPMENT LTDA."

    dia = AnalisadorDiarias(canon).build()
    assert dia["total_pago"] == 4000.0
    assert dia["pagamentos_diarias"][0]["cpf"] == "01300000000"
