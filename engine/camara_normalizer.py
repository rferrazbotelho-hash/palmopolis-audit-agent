"""Adaptador dos dados Sigafi (Câmara Municipal) para o modelo canônico de auditoria."""
from __future__ import annotations

from typing import Any

from engine.reconciliador import _only_digits, _to_float


def normalize_camara_to_canonical(sigafi_data: dict[str, list[dict[str, Any]]]) -> dict[str, list[dict[str, Any]]]:
    """Converte os 19 datasets Sigafi da Câmara para a estrutura usada pelos motores de análise."""
    licitacoes = [
        {
            "id_licitacao": r.get("id"),
            "id_processo": r.get("id"),
            "numero_licitacao": f"{r.get('codigo')}/{r.get('exercicio')}",
            "modalidade": str(r.get("tipo_processo") or "").title(),
            "situacao": "Publicado/Homologado",
            "valor_homologado": _to_float(r.get("valor_homologado") or r.get("valor")),
            "valor_maximo_processo": _to_float(r.get("valor_estimado") or r.get("valor")),
            "descricao": str(r.get("objeto") or "").strip(),
            "data_licitacao": r.get("data"),
            "exercicio": int(r.get("exercicio") or 2026),
        }
        for r in sigafi_data.get("licitacoes", [])
    ]

    contratos = [
        {
            "id_contrato": r.get("id"),
            "numero_contrato": str(r.get("codigo") or "").replace("-", "/"),
            "tipo_ato": "Contrato",
            "modalidade": str(r.get("tipo") or "").replace("_", " ").title(),
            "fornecedor": r.get("fornecedor"),
            "fornecedor_nome": r.get("fornecedor"),
            "cpf_cnpj": r.get("cnpj_cpf") or "",
            "fornecedor_cpf_cnpj": r.get("cnpj_cpf") or "",
            "valor_contrato": _to_float(r.get("valor")),
            "situacao": str(r.get("status") or "").strip(),
            "inicio_vigencia": r.get("data_inicio_vigencia"),
            "termino_vigencia": r.get("data_fim_vigencia"),
            "data_assinatura": r.get("data"),
            "data_publicacao": r.get("data"),
            "fiscal_nome": r.get("fiscal_nome"),
            "objeto": str(r.get("objeto") or "").strip(),
            "exercicio": int(r.get("exercicio") or 2026),
        }
        for r in sigafi_data.get("contratos", [])
    ]

    dispensas = [
        l for l in licitacoes if "dispensa" in str(l.get("modalidade") or "").lower()
    ]

    empenhos = [
        {
            "id_empenho": r.get("id"),
            "numero_empenho": r.get("empenho_codigo"),
            "data_empenho": r.get("data_empenho"),
            "fornecedor_nome": r.get("fornecedor"),
            "fornecedor_cpf_cnpj": r.get("cnpj_cpf") or "",
            "valor_empenho": _to_float(r.get("valor") or r.get("valor_empenhado")),
            "historico": r.get("historico"),
            "exercicio": int(r.get("exercicio") or 2026),
        }
        for r in sigafi_data.get("empenhos", [])
    ]

    pagamentos = [
        {
            "id_empenho": r.get("empenho_id") or r.get("id"),
            "empenho_ano": r.get("empenho_codigo") or r.get("codigo"),
            "numero_empenho": r.get("empenho_codigo") or r.get("codigo"),
            "numero_pagamento": r.get("codigo"),
            "data_pagamento": r.get("data"),
            "fornecedor_nome": r.get("nome"),
            "cpf_cnpj": r.get("cnpj_cpf") or "",
            "valor_pago": _to_float(r.get("valor")),
            "des_despesa": r.get("historico") or r.get("fonte_nome") or "",
            "tipo_despesa": r.get("tipo") or "",
            "exercicio": int(r.get("exercicio") or 2026),
        }
        for r in sigafi_data.get("pagamentos", [])
    ]

    diarias = [
        {
            "nome_servidor": r.get("nome"),
            "unidade_orcamentaria": r.get("cargo") or "CÂMARA MUNICIPAL",
            "numero_empenho": r.get("num_empenho"),
            "id_empenho": r.get("num_empenho") or r.get("id"),
            "numero_pagamento": r.get("codigo"),
            "data_empenho": r.get("data_diaria") or r.get("data"),
            "data_pagamento": r.get("data"),
            "valor_empenho": _to_float(r.get("valor")),
            "valor_pago": _to_float(r.get("valor")),
            "descricao_empenho": r.get("motivo_afastamento") or r.get("cidade") or "",
            "cpf_direto": r.get("cnpj_cpf") or "",
            "exercicio": int(r.get("exercicio") or 2026),
        }
        for r in sigafi_data.get("diarias", [])
    ]

    # Propagar CPF direto nas diárias via empenhos sintéticos para o AnalisadorDiarias recuperar automaticamente
    for r in sigafi_data.get("diarias", []):
        if r.get("cnpj_cpf") and (r.get("num_empenho") or r.get("id")):
            pagamentos.append({
                "id_empenho": str(r.get("num_empenho") or r.get("id")),
                "cpf_cnpj": r.get("cnpj_cpf"),
                "fornecedor_nome": r.get("nome"),
                "valor_pago": 0.0,
                "data_pagamento": "",
                "exercicio": int(r.get("exercicio") or 2026),
            })

    servidores = [
        {
            "nome_servidor": r.get("nome"),
            "funcao": r.get("cargo"),
            "situacao_atual": r.get("vinculo") or "ATIVO",
            "doc": r.get("doc"),
            "exercicio": int(r.get("exercicio") or 2026),
        }
        for r in sigafi_data.get("servidores", [])
    ]

    # Agrupar fornecedores por CPF/CNPJ ou nome a partir de pagamentos reais
    forn_grp: dict[str, dict[str, Any]] = {}
    for p in sigafi_data.get("pagamentos", []):
        nome = str(p.get("nome") or "").strip()
        doc = str(p.get("cnpj_cpf") or "").strip()
        key = _only_digits(doc) or nome.upper()
        if not key:
            continue
        ent = forn_grp.setdefault(key, {
            "fornecedor_nome": nome,
            "fornecedor_cpf_cnpj": doc,
            "valor_empenhado": 0.0,
            "valor_liquidado": 0.0,
            "valor_pago": 0.0,
            "valor_apagar": 0.0,
        })
        v = _to_float(p.get("valor"))
        ent["valor_empenhado"] = round(ent["valor_empenhado"] + v, 2)
        ent["valor_liquidado"] = round(ent["valor_liquidado"] + v, 2)
        ent["valor_pago"] = round(ent["valor_pago"] + v, 2)

    fiscais = [
        {"numero_contrato": c["numero_contrato"], "fiscal_nome": c["fiscal_nome"]}
        for c in contratos
        if c.get("fiscal_nome")
    ]

    obras = [
        {
            "id_obra": r.get("id"),
            "descricao_objeto": r.get("descricao"),
            "data_situacao": r.get("data"),
            "exercicio": int(r.get("exercicio") or 2026),
        }
        for r in sigafi_data.get("obras", [])
    ]

    return {
        "licitacoes": licitacoes,
        "contratos": contratos,
        "dispensas_valor": dispensas,
        "naf": [],
        "fiscais_contrato": fiscais,
        "empenhos": empenhos,
        "liquidacoes": sigafi_data.get("liquidacoes", []),
        "pagamentos": pagamentos,
        "fornecedores": list(forn_grp.values()),
        "servidores": servidores,
        "diarias": diarias,
        "obras": obras,
        "convenios": [],
        "despesa_unidade": [],
        "despesa_funcao": [],
        "despesa_natureza": [],
    }
