"""Gerador do Excel Master (.xlsx) e Dashboard Executivo (.html)."""
from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
from jinja2 import Template
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.utils.dataframe import dataframe_to_rows

from config import OUTPUT_DIR, settings
from engine.analise_critica import AnaliseCriticaResult
from engine.reconciliador import AuditResult

log = logging.getLogger("engine.report")

_HEADER_FILL = PatternFill("solid", fgColor="1B365D")
_HEADER_FONT = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
_SUBHEADER_FILL = PatternFill("solid", fgColor="E9EEF5")
_THIN_BORDER = Border(
    left=Side(style="thin", color="D0D7DE"),
    right=Side(style="thin", color="D0D7DE"),
    top=Side(style="thin", color="D0D7DE"),
    bottom=Side(style="thin", color="D0D7DE"),
)
_SEV_FILLS = {
    "CRITICO": PatternFill("solid", fgColor="FDE2E1"),
    "ALTO": PatternFill("solid", fgColor="FEF0D9"),
    "MEDIO": PatternFill("solid", fgColor="FFF9DB"),
    "INFO": PatternFill("solid", fgColor="E7F5FF"),
}

_CURRENCY_COLS = (
    "valor", "valor_envolvido", "valor_memory", "valor_pncp", "diferenca_valor",
    "valor_contrato", "valor_contrato_num", "valor_homologado_num", "valor_maximo_num",
    "valor_total", "valor_total_num", "valor_empenho", "valor_empenho_num",
    "valor_empenhado_num", "valor_liquidado_num", "valor_pago_num", "valor_apagar_num",
    "valor_ref", "teto_art75", "valorTotalEstimado", "valorTotalHomologado",
    "valorGlobal", "valorInicial",
)


def _fmt_brl(v: float) -> str:
    s = f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {s}"


def _clean_cell(val: Any) -> Any:
    if isinstance(val, (dict, list)):
        return json.dumps(val, ensure_ascii=False)[:1000]
    if pd.isna(val) if not isinstance(val, (str, bytes, bool)) else False:
        return None
    if isinstance(val, str) and len(val) > 32000:
        return val[:32000]
    return val


def _style_worksheet(ws: Any, df: pd.DataFrame) -> None:
    ws.views.sheetView[0].showGridLines = True
    ws.freeze_panes = "A2"
    if df.empty:
        return
    max_row = ws.max_row
    max_col = ws.max_column
    ws.auto_filter.ref = f"A1:{get_column_letter(max_col)}{max_row}"

    for col_idx in range(1, max_col + 1):
        cell = ws.cell(row=1, column=col_idx)
        cell.fill = _HEADER_FILL
        cell.font = _HEADER_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = _THIN_BORDER

    col_names = [str(c) for c in df.columns]
    for row_idx in range(2, max_row + 1):
        sev_val = None
        if "severidade" in col_names:
            sev_val = ws.cell(row=row_idx, column=col_names.index("severidade") + 1).value
        for col_idx, cname in enumerate(col_names, start=1):
            c = ws.cell(row=row_idx, column=col_idx)
            c.border = _THIN_BORDER
            c.alignment = Alignment(vertical="top", wrap_text=cname in ("descricao", "objeto", "objeto_memory", "evidencia"))
            if cname in _CURRENCY_COLS and isinstance(c.value, (int, float)):
                c.number_format = '#,##0.00'
            if cname == "severidade" and sev_val in _SEV_FILLS:
                c.fill = _SEV_FILLS[sev_val]
                c.font = Font(name="Calibri", size=10, bold=True)

    for col_idx, cname in enumerate(col_names, start=1):
        sample_lens = [len(cname)] + [
            len(str(ws.cell(row=r, column=col_idx).value or ""))
            for r in range(2, min(max_row + 1, 60))
        ]
        ws.column_dimensions[get_column_letter(col_idx)].width = min(max(max(sample_lens) + 4, 12), 55)


def build_excel_master(result: AuditResult, output_path: Path | None = None) -> Path:
    """Gera o Excel Master consolidado com todas as trilhas e bases."""
    out = output_path or (OUTPUT_DIR / "auditoria_palmopolis_master.xlsx")
    out.parent.mkdir(parents=True, exist_ok=True)

    wb = Workbook()
    ws_res = wb.active
    ws_res.title = "Resumo_Executivo"

    ws_res["A1"] = f"AUDITORIA DE CONTROLE EXTERNO — {settings.audit_entidade_nome.upper()}"
    ws_res["A1"].font = Font(name="Calibri", size=14, bold=True, color="1B365D")
    ws_res["A2"] = f"CNPJ: {settings.audit_cnpj} | Exercícios: {', '.join(map(str, result.kpis.get('exercicios', [])))} | Gerado em: {datetime.now().strftime('%d/%m/%Y %H:%M')}"
    ws_res["A2"].font = Font(name="Calibri", size=10, italic=True, color="555555")

    kpis = result.kpis
    resumo_rows = [
        ("Indicador", "Valor"),
        ("Licitações registradas no Portal Memory", kpis.get("memory_licitacoes_qtd", 0)),
        ("Valor homologado em Licitações (Memory)", kpis.get("memory_licitacoes_valor", 0.0)),
        ("Contratos/Aditivos no Portal Memory", kpis.get("memory_contratos_qtd", 0)),
        ("Valor total de Contratos (Memory)", kpis.get("memory_contratos_valor", 0.0)),
        ("Dispensas por Valor (Memory)", kpis.get("memory_dispensas_qtd", 0)),
        ("NAFs emitidas (Memory)", kpis.get("memory_naf_qtd", 0)),
        ("Valor total em NAFs (Memory)", kpis.get("memory_naf_valor", 0.0)),
        ("Empenhos extraídos (Memory)", kpis.get("memory_empenhos_qtd", 0)),
        ("Valor empenhado extraído (Memory)", kpis.get("memory_empenhos_valor", 0.0)),
        ("Servidores cadastrados (Memory)", kpis.get("memory_servidores_qtd", 0)),
        ("Contratações publicadas no PNCP", kpis.get("pncp_contratacoes_qtd", 0)),
        ("Valor estimado no PNCP", kpis.get("pncp_contratacoes_valor_est", 0.0)),
        ("Contratos publicados no PNCP", kpis.get("pncp_contratos_qtd", 0)),
        ("Arquivos/Editais anexados no PNCP", kpis.get("pncp_arquivos_qtd", 0)),
        ("Licitações conciliadas (Memory x PNCP)", kpis.get("conciliadas_lic_qtd", 0)),
        ("Licitações Memory sem PNCP", kpis.get("sem_pncp_lic_qtd", 0)),
        ("Taxa de aderência PNCP — Licitações (%)", kpis.get("taxa_aderencia_pncp_lic_pct", 0.0)),
        ("Contratos conciliados (Memory x PNCP)", kpis.get("conciliados_ctr_qtd", 0)),
        ("Contratos Memory sem PNCP", kpis.get("sem_pncp_ctr_qtd", 0)),
        ("Total de Achados de Auditoria", kpis.get("achados_total", 0)),
        ("Achados Críticos / Altos / Médios", f"{kpis.get('achados_criticos', 0)} / {kpis.get('achados_altos', 0)} / {kpis.get('achados_medios', 0)}"),
    ]
    for r_idx, (k, v) in enumerate(resumo_rows, start=4):
        c1 = ws_res.cell(row=r_idx, column=1, value=k)
        c2 = ws_res.cell(row=r_idx, column=2, value=v)
        c1.border = _THIN_BORDER
        c2.border = _THIN_BORDER
        if r_idx == 4:
            c1.fill = _HEADER_FILL
            c2.fill = _HEADER_FILL
            c1.font = _HEADER_FONT
            c2.font = _HEADER_FONT
        else:
            if "Valor" in k:
                c2.number_format = 'R$ #,##0.00'
    ws_res.column_dimensions["A"].width = 48
    ws_res.column_dimensions["B"].width = 28

    for sheet_name, df in result.dataframes.items():
        safe_name = sheet_name[:31]
        ws = wb.create_sheet(title=safe_name)
        if df.empty:
            ws["A1"] = "Sem registros para este conjunto de dados."
            continue
        clean_df = df.copy()
        for col in clean_df.columns:
            clean_df[col] = clean_df[col].apply(_clean_cell)
        for row in dataframe_to_rows(clean_df, index=False, header=True):
            ws.append(row)
        _style_worksheet(ws, clean_df)

    wb.save(out)
    log.info("Excel Master salvo em %s", out)
    return out


_HTML_TEMPLATE = Template("""<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Auditoria Municipal — {{ entidade }}</title>
  <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.4/dist/chart.umd.min.js"></script>
  <style>
    :root {
      --bg: #f4f6f9; --card: #ffffff; --navy: #1b365d; --accent: #2b6cb0;
      --crit: #c53030; --alto: #dd6b20; --med: #b7791f; --ok: #2f855a;
      --border: #e2e8f0; --text: #1a202c; --muted: #64748b;
    }
    * { box-sizing: border-box; }
    body { margin: 0; font-family: 'Segoe UI', Roboto, Arial, sans-serif; background: var(--bg); color: var(--text); }
    header { background: linear-gradient(135deg, #1b365d, #2b4c7e); color: #fff; padding: 24px 32px; }
    header h1 { margin: 0 0 6px 0; font-size: 22px; }
    header p { margin: 0; opacity: 0.9; font-size: 13px; }
    main { max-width: 1360px; margin: 24px auto; padding: 0 20px 40px; }
    .kpi-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(210px, 1fr)); gap: 14px; margin-bottom: 24px; }
    .kpi { background: var(--card); border: 1px solid var(--border); border-radius: 10px; padding: 16px; box-shadow: 0 1px 3px rgba(0,0,0,.04); }
    .kpi .label { font-size: 12px; color: var(--muted); text-transform: uppercase; letter-spacing: .4px; }
    .kpi .val { font-size: 24px; font-weight: 700; color: var(--navy); margin: 6px 0 2px; }
    .kpi .sub { font-size: 12px; color: var(--muted); }
    .charts { display: grid; grid-template-columns: repeat(auto-fit, minmax(420px, 1fr)); gap: 18px; margin-bottom: 24px; }
    .card { background: var(--card); border: 1px solid var(--border); border-radius: 10px; padding: 18px; margin-bottom: 20px; box-shadow: 0 1px 3px rgba(0,0,0,.04); }
    .card h2 { margin: 0 0 14px; font-size: 16px; color: var(--navy); border-bottom: 1px solid var(--border); padding-bottom: 8px; }
    table { width: 100%; border-collapse: collapse; font-size: 13px; }
    th, td { text-align: left; padding: 9px 10px; border-bottom: 1px solid var(--border); vertical-align: top; }
    th { background: #f8fafc; color: var(--navy); font-weight: 600; }
    .badge { display: inline-block; padding: 2px 8px; border-radius: 999px; font-size: 11px; font-weight: 700; }
    .CRITICO { background: #fde2e1; color: var(--crit); }
    .ALTO { background: #fef0d9; color: var(--alto); }
    .MEDIO { background: #fff9db; color: var(--med); }
    .INFO, .OK { background: #e6fffa; color: var(--ok); }
    .VAZIO, .DEFICIT_TRANSPARENCIA { background: #fff9db; color: var(--med); }
    .ERRO { background: #fde2e1; color: var(--crit); }
    .num { text-align: right; font-variant-numeric: tabular-nums; }
  </style>
</head>
<body>
<header>
  <h1>Painel Executivo de Auditoria Municipal — {{ entidade }}</h1>
  <p>CNPJ {{ cnpj }} | Exercícios: {{ exercicios }} | Referencial: Lei 14.133/2021 (Arts. 9º, 14, 54, 75 e 94) e LAI (Lei 12.527/2011) | Gerado em {{ gerado_em }}</p>
</header>
<main>
  <section class="kpi-grid">
    <div class="kpi"><div class="label">Licitações (Memory)</div><div class="val">{{ kpis.memory_licitacoes_qtd }}</div><div class="sub">Homologado: {{ fmt_brl(kpis.memory_licitacoes_valor) }}</div></div>
    <div class="kpi"><div class="label">Contratos (Memory)</div><div class="val">{{ kpis.memory_contratos_qtd }}</div><div class="sub">Total: {{ fmt_brl(kpis.memory_contratos_valor) }}</div></div>
    <div class="kpi"><div class="label">Contratações no PNCP</div><div class="val">{{ kpis.pncp_contratacoes_qtd }}</div><div class="sub">Contratos PNCP: {{ kpis.pncp_contratos_qtd }} | Arquivos: {{ kpis.pncp_arquivos_qtd }}</div></div>
    <div class="kpi"><div class="label">Aderência PNCP (Licitações)</div><div class="val">{{ kpis.taxa_aderencia_pncp_lic_pct }}%</div><div class="sub">{{ kpis.conciliadas_lic_qtd }} conciliadas | {{ kpis.sem_pncp_lic_qtd }} sem PNCP</div></div>
    <div class="kpi"><div class="label">NAFs Emitidas (Memory)</div><div class="val">{{ kpis.memory_naf_qtd }}</div><div class="sub">Volume: {{ fmt_brl(kpis.memory_naf_valor) }}</div></div>
    <div class="kpi"><div class="label">Achados de Auditoria</div><div class="val">{{ kpis.achados_total }}</div><div class="sub">Críticos: {{ kpis.achados_criticos }} | Altos: {{ kpis.achados_altos }} | Médios: {{ kpis.achados_medios }}</div></div>
  </section>

  <section class="charts">
    <div class="card">
      <h2>Conciliação Local (Memory) x PNCP</h2>
      <canvas id="chartConc" height="190"></canvas>
    </div>
    <div class="card">
      <h2>Top 10 Fornecedores por Valor Empenhado (R$)</h2>
      <canvas id="chartForn" height="190"></canvas>
    </div>
  </section>

  <section class="card">
    <h2>Matriz de Achados — Lei nº 14.133/2021 e Lei nº 12.527/2011</h2>
    <table>
      <thead><tr><th>Código</th><th>Severidade</th><th>Base Legal</th><th>Achado</th><th class="num">Qtd</th><th class="num">Valor Envolvido</th><th>Evidência / Amostra</th></tr></thead>
      <tbody>
        {% for a in achados %}
        <tr>
          <td><strong>{{ a.codigo }}</strong></td>
          <td><span class="badge {{ a.severidade }}">{{ a.severidade }}</span></td>
          <td>{{ a.base_legal }}</td>
          <td><strong>{{ a.titulo }}</strong><br><small style="color:#64748b">{{ a.descricao }}</small></td>
          <td class="num">{{ a.quantidade }}</td>
          <td class="num">{{ fmt_brl(a.valor_envolvido) }}</td>
          <td><small>{{ a.evidencia }}</small></td>
        </tr>
        {% endfor %}
      </tbody>
    </table>
  </section>

  <section class="card">
    <h2>Cobertura de Extração — iLAI Memory, PNCP e Portal Institucional</h2>
    <table>
      <thead><tr><th>Fonte</th><th>Conjunto de Dados</th><th>Exercício</th><th class="num">Registros</th><th>Status</th><th>Detalhe</th></tr></thead>
      <tbody>
        {% for s in statuses %}
        <tr>
          <td>{{ s.fonte }}</td>
          <td>{{ s.dataset }}</td>
          <td>{{ s.exercicio if s.exercicio else '-' }}</td>
          <td class="num">{{ s.registros }}</td>
          <td><span class="badge {{ s.status }}">{{ s.status }}</span></td>
          <td><small>{{ s.detalhe }}</small></td>
        </tr>
        {% endfor %}
      </tbody>
    </table>
  </section>
</main>
<script>
new Chart(document.getElementById('chartConc'), {
  type: 'bar',
  data: {
    labels: ['Licitações', 'Contratos'],
    datasets: [
      { label: 'Conciliados', data: [{{ kpis.conciliadas_lic_qtd }}, {{ kpis.conciliados_ctr_qtd }}], backgroundColor: '#2f855a' },
      { label: 'Somente Memory (sem PNCP)', data: [{{ kpis.sem_pncp_lic_qtd }}, {{ kpis.sem_pncp_ctr_qtd }}], backgroundColor: '#c53030' }
    ]
  },
  options: { responsive: true, plugins: { legend: { position: 'bottom' } }, scales: { y: { beginAtZero: true } } }
});

new Chart(document.getElementById('chartForn'), {
  type: 'bar',
  data: {
    labels: {{ top_forn_labels | tojson }},
    datasets: [{ label: 'Valor (R$)', data: {{ top_forn_vals | tojson }}, backgroundColor: '#2b6cb0' }]
  },
  options: { indexAxis: 'y', responsive: true, plugins: { legend: { display: false } } }
});
</script>
</body>
</html>
""")


def build_dashboard_html(
    result: AuditResult,
    statuses: list[dict[str, Any]],
    output_path: Path | None = None,
) -> Path:
    """Gera o Dashboard Executivo HTML interativo."""
    out = output_path or (OUTPUT_DIR / "dashboard_executivo_palmopolis.html")
    out.parent.mkdir(parents=True, exist_ok=True)

    df_forn = result.dataframes.get("Fornecedores_CurvaABC", pd.DataFrame())
    if not df_forn.empty:
        top = df_forn[~df_forn.get("eh_proprio_municipio", False)].head(10)
        labels = [str(x)[:32] for x in top["fornecedor_nome"].fillna("-")]
        vals = [round(float(x), 2) for x in top["valor_ref"].fillna(0)]
    else:
        labels, vals = [], []

    html = _HTML_TEMPLATE.render(
        entidade=settings.audit_entidade_nome,
        cnpj=settings.audit_cnpj,
        exercicios=", ".join(map(str, result.kpis.get("exercicios", []))),
        gerado_em=datetime.now().strftime("%d/%m/%Y %H:%M"),
        kpis=result.kpis,
        achados=[a.model_dump() for a in result.achados],
        statuses=statuses,
        top_forn_labels=labels,
        top_forn_vals=vals,
        fmt_brl=_fmt_brl,
    )
    out.write_text(html, encoding="utf-8")
    log.info("Dashboard HTML salvo em %s", out)
    return out


_CRITICA_HTML_TEMPLATE = Template("""<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Análise Crítica e Variações Inconsistentes — {{ entidade }}</title>
  <style>
    body { margin: 0; font-family: 'Segoe UI', Roboto, Arial, sans-serif; background: #f4f6f9; color: #1a202c; }
    header { background: linear-gradient(135deg, #63171b, #9b2c2c); color: #fff; padding: 22px 30px; }
    header h1 { margin: 0 0 6px; font-size: 21px; }
    header p { margin: 0; font-size: 13px; opacity: 0.9; }
    main { max-width: 1380px; margin: 22px auto; padding: 0 20px 40px; }
    .kpi-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(210px, 1fr)); gap: 14px; margin-bottom: 22px; }
    .kpi { background: #fff; border: 1px solid #e2e8f0; border-radius: 10px; padding: 15px; }
    .kpi .label { font-size: 12px; color: #64748b; text-transform: uppercase; }
    .kpi .val { font-size: 24px; font-weight: 700; color: #742a2a; margin-top: 6px; }
    .card { background: #fff; border: 1px solid #e2e8f0; border-radius: 10px; padding: 18px; margin-bottom: 20px; }
    .card h2 { margin: 0 0 12px; font-size: 16px; color: #1b365d; border-bottom: 1px solid #e2e8f0; padding-bottom: 8px; }
    table { width: 100%; border-collapse: collapse; font-size: 13px; }
    th, td { text-align: left; padding: 8px 10px; border-bottom: 1px solid #e2e8f0; vertical-align: top; }
    th { background: #f8fafc; color: #1b365d; }
    .num { text-align: right; font-variant-numeric: tabular-nums; }
    .badge { display: inline-block; padding: 2px 8px; border-radius: 999px; font-size: 11px; font-weight: 700; }
    .CRITICA { background: #fde2e1; color: #c53030; }
    .ALTA { background: #fef0d9; color: #dd6b20; }
    .MEDIA { background: #fff9db; color: #b7791f; }
  </style>
</head>
<body>
<header>
  <h1>Análise Crítica de Variações Inconsistentes — {{ entidade }}</h1>
  <p>CNPJ {{ cnpj }} | Foco: Divergências entre Bases do Governo (PNCP × Memory × Lei 4.320/64 × Lei 14.133/21) | Gerado em {{ gerado_em }}</p>
</header>
<main>
  <section class="kpi-grid">
    <div class="kpi"><div class="label">Total de Inconsistências</div><div class="val">{{ anomalias|length }}</div></div>
    <div class="kpi"><div class="label">Criticidade Crítica</div><div class="val">{{ qtd_crit }}</div></div>
    <div class="kpi"><div class="label">Criticidade Alta</div><div class="val">{{ qtd_alta }}</div></div>
    <div class="kpi"><div class="label">Valor Total Exposto</div><div class="val">{{ fmt_brl(valor_exposto_total) }}</div></div>
  </section>

  <section class="card">
    <h2>Resumo por Eixo de Risco</h2>
    <table>
      <thead><tr><th>Eixo de Análise Crítica</th><th class="num">Ocorrências</th></tr></thead>
      <tbody>
        {% for eixo, qtd in resumo_eixos.items() %}
        <tr><td>{{ eixo }}</td><td class="num"><strong>{{ qtd }}</strong></td></tr>
        {% endfor %}
      </tbody>
    </table>
  </section>

  <section class="card">
    <h2>Ranking de Variações Inconsistentes para Avaliação Aprofundada</h2>
    <table>
      <thead>
        <tr>
          <th>Score</th><th>Criticidade</th><th>Eixo / Base Gov.</th><th>Item Analisado</th>
          <th>Esperado</th><th>Observado</th><th class="num">Var %</th><th class="num">Valor Exposto</th><th>Ação Recomendada</th>
        </tr>
      </thead>
      <tbody>
        {% for a in anomalias %}
        <tr>
          <td class="num"><strong>{{ a.score_risco }}</strong></td>
          <td><span class="badge {{ a.criticidade }}">{{ a.criticidade }}</span></td>
          <td><strong>{{ a.eixo }}</strong><br><small style="color:#64748b">{{ a.base_governo_ref }}</small></td>
          <td>{{ a.item_analisado }}</td>
          <td>{{ a.esperado }}</td>
          <td>{{ a.observado }}</td>
          <td class="num">{{ "%.1f%%"|format(a.variacao_pct) if a.variacao_pct is not none else "-" }}</td>
          <td class="num">{{ fmt_brl(a.valor_exposto) }}</td>
          <td><small>{{ a.acao_recomendada }}</small></td>
        </tr>
        {% endfor %}
      </tbody>
    </table>
  </section>
</main>
</body>
</html>
""")


def build_analise_critica_html(critica: AnaliseCriticaResult, output_path: Path | None = None) -> Path:
    """Gera o Painel HTML de Análise Crítica e Variações Inconsistentes."""
    out = output_path or (OUTPUT_DIR / "painel_analise_critica.html")
    out.parent.mkdir(parents=True, exist_ok=True)
    anomalias = [a.model_dump() for a in critica.anomalias]
    html = _CRITICA_HTML_TEMPLATE.render(
        entidade=settings.audit_entidade_nome,
        cnpj=settings.audit_cnpj,
        gerado_em=datetime.now().strftime("%d/%m/%Y %H:%M"),
        anomalias=anomalias,
        resumo_eixos=critica.resumo_eixos,
        qtd_crit=sum(1 for a in critica.anomalias if a.criticidade == "CRITICA"),
        qtd_alta=sum(1 for a in critica.anomalias if a.criticidade == "ALTA"),
        valor_exposto_total=sum(a.valor_exposto for a in critica.anomalias),
        fmt_brl=_fmt_brl,
    )
    out.write_text(html, encoding="utf-8")
    log.info("Painel de Análise Crítica HTML salvo em %s", out)
    return out

