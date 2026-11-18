"""Pesquisador de Contratos por Fornecedor, Análise Detalhada de Contratos e Recebimentos Cronológicos.

Cruza Contratos x Licitações x NAFs x Pagamentos do Portal iLAI (Memory) para:
1. Enriquecer cada contrato com Empresa Homologada (fornecedor_nome/fornecedor_cpf_cnpj
   do próprio contrato + fallback NAFs) e dados do Processo Licitatório vinculado;
2. Montar o pesquisador de contratos por fornecedor em lista;
3. Gerar a lista completa de recebimentos em ordem cronológica (Data, Fornecedor,
   Empenho, Contrato, Objeto, Valor Recebido);
4. Fornecer o descritivo completo (Processo, Contrato, Empresa Homologada e Extrato
   de Pagamentos) para a aba de Análise de Contratos.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
from openpyxl import Workbook
from openpyxl.utils.dataframe import dataframe_to_rows

from config import OUTPUT_DIR
from engine.reconciliador import _only_digits, _to_float

log = logging.getLogger("engine.fornecedor_contratos")


def _iso_date(br_or_iso: Any) -> tuple[str, str]:
    """Retorna (YYYY-MM-DD, DD/MM/YYYY) para ordenação cronológica exata."""
    s = str(br_or_iso or "").strip()
    if not s:
        return "9999-12-31", ""
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d", "%d/%m/%Y"):
        try:
            dt = datetime.strptime(s[:19] if "T" in fmt else s[:10], fmt)
            return dt.strftime("%Y-%m-%d"), dt.strftime("%d/%m/%Y")
        except ValueError:
            continue
    return "9999-12-31", s


class PesquisadorContratosRecebimentos:
    def __init__(self, mem_data: dict[str, list[dict[str, Any]]]) -> None:
        self.mem = mem_data

    def build(self) -> dict[str, Any]:
        contratos = self.mem.get("contratos", [])
        licitacoes = self.mem.get("licitacoes", [])
        nafs = self.mem.get("naf", [])
        pagamentos = self.mem.get("pagamentos", [])

        # Índices de licitações por id_licitacao e por (numero_licitacao, exercicio)
        lic_by_id: dict[str, dict[str, Any]] = {}
        lic_by_num: dict[tuple[str, Any], dict[str, Any]] = {}
        for l in licitacoes:
            lid = str(l.get("id_licitacao") or "").strip()
            if lid:
                lic_by_id[lid] = l
            nlic = str(l.get("numero_licitacao") or "").strip()
            if nlic:
                lic_by_num[(nlic, l.get("exercicio"))] = l

        # Índice de contratos por id_contrato
        ctr_by_id: dict[str, dict[str, Any]] = {}
        for c in contratos:
            cid = str(c.get("id_contrato") or "").strip()
            if cid and cid not in ctr_by_id:
                ctr_by_id[cid] = c

        # NAFs: mapeia id_contrato -> nafs, e id_empenho -> contrato
        nafs_by_ctr: dict[str, list[dict[str, Any]]] = {}
        emp_to_ctr: dict[str, dict[str, Any]] = {}
        for n in nafs:
            cid = str(n.get("id_contrato") or "").strip()
            eid = str(n.get("id_empenho") or "").strip()
            if cid:
                nafs_by_ctr.setdefault(cid, []).append(n)
            if eid and cid and cid in ctr_by_id:
                emp_to_ctr[eid] = ctr_by_id[cid]
            elif eid and n.get("numero_contrato"):
                emp_to_ctr[eid] = {
                    "id_contrato": cid,
                    "numero_contrato": n.get("numero_contrato"),
                    "objeto": "",
                }

        # 1. Lista cronológica de recebimentos (pagamentos)
        recebimentos: list[dict[str, Any]] = []
        pago_by_ctr: dict[str, float] = {}

        for p in pagamentos:
            dt_iso, dt_br = _iso_date(p.get("data_pagamento_format") or p.get("data_pagamento"))
            eid = str(p.get("id_empenho") or "").strip()
            forn_nome = str(p.get("fornecedor_nome") or "").strip()
            cpf_cnpj = str(p.get("cpf_cnpj") or "").strip()
            valor_pago = round(_to_float(p.get("valor_pago")), 2)

            ctr = emp_to_ctr.get(eid)
            num_ctr = str(ctr.get("numero_contrato") or "-") if ctr else "-"
            cid = str(ctr.get("id_contrato") or "") if ctr else ""
            obj = (
                str(ctr.get("objeto") or "").strip()
                if ctr and str(ctr.get("objeto") or "").strip()
                else str(p.get("des_despesa") or p.get("tipo_despesa") or "").strip()
            )
            empenho_lbl = str(p.get("empenho_ano") or p.get("numero_empenho") or eid).strip()

            if cid:
                pago_by_ctr[cid] = round(pago_by_ctr.get(cid, 0.0) + valor_pago, 2)

            recebimentos.append({
                "data_iso": dt_iso,
                "data": dt_br,
                "exercicio": p.get("exercicio"),
                "fornecedor_nome": forn_nome,
                "cpf_cnpj": cpf_cnpj,
                "empenho": empenho_lbl,
                "id_empenho": eid,
                "numero_pagamento": str(p.get("numero_pagamento") or "").strip(),
                "contrato": num_ctr,
                "id_contrato": cid,
                "objeto": obj,
                "des_despesa": str(p.get("des_despesa") or "").strip(),
                "valor_recebido": valor_pago,
                "nota_fiscal": str(p.get("nota_fiscal") or "").strip(),
            })

        recebimentos.sort(key=lambda r: (r["data_iso"], str(r["empenho"])))

        # 2. Contratos enriquecidos com fornecedor, processo e valores
        contratos_lista: list[dict[str, Any]] = []
        forn_contratos_count: dict[str, dict[str, Any]] = {}

        for c in contratos:
            cid = str(c.get("id_contrato") or "").strip()
            nafs_c = nafs_by_ctr.get(cid, [])

            forn_nome = str(c.get("fornecedor_nome") or c.get("fornecedor") or "").strip()
            cpf_cnpj = str(c.get("fornecedor_cpf_cnpj") or c.get("cpf_cnpj") or "").strip()

            if not forn_nome and nafs_c:
                nomes = sorted({str(x.get("fornecedor_nome") or "").strip() for x in nafs_c if x.get("fornecedor_nome")})
                cnpjs = sorted({str(x.get("fornecedor_cpf_cnpj") or "").strip() for x in nafs_c if x.get("fornecedor_cpf_cnpj")})
                forn_nome = " | ".join(nomes) if nomes else ""
                cpf_cnpj = " | ".join(cnpjs)

            if not forn_nome:
                forn_nome = "NÃO IDENTIFICADO NA TRANSPARÊNCIA"

            # Dados do processo vinculado
            num_lic = str(c.get("numero_licitacao") or c.get("licitacao_numero") or "").strip()
            id_lic = str(c.get("id_licitacao") or "").strip()
            lic_obj = lic_by_id.get(id_lic) or lic_by_num.get((num_lic, c.get("exercicio")))
            num_direta = str(c.get("numero_compradireta") or "").strip()
            processo_lbl = num_lic or (f"Compra Direta {num_direta}" if num_direta else "-")

            val_ctr = round(_to_float(c.get("valor_contrato")), 2)
            val_nafs = round(sum(_to_float(x.get("valor_total")) for x in nafs_c), 2)
            val_pago = pago_by_ctr.get(cid, 0.0)

            item = {
                "id_contrato": cid,
                "numero_contrato": str(c.get("numero_contrato") or "").strip(),
                "exercicio": c.get("exercicio"),
                "fornecedor_nome": forn_nome,
                "cpf_cnpj": cpf_cnpj,
                "modalidade": str(c.get("modalidade") or "").strip(),
                "tipo_ato": str(c.get("tipo_ato") or "").strip(),
                "situacao": str(c.get("situacao") or "").strip(),
                "inicio_vigencia": str(c.get("inicio_vigencia") or "").strip(),
                "termino_vigencia": str(c.get("termino_vigencia") or "").strip(),
                "data_assinatura": str(c.get("data_assinatura") or "").strip(),
                "data_publicacao": str(c.get("data_publicacao") or "").strip(),
                "processo_numero": processo_lbl,
                "id_processo": str(c.get("id_processo") or "").strip(),
                "data_processo": str(c.get("data_processo") or "").strip(),
                "processo_situacao": str(lic_obj.get("situacao") or "").strip() if lic_obj else "",
                "processo_valor_homologado": round(_to_float(lic_obj.get("valor_homologado")), 2) if lic_obj else 0.0,
                "valor_contrato": val_ctr,
                "qtd_nafs": len(nafs_c),
                "valor_nafs": val_nafs,
                "valor_pago_vinculado": val_pago,
                "objeto": str(c.get("objeto") or "").strip(),
            }
            contratos_lista.append(item)

            for nome_ind in [x.strip() for x in forn_nome.split("|") if x.strip()]:
                fkey = _only_digits(cpf_cnpj) or nome_ind.upper()
                entry = forn_contratos_count.setdefault(fkey, {
                    "fornecedor_nome": nome_ind,
                    "cpf_cnpj": cpf_cnpj,
                    "qtd_contratos": 0,
                    "valor_contratado": 0.0,
                    "valor_pago_contratos": 0.0,
                })
                entry["qtd_contratos"] += 1
                entry["valor_contratado"] = round(entry["valor_contratado"] + val_ctr, 2)
                entry["valor_pago_contratos"] = round(entry["valor_pago_contratos"] + val_pago, 2)

        fornecedores_lista = sorted(
            forn_contratos_count.values(),
            key=lambda x: (x["qtd_contratos"], x["valor_contratado"]),
            reverse=True,
        )

        log.info(
            "Pesquisador gerado: %d fornecedores, %d contratos, %d recebimentos cronológicos.",
            len(fornecedores_lista), len(contratos_lista), len(recebimentos),
        )
        return {
            "fornecedores_lista": fornecedores_lista,
            "contratos": contratos_lista,
            "recebimentos_cronologicos": recebimentos,
        }


def export_contratos_recebimentos(bundle: dict[str, Any], out_dir: Path | None = None) -> dict[str, Path]:
    dest = out_dir or OUTPUT_DIR
    dest.mkdir(parents=True, exist_ok=True)

    json_path = dest / "fornecedor_contratos_recebimentos.json"
    json_path.write_text(json.dumps(bundle, ensure_ascii=False), encoding="utf-8")

    xlsx_path = dest / "contratos_fornecedor_e_recebimentos.xlsx"
    wb = Workbook()
    ws1 = wb.active
    ws1.title = "Contratos_por_Fornecedor"
    df_ctr = pd.DataFrame(bundle.get("contratos", []))
    if not df_ctr.empty:
        for r in dataframe_to_rows(df_ctr, index=False, header=True):
            ws1.append(r)

    ws2 = wb.create_sheet("Recebimentos_Cronologicos")
    df_rec = pd.DataFrame(bundle.get("recebimentos_cronologicos", []))
    if not df_rec.empty:
        cols = ["data", "exercicio", "fornecedor_nome", "cpf_cnpj", "empenho", "contrato", "objeto", "valor_recebido", "nota_fiscal"]
        df_rec = df_rec[[c for c in cols if c in df_rec.columns]]
        for r in dataframe_to_rows(df_rec, index=False, header=True):
            ws2.append(r)

    wb.save(xlsx_path)
    log.info("Exportado pesquisador de contratos e recebimentos em %s", dest)
    return {"json": json_path, "xlsx": xlsx_path}
