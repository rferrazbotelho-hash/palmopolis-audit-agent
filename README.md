# Sistema de Auditoria Municipal — Prefeitura de Palmópolis/MG (CNPJ 66234345000118)

Aplicação completa em Python 3.11+ para extração, auditoria legal (Lei nº 14.133/2021, Lei nº 4.320/1964 e LAI nº 12.527/2011), análise crítica de variações inconsistentes e emissão de relatório técnico de Fiscal de Contas Públicas referente aos exercícios de **2025 e 2026**.

## Estrutura
- `connectors/` — Autenticação SPA iLAI Memory via Playwright, extração dos 19+ endpoints OData, extrator PNCP e scraper do portal institucional.
- `engine/` — Reconciliador (`reconciliador.py`), Análise Crítica (`analise_critica.py`), Fiscal de Contas Públicas (`fiscal_contas.py`) e Gerador de Relatórios (`report_builder.py`).
- `test_lab.py` & `tests/` — Ambiente de testes e análise seletiva por itens (`pytest`).
- `web_app.py` & `public/` — Central interativa web (pronta para Vercel via `outputDirectory: "public"`).

## Execução Local
```bash
pip install -r requirements.txt
python main.py --from-raw
python web_app.py --host 127.0.0.1 --port 8050
```
