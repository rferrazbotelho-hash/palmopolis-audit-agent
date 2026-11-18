EXCELENTÍSSIMO(A) SENHOR(A) CONSELHEIRO(A)-PRESIDENTE DO TRIBUNAL DE CONTAS DO ESTADO DE MINAS GERAIS (TCE-MG)

**Assunto:** Representação / Denúncia com Pedido de Diligência e Apuração de Irregularidades — Câmara Municipal de Palmópolis/MG (CNPJ `03689862000161`), Exercícios 2025, 2026.

## 1. DA LEGITIMIDADE E COMPETÊNCIA (ESCLARECIMENTO QUANTO AO TCE-MG / TCM-MG)
Com fundamento no **Art. 74, §2º, e Art. 113, §1º, da Constituição Federal**, c/c **Art. 170, §4º, da Lei nº 14.133/2021** e **Arts. 65 a 70 da Lei Complementar Estadual nº 102/2008 (Lei Orgânica do TCE-MG)**, apresenta-se a presente **REPRESENTAÇÃO** instruída com provas documentais extraídas integralmente de bases públicas oficiais.

> **Nota Técnica de Competência (TCE-MG vs. TCM-MG):** Em Minas Gerais, a fiscalização contábil, financeira, orçamentária, operacional e patrimonial dos municípios é exercida privativamente pelo **TCE-MG** (Art. 76 da Constituição do Estado de Minas Gerais), não existindo Tribunal de Contas dos Municípios (TCM-MG) autônomo.

## 2. DOS FATOS E IRREGULARIDADES APURADAS
O cruzamento automatizado entre o Portal da Transparência Municipal (sistema iLAI Memory), o Portal Nacional de Contratações Públicas (PNCP) e o Portal Institucional revelou os seguintes indícios de irregularidades:

### AP-001 — Ausência de divulgação de contratos no PNCP (condição legal de eficácia) (IRREGULARIDADE_GRAVE)
- **Base Legal:** Lei Federal nº 14.133/2021, Art. 94, caput e incisos I e II; CF/88, Art. 37, caput
- **Quantitativo / Materialidade:** 26 ocorrência(s) | R$ 506.195,42
- **Descrição Fática:** Identificados 26 contratos/aditivos no Portal da Transparência local (Memory) sem registro correspondente na API de consulta de contratos do PNCP.
- **Evidências Extraídas (Portal iLAI Memory / PNCP):**
    - 0001/2025
    - 0002/2025
    - 0003/2025
    - 0004/2025
    - 0005/2025
    - 0006/2025

### AP-002 — Processos licitatórios locais sem publicação no Portal Nacional de Contratações Públicas (IRREGULARIDADE_GRAVE)
- **Base Legal:** Lei Federal nº 14.133/2021, Arts. 54 e 174; Lei nº 12.527/2011, Art. 8º
- **Quantitativo / Materialidade:** 14 ocorrência(s) | R$ 0,00
- **Descrição Fática:** 14 processos registrados no sistema Memory não possuem publicação localizada no PNCP (taxa de aderência atual de 0.0% nas licitações).
- **Evidências Extraídas (Portal iLAI Memory / PNCP):**
    - 1/2025
    - 2/2025
    - 3/2025
    - 4/2025
    - 5/2025
    - 6/2025

### AP-009 — Homonímia exata entre fornecedores pagos e servidores municipais (RESSALVA_RELEVANTE)
- **Base Legal:** Lei Federal nº 14.133/2021, Art. 9º, §1º e Art. 14, IV; CF/88, Art. 37, caput
- **Quantitativo / Materialidade:** 12 ocorrência(s) | R$ 89.931,88
- **Descrição Fática:** Cruzamento nominal apontou 12 fornecedores com nome idêntico ao de servidores constantes na folha municipal (CPFs parcialmente mascarados na LAI).
- **Evidências Extraídas (Portal iLAI Memory / PNCP):**
    - ALEXANDRE PEREIRA DA ROCHA
    - ARI GIL DE SOUZA NETO
    - ALEXANDRE ANGELO DA SILVA
    - RONALDO DIAS DE FREITAS
    - MARYEL GOMES AGUIAR
    - THIAGO PARAGUAI DE AQUINO

### AP-010 — Omissão de identificação de contratados em contratos e lacunas de transparência ativa (RESSALVA_RELEVANTE)
- **Base Legal:** Lei nº 12.527/2011, Art. 8º, §1º, IV e §3º; LC 131/2009; Lei 14.133/2021, Art. 54
- **Quantitativo / Materialidade:** 54 ocorrência(s) | R$ 506.195,42
- **Descrição Fática:** Todos os contratos retornados no endpoint Memory estão com campos 'fornecedor' e 'cpf_cnpj' nulos; adicionalmente, há endpoints de 2025 vazios/erro (servidores/2025 HTTP 500) e seções vazias no portal institucional (Licitações, Decretos, Leis e Diário Oficial).
- **Evidências Extraídas (Portal iLAI Memory / PNCP):**
    - Contratos sem fornecedor/CPF-CNPJ: 26 (0001/2025; 0002/2025; 0003/2025; 0004/2025; 0005/2025; 0006/2025; 0007/2025; 0008/2025; 0009/2025; 0010/2025)
    - Lacunas LAI/Portal: 28 (repasse_concedido(2025); repasse_concedido(2026); obras(2025); medicoes(2025); medicoes(2026); concursos(2025); concursos(2026); divida_ativ)

### AP-011 — Variações interanuais abruptas (2025 × 2026) e concentração atípica de diárias (RECOMENDACAO_CONTROLE)
- **Base Legal:** CF/88, Art. 37 (Eficiência/Economicidade); LRF Art. 1º, §1º
- **Quantitativo / Materialidade:** 1 ocorrência(s) | R$ 17.000,00
- **Descrição Fática:** 0 dotações/naturezas com variação >= +150% ou <= -80% entre 2025 e 2026; 1 alerta estatístico de concentração de diárias por servidor.
- **Evidências Extraídas (Portal iLAI Memory / PNCP):**
    - 1 servidores acima do limite IQR (R$ 11,662.50): Maior acumulado: ALEXANDRE PEREIRA DA ROCHA (R$ 17,000.00)

## 3. DOS PEDIDOS AO TCE-MG
Diante do exposto, requer-se a Vossa Excelência:
1. O **recebimento e autuação** da presente Representação/Denúncia, com distribuição a Relator;
2. A **citação/intimação do(a) Prefeito(a) Municipal e dos ordenadores de despesas** para apresentação dos autos físicos, justificativas, termos aditivos, decretos de créditos adicionais e comprovantes de envio ao PNCP e ao **SICOM/TCE-MG**;
3. A **realização de inspeção ou auditoria de conformidade** pela Unidade Técnica competente, especialmente quanto aos contratos sem eficácia no PNCP (`AP-001`), dotações empenhadas acima do limite (`AP-003`) e contratos com NAFs > 125% (`AP-006`);
4. A aplicação das **sanções cabíveis** (Art. 83 e Art. 85 da LC 102/2008) caso não saneadas ou comprovado dano ao erário.

Termos em que pede deferimento.
Palmópolis/MG, 18/11/2026.
