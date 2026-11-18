"""Fixtures sintéticas e de recorte para o ambiente de testes."""
from __future__ import annotations

from typing import Any

import pytest


@pytest.fixture
def dados_sinteticos() -> dict[str, Any]:
    """Massa sintética controlada que exercita todas as trilhas da Lei 14.133/2021 e LAI."""
    memory_data = {
        "licitacoes": [
            {
                "numero_licitacao": "1/2025",
                "modalidade": "Pregão Eletrônico",
                "situacao": "Homologado",
                "valor_homologado": "100.000,00",
                "valor_maximo_processo": "120.000,00",
                "descricao": "AQUISICAO DE COMBUSTIVEIS PARA FROTA MUNICIPAL",
                "exercicio": 2025,
            },
            {
                "numero_licitacao": "99/2025",
                "modalidade": "Pregão Presencial",
                "situacao": "Homologado",
                "valor_homologado": "250.000,00",
                "valor_maximo_processo": "250.000,00",
                "descricao": "CONTRATACAO DE SHOW ARTISTICO SEM PNCP",
                "exercicio": 2025,
            },
            {
                "numero_licitacao": "10/2026",
                "modalidade": "Dispensa",
                "situacao": "Homologado",
                "valor_homologado": "95.000,00",
                "valor_maximo_processo": "95.000,00",
                "descricao": "AQUISICAO DE MATERIAL DE ESCRITORIO ACIMA DO TETO",
                "exercicio": 2026,
            },
        ],
        "contratos": [
            {
                "numero_contrato": "10/2025",
                "tipo_ato": "Contrato",
                "modalidade": "Pregão Eletrônico",
                "fornecedor": "POSTO MODELO LTDA",
                "cpf_cnpj": "11.111.111/0001-11",
                "valor_contrato": 100000.0,
                "objeto": "FORNECIMENTO DE COMBUSTIVEIS",
                "exercicio": 2025,
            },
            {
                "numero_contrato": "20/2026",
                "tipo_ato": "Contrato",
                "modalidade": "Dispensa",
                "fornecedor": None,
                "cpf_cnpj": None,
                "valor_contrato": 95000.0,
                "objeto": "CONTRATO SEM FORNECEDOR E SEM PNCP",
                "exercicio": 2026,
            },
        ],
        "dispensas_valor": [
            {
                "numero_direta": "5/2026",
                "modalidade": "Dispensa",
                "situacao": "Homologado",
                "objeto": "COMPRA DIRETA PEQUENO VALOR",
                "exercicio": 2026,
            }
        ],
        "naf": [
            {
                "numero_naf": "100/2026",
                "id_compradireta": 999,
                "fornecedor_cpf_cnpj": "22.222.222/0001-22",
                "fornecedor_nome": "EMPRESA FRACIONADA LTDA",
                "valor_total": 75000.0,
                "exercicio": 2026,
            }
        ],
        "empenhos": [
            {
                "numero_empenho": 1,
                "fornecedor_cpf_cnpj": "11.111.111/0001-11",
                "fornecedor_nome": "POSTO MODELO LTDA",
                "valor_empenho": 100000.0,
                "exercicio": 2025,
            }
        ],
        "fornecedores": [
            {
                "fornecedor_cpf_cnpj": "11.111.111/0001-11",
                "fornecedor_nome": "POSTO MODELO LTDA",
                "valor_empenhado": 100000.0,
                "valor_liquidado": 90000.0,
                "valor_pago": 80000.0,
                "valor_apagar": 10000.0,
            },
            {
                "fornecedor_cpf_cnpj": "333.333.333-33",
                "fornecedor_nome": "SERVIDOR HOMONIMO DA SILVA",
                "valor_empenhado": 15000.0,
                "valor_liquidado": 15000.0,
                "valor_pago": 15000.0,
                "valor_apagar": 0.0,
            },
        ],
        "servidores": [
            {"nome_servidor": "SERVIDOR HOMONIMO DA SILVA", "situacao_atual": "ATIVO"}
        ],
        "fiscais_contrato": [],
        "obras": [],
        "convenios": [],
    }

    pncp_data = {
        "contratacoes": [
            {
                "numeroControlePNCP": "66234345000118-1-000001/2025",
                "anoCompra": 2025,
                "numeroCompra": "1",
                "processo": "1/2025",
                "modalidadeNome": "Pregão - Eletrônico",
                "objetoCompra": "AQUISICAO DE COMBUSTIVEIS PARA FROTA MUNICIPAL",
                "valorTotalEstimado": 120000.0,
                "valorTotalHomologado": 100000.0,
                "dataPublicacaoPncp": "2025-02-01T10:00:00",
            },
            {
                "numeroControlePNCP": "66234345000118-1-000099/2026",
                "anoCompra": 2026,
                "numeroCompra": "99",
                "processo": "99/2026",
                "modalidadeNome": "Concorrência - Eletrônica",
                "objetoCompra": "OBRA PUBLICA SEM ESPELHAMENTO LOCAL",
                "valorTotalEstimado": 500000.0,
                "valorTotalHomologado": 0.0,
                "dataPublicacaoPncp": "2026-03-10T10:00:00",
            },
        ],
        "contratos": [
            {
                "numeroControlePNCP": "66234345000118-2-000001/2025",
                "numeroContratoEmpenho": "10",
                "anoContrato": 2025,
                "niFornecedor": "11111111000111",
                "nomeRazaoSocialFornecedor": "POSTO MODELO LTDA",
                "valorGlobal": 100000.0,
                "dataAssinatura": "2025-02-01",
                "dataPublicacaoPncp": "2025-03-20T10:00:00",  # > 20 dias úteis -> atraso
                "objetoContrato": "FORNECIMENTO DE COMBUSTIVEIS",
            }
        ],
        "arquivos": [
            {"numeroControlePNCP": "66234345000118-1-000001/2025", "titulo": "Edital.pdf"}
        ],
        "itens": [],
        "atas": [],
    }

    portal_data = {
        "home_links": [],
        "publicacoes": [
            {"categoria": "licitacoes_portal", "url": "https://www.palmopolis.mg.gov.br/publicacao/diretorio/14", "vazio_declarado": True, "qtd_documentos": 0}
        ],
        "diario_oficial": [],
        "noticias": [],
    }

    statuses = [
        {"fonte": "Memory iLAI", "dataset": "licitacoes", "exercicio": 2025, "registros": 2, "status": "OK", "detalhe": "Licitações"},
        {"fonte": "Portal Institucional", "dataset": "diario_oficial", "exercicio": None, "registros": 0, "status": "VAZIO", "detalhe": ""},
    ]

    return {
        "memory": memory_data,
        "pncp": pncp_data,
        "portal": portal_data,
        "statuses": statuses,
        "exercicios": [2025, 2026],
    }
