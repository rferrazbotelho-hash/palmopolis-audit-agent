"""Módulo de Pagamento de Diárias — Pesquisa por Nome ou CPF e Lista Cronológica."""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import pandas as pd
from openpyxl import Workbook
from openpyxl.utils.dataframe import dataframe_to_rows

from config import OUTPUT_DIR
from engine.fornecedor_contratos import _iso_date
from engine.reconciliador import _norm_text, _to_float

log = logging.getLogger("engine.diarias")


class AnalisadorDiarias:
    def __init__(self, mem_data: dict[str, list[dict[str, Any]]]) -> None:
        self.mem = mem_data

    def build(self) -> dict[str, Any]:
        diarias = self.mem.get("diarias", [])
        pagamentos = self.mem.get("pagamentos", [])
        empenhos = self.mem.get("empenhos", [])
        servidores = self.mem.get("servidores", [])

        # Mapear id_empenho -> cpf_cnpj (via pagamentos e empenhos)
        cpf_by_emp: dict[str, str] = {}
        for p in pagamentos:
            eid = str(p.get("id_empenho") or "").strip()
            cpf = str(p.get("cpf_cnpj") or "").strip()
            if eid and cpf:
                cpf_by_emp[eid] = cpf
        for e in empenhos:
            eid = str(e.get("id_empenho") or "").strip()
            cpf = str(e.get("fornecedor_cpf_cnpj") or "").strip()
            if eid and cpf and eid not in cpf_by_emp:
                cpf_by_emp[eid] = cpf

        # Mapear nome_servidor normalizado -> funcao e cpf (se houver)
        func_by_nome: dict[str, str] = {}
        for s in servidores:
            nm = _norm_text(s.get("nome_servidor"))
            if nm:
                func_by_nome[nm] = str(s.get("funcao") or "").strip()

        # Também propagar CPF entre registros do mesmo servidor
        cpf_by_nome: dict[str, str] = {}
        for d in diarias:
            eid = str(d.get("id_empenho") or "").strip()
            nm = _norm_text(d.get("nome_servidor"))
            if eid in cpf_by_emp and nm and nm not in cpf_by_nome:
                cpf_by_nome[nm] = cpf_by_emp[eid]

        registros: list[dict[str, Any]] = []
        resumo_srv: dict[str, dict[str, Any]] = {}

        for d in diarias:
            eid = str(d.get("id_empenho") or "").strip()
            nome = str(d.get("nome_servidor") or "").strip()
            nm_norm = _norm_text(nome)
            cpf = cpf_by_emp.get(eid) or cpf_by_nome.get(nm_norm, "")
            funcao = func_by_nome.get(nm_norm, "")
            unidade = str(d.get("unidade_orcamentaria") or "").strip()
            dt_iso, dt_br = _iso_date(d.get("data_pagamento") or d.get("data_empenho"))
            v_emp = round(_to_float(d.get("valor_empenho")), 2)
            v_pago = round(_to_float(d.get("valor_pago")), 2)

            registros.append({
                "data_iso": dt_iso,
                "data_pagamento": dt_br,
                "data_empenho": str(d.get("data_empenho") or "").strip(),
                "exercicio": d.get("exercicio"),
                "nome_servidor": nome,
                "cpf": cpf,
                "funcao": funcao,
                "unidade_orcamentaria": unidade,
                "numero_empenho": d.get("numero_empenho"),
                "id_empenho": eid,
                "numero_pagamento": d.get("numero_pagamento"),
                "valor_empenho": v_emp,
                "valor_pago": v_pago,
                "descricao": str(d.get("descricao_empenho") or "").strip(),
            })

            entry = resumo_srv.setdefault(nm_norm or nome, {
                "nome_servidor": nome,
                "cpf": cpf,
                "funcao": funcao,
                "unidade_orcamentaria": unidade,
                "qtd_diarias": 0,
                "total_empenhado": 0.0,
                "total_pago": 0.0,
            })
            if not entry["cpf"] and cpf:
                entry["cpf"] = cpf
            entry["qtd_diarias"] += 1
            entry["total_empenhado"] = round(entry["total_empenhado"] + v_emp, 2)
            entry["total_pago"] = round(entry["total_pago"] + v_pago, 2)

        registros.sort(key=lambda r: (r["data_iso"], str(r["numero_pagamento"] or "")))
        servidores_lista = sorted(resumo_srv.values(), key=lambda x: x["total_pago"], reverse=True)

        log.info("Diárias processadas: %d servidores, %d pagamentos.", len(servidores_lista), len(registros))
        return {
            "servidores_resumo": servidores_lista,
            "pagamentos_diarias": registros,
            "total_pago": round(sum(r["valor_pago"] for r in registros), 2),
            "total_empenhado": round(sum(r["valor_empenho"] for r in registros), 2),
        }


def export_diarias_pagamento(bundle: dict[str, Any], out_dir: Path | None = None) -> dict[str, Path]:
    dest = out_dir or OUTPUT_DIR
    dest.mkdir(parents=True, exist_ok=True)

    json_path = dest / "pagamento_diarias.json"
    json_path.write_text(json.dumps(bundle, ensure_ascii=False), encoding="utf-8")

    xlsx_path = dest / "pagamento_diarias_completo.xlsx"
    wb = Workbook()
    ws1 = wb.active
    ws1.title = "Resumo_por_Servidor"
    df_srv = pd.DataFrame(bundle.get("servidores_resumo", []))
    if not df_srv.empty:
        for r in dataframe_to_rows(df_srv, index=False, header=True):
            ws1.append(r)

    ws2 = wb.create_sheet("Pagamentos_Diarias")
    df_pag = pd.DataFrame(bundle.get("pagamentos_diarias", []))
    if not df_pag.empty:
        cols = [
            "data_pagamento", "exercicio", "nome_servidor", "cpf", "funcao",
            "unidade_orcamentaria", "numero_empenho", "numero_pagamento",
            "valor_empenho", "valor_pago", "descricao",
        ]
        df_pag = df_pag[[c for c in cols if c in df_pag.columns]]
        for r in dataframe_to_rows(df_pag, index=False, header=True):
            ws2.append(r)

    wb.save(xlsx_path)
    log.info("Exportado pagamento de diárias em %s", dest)
    return {"json": json_path, "xlsx": xlsx_path}
