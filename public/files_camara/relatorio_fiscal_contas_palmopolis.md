# RELATÓRIO TÉCNICO DE FISCALIZAÇÃO DE CONTAS PÚBLICAS
**Entidade:** Câmara Municipal de Palmópolis/MG | **CNPJ:** `03689862000161`  
**Exercícios Auditados:** 2025, 2026 | **Emissão:** 18/11/2026 18:08

> **Parecer Síntese:** CONCLUSÃO TÉCNICA PRELIMINAR: Diante das 2 irregularidade(s) grave(s) e 2 ressalva(s) relevante(s) apuradas nos exercícios de 2025, 2026, recomenda-se a INSTAURAÇÃO DE DILIGÊNCIA / CITAÇÃO DO GESTOR para saneamento documental e regularização imediata dos registros no PNCP, no Portal iLAI e no SICOM/TCE-MG.

## Quadro Resumo dos Apontamentos
| Indicador | Quantidade |
|---|---|
| Total de Apontamentos | 5 |
| Irregularidades Graves | 2 |
| Ressalvas Relevantes | 2 |
| Recomendações de Controle | 1 |
| Soma de Valores Envolvidos (não cumulativa entre trilhas) | R$ 1.119.322,72 |

---
## Detalhamento dos Apontamentos
### AP-001 — Ausência de divulgação de contratos no PNCP (condição legal de eficácia)
- **Categoria:** Licitações, Contratos e Publicidade (PNCP) | **Gravidade:** `IRREGULARIDADE_GRAVE` | **Prazo Sugerido:** 15 dias
- **Enquadramento Legal:** Lei Federal nº 14.133/2021, Art. 94, caput e incisos I e II; CF/88, Art. 37, caput
- **Ocorrências:** 26 | **Valor Envolvido:** R$ 506.195,42
- **Situação Encontrada:** Identificados 26 contratos/aditivos no Portal da Transparência local (Memory) sem registro correspondente na API de consulta de contratos do PNCP.
- **Risco Procedimental / ao Erário:** Nos termos expressos do Art. 94 da Lei nº 14.133/2021, a divulgação no PNCP é condição indispensável para a eficácia do contrato e de seus aditamentos. Pagamentos executados sem essa publicação sujeitam-se à glosa e responsabilização do ordenador de despesas.
- **Evidências Principais:**
  - 0001/2025
  - 0002/2025
  - 0003/2025
  - 0004/2025
  - 0005/2025
  - 0006/2025
  - 0007/2025
  - 0008/2025
  - 0009/2025
  - 0010/2025
- **Determinação ao Gestor:** Providenciar a imediata integração/envio dos instrumentos contratuais ao PNCP, comprovar as justificativas técnicas de eventual regime anterior (Lei 8.666/93) e apresentar planilha de enquadramento por contrato.

### AP-002 — Processos licitatórios locais sem publicação no Portal Nacional de Contratações Públicas
- **Categoria:** Licitações, Contratos e Publicidade (PNCP) | **Gravidade:** `IRREGULARIDADE_GRAVE` | **Prazo Sugerido:** 15 dias
- **Enquadramento Legal:** Lei Federal nº 14.133/2021, Arts. 54 e 174; Lei nº 12.527/2011, Art. 8º
- **Ocorrências:** 14 | **Valor Envolvido:** R$ 0,00
- **Situação Encontrada:** 14 processos registrados no sistema Memory não possuem publicação localizada no PNCP (taxa de aderência atual de 0.0% nas licitações).
- **Risco Procedimental / ao Erário:** Restrição à competitividade, déficit de controle social e descumprimento da publicidade nacional obrigatória dos atos convocatórios.
- **Evidências Principais:**
  - 1/2025
  - 2/2025
  - 3/2025
  - 4/2025
  - 5/2025
  - 6/2025
  - 7/2025
  - 8/2025
  - 9/2025
  - 10/2025
- **Determinação ao Gestor:** Apresentar relação dos processos regidos pela Lei 14.133/2021 com seus respectivos números de controle PNCP e corrigir a rotina de exportação da plataforma de compras.

### AP-009 — Homonímia exata entre fornecedores pagos e servidores municipais
- **Categoria:** Moralidade Administrativa e Impedimentos | **Gravidade:** `RESSALVA_RELEVANTE` | **Prazo Sugerido:** 20 dias
- **Enquadramento Legal:** Lei Federal nº 14.133/2021, Art. 9º, §1º e Art. 14, IV; CF/88, Art. 37, caput
- **Ocorrências:** 12 | **Valor Envolvido:** R$ 89.931,88
- **Situação Encontrada:** Cruzamento nominal apontou 12 fornecedores com nome idêntico ao de servidores constantes na folha municipal (CPFs parcialmente mascarados na LAI).
- **Risco Procedimental / ao Erário:** Possível contratação ou pagamento comercial a agente público em exercício, vedada pelo Art. 9º, §1º e Art. 14, IV da Lei 14.133/2021 (ou eventual registro de diária/indenização na base de fornecedores).
- **Evidências Principais:**
  - ALEXANDRE PEREIRA DA ROCHA
  - ARI GIL DE SOUZA NETO
  - ALEXANDRE ANGELO DA SILVA
  - RONALDO DIAS DE FREITAS
  - MARYEL GOMES AGUIAR
  - THIAGO PARAGUAI DE AQUINO
  - ADALBERTO JOSE COSTA
  - ANA ROSA DE MATOS
- **Determinação ao Gestor:** Realizar batimento de CPF completo em folha e contabilidade, segregando eventuais reembolsos/diárias de fornecimentos vedados.

### AP-010 — Omissão de identificação de contratados em contratos e lacunas de transparência ativa
- **Categoria:** Transparência Ativa e Controle Social (LAI) | **Gravidade:** `RESSALVA_RELEVANTE` | **Prazo Sugerido:** 15 dias
- **Enquadramento Legal:** Lei nº 12.527/2011, Art. 8º, §1º, IV e §3º; LC 131/2009; Lei 14.133/2021, Art. 54
- **Ocorrências:** 54 | **Valor Envolvido:** R$ 506.195,42
- **Situação Encontrada:** Todos os contratos retornados no endpoint Memory estão com campos 'fornecedor' e 'cpf_cnpj' nulos; adicionalmente, há endpoints de 2025 vazios/erro (servidores/2025 HTTP 500) e seções vazias no portal institucional (Licitações, Decretos, Leis e Diário Oficial).
- **Risco Procedimental / ao Erário:** Impede a fiscalização cidadã e o controle de impedimentos cadastrais (CEIS/CNEP) por ausência de CNPJ/CPF.
- **Evidências Principais:**
  - Contratos sem fornecedor/CPF-CNPJ: 26 (0001/2025; 0002/2025; 0003/2025; 0004/2025; 0005/2025; 0006/2025; 0007/2025; 0008/2025; 0009/2025; 0010/2025)
  - Lacunas LAI/Portal: 28 (repasse_concedido(2025); repasse_concedido(2026); obras(2025); medicoes(2025); medicoes(2026); concursos(2025); concursos(2026); divida_ativ)
- **Determinação ao Gestor:** Habilitar a exibição integral de razão social e CNPJ/CPF nos contratos do iLAI e regularizar as publicações de Diário Oficial, Decretos, Leis e Licitações no portal institucional.

### AP-011 — Variações interanuais abruptas (2025 × 2026) e concentração atípica de diárias
- **Categoria:** Gestão Orçamentária e Pessoal | **Gravidade:** `RECOMENDACAO_CONTROLE` | **Prazo Sugerido:** 30 dias
- **Enquadramento Legal:** CF/88, Art. 37 (Eficiência/Economicidade); LRF Art. 1º, §1º
- **Ocorrências:** 1 | **Valor Envolvido:** R$ 17.000,00
- **Situação Encontrada:** 0 dotações/naturezas com variação >= +150% ou <= -80% entre 2025 e 2026; 1 alerta estatístico de concentração de diárias por servidor.
- **Risco Procedimental / ao Erário:** Necessidade de monitoramento contínuo de planejamento orçamentário e despesas com viagens.
- **Evidências Principais:**
  - 1 servidores acima do limite IQR (R$ 11,662.50): Maior acumulado: ALEXANDRE PEREIRA DA ROCHA (R$ 17,000.00)
- **Determinação ao Gestor:** Documentar motivação técnica das variações orçamentárias e relatórios de viagem.
