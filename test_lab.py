"""Ambiente de Testes e Análise Dirigida por Seleção de Itens — Palmópolis/MG.

Permite selecionar itens específicos (trilhas legais, exercícios, modalidades,
fornecedores, números de processo/contrato) e executar análises isoladas tanto
sobre massa sintética (sandbox) quanto sobre os dados reais já coletados em
`data/raw/`, gerando relatórios dedicados em `data/test_lab/`.

Exemplos de uso:
  python test_lab.py --interactive
  python test_lab.py --source raw --itens licitacoes dispensas --exercicios 2026
  python test_lab.py --source raw --itens contratos fornecedores --fornecedor "PALMOPOLIS"
  python test_lab.py --source sandbox --itens todos
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from config import DATA_DIR, setup_logging
from engine.analise_critica import AnalisadorCritico
from engine.reconciliador import AuditResult, Reconciliador
from engine.report_builder import build_analise_critica_html, build_dashboard_html, build_excel_master
from main import _load_from_raw

TEST_LAB_DIR = DATA_DIR / "test_lab"

# Catálogo de itens selecionáveis para análise
ITENS_CATALOGO: dict[str, dict[str, Any]] = {
    "licitacoes": {
        "titulo": "Licitações e Editais (Memory × PNCP — Arts. 54 e 94)",
        "sheets": ["Cruzamento_Licitacoes", "Memory_Licitacoes", "PNCP_Contratacoes", "PNCP_Arquivos"],
        "achados": {"ACH-01", "ACH-02", "ACH-07"},
    },
    "contratos": {
        "titulo": "Contratos e Tempestividade (Memory × PNCP — Arts. 94 e 117)",
        "sheets": ["Cruzamento_Contratos", "Memory_Contratos", "PNCP_Contratos"],
        "achados": {"ACH-03", "ACH-04", "ACH-05", "ACH-09"},
    },
    "dispensas": {
        "titulo": "Dispensas por Valor e Fracionamento (Art. 75, I, II e §1º)",
        "sheets": ["Auditoria_Art75_Dispensas", "Memory_Dispensas", "Memory_NAF"],
        "achados": {"ACH-06"},
    },
    "fornecedores": {
        "titulo": "Fornecedores Curva ABC e Vínculos com Servidores (Arts. 9º e 14)",
        "sheets": ["Fornecedores_CurvaABC", "Memory_Empenhos"],
        "achados": {"ACH-08"},
    },
    "lai": {
        "titulo": "Transparência Ativa e Cobertura LAI (Lei nº 12.527/2011)",
        "sheets": ["Transparencia_LAI", "Log_Extracoes"],
        "achados": {"ACH-10"},
    },
    "obras_convenios": {
        "titulo": "Obras Públicas e Convênios (Memory)",
        "sheets": ["Memory_Obras", "Memory_Convenios"],
        "achados": set(),
    },
    "analise_critica": {
        "titulo": "Análise Crítica de Variações Inconsistentes (Bases do Governo)",
        "sheets": [
            "Critica_Ranking", "Critica_Var_Valores", "Critica_Orcamentaria",
            "Critica_Interanual", "Critica_Contratos_NAF", "Critica_Itens_PNCP", "Critica_Outliers_Diarias",
        ],
        "achados": set(),
    },
}


def _sandbox_data() -> tuple[dict[str, list[dict[str, Any]]], dict[str, list[dict[str, Any]]], dict[str, list[dict[str, Any]]], list[dict[str, Any]]]:
    """Importa a mesma massa sintética controlada usada na suíte pytest."""
    from tests.conftest import dados_sinteticos

    # Invoca a função subjacente da fixture pytest
    fn = getattr(dados_sinteticos, "__wrapped__", dados_sinteticos)
    d = fn()
    return d["memory"], d["pncp"], d["portal"], d["statuses"]


def _filter_records(
    records: list[dict[str, Any]],
    *,
    modalidade: str | None = None,
    fornecedor: str | None = None,
    numero: str | None = None,
) -> list[dict[str, Any]]:
    if not records or not any((modalidade, fornecedor, numero)):
        return records
    out: list[dict[str, Any]] = []
    for r in records:
        if modalidade:
            mod_val = str(r.get("modalidade") or r.get("modalidadeNome") or "")
            if modalidade.lower() not in mod_val.lower():
                continue
        if fornecedor:
            forn_val = " ".join(
                str(r.get(k) or "")
                for k in ("fornecedor", "fornecedor_nome", "fornecedor_cpf_cnpj", "cpf_cnpj", "niFornecedor", "nomeRazaoSocialFornecedor")
            )
            if fornecedor.lower() not in forn_val.lower():
                continue
        if numero:
            num_val = " ".join(
                str(r.get(k) or "")
                for k in ("numero_licitacao", "numero_contrato", "numero_direta", "numeroCompra", "numeroContratoEmpenho", "numeroControlePNCP")
            )
            if numero.lower() not in num_val.lower():
                continue
        out.append(r)
    return out


def aplicar_filtros_selecao(
    mem: dict[str, list[dict[str, Any]]],
    pncp: dict[str, list[dict[str, Any]]],
    *,
    modalidade: str | None = None,
    fornecedor: str | None = None,
    numero: str | None = None,
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, list[dict[str, Any]]]]:
    if not any((modalidade, fornecedor, numero)):
        return mem, pncp
    mem_f = {
        k: _filter_records(v, modalidade=modalidade, fornecedor=fornecedor, numero=numero)
        if k in ("licitacoes", "contratos", "dispensas_valor", "naf", "empenhos", "fornecedores")
        else v
        for k, v in mem.items()
    }
    pncp_f = {
        k: _filter_records(v, modalidade=modalidade, fornecedor=fornecedor, numero=numero)
        if k in ("contratacoes", "contratos")
        else v
        for k, v in pncp.items()
    }
    return mem_f, pncp_f


def filtrar_resultado_por_itens(result: AuditResult, itens: list[str]) -> AuditResult:
    if "todos" in itens:
        return result
    sheets_keep: list[str] = ["Achados_Auditoria"]
    achados_codes: set[str] = set()
    for it in itens:
        meta = ITENS_CATALOGO.get(it)
        if not meta:
            continue
        for sh in meta["sheets"]:
            if sh not in sheets_keep:
                sheets_keep.append(sh)
        achados_codes.update(meta["achados"])

    achados_filtrados = [a for a in result.achados if a.codigo in achados_codes]
    dfs_filtrados = {k: v for k, v in result.dataframes.items() if k in sheets_keep}
    if "Achados_Auditoria" in dfs_filtrados and not dfs_filtrados["Achados_Auditoria"].empty:
        df_a = dfs_filtrados["Achados_Auditoria"]
        dfs_filtrados["Achados_Auditoria"] = df_a[df_a["codigo"].isin(achados_codes)].reset_index(drop=True)

    kpis = dict(result.kpis)
    kpis["achados_total"] = len(achados_filtrados)
    kpis["achados_criticos"] = sum(1 for a in achados_filtrados if a.severidade == "CRITICO")
    kpis["achados_altos"] = sum(1 for a in achados_filtrados if a.severidade == "ALTO")
    kpis["achados_medios"] = sum(1 for a in achados_filtrados if a.severidade == "MEDIO")

    return AuditResult(achados=achados_filtrados, kpis=kpis, dataframes=dfs_filtrados)


def menu_interativo() -> argparse.Namespace:
    keys = list(ITENS_CATALOGO.keys())
    print("\n=== AMBIENTE DE TESTES E ANÁLISE SELETIVA — PALMÓPOLIS/MG ===")
    for idx, k in enumerate(keys, start=1):
        print(f"  [{idx}] {k:<16} - {ITENS_CATALOGO[k]['titulo']}")
    print("  [0] todos            - Todas as trilhas e planilhas")
    sel = input("\nSelecione os itens (ex: 1,3 ou 0 para todos): ").strip() or "0"
    if "0" in sel.split(","):
        itens = ["todos"]
    else:
        itens = [keys[int(s.strip()) - 1] for s in sel.split(",") if s.strip().isdigit() and 1 <= int(s.strip()) <= len(keys)]
        if not itens:
            itens = ["todos"]

    src = input("Fonte de dados [raw/sandbox] (padrão: raw): ").strip().lower() or "raw"
    ex_raw = input("Exercícios [ex: 2025 2026] (padrão: 2025 2026): ").strip() or "2025 2026"
    exercicios = [int(x) for x in ex_raw.split() if x.isdigit()] or [2025, 2026]
    mod = input("Filtro de modalidade (Enter para todas): ").strip() or None
    forn = input("Filtro de fornecedor/CNPJ (Enter para todos): ").strip() or None
    num = input("Filtro de número processo/contrato (Enter para todos): ").strip() or None

    return argparse.Namespace(
        interactive=False,
        source=src if src in ("raw", "sandbox") else "raw",
        itens=itens,
        exercicios=exercicios,
        modalidade=mod,
        fornecedor=forn,
        numero=num,
        tag="",
    )


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Ambiente de testes e análise por seleção de itens")
    p.add_argument("--interactive", action="store_true", help="Abre menu interativo para seleção dos itens")
    p.add_argument("--source", choices=["raw", "sandbox"], default="raw",
                   help="raw = JSONs em data/raw/; sandbox = massa sintética controlada")
    p.add_argument("--itens", nargs="+", default=["todos"],
                   choices=["todos", *ITENS_CATALOGO.keys()],
                   help="Itens/trilhas a analisar")
    p.add_argument("--exercicios", nargs="+", type=int, default=[2025, 2026], help="Exercícios a incluir")
    p.add_argument("--modalidade", default=None, help="Filtrar por trecho do nome da modalidade")
    p.add_argument("--fornecedor", default=None, help="Filtrar por trecho do nome ou CNPJ/CPF do fornecedor")
    p.add_argument("--numero", default=None, help="Filtrar por número de processo/contrato/PNCP")
    p.add_argument("--tag", default="", help="Nome curto para a pasta de saída em data/test_lab/")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    if args.interactive:
        args = menu_interativo()

    log = setup_logging("INFO")
    exercicios = sorted(set(args.exercicios))

    if args.source == "sandbox":
        mem, pncp, portal, statuses = _sandbox_data()
    else:
        mem, pncp, portal, statuses = _load_from_raw(exercicios)

    mem, pncp = aplicar_filtros_selecao(
        mem, pncp, modalidade=args.modalidade, fornecedor=args.fornecedor, numero=args.numero
    )

    full_result = Reconciliador(
        memory_data=mem,
        pncp_data=pncp,
        portal_data=portal,
        extraction_statuses=statuses,
        exercicios=exercicios,
    ).run()

    critica_result = AnalisadorCritico(
        memory_data=mem,
        pncp_data=pncp,
        cruzamento_lic=full_result.dataframes.get("Cruzamento_Licitacoes"),
        exercicios=exercicios,
    ).run()
    full_result.dataframes.update(critica_result.dataframes)

    selected = filtrar_resultado_por_itens(full_result, args.itens)

    run_name = args.tag or f"{args.source}_{'_'.join(args.itens)}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    out_dir = TEST_LAB_DIR / run_name
    out_dir.mkdir(parents=True, exist_ok=True)

    xlsx = build_excel_master(selected, output_path=out_dir / "analise_selecionada.xlsx")
    html = build_dashboard_html(selected, statuses, output_path=out_dir / "dashboard_selecionado.html")
    if "todos" in args.itens or "analise_critica" in args.itens:
        build_analise_critica_html(critica_result, output_path=out_dir / "painel_analise_critica.html")
    resumo = out_dir / "resumo_selecao.json"
    resumo.write_text(
        json.dumps(
            {
                "parametros": {
                    "source": args.source,
                    "itens": args.itens,
                    "exercicios": exercicios,
                    "modalidade": args.modalidade,
                    "fornecedor": args.fornecedor,
                    "numero": args.numero,
                },
                "kpis": selected.kpis,
                "achados": [a.model_dump() for a in selected.achados],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print("\n--- RESULTADO DA ANÁLISE SELECIONADA ---")
    print(f"Fonte: {args.source} | Itens: {args.itens} | Exercícios: {exercicios}")
    print(f"Achados no recorte: {len(selected.achados)}")
    for a in selected.achados:
        print(f"  [{a.severidade:<7}] {a.codigo} | {a.titulo} (qtd={a.quantidade}, R$ {a.valor_envolvido:,.2f})")
    print(f"\nSaídas isoladas em: {out_dir}")
    print(f"  - {xlsx.name}")
    print(f"  - {html.name}")
    print(f"  - {resumo.name}")
    log.info("Test Lab concluído em %s", out_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
