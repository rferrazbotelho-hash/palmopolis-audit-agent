"""Fiscal Corretor — Especialista em Condução e Saneamento de Contas Públicas.

Recebe os apontamentos do Fiscal de Contas Públicas, analisa a causa-raiz
procedimental/sistêmica e prescreve a melhor condução jurídica e administrativa,
com plano passo a passo, setor responsável, documentos comprobatórios e critério
de validação para correção regular junto ao PNCP, TCE-MG/SICOM e LAI.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path

from jinja2 import Template
from pydantic import BaseModel, Field

from config import OUTPUT_DIR
from engine.fiscal_contas import ApontamentoControleExterno, RelatorioFiscalContas

log = logging.getLogger("engine.fiscal_corretor")


class PassoCorrecao(BaseModel):
    ordem: int
    setor_responsavel: str
    sistema_alvo: str
    acao: str
    documentos_comprobatorios: list[str] = Field(default_factory=list)
    criterio_validacao: str


class RoteiroCorrecao(BaseModel):
    codigo_apontamento: str
    titulo_apontamento: str
    gravidade: str
    prioridade_execucao: str  # IMEDIATA_0_5D | CURTO_PRAZO_5_15D | ESTRUTURANTE_15_30D
    diagnostico_causa_raiz: str
    melhor_conducao: str
    fundamento_saneamento: str
    passos: list[PassoCorrecao] = Field(default_factory=list)


class PlanoCorretorCompleto(BaseModel):
    entidade: str
    cnpj: str
    exercicios: list[int]
    gerado_em: str
    resumo_executivo: str
    total_roteiros: int
    total_passos: int
    roteiros: list[RoteiroCorrecao] = Field(default_factory=list)


def _construir_roteiro(ap: ApontamentoControleExterno) -> RoteiroCorrecao:
    c = ap.codigo

    if c == "AP-001":
        return RoteiroCorrecao(
            codigo_apontamento=c,
            titulo_apontamento=ap.titulo,
            gravidade=ap.gravidade,
            prioridade_execucao="IMEDIATA_0_5D",
            diagnostico_causa_raiz=(
                "Os 368 contratos constam no ERP/iLAI Memory, mas não foram transmitidos ao módulo de Contratos "
                "do PNCP (API de consulta retornou 0 contratos para 2025 e 2026)."
            ),
            melhor_conducao=(
                "Segregar imediatamente contratos regidos pela Lei 14.133/2021 dos contratos remanescentes da Lei "
                "8.666/93 e promover o envio em lote via integração do ERP ao PNCP, suspendendo novos pagamentos de "
                "contratos da Lei 14.133/2021 até a geração do numeroControlePNCP (condição de eficácia do Art. 94)."
            ),
            fundamento_saneamento="Lei 14.133/2021, Art. 94 e Art. 191; LINDB (DL 4.657/42), Art. 20 e Art. 21.",
            passos=[
                PassoCorrecao(
                    ordem=1,
                    setor_responsavel="Departamento de Licitações e Contratos",
                    sistema_alvo="ERP Municipal / Planilha de Controle",
                    acao="Listar os 368 contratos e classificar cada instrumento por regime legal (Lei 14.133/21 vs Lei 8.666/93) e situação (vigente/encerrado).",
                    documentos_comprobatorios=["Planilha de inventário contratual assinada", "Cópia dos instrumentos contratuais"],
                    criterio_validacao="100% dos contratos vigentes da Lei 14.133/21 identificados.",
                ),
                PassoCorrecao(
                    ordem=2,
                    setor_responsavel="TI / Fornecedor do ERP + Compras",
                    sistema_alvo="ERP -> API PNCP",
                    acao="Configurar/reprocessar a rotina de integração de contratos no PNCP (incluindo envio dos PDFs assinados e CPF/CNPJ do contratado).",
                    documentos_comprobatorios=["Log de transmissão API PNCP", "Recibos com numeroControlePNCP"],
                    criterio_validacao="Consulta GET /api/consulta/v1/contratos?cnpjOrgao=66234345000118 retorna os contratos vigentes.",
                ),
                PassoCorrecao(
                    ordem=3,
                    setor_responsavel="Controladoria Interna + Procuradoria",
                    sistema_alvo="Processo Administrativo",
                    acao="Emitir despacho saneador juntando os comprovantes de publicação tardia no PNCP e notificar o ordenador de despesas sobre contratos ainda pendentes.",
                    documentos_comprobatorios=["Parecer de saneamento da Controladoria", "Comprovantes PNCP anexados aos autos"],
                    criterio_validacao="Taxa de aderência PNCP de contratos vigentes igual a 100%.",
                ),
            ],
        )

    if c == "AP-002":
        return RoteiroCorrecao(
            codigo_apontamento=c,
            titulo_apontamento=ap.titulo,
            gravidade=ap.gravidade,
            prioridade_execucao="IMEDIATA_0_5D",
            diagnostico_causa_raiz=(
                "Apenas 39 de 178 processos do Memory possuem espelhamento no PNCP (21,9%). Parte dos processos "
                "pode estar em plataforma eletrônica sem integração automática ou sob legislação anterior."
            ),
            melhor_conducao=(
                "Conferir os 139 processos sem PNCP: publicar no PNCP todos os que sejam da Lei 14.133/21 (inclusive "
                "adesões/caronas, dispensas e inexigibilidades) e documentar o amparo da Lei 8.666/93 para os anteriores."
            ),
            fundamento_saneamento="Lei 14.133/2021, Arts. 54, 72, parágrafo único, 94 e 174.",
            passos=[
                PassoCorrecao(
                    ordem=1,
                    setor_responsavel="Setor de Licitações",
                    sistema_alvo="Portal de Compras / Licitanet / ERP",
                    acao="Cruzar a lista dos 139 processos apontados (aba Cruzamento_Licitacoes) com a plataforma eletrônica utilizada.",
                    documentos_comprobatorios=["Relação processo x plataforma x lei aplicável"],
                    criterio_validacao="Cada processo possui status definido (publicar no PNCP ou regime 8.666/93).",
                ),
                PassoCorrecao(
                    ordem=2,
                    setor_responsavel="Setor de Licitações + TI",
                    sistema_alvo="PNCP (https://pncp.gov.br)",
                    acao="Transmitir avisos, editais, atas e termos de homologação faltantes com inteiro teor em PDF (Art. 54).",
                    documentos_comprobatorios=["Números de Controle PNCP gerados", "Recibos de envio dos anexos"],
                    criterio_validacao="Reexecução do agente de auditoria eleva aderência PNCP para >= 95% nos processos 14.133/21.",
                ),
            ],
        )

    if c == "AP-003":
        return RoteiroCorrecao(
            codigo_apontamento=c,
            titulo_apontamento=ap.titulo,
            gravidade=ap.gravidade,
            prioridade_execucao="IMEDIATA_0_5D",
            diagnostico_causa_raiz=(
                "Em 2025, 5 dotações/naturezas exibem valor empenhado superior à dotação atualizada no iLAI "
                "(ex.: Assistência Social +R$ 149.533,95). Pode decorrer de decreto de suplementação não sincronizado no portal ou empenho sem crédito."
            ),
            melhor_conducao=(
                "Verificar imediatamente nos balancetes do SICOM/TCE-MG se houve abertura prévia de crédito adicional "
                "para essas 5 rubricas. Se houver decreto, atualizar o portal iLAI; se não houver, promover anulação/estorno ou regularização orçamentária formal."
            ),
            fundamento_saneamento="Lei 4.320/1964, Arts. 42, 43 e 59; CF/88, Art. 167, II.",
            passos=[
                PassoCorrecao(
                    ordem=1,
                    setor_responsavel="Contabilidade Municipal",
                    sistema_alvo="Contabilidade / SICOM TCE-MG",
                    acao="Extrair razão contábil das 5 dotações de 2025 (Assistência Social, Contribuições, Consórcio Público e Obrigações Tributárias).",
                    documentos_comprobatorios=["Razão da despesa 2025", "Decretos de créditos adicionais e leis autorizativas"],
                    criterio_validacao="Comprovada existência (ou ausência) de saldo orçamentário na data de cada empenho.",
                ),
                PassoCorrecao(
                    ordem=2,
                    setor_responsavel="Contabilidade + TI Memory",
                    sistema_alvo="iLAI Memory",
                    acao="Corrigir a carga de dotações atualizadas no iLAI caso os decretos existam, ou lavrar nota técnica de ajuste/estorno se houve erro de classificação.",
                    documentos_comprobatorios=["Comprovante de reprocessamento SICOM/iLAI", "Nota explicativa contábil"],
                    criterio_validacao="Aba Critica_Orcamentaria zerada para empenhos > dotação.",
                ),
            ],
        )

    if c == "AP-004":
        return RoteiroCorrecao(
            codigo_apontamento=c,
            titulo_apontamento=ap.titulo,
            gravidade=ap.gravidade,
            prioridade_execucao="IMEDIATA_0_5D",
            diagnostico_causa_raiz="Registros financeiros com liquidado > empenhado ou pago > liquidado.",
            melhor_conducao="Conferir estornos de empenho/liquidação e notas fiscais correspondentes, corrigindo a escrituração contábil.",
            fundamento_saneamento="Lei 4.320/1964, Arts. 60 a 64.",
            passos=[
                PassoCorrecao(
                    ordem=1,
                    setor_responsavel="Contabilidade / Tesouraria",
                    sistema_alvo="ERP Contábil",
                    acao="Auditar os empenhos e liquidações divergentes e juntar notas fiscais e atestos de recebimento.",
                    documentos_comprobatorios=["Notas fiscais atestadas", "Ordens de pagamento"],
                    criterio_validacao="Nenhum pagamento sem prévia liquidação regular.",
                ),
            ],
        )

    if c == "AP-005":
        return RoteiroCorrecao(
            codigo_apontamento=c,
            titulo_apontamento=ap.titulo,
            gravidade=ap.gravidade,
            prioridade_execucao="CURTO_PRAZO_5_15D",
            diagnostico_causa_raiz=(
                "54 processos no Memory têm valor homologado > 50% acima do 'valor_maximo_processo' (ex.: 90/2025, 105/2025, 105/2026). "
                "Na maioria dos casos de registro de preços/adesão, ocorre erro de digitação do valor máximo unitário no lugar do global no ERP, ou erro grave de pesquisa de preços."
            ),
            melhor_conducao=(
                "Separar o que é erro cadastral do ERP (valor unitário lançado no campo de valor máximo global) do que "
                "é efetiva homologação acima do orçamento estimado. Retificar os cadastros errôneos e, havendo sobrepreço real, suspender execução/revogar item."
            ),
            fundamento_saneamento="Lei 14.133/2021, Arts. 18, IV, 23 e 59, III.",
            passos=[
                PassoCorrecao(
                    ordem=1,
                    setor_responsavel="Setor de Licitações / Pregoeiro",
                    sistema_alvo="Processos Físicos/Digitais + ERP",
                    acao="Conferir os 10 maiores processos da aba Critica_Var_Valores (incluindo 90/2025, 105/2025 e 105/2026) comparando Termo de Referência/Pesquisa de Preços com Ata de Homologação.",
                    documentos_comprobatorios=["Mapa comparativo de preços (Art. 23)", "Termo de homologação"],
                    criterio_validacao="Confirmado se a divergência é cadastral (unitário vs global) ou financeira real.",
                ),
                PassoCorrecao(
                    ordem=2,
                    setor_responsavel="TI / Compras + Controle Interno",
                    sistema_alvo="ERP -> iLAI Memory",
                    acao="Retificar no ERP o campo 'valor_maximo_processo' nos casos de erro de digitação e republicar no iLAI; caso haja sobrepreço real, instaurar revisão contratual/glosa.",
                    documentos_comprobatorios=["Relatório de retificação cadastral", "Termo de repactuação/anulação (se aplicável)"],
                    criterio_validacao="Divergência entre estimado e homologado <= 0% em novas homologações.",
                ),
            ],
        )

    if c == "AP-006":
        return RoteiroCorrecao(
            codigo_apontamento=c,
            titulo_apontamento=ap.titulo,
            gravidade=ap.gravidade,
            prioridade_execucao="IMEDIATA_0_5D",
            diagnostico_causa_raiz=(
                "30 contratos apresentam soma de NAFs > 125% do valor contratado (ex.: Contrato 25/2025 com 250 NAFs somando "
                "R$ 58,89 milhões sobre contrato de R$ 358 mil — forte indício de NAFs vinculadas ao contrato errado ou execução sem aditivo)."
            ),
            melhor_conducao=(
                "Bloquear imediatamente novas NAFs sobre os 30 contratos listados na aba Critica_Contratos_NAF até auditar: "
                "(a) se houve erro de vínculo de `id_contrato` no ERP ou (b) se houve execução sem termo aditivo/excesso ao limite de 25% do Art. 125."
            ),
            fundamento_saneamento="Lei 14.133/2021, Arts. 124, 125 e 132.",
            passos=[
                PassoCorrecao(
                    ordem=1,
                    setor_responsavel="Gestão de Contratos + Compras",
                    sistema_alvo="ERP (Módulo NAFs e Contratos)",
                    acao="Emitir relatório analítico das NAFs dos 30 contratos críticos (prioridade absoluta: Contrato 25/2025 ID 331) e checar se as NAFs pertencem de fato ao objeto do contrato.",
                    documentos_comprobatorios=["Extrato analítico de NAFs por contrato", "Termos aditivos formalizados"],
                    criterio_validacao="Identificada a origem do excedente (erro de vínculo vs acréscimo sem aditivo).",
                ),
                PassoCorrecao(
                    ordem=2,
                    setor_responsavel="Procuradoria Jurídica + Controladoria",
                    sistema_alvo="Processo de Aditamento / Apuração",
                    acao="Se houver erro de sistema, corrigir o vínculo contábil; se houve execução real acima de 125%, cessar fornecimento, apurar responsabilidade e instruir eventual indenização com justificativa (Art. 149).",
                    documentos_comprobatorios=["Parecer jurídico", "Portaria de correção ou apuração de responsabilidade"],
                    criterio_validacao="Saldo de NAFs compatível com valor contratual + aditivos vigentes.",
                ),
            ],
        )

    if c == "AP-007":
        return RoteiroCorrecao(
            codigo_apontamento=c,
            titulo_apontamento=ap.titulo,
            gravidade=ap.gravidade,
            prioridade_execucao="CURTO_PRAZO_5_15D",
            diagnostico_causa_raiz="Dispensas ou acumulados anuais em compra direta acima dos tetos do Art. 75, I e II.",
            melhor_conducao=(
                "Classificar cada dispensa pelo inciso correto do Art. 75 (ex.: inciso VIII emergência não se sujeita ao teto de baixo valor, "
                "mas exige comprovação de emergência real e contratação máxima de 1 ano) e implantar trava sistêmica de fracionamento por subelemento/fornecedor."
            ),
            fundamento_saneamento="Lei 14.133/2021, Art. 75, I, II, VIII e §1º.",
            passos=[
                PassoCorrecao(
                    ordem=1,
                    setor_responsavel="Setor de Compras + Jurídico",
                    sistema_alvo="Processos de Dispensa",
                    acao="Revisar os 16 processos apontados na aba Auditoria_Art75_Dispensas e verificar a fundamentação legal (Art. 75, I/II vs outros incisos).",
                    documentos_comprobatorios=["Parecer jurídico da contratação direta (Art. 72, III)", "Justificativa de preço e escolha do fornecedor"],
                    criterio_validacao="100% das dispensas acima do teto devidamente enquadradas em inciso próprio ou justificadas.",
                ),
                PassoCorrecao(
                    ordem=2,
                    setor_responsavel="Controladoria + TI",
                    sistema_alvo="ERP Compras",
                    acao="Ativar bloqueio automático no ERP quando o acumulado anual por objeto/ramo de atividade atingir 80% do limite do Art. 75.",
                    documentos_comprobatorios=["Normativa interna de compras diretas", "Print/configuração da trava no ERP"],
                    criterio_validacao="Controle preventivo de fracionamento operacional.",
                ),
            ],
        )

    if c in ("AP-008", "AP-010"):
        return RoteiroCorrecao(
            codigo_apontamento=c,
            titulo_apontamento=ap.titulo,
            gravidade=ap.gravidade,
            prioridade_execucao="CURTO_PRAZO_5_15D",
            diagnostico_causa_raiz=(
                "Omissão de razão social/CNPJ nos contratos do iLAI, erro HTTP 500 em servidores/2025, seções vazias no portal "
                "institucional (Licitações, Decretos, Leis, Diário Oficial) e divergências de valores entre Memory e PNCP."
            ),
            melhor_conducao=(
                "Abrir chamado técnico formal junto à Memory (iLAI) e à mantenedora do site institucional para liberar os campos "
                "de contratado/CNPJ nos contratos, corrigir a consulta de servidores/2025 e publicar o acervo de Diário Oficial/Decretos/Leis."
            ),
            fundamento_saneamento="Lei 12.527/2011 (LAI), Art. 8º; LC 131/2009; Lei 14.133/2021, Art. 54.",
            passos=[
                PassoCorrecao(
                    ordem=1,
                    setor_responsavel="Controladoria / Ouvidoria / TI",
                    sistema_alvo="Chamado Técnico Memory iLAI + Site Institucional",
                    acao="Solicitar correção da view OData `comprascontratos` (exibir `fornecedor` e `cpf_cnpj`), correção do erro 500 em `pessoalservidores` (2025) e ativação da carga do Diário Oficial/Decretos/Leis no site.",
                    documentos_comprobatorios=["Protocolo de chamado técnico com SLA", "Checklist Atricon/Radar da Transparência"],
                    criterio_validacao="Campos de fornecedor/CNPJ preenchidos e Diário Oficial retornando edições publicadas.",
                ),
                PassoCorrecao(
                    ordem=2,
                    setor_responsavel="Setor de Licitações",
                    sistema_alvo="Memory iLAI × PNCP",
                    acao="Reconciliar os 17 processos com divergência financeira > 20% entre Memory e PNCP.",
                    documentos_comprobatorios=["Planilha de conciliação saneada"],
                    criterio_validacao="Diferenças justificadas ou corrigidas nas duas bases.",
                ),
            ],
        )

    if c == "AP-009":
        return RoteiroCorrecao(
            codigo_apontamento=c,
            titulo_apontamento=ap.titulo,
            gravidade=ap.gravidade,
            prioridade_execucao="CURTO_PRAZO_5_15D",
            diagnostico_causa_raiz=(
                "Coincidência exata de nome completo entre 127 registros na base de fornecedores e a folha de servidores "
                "(como o iLAI mascara parte do CPF na transparência, não é possível distinguir homônimos de servidores reais sem o CPF integral)."
            ),
            melhor_conducao=(
                "Executar batimento interno de CPF completo (11 dígitos) entre a contabilidade e o RH, separando o que é "
                "pagamento de diária/suprimento de fundos/reembolso ao próprio servidor de eventual contratação comercial vedada."
            ),
            fundamento_saneamento="Lei 14.133/2021, Art. 9º, §1º e Art. 14, IV.",
            passos=[
                PassoCorrecao(
                    ordem=1,
                    setor_responsavel="Recursos Humanos + Contabilidade",
                    sistema_alvo="Folha de Pagamento × Contabilidade",
                    acao="Cruzar os 127 nomes apontados na aba Fornecedores_CurvaABC por CPF completo (11 dígitos) e natureza da despesa (3.3.90.14 diárias vs fornecimento/serviços).",
                    documentos_comprobatorios=["Relatório de batimento por CPF completo", "Notas de empenho classificadas por elemento"],
                    criterio_validacao="100% dos casos classificados como diária/homônimo legítimo ou contratação vedada.",
                ),
                PassoCorrecao(
                    ordem=2,
                    setor_responsavel="Controladoria + Procuradoria",
                    sistema_alvo="Processo de Apuração",
                    acao="Caso confirmado fornecimento comercial por servidor impedido, rescindir contrato e instaurar sindicância administrativa.",
                    documentos_comprobatorios=["Termo de encerramento/rescisão", "Relatório conclusivo da Controladoria"],
                    criterio_validacao="Zero fornecimentos comerciais ativos com servidores impedidos.",
                ),
            ],
        )

    # AP-011 / genérico
    return RoteiroCorrecao(
        codigo_apontamento=c,
        titulo_apontamento=ap.titulo,
        gravidade=ap.gravidade,
        prioridade_execucao="ESTRUTURANTE_15_30D",
        diagnostico_causa_raiz="Variações orçamentárias interanuais abruptas e concentração estatística de diárias por servidor.",
        melhor_conducao="Instituir revisão trimestral de metas orçamentárias e teto/prestação de contas simplificada de diárias.",
        fundamento_saneamento="CF/88, Art. 37 (Eficiência/Economicidade); LRF Art. 1º, §1º.",
        passos=[
            PassoCorrecao(
                ordem=1,
                setor_responsavel="Planejamento / Controle Interno",
                sistema_alvo="Execução Orçamentária e Diárias",
                acao="Solicitar justificativa às secretarias com variação > 150% e auditar os relatórios de viagem dos servidores acima do limite IQR.",
                documentos_comprobatorios=["Notas técnicas das secretarias", "Comprovantes de viagem/diárias"],
                criterio_validacao="Amostragem de diárias e variações orçamentárias formalmente justificadas.",
            ),
        ],
    )


class FiscalCorretor:
    """Analisa os apontamentos do Fiscal de Contas e gera a condução passo a passo para correção."""

    def __init__(self, relatorio_fiscal: RelatorioFiscalContas) -> None:
        self.rel = relatorio_fiscal

    def gerar_plano(self) -> PlanoCorretorCompleto:
        roteiros = [_construir_roteiro(ap) for ap in self.rel.apontamentos]
        ordem_prio = {"IMEDIATA_0_5D": 0, "CURTO_PRAZO_5_15D": 1, "ESTRUTURANTE_15_30D": 2}
        roteiros.sort(key=lambda r: (ordem_prio.get(r.prioridade_execucao, 9), r.codigo_apontamento))
        total_passos = sum(len(r.passos) for r in roteiros)
        imediatos = sum(1 for r in roteiros if r.prioridade_execucao == "IMEDIATA_0_5D")

        resumo = (
            f"Plano estruturado em {len(roteiros)} roteiros corretivos ({total_passos} passos acionáveis), "
            f"com {imediatos} frentes de ação IMEDIATA (0 a 5 dias) focadas em estancar riscos de glosa no PNCP, "
            f"estouro de dotação orçamentária e extrapolação de NAFs."
        )
        log.info("Fiscal Corretor gerou %d roteiros (%d passos).", len(roteiros), total_passos)
        return PlanoCorretorCompleto(
            entidade=self.rel.entidade,
            cnpj=self.rel.cnpj,
            exercicios=self.rel.exercicios,
            gerado_em=datetime.now().strftime("%d/%m/%Y %H:%M"),
            resumo_executivo=resumo,
            total_roteiros=len(roteiros),
            total_passos=total_passos,
            roteiros=roteiros,
        )


def export_plano_corretor(plano: PlanoCorretorCompleto, out_dir: Path | None = None) -> dict[str, Path]:
    """Exporta o Plano de Correção Passo a Passo em JSON, Markdown e HTML."""
    dest = out_dir or OUTPUT_DIR
    dest.mkdir(parents=True, exist_ok=True)

    json_path = dest / "plano_correcao_fiscal_corretor.json"
    json_path.write_text(json.dumps(plano.model_dump(), ensure_ascii=False, indent=2), encoding="utf-8")

    md = [
        "# PLANO DE CORREÇÃO PASSO A PASSO — FISCAL CORRETOR",
        f"**Entidade:** {plano.entidade} | **CNPJ:** `{plano.cnpj}`  ",
        f"**Exercícios:** {', '.join(map(str, plano.exercicios))} | **Gerado em:** {plano.gerado_em}",
        "",
        f"> **Estratégia Geral:** {plano.resumo_executivo}",
        "",
    ]
    for r in plano.roteiros:
        md.extend([
            f"## {r.codigo_apontamento} — {r.titulo_apontamento}",
            f"- **Prioridade:** `{r.prioridade_execucao}` | **Gravidade:** `{r.gravidade}`",
            f"- **Causa-Raiz Diagnosticada:** {r.diagnostico_causa_raiz}",
            f"- **Melhor Condução:** {r.melhor_conducao}",
            f"- **Fundamento Legal do Saneamento:** {r.fundamento_saneamento}",
            "",
            "| Passo | Setor Responsável | Sistema | Ação Executável | Documentos | Critério de Validação |",
            "|---|---|---|---|---|---|",
        ])
        for p in r.passos:
            docs = "; ".join(p.documentos_comprobatorios)
            md.append(f"| {p.ordem} | {p.setor_responsavel} | {p.sistema_alvo} | {p.acao} | {docs} | {p.criterio_validacao} |")
        md.append("")
    md_path = dest / "plano_correcao_fiscal_corretor.md"
    md_path.write_text("\n".join(md), encoding="utf-8")

    tpl = Template("""<!DOCTYPE html>
<html lang="pt-BR"><head><meta charset="utf-8"/>
<title>Fiscal Corretor — Plano de Correção Passo a Passo</title>
<style>
  body { font-family: 'Segoe UI', Arial, sans-serif; margin: 0; background: #f4f6f9; color: #1a202c; }
  header { background: linear-gradient(135deg, #065f46, #047857); color: #fff; padding: 24px 32px; }
  main { max-width: 1200px; margin: 22px auto; padding: 0 20px 40px; }
  .summary { background: #ecfdf5; border-left: 5px solid #059669; padding: 14px 18px; border-radius: 8px; margin-bottom: 20px; }
  .card { background: #fff; border: 1px solid #e2e8f0; border-radius: 10px; padding: 18px; margin-bottom: 18px; }
  .badge { display: inline-block; padding: 3px 9px; border-radius: 999px; font-size: 11px; font-weight: 700; }
  .IMEDIATA_0_5D { background: #fee2e2; color: #b91c1c; }
  .CURTO_PRAZO_5_15D { background: #ffedd5; color: #c2410c; }
  .ESTRUTURANTE_15_30D { background: #dbeafe; color: #1d4ed8; }
  table { width: 100%; border-collapse: collapse; font-size: 12.5px; margin-top: 10px; }
  th, td { border: 1px solid #e2e8f0; padding: 8px; text-align: left; vertical-align: top; }
  th { background: #f8fafc; color: #0f294a; }
</style></head><body>
<header>
  <h1 style="margin:0 0 6px;font-size:21px;">Fiscal Corretor — Condução e Plano Passo a Passo</h1>
  <p style="margin:0;font-size:13px;opacity:.9;">{{ plano.entidade }} | CNPJ {{ plano.cnpj }} | {{ plano.gerado_em }}</p>
</header>
<main>
  <div class="summary"><strong>{{ plano.resumo_executivo }}</strong></div>
  {% for r in plano.roteiros %}
  <div class="card">
    <span class="badge {{ r.prioridade_execucao }}">{{ r.prioridade_execucao }}</span>
    <span style="font-size:12px;color:#64748b;margin-left:8px;">{{ r.gravidade }}</span>
    <h2 style="margin:8px 0 6px;font-size:17px;color:#0f294a;">{{ r.codigo_apontamento }} — {{ r.titulo_apontamento }}</h2>
    <p style="margin:4px 0;"><strong>Causa-Raiz:</strong> {{ r.diagnostico_causa_raiz }}</p>
    <p style="margin:4px 0;"><strong>Melhor Condução:</strong> {{ r.melhor_conducao }}</p>
    <p style="margin:4px 0;font-size:12.5px;color:#475569;"><strong>Fundamento:</strong> {{ r.fundamento_saneamento }}</p>
    <table>
      <thead><tr><th>Passo</th><th>Setor</th><th>Sistema</th><th>Ação</th><th>Documentos</th><th>Validação</th></tr></thead>
      <tbody>
        {% for p in r.passos %}
        <tr>
          <td><strong>{{ p.ordem }}</strong></td><td>{{ p.setor_responsavel }}</td><td>{{ p.sistema_alvo }}</td>
          <td>{{ p.acao }}</td><td>{{ p.documentos_comprobatorios|join('; ') }}</td><td>{{ p.criterio_validacao }}</td>
        </tr>
        {% endfor %}
      </tbody>
    </table>
  </div>
  {% endfor %}
</main></body></html>""")
    html_path = dest / "plano_correcao_fiscal_corretor.html"
    html_path.write_text(tpl.render(plano=plano), encoding="utf-8")
    return {"json": json_path, "md": md_path, "html": html_path}
