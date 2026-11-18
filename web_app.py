"""Servidor Web Local Interativo para Visualização da Auditoria — Palmópolis/MG.

Serve uma interface única (SPA leve) em http://127.0.0.1:8050 com:
- Visão Executiva (KPIs + gráficos Memory x PNCP e Top Fornecedores);
- Relatório do Fiscal de Contas Públicas (apontamentos filtráveis);
- Análise Crítica e Variações Inconsistentes (127 anomalias ordenadas por risco);
- Explorador de Tabelas Reais (Cruzamento Licitações, Contratos, Art. 75, Curva ABC);
- Atalhos para os relatórios HTML individuais e execução de recortes via Test Lab.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from config import OUTPUT_DIR, settings
from engine.analise_critica import AnalisadorCritico
from engine.reconciliador import Reconciliador
from main import _load_from_raw

_CACHE: dict[str, Any] = {}


def _load_portal_bundle(force: bool = False) -> dict[str, Any]:
    if _CACHE and not force:
        return _CACHE

    resumo_p = OUTPUT_DIR / "resumo_auditoria.json"
    critica_p = OUTPUT_DIR / "analise_critica.json"
    fiscal_p = OUTPUT_DIR / "apontamentos_fiscal_contas.json"
    corretor_p = OUTPUT_DIR / "plano_correcao_fiscal_corretor.json"
    jur_p = OUTPUT_DIR / "dossie_juridico_tcu.json"

    resumo = json.loads(resumo_p.read_text(encoding="utf-8")) if resumo_p.exists() else {"kpis": {}, "achados": []}
    critica = json.loads(critica_p.read_text(encoding="utf-8")) if critica_p.exists() else {"resumo_eixos": {}, "anomalias": []}
    fiscal = json.loads(fiscal_p.read_text(encoding="utf-8")) if fiscal_p.exists() else {"apontamentos": []}
    corretor = json.loads(corretor_p.read_text(encoding="utf-8")) if corretor_p.exists() else {"roteiros": []}
    juridico = json.loads(jur_p.read_text(encoding="utf-8")) if jur_p.exists() else {"validacoes_tcu": []}

    mem, pncp, portal, statuses = _load_from_raw(settings.audit_exercicios)
    audit = Reconciliador(mem, pncp, portal, statuses, settings.audit_exercicios).run()
    crit_res = AnalisadorCritico(mem, pncp, audit.dataframes.get("Cruzamento_Licitacoes"), settings.audit_exercicios).run()
    audit.dataframes.update(crit_res.dataframes)

    tables: dict[str, list[dict[str, Any]]] = {}
    for key in (
        "Cruzamento_Licitacoes",
        "Cruzamento_Contratos",
        "Auditoria_Art75_Dispensas",
        "Fornecedores_CurvaABC",
        "Critica_Var_Valores",
        "Critica_Contratos_NAF",
        "Critica_Orcamentaria",
    ):
        df = audit.dataframes.get(key)
        if df is not None and not df.empty:
            tables[key] = json.loads(df.head(500).to_json(orient="records", force_ascii=False))
        else:
            tables[key] = []

    _CACHE.clear()
    _CACHE.update({
        "entidade": settings.audit_entidade_nome,
        "cnpj": settings.audit_cnpj,
        "resumo": resumo,
        "critica": critica,
        "fiscal": fiscal,
        "corretor": corretor,
        "juridico": juridico,
        "statuses": statuses,
        "tables": tables,
    })
    return _CACHE


_INDEX_HTML = r"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Central de Auditoria — Palmópolis/MG</title>
  <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.4/dist/chart.umd.min.js"></script>
  <style>
    :root {
      --bg: #f1f5f9; --card: #ffffff; --navy: #0f294a; --accent: #1d4ed8;
      --crit: #b91c1c; --alto: #c2410c; --med: #a16207; --ok: #15803d;
      --border: #e2e8f0; --text: #0f172a; --muted: #64748b;
    }
    * { box-sizing: border-box; }
    body { margin: 0; font-family: 'Segoe UI', Roboto, Arial, sans-serif; background: var(--bg); color: var(--text); }
    header { background: linear-gradient(135deg, #0f294a, #1e3a8a); color: #fff; padding: 18px 28px; display: flex; flex-wrap: wrap; justify-content: space-between; align-items: center; gap: 12px; }
    header h1 { margin: 0; font-size: 20px; }
    header p { margin: 4px 0 0; font-size: 12px; opacity: 0.88; }
    .links-top a { color: #e2e8f0; text-decoration: none; font-size: 12px; border: 1px solid rgba(255,255,255,.3); padding: 6px 10px; border-radius: 6px; margin-left: 6px; }
    .links-top a:hover { background: rgba(255,255,255,.15); color: #fff; }
    nav { background: #fff; border-bottom: 1px solid var(--border); padding: 0 28px; display: flex; gap: 6px; overflow-x: auto; }
    nav button { background: none; border: none; padding: 13px 16px; font-size: 13px; font-weight: 600; color: var(--muted); cursor: pointer; border-bottom: 3px solid transparent; white-space: nowrap; }
    nav button.active { color: var(--navy); border-bottom-color: var(--accent); }
    main { max-width: 1420px; margin: 20px auto; padding: 0 20px 40px; }
    .tab { display: none; }
    .tab.active { display: block; }
    .kpi-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(210px, 1fr)); gap: 14px; margin-bottom: 20px; }
    .kpi { background: var(--card); border: 1px solid var(--border); border-radius: 10px; padding: 15px; }
    .kpi .lbl { font-size: 11px; text-transform: uppercase; color: var(--muted); letter-spacing: .4px; }
    .kpi .val { font-size: 23px; font-weight: 700; color: var(--navy); margin: 6px 0 2px; }
    .kpi .sub { font-size: 12px; color: var(--muted); }
    .charts { display: grid; grid-template-columns: repeat(auto-fit, minmax(420px, 1fr)); gap: 16px; margin-bottom: 20px; }
    .card { background: var(--card); border: 1px solid var(--border); border-radius: 10px; padding: 18px; margin-bottom: 18px; }
    .card h2 { margin: 0 0 12px; font-size: 16px; color: var(--navy); border-bottom: 1px solid var(--border); padding-bottom: 8px; }
    .toolbar { display: flex; flex-wrap: wrap; gap: 10px; margin-bottom: 14px; align-items: center; }
    input, select { padding: 8px 10px; border: 1px solid #cbd5e1; border-radius: 6px; font-size: 13px; background: #fff; }
    input[type="search"] { min-width: 260px; flex: 1; }
    table { width: 100%; border-collapse: collapse; font-size: 12.5px; }
    th, td { padding: 8px 10px; border-bottom: 1px solid var(--border); text-align: left; vertical-align: top; }
    th { background: #f8fafc; color: var(--navy); position: sticky; top: 0; }
    .tbl-wrap { max-height: 580px; overflow: auto; border: 1px solid var(--border); border-radius: 8px; }
    .num { text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap; }
    .badge { display: inline-block; padding: 2px 8px; border-radius: 999px; font-size: 11px; font-weight: 700; }
    .IRREGULARIDADE_GRAVE, .CRITICA, .CRITICO { background: #fee2e2; color: var(--crit); }
    .RESSALVA_RELEVANTE, .ALTA, .ALTO { background: #ffedd5; color: var(--alto); }
    .RECOMENDACAO_CONTROLE, .MEDIA, .MEDIO { background: #fef9c3; color: var(--med); }
    .OK, .CONCILIADO { background: #dcfce7; color: var(--ok); }
    .SOMENTE_LOCAL_SEM_PNCP { background: #fee2e2; color: var(--crit); }
    .SOMENTE_PNCP_SEM_LOCAL { background: #ffedd5; color: var(--alto); }
    .ap-card { background: #fff; border: 1px solid var(--border); border-left: 5px solid var(--navy); border-radius: 8px; padding: 16px; margin-bottom: 14px; }
    .ap-card.IRREGULARIDADE_GRAVE { border-left-color: var(--crit); }
    .ap-card.RESSALVA_RELEVANTE { border-left-color: var(--alto); }
    .parecer { background: #fef2f2; border: 1px solid #fecaca; border-left: 5px solid var(--crit); padding: 14px; border-radius: 8px; margin-bottom: 16px; font-size: 13.5px; }
  </style>
</head>
<body>
<header>
  <div>
    <h1 id="hdr-title">Central Interativa de Auditoria — Palmópolis/MG</h1>
    <p id="hdr-sub">Carregando base de auditoria...</p>
  </div>
  <div class="links-top">
    <a href="/files/dashboard_executivo_palmopolis.html" target="_blank">Dashboard Executivo</a>
    <a href="/files/painel_analise_critica.html" target="_blank">Painel Análise Crítica</a>
    <a href="/files/relatorio_fiscal_contas_palmopolis.html" target="_blank">Relatório Fiscal (Impressão)</a>
    <a href="/files/plano_correcao_fiscal_corretor.html" target="_blank">Plano Corretor (Impressão)</a>
    <a href="/files/dossie_juridico_completo.html" target="_blank">Dossiê Jurídico (TCU/TCE/MP)</a>
    <a href="/files/auditoria_palmopolis_master.xlsx" target="_blank">Baixar Excel (.xlsx)</a>
  </div>
</header>

<nav>
  <button class="active" data-tab="visao">Visão Executiva</button>
  <button data-tab="fiscal">Fiscal de Contas Públicas</button>
  <button data-tab="corretor">Fiscal Corretor (Passo a Passo)</button>
  <button data-tab="juridico">Agente Jurídico (TCE-MG / MPMG / TCU)</button>
  <button data-tab="pesquisador">Contratos &amp; Recebimentos</button>
  <button data-tab="analise_contrato">Análise de Contratos</button>
  <button data-tab="diarias">Pagamento de Diárias</button>
  <button data-tab="critica">Análise Crítica (Variações)</button>
  <button data-tab="tabelas">Explorador de Bases</button>
  <button data-tab="cobertura">Cobertura &amp; Endpoints</button>
</nav>

<main>
  <!-- ABA 1: VISÃO EXECUTIVA -->
  <section id="tab-visao" class="tab active">
    <div id="kpi-grid" class="kpi-grid"></div>
    <div class="charts">
      <div class="card"><h2>Conciliação Memory × PNCP</h2><canvas id="ch-conc" height="175"></canvas></div>
      <div class="card"><h2>Top 10 Fornecedores (R$)</h2><canvas id="ch-forn" height="175"></canvas></div>
    </div>
    <div class="card">
      <h2>Achados Legais (Lei 14.133/2021 e LAI)</h2>
      <div class="tbl-wrap"><table><thead><tr><th>Código</th><th>Severidade</th><th>Base Legal</th><th>Título</th><th class="num">Qtd</th><th class="num">Valor Envolvido</th></tr></thead><tbody id="tb-achados"></tbody></table></div>
    </div>
  </section>

  <!-- ABA 2: FISCAL DE CONTAS -->
  <section id="tab-fiscal" class="tab">
    <div id="parecer-box" class="parecer"></div>
    <div class="toolbar">
      <select id="flt-grav">
        <option value="">Todas as gravidades</option>
        <option value="IRREGULARIDADE_GRAVE">Irregularidade Grave</option>
        <option value="RESSALVA_RELEVANTE">Ressalva Relevante</option>
        <option value="RECOMENDACAO_CONTROLE">Recomendação de Controle</option>
      </select>
      <input type="search" id="flt-fiscal-txt" placeholder="Filtrar apontamentos por título, lei ou evidência..." />
    </div>
    <div id="fiscal-list"></div>
  </section>

  <!-- ABA 2B: FISCAL CORRETOR -->
  <section id="tab-corretor" class="tab">
    <div id="corretor-resumo" class="parecer" style="background:#ecfdf5;border-color:#a7f3d0;border-left-color:#059669;"></div>
    <div class="toolbar">
      <select id="flt-prio">
        <option value="">Todas as prioridades</option>
        <option value="IMEDIATA_0_5D">Imediata (0 a 5 dias)</option>
        <option value="CURTO_PRAZO_5_15D">Curto Prazo (5 a 15 dias)</option>
        <option value="ESTRUTURANTE_15_30D">Estruturante (15 a 30 dias)</option>
      </select>
      <input type="search" id="flt-corretor-txt" placeholder="Filtrar roteiro por setor, sistema, ação ou apontamento..." />
    </div>
    <div id="corretor-list"></div>
  </section>

  <!-- ABA 2C: AGENTE JURÍDICO -->
  <section id="tab-juridico" class="tab">
    <div id="jur-comp" class="parecer" style="background:#eff6ff;border-color:#bfdbfe;border-left-color:#2563eb;"></div>
    <div id="jur-conc" class="parecer"></div>
    <div class="card">
      <h2>Matriz de Validação Jurídica (Referencial TCU × Apontamentos)</h2>
      <div class="tbl-wrap">
        <table>
          <thead><tr><th>Apont.</th><th>Status TCU</th><th>Entendimento TCU</th><th>Tipificação</th><th>Repercussão</th></tr></thead>
          <tbody id="tb-tcu"></tbody>
        </table>
      </div>
    </div>
    <div class="card">
      <h2>Minuta 1 — Representação ao TCE-MG</h2>
      <pre id="min-tce" style="white-space:pre-wrap;font-size:12.5px;background:#f8fafc;padding:12px;border-radius:8px;border:1px solid #e2e8f0;max-height:420px;overflow:auto;"></pre>
    </div>
    <div class="card">
      <h2>Minuta 2 — Notícia de Fato ao MPMG</h2>
      <pre id="min-mp" style="white-space:pre-wrap;font-size:12.5px;background:#f8fafc;padding:12px;border-radius:8px;border:1px solid #e2e8f0;max-height:420px;overflow:auto;"></pre>
    </div>
  </section>

  <!-- ABA 2D: PESQUISADOR DE CONTRATOS POR FORNECEDOR E RECEBIMENTOS CRONOLÓGICOS -->
  <section id="tab-pesquisador" class="tab">
    <div class="toolbar">
      <input type="search" id="flt-forn-list" placeholder="Pesquisar fornecedor por nome ou CPF/CNPJ..." />
      <button id="btn-limpar-forn" style="padding:8px 12px;border:1px solid #cbd5e1;border-radius:6px;background:#fff;cursor:pointer;">Mostrar Todos</button>
      <a href="/files/contratos_fornecedor_e_recebimentos.xlsx" target="_blank" style="padding:8px 12px;background:#0f294a;color:#fff;text-decoration:none;border-radius:6px;font-size:12.5px;">Baixar Excel (.xlsx)</a>
      <span id="forn-sel-badge" style="font-size:12.5px;font-weight:600;color:#1d4ed8;"></span>
    </div>
    <div style="display:grid;grid-template-columns:340px 1fr;gap:16px;align-items:start;">
      <div class="card" style="padding:12px;">
        <h2 style="font-size:14px;">Fornecedores (<span id="cnt-forn-list">0</span>)</h2>
        <div id="forn-lista-lateral" style="max-height:660px;overflow:auto;font-size:12.5px;"></div>
      </div>
      <div>
        <div class="card">
          <h2>Contratos do Fornecedor (<span id="cnt-ctr-forn">0</span>)</h2>
          <div class="tbl-wrap" style="max-height:280px;">
            <table>
              <thead><tr><th>Contrato</th><th>Exerc.</th><th>Fornecedor</th><th>Modalidade</th><th class="num">Valor Contrato</th><th class="num">Pago Vinc.</th><th>Objeto</th></tr></thead>
              <tbody id="tb-ctr-forn"></tbody>
            </table>
          </div>
        </div>
        <div class="card">
          <div style="display:flex;justify-content:space-between;align-items:center;gap:10px;margin-bottom:10px;">
            <h2 style="margin:0;border:none;padding:0;">Recebimentos por Ordem Cronológica (<span id="cnt-rec-cron">0</span>)</h2>
            <div style="display:flex;gap:8px;">
              <input type="search" id="flt-rec-txt" placeholder="Filtrar data, empenho, contrato ou objeto..." style="min-width:220px;" />
              <button id="btn-ordem-cron" style="padding:6px 10px;border:1px solid #cbd5e1;border-radius:6px;background:#f8fafc;cursor:pointer;font-size:12px;">Ordem: Mais Antiga → Recente</button>
            </div>
          </div>
          <div class="tbl-wrap" style="max-height:380px;">
            <table>
              <thead><tr><th>Data</th><th>Fornecedor</th><th>Empenho</th><th>Contrato</th><th>Objeto</th><th class="num">Valor Recebido</th><th>NF</th></tr></thead>
              <tbody id="tb-rec-cron"></tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  </section>

  <!-- ABA 2F: ANÁLISE DE CONTRATOS (FILTROS EM LISTAS + DESCRITIVO + EXTRATO) -->
  <section id="tab-analise_contrato" class="tab">
    <div class="toolbar">
      <select id="flt-ac-num" style="min-width:210px;"><option value="">Filtrar por Nº do Contrato (Todos)</option></select>
      <select id="flt-ac-obj" style="max-width:360px;"><option value="">Filtrar por Objeto (Todos)</option></select>
      <input type="search" id="flt-ac-txt" placeholder="Buscar contrato, objeto, processo ou empresa..." />
      <button id="btn-ac-limpar" style="padding:8px 12px;border:1px solid #cbd5e1;border-radius:6px;background:#fff;cursor:pointer;">Limpar Filtros</button>
    </div>
    <div style="display:grid;grid-template-columns:360px 1fr;gap:16px;align-items:start;">
      <div class="card" style="padding:12px;">
        <h2 style="font-size:14px;">Contratos (<span id="cnt-ac-lista">0</span>)</h2>
        <div id="ac-lista-lateral" style="max-height:680px;overflow:auto;font-size:12.5px;"></div>
      </div>
      <div>
        <div id="ac-descritivo" class="card">
          <h2>Descritivo do Contrato Selecionado</h2>
          <p style="color:#64748b;font-size:13px;">Selecione um contrato na lista ao lado ou nos filtros acima.</p>
        </div>
        <div class="card">
          <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px;margin-bottom:10px;">
            <h2 style="margin:0;border:none;padding:0;">Extrato de Pagamentos (<span id="cnt-ac-ext">0</span>)</h2>
            <label style="font-size:12.5px;color:#334155;cursor:pointer;">
              <input type="checkbox" id="chk-ac-por-objeto" /> Incluir pagamentos com objeto semelhante
            </label>
          </div>
          <div id="ac-ext-resumo" style="margin-bottom:10px;font-size:13px;font-weight:600;color:#0f294a;"></div>
          <div class="tbl-wrap" style="max-height:360px;">
            <table>
              <thead><tr><th>Data</th><th>Empenho</th><th>Pgto</th><th>NF</th><th>Fornecedor</th><th>Contrato</th><th>Descrição / Objeto</th><th class="num">Valor Pago</th></tr></thead>
              <tbody id="tb-ac-ext"></tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  </section>

  <!-- ABA 2E: PAGAMENTO DE DIÁRIAS -->
  <section id="tab-diarias" class="tab">
    <div class="toolbar">
      <input type="search" id="flt-dia-nome-cpf" placeholder="Pesquisar servidor por Nome ou CPF (ex: 639 ou LAERCIO)..." />
      <select id="flt-dia-unid"><option value="">Todas as unidades</option></select>
      <button id="btn-limpar-dia" style="padding:8px 12px;border:1px solid #cbd5e1;border-radius:6px;background:#fff;cursor:pointer;">Mostrar Todos</button>
      <button id="btn-dia-ordem" style="padding:8px 12px;border:1px solid #cbd5e1;border-radius:6px;background:#f8fafc;cursor:pointer;font-size:12.5px;">Ordem: Mais Antiga → Recente</button>
      <a href="/files/pagamento_diarias_completo.xlsx" target="_blank" style="padding:8px 12px;background:#0f294a;color:#fff;text-decoration:none;border-radius:6px;font-size:12.5px;">Baixar Excel (.xlsx)</a>
    </div>
    <div id="dia-kpis" class="kpi-grid"></div>
    <div style="display:grid;grid-template-columns:340px 1fr;gap:16px;align-items:start;">
      <div class="card" style="padding:12px;">
        <h2 style="font-size:14px;">Servidores Beneficiários (<span id="cnt-dia-srv">0</span>)</h2>
        <div id="dia-srv-lista" style="max-height:620px;overflow:auto;font-size:12.5px;"></div>
      </div>
      <div class="card">
        <h2>Pagamentos de Diárias (<span id="cnt-dia-pags">0</span>) <span id="dia-sel-badge" style="font-size:12px;color:#1d4ed8;font-weight:500;"></span></h2>
        <div class="tbl-wrap" style="max-height:620px;">
          <table>
            <thead><tr><th>Data Pgto</th><th>Servidor</th><th>CPF</th><th>Função</th><th>Unidade</th><th>Emp.</th><th>Pgto</th><th class="num">Valor Pago</th><th>Descrição</th></tr></thead>
            <tbody id="tb-dia-pags"></tbody>
          </table>
        </div>
      </div>
    </div>
  </section>

  <!-- ABA 3: ANÁLISE CRÍTICA -->
  <section id="tab-critica" class="tab">
    <div class="toolbar">
      <select id="flt-eixo"><option value="">Todos os eixos</option></select>
      <select id="flt-crit">
        <option value="">Todas as criticidades</option>
        <option value="CRITICA">Crítica</option>
        <option value="ALTA">Alta</option>
        <option value="MEDIA">Média</option>
      </select>
      <input type="search" id="flt-crit-txt" placeholder="Buscar processo, contrato, unidade ou ação..." />
    </div>
    <div class="card">
      <h2>Ranking de Variações Inconsistentes (<span id="crit-count">0</span>)</h2>
      <div class="tbl-wrap">
        <table>
          <thead><tr><th>Score</th><th>Crit.</th><th>Eixo</th><th>Item Analisado</th><th>Esperado</th><th>Observado</th><th class="num">Var %</th><th class="num">Valor Exposto</th></tr></thead>
          <tbody id="tb-critica"></tbody>
        </table>
      </div>
    </div>
  </section>

  <!-- ABA 4: EXPLORADOR DE BASES -->
  <section id="tab-tabelas" class="tab">
    <div class="toolbar">
      <select id="sel-tabela">
        <option value="Cruzamento_Licitacoes">Cruzamento Licitações (Memory × PNCP)</option>
        <option value="Cruzamento_Contratos">Cruzamento Contratos (Memory × PNCP)</option>
        <option value="Auditoria_Art75_Dispensas">Auditoria Art. 75 (Dispensas)</option>
        <option value="Fornecedores_CurvaABC">Fornecedores Curva ABC</option>
        <option value="Critica_Var_Valores">Variações de Valores (Licitações)</option>
        <option value="Critica_Contratos_NAF">Contratos extrapolados por NAF (&gt;25%)</option>
        <option value="Critica_Orcamentaria">Inconsistências Orçamentárias (Lei 4.320)</option>
      </select>
      <input type="search" id="flt-tbl-txt" placeholder="Pesquisar em qualquer coluna..." />
      <span id="tbl-info" style="font-size:12px;color:#64748b"></span>
    </div>
    <div class="card">
      <div class="tbl-wrap" id="tbl-dyn-wrap"></div>
    </div>
  </section>

  <!-- ABA 5: COBERTURA -->
  <section id="tab-cobertura" class="tab">
    <div class="card">
      <h2>Cobertura de Extração (Memory iLAI, PNCP e Portal Institucional)</h2>
      <div class="tbl-wrap">
        <table>
          <thead><tr><th>Fonte</th><th>Dataset</th><th>Exercício</th><th class="num">Registros</th><th>Status</th><th>Detalhe</th></tr></thead>
          <tbody id="tb-status"></tbody>
        </table>
      </div>
    </div>
  </section>
</main>

<script>
const brl = v => 'R$ ' + Number(v || 0).toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
let DATA = null;

document.querySelectorAll('nav button').forEach(btn => {
  btn.onclick = () => {
    document.querySelectorAll('nav button, .tab').forEach(el => el.classList.remove('active'));
    btn.classList.add('active');
    document.getElementById('tab-' + btn.dataset.tab).classList.add('active');
  };
});

async function init() {
  let r = await fetch('/api/bundle').catch(() => null);
  if (!r || !r.ok) r = await fetch('./data/bundle.json');
  DATA = await r.json();
  const k = DATA.resumo.kpis || {};
  document.getElementById('hdr-title').textContent = `Central Interativa de Auditoria — ${DATA.entidade}`;
  document.getElementById('hdr-sub').textContent = `CNPJ ${DATA.cnpj} | Exercícios: ${(k.exercicios||[]).join(', ')} | Apontamentos Fiscais: ${(DATA.fiscal.apontamentos||[]).length} | Inconsistências Críticas: ${(DATA.critica.anomalias||[]).length}`;

  const kpis = [
    ['Licitações (Memory)', k.memory_licitacoes_qtd, brl(k.memory_licitacoes_valor)],
    ['Contratos (Memory)', k.memory_contratos_qtd, brl(k.memory_contratos_valor)],
    ['Contratações PNCP', k.pncp_contratacoes_qtd, `${k.pncp_arquivos_qtd || 0} arquivos | ${k.pncp_contratos_qtd || 0} contratos`],
    ['Aderência PNCP', (k.taxa_aderencia_pncp_lic_pct || 0) + '%', `${k.conciliadas_lic_qtd || 0} conciliadas / ${k.sem_pncp_lic_qtd || 0} sem PNCP`],
    ['Apontamentos Fiscais', DATA.fiscal.total_apontamentos || 0, `Graves: ${DATA.fiscal.graves || 0} | Ressalvas: ${DATA.fiscal.ressalvas || 0}`],
    ['Variações Críticas', (DATA.critica.anomalias || []).length, 'Avaliação prioritária em bases gov.'],
  ];
  document.getElementById('kpi-grid').innerHTML = kpis.map(([l,v,s]) =>
    `<div class="kpi"><div class="lbl">${l}</div><div class="val">${v ?? 0}</div><div class="sub">${s}</div></div>`
  ).join('');

  document.getElementById('tb-achados').innerHTML = (DATA.resumo.achados || []).map(a =>
    `<tr><td><strong>${a.codigo}</strong></td><td><span class="badge ${a.severidade}">${a.severidade}</span></td><td>${a.base_legal}</td><td><strong>${a.titulo}</strong><br><small style="color:#64748b">${a.descricao}</small></td><td class="num">${a.quantidade}</td><td class="num">${brl(a.valor_envolvido)}</td></tr>`
  ).join('');

  new Chart(document.getElementById('ch-conc'), {
    type: 'bar',
    data: {
      labels: ['Licitações', 'Contratos'],
      datasets: [
        { label: 'Conciliados', data: [k.conciliadas_lic_qtd||0, k.conciliados_ctr_qtd||0], backgroundColor: '#15803d' },
        { label: 'Somente Memory (sem PNCP)', data: [k.sem_pncp_lic_qtd||0, k.sem_pncp_ctr_qtd||0], backgroundColor: '#b91c1c' }
      ]
    },
    options: { responsive: true, plugins: { legend: { position: 'bottom' } } }
  });

  const abc = (DATA.tables.Fornecedores_CurvaABC || []).filter(x => !x.eh_proprio_municipio).slice(0, 10);
  new Chart(document.getElementById('ch-forn'), {
    type: 'bar',
    data: {
      labels: abc.map(x => String(x.fornecedor_nome||'').slice(0, 28)),
      datasets: [{ label: 'Valor (R$)', data: abc.map(x => Number(x.valor_ref||0)), backgroundColor: '#1d4ed8' }]
    },
    options: { indexAxis: 'y', responsive: true, plugins: { legend: { display: false } } }
  });

  // Fiscal
  document.getElementById('parecer-box').textContent = DATA.fiscal.parecer_sintese || '';
  renderFiscal();
  document.getElementById('flt-grav').onchange = renderFiscal;
  document.getElementById('flt-fiscal-txt').oninput = renderFiscal;

  // Corretor
  document.getElementById('corretor-resumo').textContent = (DATA.corretor && DATA.corretor.resumo_executivo) || '';
  renderCorretor();
  document.getElementById('flt-prio').onchange = renderCorretor;
  document.getElementById('flt-corretor-txt').oninput = renderCorretor;

  // Jurídico
  const j = DATA.juridico || {};
  document.getElementById('jur-comp').textContent = j.nota_competencia_tce_tcm_mg || '';
  document.getElementById('jur-conc').textContent = j.parecer_juridico_conclusivo || '';
  document.getElementById('tb-tcu').innerHTML = (j.validacoes_tcu || []).map(v =>
    `<tr><td><strong>${v.codigo_apontamento}</strong></td><td><span class="badge ${v.status_validacao_tcu==='VALIDADO_RISCO_DEBITO_MULTA'?'CRITICO':v.status_validacao_tcu==='VALIDADO_RISCO_GLOSA'?'ALTO':'MEDIO'}">${v.status_validacao_tcu}</span></td><td>${v.entendimento_tcu_aplicavel}</td><td>${v.tipificacao_controle_externo}</td><td>${v.repercussao_juridica}</td></tr>`
  ).join('');
  document.getElementById('min-tce').textContent = j.minuta_tce_mg || '';
  document.getElementById('min-mp').textContent = j.minuta_mpmg || '';

  // Crítica
  const eixos = Object.keys(DATA.critica.resumo_eixos || {});
  document.getElementById('flt-eixo').innerHTML += eixos.map(e => `<option value="${e}">${e}</option>`).join('');
  renderCritica();
  ['flt-eixo', 'flt-crit'].forEach(id => document.getElementById(id).onchange = renderCritica);
  document.getElementById('flt-crit-txt').oninput = renderCritica;

  // Tabelas
  renderTable();
  document.getElementById('sel-tabela').onchange = renderTable;
  document.getElementById('flt-tbl-txt').oninput = renderTable;

  // Cobertura
  document.getElementById('tb-status').innerHTML = (DATA.statuses || []).map(s =>
    `<tr><td>${s.fonte}</td><td>${s.dataset}</td><td>${s.exercicio || '-'}</td><td class="num">${s.registros}</td><td><span class="badge ${s.status}">${s.status}</span></td><td><small>${s.detalhe||''}</small></td></tr>`
  ).join('');

  // Pesquisador de Contratos por Fornecedor e Recebimentos Cronológicos
  initPesquisador();
  initDiarias();
}

let PESQ = null;
let FORN_SEL = '';
let ORDEM_ASC = true;

async function initPesquisador() {
  let r = await fetch('/files/fornecedor_contratos_recebimentos.json').catch(() => null);
  if (!r || !r.ok) r = await fetch('./files/fornecedor_contratos_recebimentos.json').catch(() => null);
  if (!r || !r.ok) return;
  PESQ = await r.json();
  document.getElementById('flt-forn-list').oninput = renderFornecedoresLista;
  document.getElementById('flt-rec-txt').oninput = renderRecebimentosCron;
  document.getElementById('btn-limpar-forn').onclick = () => { FORN_SEL = ''; renderFornecedoresLista(); renderContratosFornecedor(); renderRecebimentosCron(); };
  document.getElementById('btn-ordem-cron').onclick = () => {
    ORDEM_ASC = !ORDEM_ASC;
    document.getElementById('btn-ordem-cron').textContent = ORDEM_ASC ? 'Ordem: Mais Antiga → Recente' : 'Ordem: Mais Recente → Antiga';
    renderRecebimentosCron();
  };
  renderFornecedoresLista();
  renderContratosFornecedor();
  renderRecebimentosCron();
  initAnaliseContratos();
}

function renderFornecedoresLista() {
  if (!PESQ) return;
  const q = document.getElementById('flt-forn-list').value.toLowerCase();
  const list = (PESQ.fornecedores_lista || []).filter(f =>
    !q || (f.fornecedor_nome + ' ' + (f.cpf_cnpj||'')).toLowerCase().includes(q)
  );
  document.getElementById('cnt-forn-list').textContent = list.length;
  document.getElementById('forn-sel-badge').textContent = FORN_SEL ? `Selecionado: ${FORN_SEL}` : 'Exibindo todos os fornecedores';
  document.getElementById('forn-lista-lateral').innerHTML = list.slice(0, 300).map(f => {
    const active = FORN_SEL && FORN_SEL === f.fornecedor_nome;
    return `<div onclick="selecionarFornecedor('${String(f.fornecedor_nome).replace(/'/g, "\\'")}')" style="padding:8px;border-bottom:1px solid #e2e8f0;cursor:pointer;border-radius:6px;background:${active?'#eff6ff':'transparent'}">
      <strong style="color:#0f294a">${f.fornecedor_nome}</strong><br>
      <span style="color:#64748b">${f.cpf_cnpj || '-'} • ${f.qtd_contratos} contrato(s) • ${brl(f.valor_contratado)}</span>
    </div>`;
  }).join('');
}

window.selecionarFornecedor = function(nome) {
  FORN_SEL = (FORN_SEL === nome) ? '' : nome;
  renderFornecedoresLista();
  renderContratosFornecedor();
  renderRecebimentosCron();
};

function renderContratosFornecedor() {
  if (!PESQ) return;
  const q = document.getElementById('flt-forn-list').value.toLowerCase();
  const rows = (PESQ.contratos || []).filter(c => {
    if (FORN_SEL) return c.fornecedor_nome.toLowerCase().includes(FORN_SEL.toLowerCase());
    return !q || (c.fornecedor_nome + ' ' + c.cpf_cnpj + ' ' + c.numero_contrato + ' ' + c.objeto).toLowerCase().includes(q);
  });
  document.getElementById('cnt-ctr-forn').textContent = rows.length;
  document.getElementById('tb-ctr-forn').innerHTML = rows.slice(0, 300).map(c =>
    `<tr><td><strong>${c.numero_contrato}</strong></td><td>${c.exercicio||''}</td><td>${c.fornecedor_nome}<br><small style="color:#64748b">${c.cpf_cnpj||''}</small></td><td>${c.modalidade}</td><td class="num">${brl(c.valor_contrato)}</td><td class="num">${brl(c.valor_pago_vinculado)}</td><td><small>${String(c.objeto||'').slice(0,180)}</small></td></tr>`
  ).join('');
}

function renderRecebimentosCron() {
  if (!PESQ) return;
  const qForn = document.getElementById('flt-forn-list').value.toLowerCase();
  const qRec = document.getElementById('flt-rec-txt').value.toLowerCase();
  let rows = (PESQ.recebimentos_cronologicos || []).filter(r => {
    if (FORN_SEL && !r.fornecedor_nome.toLowerCase().includes(FORN_SEL.toLowerCase())) return false;
    if (!FORN_SEL && qForn && !(r.fornecedor_nome + ' ' + r.cpf_cnpj).toLowerCase().includes(qForn)) return false;
    if (qRec && !(r.data + ' ' + r.empenho + ' ' + r.contrato + ' ' + r.objeto + ' ' + r.fornecedor_nome).toLowerCase().includes(qRec)) return false;
    return true;
  });
  if (!ORDEM_ASC) rows = rows.slice().reverse();
  document.getElementById('cnt-rec-cron').textContent = rows.length;
  document.getElementById('tb-rec-cron').innerHTML = rows.slice(0, 500).map(r =>
    `<tr><td style="white-space:nowrap">${r.data}</td><td>${r.fornecedor_nome}<br><small style="color:#64748b">${r.cpf_cnpj||''}</small></td><td style="white-space:nowrap">${r.empenho}</td><td style="white-space:nowrap">${r.contrato}</td><td><small>${String(r.objeto||'').slice(0,180)}</small></td><td class="num"><strong>${brl(r.valor_recebido)}</strong></td><td>${r.nota_fiscal||''}</td></tr>`
  ).join('');
}

let AC_SEL_ID = '';

function initAnaliseContratos() {
  if (!PESQ) return;
  const ctrs = PESQ.contratos || [];
  const nums = [...new Set(ctrs.map(c => c.numero_contrato).filter(Boolean))];
  const objs = [...new Set(ctrs.map(c => String(c.objeto || '').slice(0, 95)).filter(Boolean))].sort();

  document.getElementById('flt-ac-num').innerHTML = '<option value="">Filtrar por Nº do Contrato (Todos)</option>' +
    nums.map(n => `<option value="${n}">${n}</option>`).join('');
  document.getElementById('flt-ac-obj').innerHTML = '<option value="">Filtrar por Objeto (Todos)</option>' +
    objs.map(o => `<option value="${o.replace(/"/g, '&quot;')}">${o}</option>`).join('');

  document.getElementById('flt-ac-num').onchange = () => {
    const num = document.getElementById('flt-ac-num').value;
    if (num) {
      const found = ctrs.find(c => c.numero_contrato === num);
      if (found) AC_SEL_ID = found.id_contrato;
    }
    renderAnaliseContratosLista();
    renderDescritivoEExtrato();
  };
  document.getElementById('flt-ac-obj').onchange = () => {
    const obj = document.getElementById('flt-ac-obj').value;
    if (obj) {
      const found = ctrs.find(c => String(c.objeto || '').startsWith(obj));
      if (found) AC_SEL_ID = found.id_contrato;
    }
    renderAnaliseContratosLista();
    renderDescritivoEExtrato();
  };
  document.getElementById('flt-ac-txt').oninput = renderAnaliseContratosLista;
  document.getElementById('chk-ac-por-objeto').onchange = renderDescritivoEExtrato;
  document.getElementById('btn-ac-limpar').onclick = () => {
    document.getElementById('flt-ac-num').value = '';
    document.getElementById('flt-ac-obj').value = '';
    document.getElementById('flt-ac-txt').value = '';
    AC_SEL_ID = ctrs.length ? ctrs[0].id_contrato : '';
    renderAnaliseContratosLista();
    renderDescritivoEExtrato();
  };

  if (ctrs.length) AC_SEL_ID = ctrs[0].id_contrato;
  renderAnaliseContratosLista();
  renderDescritivoEExtrato();
}

function getContratosFiltradosAC() {
  const num = document.getElementById('flt-ac-num').value;
  const obj = document.getElementById('flt-ac-obj').value;
  const q = document.getElementById('flt-ac-txt').value.toLowerCase().trim();
  return (PESQ.contratos || []).filter(c => {
    if (num && c.numero_contrato !== num) return false;
    if (obj && !String(c.objeto || '').startsWith(obj)) return false;
    if (q && !(c.numero_contrato + ' ' + c.objeto + ' ' + c.fornecedor_nome + ' ' + c.cpf_cnpj + ' ' + c.processo_numero).toLowerCase().includes(q)) return false;
    return true;
  });
}

window.selecionarContratoAC = function(idCtr) {
  AC_SEL_ID = idCtr;
  renderAnaliseContratosLista();
  renderDescritivoEExtrato();
};

function renderAnaliseContratosLista() {
  if (!PESQ) return;
  const list = getContratosFiltradosAC();
  document.getElementById('cnt-ac-lista').textContent = list.length;
  document.getElementById('ac-lista-lateral').innerHTML = list.slice(0, 350).map(c => {
    const active = AC_SEL_ID === c.id_contrato;
    return `<div onclick="selecionarContratoAC('${String(c.id_contrato).replace(/'/g, "\\'")}')" style="padding:9px;border-bottom:1px solid #e2e8f0;cursor:pointer;border-radius:6px;background:${active?'#eff6ff':'transparent'}">
      <strong style="color:#0f294a">Contrato ${c.numero_contrato}</strong> <span style="color:#64748b">(${c.exercicio || ''})</span><br>
      <span style="color:#1e40af;font-weight:600">${c.fornecedor_nome}</span><br>
      <small style="color:#475569">${String(c.objeto || '').slice(0, 95)}...</small><br>
      <small style="color:#0f294a"><strong>${brl(c.valor_contrato)}</strong> • Pago: ${brl(c.valor_pago_vinculado)}</small>
    </div>`;
  }).join('');
}

function renderDescritivoEExtrato() {
  if (!PESQ) return;
  const c = (PESQ.contratos || []).find(x => x.id_contrato === AC_SEL_ID);
  if (!c) {
    document.getElementById('ac-descritivo').innerHTML = '<h2>Descritivo do Contrato</h2><p style="color:#64748b">Nenhum contrato selecionado.</p>';
    document.getElementById('tb-ac-ext').innerHTML = '';
    return;
  }

  const pct = c.valor_contrato > 0 ? ((c.valor_pago_vinculado / c.valor_contrato) * 100).toFixed(1) : '0.0';
  const saldo = c.valor_contrato - c.valor_pago_vinculado;

  document.getElementById('ac-descritivo').innerHTML = `
    <h2>Descritivo Completo — Contrato ${c.numero_contrato} (${c.exercicio || ''})</h2>
    <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:12px;margin-bottom:12px;">
      <div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:12px;">
        <div style="font-size:11px;text-transform:uppercase;color:#64748b;font-weight:700;">1. Processo Originário</div>
        <p style="margin:6px 0 2px;font-size:13px;"><strong>Processo/Licitação:</strong> ${c.processo_numero || '-'}</p>
        <p style="margin:2px 0;font-size:13px;"><strong>ID Processo:</strong> ${c.id_processo || '-'} | <strong>Data:</strong> ${c.data_processo || '-'}</p>
        <p style="margin:2px 0;font-size:13px;"><strong>Modalidade:</strong> ${c.modalidade || '-'}</p>
        <p style="margin:2px 0;font-size:13px;"><strong>Situação Processo:</strong> ${c.processo_situacao || c.situacao || '-'}</p>
        ${c.processo_valor_homologado ? `<p style="margin:2px 0;font-size:13px;"><strong>Homologado Processo:</strong> ${brl(c.processo_valor_homologado)}</p>` : ''}
      </div>
      <div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:12px;">
        <div style="font-size:11px;text-transform:uppercase;color:#64748b;font-weight:700;">2. Dados do Contrato</div>
        <p style="margin:6px 0 2px;font-size:13px;"><strong>Contrato Nº:</strong> ${c.numero_contrato} (${c.tipo_ato || 'Contrato'})</p>
        <p style="margin:2px 0;font-size:13px;"><strong>Vigência:</strong> ${c.inicio_vigencia || '-'} a ${c.termino_vigencia || '-'}</p>
        <p style="margin:2px 0;font-size:13px;"><strong>Assinatura / Pub.:</strong> ${c.data_assinatura || '-'} / ${c.data_publicacao || '-'}</p>
        <p style="margin:2px 0;font-size:13px;"><strong>Valor Contrato:</strong> <strong>${brl(c.valor_contrato)}</strong></p>
        <p style="margin:2px 0;font-size:13px;"><strong>NAFs Emitidas:</strong> ${c.qtd_nafs} (${brl(c.valor_nafs)})</p>
      </div>
      <div style="background:#eff6ff;border:1px solid #bfdbfe;border-radius:8px;padding:12px;">
        <div style="font-size:11px;text-transform:uppercase;color:#1e40af;font-weight:700;">3. Empresa Homologada &amp; Execução</div>
        <p style="margin:6px 0 2px;font-size:13.5px;color:#0f294a;"><strong>${c.fornecedor_nome}</strong></p>
        <p style="margin:2px 0;font-size:13px;"><strong>CPF/CNPJ:</strong> ${c.cpf_cnpj || '-'}</p>
        <p style="margin:2px 0;font-size:13px;"><strong>Total Pago no Contrato:</strong> <strong style="color:#15803d">${brl(c.valor_pago_vinculado)}</strong> (${pct}%)</p>
        <p style="margin:2px 0;font-size:13px;"><strong>Saldo Contratual:</strong> ${brl(saldo)}</p>
      </div>
    </div>
    <div style="background:#fff;border:1px solid #e2e8f0;border-radius:8px;padding:10px 12px;font-size:13px;">
      <strong>Objeto:</strong> ${c.objeto || '-'}
    </div>
  `;

  const incluirObj = document.getElementById('chk-ac-por-objeto').checked;
  const objSnippet = String(c.objeto || '').trim().slice(0, 45).toLowerCase();
  const ext = (PESQ.recebimentos_cronologicos || []).filter(r => {
    if (r.id_contrato && r.id_contrato === c.id_contrato) return true;
    if (r.contrato && r.contrato === c.numero_contrato) return true;
    if (incluirObj && objSnippet.length >= 12 && String(r.objeto || '').toLowerCase().includes(objSnippet)) return true;
    return false;
  });
  const totalExt = ext.reduce((s, x) => s + Number(x.valor_recebido || 0), 0);
  document.getElementById('cnt-ac-ext').textContent = ext.length;
  document.getElementById('ac-ext-resumo').textContent = `Total no Extrato: ${brl(totalExt)} em ${ext.length} pagamento(s)`;
  document.getElementById('tb-ac-ext').innerHTML = ext.length
    ? ext.map(r => `<tr><td style="white-space:nowrap">${r.data}</td><td style="white-space:nowrap">${r.empenho}</td><td>${r.numero_pagamento||''}</td><td>${r.nota_fiscal||''}</td><td>${r.fornecedor_nome}</td><td>${r.contrato}</td><td><small>${String(r.objeto||r.des_despesa||'').slice(0,150)}</small></td><td class="num"><strong>${brl(r.valor_recebido)}</strong></td></tr>`).join('')
    : '<tr><td colspan="8" style="color:#64748b;padding:14px;">Nenhum pagamento vinculado diretamente a este contrato no extrato de 2026 (marque a opção acima para buscar por objeto semelhante).</td></tr>';
}

let DIA = null;
let DIA_SRV_SEL = '';
let DIA_ASC = true;

async function initDiarias() {
  let r = await fetch('/files/pagamento_diarias.json').catch(() => null);
  if (!r || !r.ok) r = await fetch('./files/pagamento_diarias.json').catch(() => null);
  if (!r || !r.ok) return;
  DIA = await r.json();
  const unids = [...new Set((DIA.pagamentos_diarias || []).map(x => x.unidade_orcamentaria).filter(Boolean))].sort();
  document.getElementById('flt-dia-unid').innerHTML += unids.map(u => `<option value="${u}">${u}</option>`).join('');
  document.getElementById('flt-dia-nome-cpf').oninput = () => { renderDiaServidores(); renderDiaPagamentos(); };
  document.getElementById('flt-dia-unid').onchange = () => { renderDiaServidores(); renderDiaPagamentos(); };
  document.getElementById('btn-limpar-dia').onclick = () => {
    DIA_SRV_SEL = '';
    document.getElementById('flt-dia-nome-cpf').value = '';
    document.getElementById('flt-dia-unid').value = '';
    renderDiaServidores();
    renderDiaPagamentos();
  };
  document.getElementById('btn-dia-ordem').onclick = () => {
    DIA_ASC = !DIA_ASC;
    document.getElementById('btn-dia-ordem').textContent = DIA_ASC ? 'Ordem: Mais Antiga → Recente' : 'Ordem: Mais Recente → Antiga';
    renderDiaPagamentos();
  };
  renderDiaServidores();
  renderDiaPagamentos();
}

window.selecionarServidorDiaria = function(nome) {
  DIA_SRV_SEL = (DIA_SRV_SEL === nome) ? '' : nome;
  renderDiaServidores();
  renderDiaPagamentos();
};

function renderDiaServidores() {
  if (!DIA) return;
  const q = document.getElementById('flt-dia-nome-cpf').value.toLowerCase().trim();
  const unid = document.getElementById('flt-dia-unid').value;
  const qDigits = q.replace(/\D/g, '');
  const list = (DIA.servidores_resumo || []).filter(s => {
    if (unid && s.unidade_orcamentaria !== unid) return false;
    if (!q) return true;
    const hay = (s.nome_servidor + ' ' + (s.cpf || '') + ' ' + (s.funcao || '')).toLowerCase();
    const cpfDigits = String(s.cpf || '').replace(/\D/g, '');
    return hay.includes(q) || (qDigits && cpfDigits.includes(qDigits));
  });
  document.getElementById('cnt-dia-srv').textContent = list.length;
  document.getElementById('dia-srv-lista').innerHTML = list.map(s => {
    const active = DIA_SRV_SEL && DIA_SRV_SEL === s.nome_servidor;
    return `<div onclick="selecionarServidorDiaria('${String(s.nome_servidor).replace(/'/g, "\\'")}')" style="padding:8px;border-bottom:1px solid #e2e8f0;cursor:pointer;border-radius:6px;background:${active?'#eff6ff':'transparent'}">
      <strong style="color:#0f294a">${s.nome_servidor}</strong><br>
      <span style="color:#64748b">CPF: ${s.cpf || 'N/D'} • ${s.qtd_diarias} diária(s) • <strong>${brl(s.total_pago)}</strong></span>
    </div>`;
  }).join('');
}

function renderDiaPagamentos() {
  if (!DIA) return;
  const q = document.getElementById('flt-dia-nome-cpf').value.toLowerCase().trim();
  const unid = document.getElementById('flt-dia-unid').value;
  const qDigits = q.replace(/\D/g, '');
  let rows = (DIA.pagamentos_diarias || []).filter(r => {
    if (DIA_SRV_SEL && r.nome_servidor !== DIA_SRV_SEL) return false;
    if (unid && r.unidade_orcamentaria !== unid) return false;
    if (!q) return true;
    const hay = (r.nome_servidor + ' ' + (r.cpf || '') + ' ' + (r.funcao || '') + ' ' + (r.descricao || '')).toLowerCase();
    const cpfDigits = String(r.cpf || '').replace(/\D/g, '');
    return hay.includes(q) || (qDigits && cpfDigits.includes(qDigits));
  });
  if (!DIA_ASC) rows = rows.slice().reverse();

  const totalPago = rows.reduce((acc, x) => acc + Number(x.valor_pago || 0), 0);
  const totalEmp = rows.reduce((acc, x) => acc + Number(x.valor_empenho || 0), 0);
  const srvsUnicos = new Set(rows.map(x => x.nome_servidor)).size;

  document.getElementById('dia-kpis').innerHTML = [
    ['Servidores no Filtro', srvsUnicos, 'Com recebimento de diárias'],
    ['Pagamentos de Diárias', rows.length, 'Registros encontrados'],
    ['Total Empenhado', brl(totalEmp), 'No recorte selecionado'],
    ['Total Pago em Diárias', brl(totalPago), 'No recorte selecionado'],
  ].map(([l, v, s]) => `<div class="kpi"><div class="lbl">${l}</div><div class="val">${v}</div><div class="sub">${s}</div></div>`).join('');

  document.getElementById('cnt-dia-pags').textContent = rows.length;
  document.getElementById('dia-sel-badge').textContent = DIA_SRV_SEL ? `• Selecionado: ${DIA_SRV_SEL}` : '';
  document.getElementById('tb-dia-pags').innerHTML = rows.slice(0, 600).map(r =>
    `<tr><td style="white-space:nowrap">${r.data_pagamento}</td><td><strong>${r.nome_servidor}</strong></td><td style="white-space:nowrap">${r.cpf || '-'}</td><td><small>${r.funcao || '-'}</small></td><td><small>${r.unidade_orcamentaria}</small></td><td>${r.numero_empenho || ''}</td><td>${r.numero_pagamento || ''}</td><td class="num"><strong>${brl(r.valor_pago)}</strong></td><td><small>${String(r.descricao || '').slice(0, 140)}</small></td></tr>`
  ).join('');
}

function renderFiscal() {
  const g = document.getElementById('flt-grav').value;
  const q = document.getElementById('flt-fiscal-txt').value.toLowerCase();
  const list = (DATA.fiscal.apontamentos || []).filter(ap =>
    (!g || ap.gravidade === g) &&
    (!q || JSON.stringify(ap).toLowerCase().includes(q))
  );
  document.getElementById('fiscal-list').innerHTML = list.map(ap => `
    <div class="ap-card ${ap.gravidade}">
      <span class="badge ${ap.gravidade}">${ap.gravidade}</span>
      <span style="font-size:12px;color:#64748b;margin-left:8px">${ap.categoria} | Prazo: ${ap.prazo_sugerido_dias}d | Ocorrências: ${ap.quantidade_ocorrencias} | ${brl(ap.valor_envolvido)}</span>
      <h3 style="margin:8px 0 4px;color:#0f294a">${ap.codigo} — ${ap.titulo}</h3>
      <p style="margin:4px 0;font-size:13px"><strong>Base Legal:</strong> ${ap.base_legal}</p>
      <p style="margin:4px 0;font-size:13px"><strong>Situação:</strong> ${ap.situacao_encontrada}</p>
      <p style="margin:4px 0;font-size:13px"><strong>Risco:</strong> ${ap.risco_procedimental}</p>
      <p style="margin:6px 0 2px;font-size:12.5px"><strong>Evidências:</strong> ${(ap.evidencias_principais||[]).join(' • ')}</p>
      <p style="margin:6px 0 0;background:#f8fafc;padding:8px;border-left:3px solid #1d4ed8;font-size:13px"><strong>Determinação:</strong> ${ap.determinacao_ao_gestor}</p>
    </div>
  `).join('');
}

function renderCorretor() {
  const prio = document.getElementById('flt-prio').value;
  const q = document.getElementById('flt-corretor-txt').value.toLowerCase();
  const list = ((DATA.corretor && DATA.corretor.roteiros) || []).filter(r =>
    (!prio || r.prioridade_execucao === prio) && (!q || JSON.stringify(r).toLowerCase().includes(q))
  );
  document.getElementById('corretor-list').innerHTML = list.map(r => `
    <div class="ap-card" style="border-left-color:${r.prioridade_execucao==='IMEDIATA_0_5D'?'#b91c1c':r.prioridade_execucao==='CURTO_PRAZO_5_15D'?'#c2410c':'#1d4ed8'}">
      <span class="badge ${r.gravidade}">${r.prioridade_execucao}</span>
      <span style="font-size:12px;color:#64748b;margin-left:8px">${r.gravidade}</span>
      <h3 style="margin:8px 0 4px;color:#0f294a">${r.codigo_apontamento} — ${r.titulo_apontamento}</h3>
      <p style="margin:4px 0;font-size:13px"><strong>Causa-Raiz:</strong> ${r.diagnostico_causa_raiz}</p>
      <p style="margin:4px 0;font-size:13px"><strong>Melhor Condução:</strong> ${r.melhor_conducao}</p>
      <p style="margin:4px 0 8px;font-size:12px;color:#475569"><strong>Fundamento:</strong> ${r.fundamento_saneamento}</p>
      <table><thead><tr><th>Passo</th><th>Setor Responsável</th><th>Sistema</th><th>Ação Executável</th><th>Documentos</th><th>Validação</th></tr></thead>
      <tbody>${(r.passos||[]).map(p => `<tr><td><strong>${p.ordem}</strong></td><td>${p.setor_responsavel}</td><td>${p.sistema_alvo}</td><td>${p.acao}</td><td>${(p.documentos_comprobatorios||[]).join('; ')}</td><td>${p.criterio_validacao}</td></tr>`).join('')}</tbody></table>
    </div>
  `).join('');
}

function renderCritica() {
  const eixo = document.getElementById('flt-eixo').value;
  const crit = document.getElementById('flt-crit').value;
  const q = document.getElementById('flt-crit-txt').value.toLowerCase();
  const list = (DATA.critica.anomalias || []).filter(a =>
    (!eixo || a.eixo === eixo) && (!crit || a.criticidade === crit) && (!q || JSON.stringify(a).toLowerCase().includes(q))
  );
  document.getElementById('crit-count').textContent = list.length;
  document.getElementById('tb-critica').innerHTML = list.map(a =>
    `<tr><td class="num"><strong>${a.score_risco}</strong></td><td><span class="badge ${a.criticidade}">${a.criticidade}</span></td><td>${a.eixo}<br><small style="color:#64748b">${a.base_governo_ref}</small></td><td>${a.item_analisado}</td><td>${a.esperado}</td><td>${a.observado}</td><td class="num">${a.variacao_pct != null ? a.variacao_pct.toFixed(1)+'%' : '-'}</td><td class="num">${brl(a.valor_exposto)}</td></tr>`
  ).join('');
}

function renderTable() {
  const name = document.getElementById('sel-tabela').value;
  const q = document.getElementById('flt-tbl-txt').value.toLowerCase();
  const rows = (DATA.tables[name] || []).filter(r => !q || JSON.stringify(r).toLowerCase().includes(q));
  document.getElementById('tbl-info').textContent = `${rows.length} registros exibidos`;
  if (!rows.length) {
    document.getElementById('tbl-dyn-wrap').innerHTML = '<p style="padding:16px;color:#64748b">Sem registros para este filtro.</p>';
    return;
  }
  const cols = Object.keys(rows[0]).slice(0, 12);
  const head = `<tr>${cols.map(c => `<th>${c}</th>`).join('')}</tr>`;
  const body = rows.slice(0, 250).map(r => `<tr>${cols.map(c => {
    const v = r[c];
    if (c === 'status_conciliacao') return `<td><span class="badge ${v}">${v}</span></td>`;
    return `<td>${v === null || v === undefined ? '' : String(v).slice(0, 140)}</td>`;
  }).join('')}</tr>`).join('');
  document.getElementById('tbl-dyn-wrap').innerHTML = `<table><thead>${head}</thead><tbody>${body}</tbody></table>`;
}

init();
</script>
</body>
</html>
"""


class AuditHandler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        return

    def _send(self, code: int, content_type: str, body: bytes) -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/":
            self._send(HTTPStatus.OK, "text/html; charset=utf-8", _INDEX_HTML.encode("utf-8"))
            return

        if path == "/api/bundle":
            q = parse_qs(parsed.query)
            bundle = _load_portal_bundle(force=q.get("refresh") == ["1"])
            self._send(HTTPStatus.OK, "application/json; charset=utf-8",
                       json.dumps(bundle, ensure_ascii=False, default=str).encode("utf-8"))
            return

        if path.startswith("/files/"):
            fname = os.path.basename(path[len("/files/"):])
            fpath = OUTPUT_DIR / fname
            if fpath.exists() and fpath.is_file():
                ctype = (
                    "text/html; charset=utf-8" if fname.endswith(".html")
                    else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" if fname.endswith(".xlsx")
                    else "application/json; charset=utf-8"
                )
                self._send(HTTPStatus.OK, ctype, fpath.read_bytes())
                return

        self._send(HTTPStatus.NOT_FOUND, "text/plain; charset=utf-8", b"Not Found")


def export_static(dest: Path | None = None) -> Path:
    """Exporta versão estática completa em public/ para hospedagem no Vercel/GitHub."""
    import shutil

    out = dest or (Path(__file__).resolve().parent / "public")
    (out / "data").mkdir(parents=True, exist_ok=True)
    (out / "files").mkdir(parents=True, exist_ok=True)

    bundle = _load_portal_bundle(force=True)
    (out / "index.html").write_text(_INDEX_HTML, encoding="utf-8")
    (out / "data" / "bundle.json").write_text(
        json.dumps(bundle, ensure_ascii=False, default=str), encoding="utf-8"
    )
    for f in OUTPUT_DIR.iterdir():
        if f.is_file():
            shutil.copy2(f, out / "files" / f.name)
    print(f"Site estático exportado em {out}")
    return out


def serve(host: str = "127.0.0.1", port: int = 8050) -> None:
    _load_portal_bundle()
    srv = ThreadingHTTPServer((host, port), AuditHandler)
    print(f"Central de Auditoria Web ativa em http://{host}:{port}/", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Servidor Web Interativo de Auditoria - Palmópolis/MG")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8050)
    p.add_argument("--export-static", action="store_true", help="Gera build estático em public/ para Vercel")
    args = p.parse_args()
    if args.export_static:
        export_static()
    else:
        serve(args.host, args.port)
