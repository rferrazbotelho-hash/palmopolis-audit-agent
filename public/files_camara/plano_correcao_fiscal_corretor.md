# PLANO DE CORREÇÃO PASSO A PASSO — FISCAL CORRETOR
**Entidade:** Câmara Municipal de Palmópolis/MG | **CNPJ:** `03689862000161`  
**Exercícios:** 2025, 2026 | **Gerado em:** 18/11/2026 18:08

> **Estratégia Geral:** Plano estruturado em 5 roteiros corretivos (10 passos acionáveis), com 2 frentes de ação IMEDIATA (0 a 5 dias) focadas em estancar riscos de glosa no PNCP, estouro de dotação orçamentária e extrapolação de NAFs.

## AP-001 — Ausência de divulgação de contratos no PNCP (condição legal de eficácia)
- **Prioridade:** `IMEDIATA_0_5D` | **Gravidade:** `IRREGULARIDADE_GRAVE`
- **Causa-Raiz Diagnosticada:** Os 368 contratos constam no ERP/iLAI Memory, mas não foram transmitidos ao módulo de Contratos do PNCP (API de consulta retornou 0 contratos para 2025 e 2026).
- **Melhor Condução:** Segregar imediatamente contratos regidos pela Lei 14.133/2021 dos contratos remanescentes da Lei 8.666/93 e promover o envio em lote via integração do ERP ao PNCP, suspendendo novos pagamentos de contratos da Lei 14.133/2021 até a geração do numeroControlePNCP (condição de eficácia do Art. 94).
- **Fundamento Legal do Saneamento:** Lei 14.133/2021, Art. 94 e Art. 191; LINDB (DL 4.657/42), Art. 20 e Art. 21.

| Passo | Setor Responsável | Sistema | Ação Executável | Documentos | Critério de Validação |
|---|---|---|---|---|---|
| 1 | Departamento de Licitações e Contratos | ERP Municipal / Planilha de Controle | Listar os 368 contratos e classificar cada instrumento por regime legal (Lei 14.133/21 vs Lei 8.666/93) e situação (vigente/encerrado). | Planilha de inventário contratual assinada; Cópia dos instrumentos contratuais | 100% dos contratos vigentes da Lei 14.133/21 identificados. |
| 2 | TI / Fornecedor do ERP + Compras | ERP -> API PNCP | Configurar/reprocessar a rotina de integração de contratos no PNCP (incluindo envio dos PDFs assinados e CPF/CNPJ do contratado). | Log de transmissão API PNCP; Recibos com numeroControlePNCP | Consulta GET /api/consulta/v1/contratos?cnpjOrgao=66234345000118 retorna os contratos vigentes. |
| 3 | Controladoria Interna + Procuradoria | Processo Administrativo | Emitir despacho saneador juntando os comprovantes de publicação tardia no PNCP e notificar o ordenador de despesas sobre contratos ainda pendentes. | Parecer de saneamento da Controladoria; Comprovantes PNCP anexados aos autos | Taxa de aderência PNCP de contratos vigentes igual a 100%. |

## AP-002 — Processos licitatórios locais sem publicação no Portal Nacional de Contratações Públicas
- **Prioridade:** `IMEDIATA_0_5D` | **Gravidade:** `IRREGULARIDADE_GRAVE`
- **Causa-Raiz Diagnosticada:** Apenas 39 de 178 processos do Memory possuem espelhamento no PNCP (21,9%). Parte dos processos pode estar em plataforma eletrônica sem integração automática ou sob legislação anterior.
- **Melhor Condução:** Conferir os 139 processos sem PNCP: publicar no PNCP todos os que sejam da Lei 14.133/21 (inclusive adesões/caronas, dispensas e inexigibilidades) e documentar o amparo da Lei 8.666/93 para os anteriores.
- **Fundamento Legal do Saneamento:** Lei 14.133/2021, Arts. 54, 72, parágrafo único, 94 e 174.

| Passo | Setor Responsável | Sistema | Ação Executável | Documentos | Critério de Validação |
|---|---|---|---|---|---|
| 1 | Setor de Licitações | Portal de Compras / Licitanet / ERP | Cruzar a lista dos 139 processos apontados (aba Cruzamento_Licitacoes) com a plataforma eletrônica utilizada. | Relação processo x plataforma x lei aplicável | Cada processo possui status definido (publicar no PNCP ou regime 8.666/93). |
| 2 | Setor de Licitações + TI | PNCP (https://pncp.gov.br) | Transmitir avisos, editais, atas e termos de homologação faltantes com inteiro teor em PDF (Art. 54). | Números de Controle PNCP gerados; Recibos de envio dos anexos | Reexecução do agente de auditoria eleva aderência PNCP para >= 95% nos processos 14.133/21. |

## AP-009 — Homonímia exata entre fornecedores pagos e servidores municipais
- **Prioridade:** `CURTO_PRAZO_5_15D` | **Gravidade:** `RESSALVA_RELEVANTE`
- **Causa-Raiz Diagnosticada:** Coincidência exata de nome completo entre 127 registros na base de fornecedores e a folha de servidores (como o iLAI mascara parte do CPF na transparência, não é possível distinguir homônimos de servidores reais sem o CPF integral).
- **Melhor Condução:** Executar batimento interno de CPF completo (11 dígitos) entre a contabilidade e o RH, separando o que é pagamento de diária/suprimento de fundos/reembolso ao próprio servidor de eventual contratação comercial vedada.
- **Fundamento Legal do Saneamento:** Lei 14.133/2021, Art. 9º, §1º e Art. 14, IV.

| Passo | Setor Responsável | Sistema | Ação Executável | Documentos | Critério de Validação |
|---|---|---|---|---|---|
| 1 | Recursos Humanos + Contabilidade | Folha de Pagamento × Contabilidade | Cruzar os 127 nomes apontados na aba Fornecedores_CurvaABC por CPF completo (11 dígitos) e natureza da despesa (3.3.90.14 diárias vs fornecimento/serviços). | Relatório de batimento por CPF completo; Notas de empenho classificadas por elemento | 100% dos casos classificados como diária/homônimo legítimo ou contratação vedada. |
| 2 | Controladoria + Procuradoria | Processo de Apuração | Caso confirmado fornecimento comercial por servidor impedido, rescindir contrato e instaurar sindicância administrativa. | Termo de encerramento/rescisão; Relatório conclusivo da Controladoria | Zero fornecimentos comerciais ativos com servidores impedidos. |

## AP-010 — Omissão de identificação de contratados em contratos e lacunas de transparência ativa
- **Prioridade:** `CURTO_PRAZO_5_15D` | **Gravidade:** `RESSALVA_RELEVANTE`
- **Causa-Raiz Diagnosticada:** Omissão de razão social/CNPJ nos contratos do iLAI, erro HTTP 500 em servidores/2025, seções vazias no portal institucional (Licitações, Decretos, Leis, Diário Oficial) e divergências de valores entre Memory e PNCP.
- **Melhor Condução:** Abrir chamado técnico formal junto à Memory (iLAI) e à mantenedora do site institucional para liberar os campos de contratado/CNPJ nos contratos, corrigir a consulta de servidores/2025 e publicar o acervo de Diário Oficial/Decretos/Leis.
- **Fundamento Legal do Saneamento:** Lei 12.527/2011 (LAI), Art. 8º; LC 131/2009; Lei 14.133/2021, Art. 54.

| Passo | Setor Responsável | Sistema | Ação Executável | Documentos | Critério de Validação |
|---|---|---|---|---|---|
| 1 | Controladoria / Ouvidoria / TI | Chamado Técnico Memory iLAI + Site Institucional | Solicitar correção da view OData `comprascontratos` (exibir `fornecedor` e `cpf_cnpj`), correção do erro 500 em `pessoalservidores` (2025) e ativação da carga do Diário Oficial/Decretos/Leis no site. | Protocolo de chamado técnico com SLA; Checklist Atricon/Radar da Transparência | Campos de fornecedor/CNPJ preenchidos e Diário Oficial retornando edições publicadas. |
| 2 | Setor de Licitações | Memory iLAI × PNCP | Reconciliar os 17 processos com divergência financeira > 20% entre Memory e PNCP. | Planilha de conciliação saneada | Diferenças justificadas ou corrigidas nas duas bases. |

## AP-011 — Variações interanuais abruptas (2025 × 2026) e concentração atípica de diárias
- **Prioridade:** `ESTRUTURANTE_15_30D` | **Gravidade:** `RECOMENDACAO_CONTROLE`
- **Causa-Raiz Diagnosticada:** Variações orçamentárias interanuais abruptas e concentração estatística de diárias por servidor.
- **Melhor Condução:** Instituir revisão trimestral de metas orçamentárias e teto/prestação de contas simplificada de diárias.
- **Fundamento Legal do Saneamento:** CF/88, Art. 37 (Eficiência/Economicidade); LRF Art. 1º, §1º.

| Passo | Setor Responsável | Sistema | Ação Executável | Documentos | Critério de Validação |
|---|---|---|---|---|---|
| 1 | Planejamento / Controle Interno | Execução Orçamentária e Diárias | Solicitar justificativa às secretarias com variação > 150% e auditar os relatórios de viagem dos servidores acima do limite IQR. | Notas técnicas das secretarias; Comprovantes de viagem/diárias | Amostragem de diárias e variações orçamentárias formalmente justificadas. |
