"""Agente Jurídico Especialista — Formulação de Denúncias e Parecer Integrado com TCU.

Produz:
1. Parecer Jurídico Completo com Matriz de Validação frente à jurisprudência e
   normativos aplicáveis do Tribunal de Contas da União (TCU);
2. Minuta robusta de Representação/Denúncia para o TCE-MG (com nota técnica de
   competência esclarecendo que em Minas Gerais não há TCM-MG autônomo, cabendo
   ao TCE-MG a fiscalização municipal);
3. Minuta robusta de Notícia de Fato / Representação para o MPMG (Promotoria de
   Justiça de Defesa do Patrimônio Público);
4. Exportação em Markdown, HTML unificado (pronto para impressão/PDF) e JSON.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from jinja2 import Template
from pydantic import BaseModel, Field

from config import OUTPUT_DIR
from engine.fiscal_contas import ApontamentoControleExterno, RelatorioFiscalContas
from engine.fiscal_corretor import PlanoCorretorCompleto

log = logging.getLogger("engine.agente_juridico")


class ValidacaoTCUItem(BaseModel):
    codigo_apontamento: str
    titulo_apontamento: str
    gravidade: str
    valor_envolvido: float
    status_validacao_tcu: str  # VALIDADO_RISCO_DEBITO_MULTA | VALIDADO_RISCO_GLOSA | REQUER_DILIGENCIA_PREVIA
    entendimento_tcu_aplicavel: str
    tipificacao_controle_externo: str
    repercussao_juridica: str


class DossieJuridicoCompleto(BaseModel):
    entidade: str
    cnpj: str
    exercicios: list[int]
    gerado_em: str
    nota_competencia_tce_tcm_mg: str
    parecer_juridico_conclusivo: str
    validacoes_tcu: list[ValidacaoTCUItem] = Field(default_factory=list)
    minuta_tce_mg: str
    minuta_mpmg: str


_TCU_MATRIZ: dict[str, dict[str, str]] = {
    "AP-001": {
        "status": "VALIDADO_RISCO_GLOSA",
        "entendimento": (
            "Conforme o Art. 94 da Lei nº 14.133/2021 e a orientação consolidada do TCU sobre o PNCP "
            "(ex.: aplicação do regime da Nova Lei de Licitações e obrigatoriedade de centralização nacional), "
            "a divulgação no PNCP constitui condição indispensável para a eficácia do contrato e de seus aditivos."
        ),
        "tipificacao": "Execução de despesa contratual sem preenchimento de condição legal de eficácia (Art. 94, Lei 14.133/2021).",
        "repercussao": "Possibilidade de determinação de regularização imediata, multa do Art. 83 da LC 102/2008 (TCE-MG) e glosa se houver dano.",
    },
    "AP-002": {
        "status": "VALIDADO_RISCO_GLOSA",
        "entendimento": (
            "Nos termos do Art. 54 e do Art. 174 da Lei nº 14.133/2021, e em consonância com a jurisprudência do TCU "
            "sobre ampla publicidade e competitividade (CF/88, Art. 37, XXI), os editais e avisos de contratação devem "
            "ser divulgados no PNCP com inteiro teor."
        ),
        "tipificacao": "Déficit de publicidade nacional obrigatória de certames licitatórios (Arts. 54 e 174, Lei 14.133/2021).",
        "repercussao": "Nulidade potencial dos certames sem publicidade adequada (Art. 147, Lei 14.133/2021) e aplicação de multa aos responsáveis.",
    },
    "AP-003": {
        "status": "VALIDADO_RISCO_DEBITO_MULTA",
        "entendimento": (
            "Jurisprudência pacífica do TCU e dos Tribunais de Contas estaduais: é vedada a realização de despesa "
            "ou assunção de obrigação direta que exceda os créditos orçamentários ou adicionais (CF/88, Art. 167, II; "
            "Lei nº 4.320/1964, Art. 59)."
        ),
        "tipificacao": "Despesa empenhada acima da dotação atualizada (Art. 59 da Lei 4.320/1964 e Art. 167, II, da CF/88).",
        "repercussao": "Irregularidade grave com reflexo direto no Parecer Prévio das contas anuais do Chefe do Executivo.",
    },
    "AP-004": {
        "status": "VALIDADO_RISCO_DEBITO_MULTA",
        "entendimento": (
            "O TCU reitera que o pagamento sem prévia e regular liquidação da despesa viola os Arts. 62 e 63 da Lei nº "
            "4.320/1964, configurando antecipação ilícita de pagamento ou falha grave de controle contábil."
        ),
        "tipificacao": "Inversão dos estágios legais da despesa pública (Arts. 60-64, Lei 4.320/1964).",
        "repercussao": "Responsabilização do ordenador de despesas e imputação de débito caso não comprovada a contraprestação.",
    },
    "AP-005": {
        "status": "REQUER_DILIGENCIA_PREVIA",
        "entendimento": (
            "Segundo o TCU (Art. 23 e Art. 59, III, da Lei 14.133/2021; IN SEGES/ME nº 65/2021), a pesquisa de preços "
            "é pressuposto de validade da contratação, sendo vedada a adjudicação acima do preço máximo aceitável sem "
            "justificativa formal."
        ),
        "tipificacao": "Distorção extrema entre valor máximo estimado e homologado (>50%, chegando a +7.743% e +1.790%).",
        "repercussao": "Indício de sobrepreço ou erro grave de escrituração no portal; exige exame dos autos físicos e atas.",
    },
    "AP-006": {
        "status": "VALIDADO_RISCO_DEBITO_MULTA",
        "entendimento": (
            "O TCU entende que alterações contratuais acima do limite de 25% (Art. 125 da Lei 14.133/2021) ou execução "
            "descoberta por notas de autorização sem termo aditivo formal violam a obrigatoriedade de licitar e o Art. 132."
        ),
        "tipificacao": "Execução por NAFs acima de 125% do valor contratado (Art. 125, Lei 14.133/2021).",
        "repercussao": "Risco de débito pelo excedente irregular, multa e apuração de contratação verbal/sem cobertura.",
    },
    "AP-007": {
        "status": "VALIDADO_RISCO_GLOSA",
        "entendimento": (
            "O TCU veda o fracionamento de despesas do mesmo ramo de atividade para fuga ao procedimento licitatório "
            "(Art. 75, §1º, I e II, da Lei 14.133/2021), exigindo planejamento anual das contratações."
        ),
        "tipificacao": "Dispensas por valor ou acumulados anuais acima dos tetos atualizados (Decretos 12.343/2024 e 12.807/2025).",
        "repercussao": "Possível caracterização de contratação direta ilegal (Art. 337-E do Código Penal, se comprovado dolo).",
    },
    "AP-008": {
        "status": "REQUER_DILIGENCIA_PREVIA",
        "entendimento": (
            "A confiabilidade dos dados abertos e da integração com o PNCP é exigência de governança pública e da LAI "
            "(Lei 12.527/2011, Art. 8º, §3º, II)."
        ),
        "tipificacao": "Divergências financeiras > 20% entre Portal local e PNCP.",
        "repercussao": "Determinação de saneamento cadastral e conciliação contábil.",
    },
    "AP-009": {
        "status": "REQUER_DILIGENCIA_PREVIA",
        "entendimento": (
            "O TCU veda a participação de servidor público do órgão contratante em licitações e contratos (Art. 9º, §1º "
            "e Art. 14, IV, da Lei 14.133/2021), ressalvadas indenizações/diárias devidamente classificadas."
        ),
        "tipificacao": "Homonímia exata entre fornecedores pagos e servidores da folha municipal (127 ocorrências).",
        "repercussao": "Requer batimento de CPF completo em folha; se confirmado fornecimento comercial vedado, nulidade e improbidade.",
    },
    "AP-010": {
        "status": "VALIDADO_RISCO_GLOSA",
        "entendimento": (
            "O TCU e a Atricon consideram violação direta à LAI (Art. 8º, §1º, IV) e à LC 131/2009 a ocultação do "
            "contratado/CNPJ nos contratos e a ausência de publicação de Diário Oficial e licitações."
        ),
        "tipificacao": "Omissão de fornecedor/CNPJ em 368 contratos no iLAI e seções institucionais vazias.",
        "repercussao": "Redução do índice de transparência e aplicação de sanção/determinação pelo TCE-MG.",
    },
    "AP-011": {
        "status": "REQUER_DILIGENCIA_PREVIA",
        "entendimento": "O controle de economicidade exige justificativa técnica para variações orçamentárias atípicas e diárias.",
        "tipificacao": "Variações interanuais >= 150% e outliers estatísticos em diárias.",
        "repercussao": "Recomendação de controle interno e auditoria amostral de prestações de contas de viagem.",
    },
}


class AgenteJuridico:
    """Formula parecer jurídico validado pelo referencial TCU e minutas para TCE-MG e MPMG."""

    def __init__(
        self,
        rel_fiscal: RelatorioFiscalContas,
        plano_corretor: PlanoCorretorCompleto | None = None,
    ) -> None:
        self.rel = rel_fiscal
        self.plano = plano_corretor

    def _validar_tcu(self, ap: ApontamentoControleExterno) -> ValidacaoTCUItem:
        ref = _TCU_MATRIZ.get(ap.codigo, {
            "status": "REQUER_DILIGENCIA_PREVIA",
            "entendimento": "Aplicação geral dos princípios da legalidade, publicidade e economicidade (CF/88, Art. 37).",
            "tipificacao": ap.titulo,
            "repercussao": "Apuração em sede de controle externo.",
        })
        return ValidacaoTCUItem(
            codigo_apontamento=ap.codigo,
            titulo_apontamento=ap.titulo,
            gravidade=ap.gravidade,
            valor_envolvido=ap.valor_envolvido,
            status_validacao_tcu=ref["status"],
            entendimento_tcu_aplicavel=ref["entendimento"],
            tipificacao_controle_externo=ref["tipificacao"],
            repercussao_juridica=ref["repercussao"],
        )

    @staticmethod
    def _brl(v: float) -> str:
        return "R$ " + f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

    def _build_minuta_tce_mg(self, validacoes: list[ValidacaoTCUItem]) -> str:
        blocos_fatos = []
        for ap in self.rel.apontamentos:
            evs = "\n".join(f"    - {e}" for e in ap.evidencias_principais[:6]) or "    - Conforme anexos digitais extraídos."
            blocos_fatos.append(
                f"### {ap.codigo} — {ap.titulo} ({ap.gravidade})\n"
                f"- **Base Legal:** {ap.base_legal}\n"
                f"- **Quantitativo / Materialidade:** {ap.quantidade_ocorrencias} ocorrência(s) | {self._brl(ap.valor_envolvido)}\n"
                f"- **Descrição Fática:** {ap.situacao_encontrada}\n"
                f"- **Evidências Extraídas (Portal iLAI Memory / PNCP):**\n{evs}\n"
            )

        return (
            "EXCELENTÍSSIMO(A) SENHOR(A) CONSELHEIRO(A)-PRESIDENTE DO TRIBUNAL DE CONTAS DO ESTADO DE MINAS GERAIS (TCE-MG)\n\n"
            "**Assunto:** Representação / Denúncia com Pedido de Diligência e Apuração de Irregularidades — "
            f"{self.rel.entidade} (CNPJ `{self.rel.cnpj}`), Exercícios {', '.join(map(str, self.rel.exercicios))}.\n\n"
            "## 1. DA LEGITIMIDADE E COMPETÊNCIA (ESCLARECIMENTO QUANTO AO TCE-MG / TCM-MG)\n"
            "Com fundamento no **Art. 74, §2º, e Art. 113, §1º, da Constituição Federal**, c/c **Art. 170, §4º, da Lei nº 14.133/2021** "
            "e **Arts. 65 a 70 da Lei Complementar Estadual nº 102/2008 (Lei Orgânica do TCE-MG)**, apresenta-se a presente "
            "**REPRESENTAÇÃO** instruída com provas documentais extraídas integralmente de bases públicas oficiais.\n\n"
            "> **Nota Técnica de Competência (TCE-MG vs. TCM-MG):** Em Minas Gerais, a fiscalização contábil, financeira, "
            "orçamentária, operacional e patrimonial dos municípios é exercida privativamente pelo **TCE-MG** (Art. 76 da "
            "Constituição do Estado de Minas Gerais), não existindo Tribunal de Contas dos Municípios (TCM-MG) autônomo.\n\n"
            "## 2. DOS FATOS E IRREGULARIDADES APURADAS\n"
            "O cruzamento automatizado entre o Portal da Transparência Municipal (sistema iLAI Memory), o Portal Nacional de "
            "Contratações Públicas (PNCP) e o Portal Institucional revelou os seguintes indícios de irregularidades:\n\n"
            + "\n".join(blocos_fatos)
            + "\n## 3. DOS PEDIDOS AO TCE-MG\n"
            "Diante do exposto, requer-se a Vossa Excelência:\n"
            "1. O **recebimento e autuação** da presente Representação/Denúncia, com distribuição a Relator;\n"
            "2. A **citação/intimação do(a) Prefeito(a) Municipal e dos ordenadores de despesas** para apresentação dos autos "
            "físicos, justificativas, termos aditivos, decretos de créditos adicionais e comprovantes de envio ao PNCP e ao **SICOM/TCE-MG**;\n"
            "3. A **realização de inspeção ou auditoria de conformidade** pela Unidade Técnica competente, especialmente quanto aos contratos "
            "sem eficácia no PNCP (`AP-001`), dotações empenhadas acima do limite (`AP-003`) e contratos com NAFs > 125% (`AP-006`);\n"
            "4. A aplicação das **sanções cabíveis** (Art. 83 e Art. 85 da LC 102/2008) caso não saneadas ou comprovado dano ao erário.\n\n"
            f"Termos em que pede deferimento.\nPalmópolis/MG, {self.rel.gerado_em[:10]}.\n"
        )

    def _build_minuta_mpmg(self) -> str:
        graves = [ap for ap in self.rel.apontamentos if ap.gravidade == "IRREGULARIDADE_GRAVE"]
        lista = "\n".join(
            f"- **{ap.codigo} — {ap.titulo}:** {ap.situacao_encontrada} (Valor envolvido: {self._brl(ap.valor_envolvido)}; Base: {ap.base_legal})."
            for ap in graves
        )
        return (
            "EXCELENTÍSSIMO(A) SENHOR(A) PROMOTOR(A) DE JUSTIÇA DO MINISTÉRIO PÚBLICO DO ESTADO DE MINAS GERAIS (MPMG)\n"
            "*(Comarca responsável por Palmópolis/MG — Curadoria de Defesa do Patrimônio Público / CAOP-PP)*\n\n"
            "**Assunto:** Notícia de Fato / Representação para Instauração de Inquérito Civil — "
            f"{self.rel.entidade} (CNPJ `{self.rel.cnpj}`), Exercícios {', '.join(map(str, self.rel.exercicios))}.\n\n"
            "## 1. DO OBJETO DA NOTÍCIA DE FATO\n"
            "Com fulcro no **Art. 129, incisos II e III, da Constituição Federal**, na **Lei nº 7.347/1985** e na "
            "**Lei nº 8.429/1992 (com redação da Lei nº 14.230/2021)**, leva-se ao conhecimento deste órgão ministerial "
            "um conjunto estruturado de indícios de irregularidades procedimentais, orçamentárias e de publicidade na gestão "
            "de compras públicas do Município de Palmópolis/MG.\n\n"
            "## 2. DOS INDÍCIOS DE IRREGULARIDADES GRAVES\n"
            f"{lista}\n\n"
            "Adicionalmente, aponta-se **ressalva de moralidade administrativa (`AP-009`)** decorrente de 127 homonímias exatas "
            "entre fornecedores pagos e servidores municipais (R$ 393.485,93), exigindo batimento de CPF completo em folha, "
            "bem como **opacidade contratual (`AP-010`)** pela ausência de identificação de fornecedor/CNPJ nos 368 contratos do portal.\n\n"
            "## 3. DA TIPIFICAÇÃO POTENCIAL (IMPROBIDADE E ILÍCITOS LICITATÓRIOS)\n"
            "Sem prejuízo da apuração do **elemento subjetivo doloso** exigido pela Lei nº 14.230/2021, os fatos demandam verificação "
            "quanto à eventual ocorrência de:\n"
            "- **Atos de Improbidade Administrativa** que causem lesão ao erário ou atentem contra os princípios da Administração Pública "
            "(Arts. 10 e 11 da Lei nº 8.429/1992);\n"
            "- **Crimes em Licitações e Contratos** (Código Penal, Arts. 337-E e seguintes, se constatada contratação direta ilegal ou fraude);\n"
            "- **Descumprimento da Lei de Acesso à Informação** (Lei nº 12.527/2011, Art. 8º).\n\n"
            "## 4. DOS REQUERIMENTOS\n"
            "Requer-se ao Ministério Público do Estado de Minas Gerais:\n"
            "1. A **instauração de Notícia de Fato / Inquérito Civil** para requisição dos processos administrativos integrais;\n"
            "2. A **requisição ao Município** do batimento de CPF completo dos 127 casos de homonímia (`AP-009`), das notas fiscais e "
            "termos aditivos dos 30 contratos extrapolados por NAFs (`AP-006`) e dos decretos orçamentários de 2025 (`AP-003`);\n"
            "3. A **expedição de Recomendação Ministerial** para publicação imediata dos contratos no PNCP (Art. 94) e regularização "
            "dos dados abertos no portal de transparência, ou propositura de **Ação Civil Pública** caso comprovado dano ao erário.\n\n"
            f"Palmópolis/MG, {self.rel.gerado_em[:10]}.\n"
        )

    def emitir_dossie(self) -> DossieJuridicoCompleto:
        validacoes = [self._validar_tcu(ap) for ap in self.rel.apontamentos]
        nota_comp = (
            "ESCLARECIMENTO INSTITUCIONAL (TCE-MG × TCM-MG): No Estado de Minas Gerais, não existe Tribunal de Contas dos "
            "Municípios (TCM-MG) separado; toda a jurisdição de controle externo municipal pertence constitucionalmente ao "
            "Tribunal de Contas do Estado de Minas Gerais (TCE-MG). Assim, a peça de controle de contas deve ser protocolada "
            "diretamente no e-TCE-MG / Ouvidoria do TCE-MG."
        )
        risco_deb = sum(1 for v in validacoes if v.status_validacao_tcu == "VALIDADO_RISCO_DEBITO_MULTA")
        risco_glosa = sum(1 for v in validacoes if v.status_validacao_tcu == "VALIDADO_RISCO_GLOSA")
        dilig = sum(1 for v in validacoes if v.status_validacao_tcu == "REQUER_DILIGENCIA_PREVIA")

        parecer = (
            f"PARECER JURÍDICO CONCLUSIVO (INTEGRAÇÃO REFERENCIAL TCU): Dos {len(validacoes)} apontamentos submetidos à "
            f"matriz de validação jurídica frente à jurisprudência consolidada do Tribunal de Contas da União (TCU), "
            f"{risco_deb} configuram risco direto de débito/multa (violação frontal à Lei 4.320/64 ou Art. 125 da Lei 14.133/21), "
            f"{risco_glosa} configuram violação objetiva de publicidade/eficácia ou fracionamento (risco de glosa/sanção) e "
            f"{dilig} requerem diligência documental prévia para confirmar erro cadastral versus irregularidade material. "
            f"Há justa causa documental suficiente para protocolo imediato no TCE-MG e Notícia de Fato no MPMG."
        )

        log.info("Agente Jurídico emitiu parecer TCU (%d validações) e minutas TCE-MG / MPMG.", len(validacoes))
        return DossieJuridicoCompleto(
            entidade=self.rel.entidade,
            cnpj=self.rel.cnpj,
            exercicios=self.rel.exercicios,
            gerado_em=datetime.now().strftime("%d/%m/%Y %H:%M"),
            nota_competencia_tce_tcm_mg=nota_comp,
            parecer_juridico_conclusivo=parecer,
            validacoes_tcu=validacoes,
            minuta_tce_mg=self._build_minuta_tce_mg(validacoes),
            minuta_mpmg=self._build_minuta_mpmg(),
        )


def export_dossie_juridico(dossie: DossieJuridicoCompleto, out_dir: Path | None = None) -> dict[str, Path]:
    dest = out_dir or OUTPUT_DIR
    dest.mkdir(parents=True, exist_ok=True)

    json_path = dest / "dossie_juridico_tcu.json"
    json_path.write_text(json.dumps(dossie.model_dump(), ensure_ascii=False, indent=2), encoding="utf-8")

    tce_path = dest / "denuncia_tce_mg.md"
    tce_path.write_text(dossie.minuta_tce_mg, encoding="utf-8")

    mpmg_path = dest / "noticia_fato_mpmg.md"
    mpmg_path.write_text(dossie.minuta_mpmg, encoding="utf-8")

    # Parecer completo MD
    md_lines = [
        "# PARECER JURÍDICO COMPLETO E VALIDAÇÃO TCU",
        f"**Entidade:** {dossie.entidade} | **CNPJ:** `{dossie.cnpj}` | **Emissão:** {dossie.gerado_em}",
        "",
        f"> {dossie.nota_competencia_tce_tcm_mg}",
        "",
        f"## Conclusão do Parecer\n{dossie.parecer_juridico_conclusivo}",
        "",
        "## Matriz de Validação Jurídica (Referencial TCU × Apontamentos)",
        "| Código | Status Validação TCU | Tipificação | Repercussão |",
        "|---|---|---|---|",
    ]
    for v in dossie.validacoes_tcu:
        md_lines.append(f"| {v.codigo_apontamento} | `{v.status_validacao_tcu}` | {v.tipificacao_controle_externo} | {v.repercussao_juridica} |")
    md_lines.extend(["", "---", "## Minuta 1 — Representação TCE-MG", dossie.minuta_tce_mg, "---", "## Minuta 2 — Notícia de Fato MPMG", dossie.minuta_mpmg])
    parecer_md = dest / "parecer_juridico_tcu_palmopolis.md"
    parecer_md.write_text("\n".join(md_lines), encoding="utf-8")

    tpl = Template("""<!DOCTYPE html>
<html lang="pt-BR"><head><meta charset="utf-8"/>
<title>Dossiê Jurídico — {{ d.entidade }}</title>
<style>
  body { font-family: 'Segoe UI', Arial, sans-serif; margin: 0; background: #f4f6f9; color: #1a202c; }
  header { background: linear-gradient(135deg, #312e81, #1e1b4b); color: #fff; padding: 24px 32px; }
  main { max-width: 1180px; margin: 22px auto; padding: 0 20px 40px; }
  .box { background: #fff; border: 1px solid #e2e8f0; border-radius: 10px; padding: 18px; margin-bottom: 18px; }
  .note { background: #eff6ff; border-left: 5px solid #2563eb; padding: 12px 16px; border-radius: 6px; margin-bottom: 16px; }
  .conc { background: #fef2f2; border-left: 5px solid #b91c1c; padding: 12px 16px; border-radius: 6px; margin-bottom: 18px; }
  .badge { display: inline-block; padding: 2px 8px; border-radius: 999px; font-size: 11px; font-weight: 700; }
  .VALIDADO_RISCO_DEBITO_MULTA { background: #fee2e2; color: #b91c1c; }
  .VALIDADO_RISCO_GLOSA { background: #ffedd5; color: #c2410c; }
  .REQUER_DILIGENCIA_PREVIA { background: #dbeafe; color: #1d4ed8; }
  table { width: 100%; border-collapse: collapse; font-size: 12.5px; }
  th, td { border: 1px solid #e2e8f0; padding: 8px; text-align: left; vertical-align: top; }
  th { background: #f8fafc; color: #1e1b4b; }
  pre { white-space: pre-wrap; font-family: 'Segoe UI', Arial, sans-serif; font-size: 13px; line-height: 1.5; background: #f8fafc; padding: 14px; border-radius: 8px; border: 1px solid #e2e8f0; }
</style></head><body>
<header>
  <h1 style="margin:0 0 6px;font-size:21px;">Parecer Jurídico Completo, Matriz TCU e Minutas TCE-MG / MPMG</h1>
  <p style="margin:0;font-size:13px;opacity:.9;">{{ d.entidade }} | CNPJ {{ d.cnpj }} | {{ d.gerado_em }}</p>
</header>
<main>
  <div class="note"><strong>{{ d.nota_competencia_tce_tcm_mg }}</strong></div>
  <div class="conc"><strong>{{ d.parecer_juridico_conclusivo }}</strong></div>
  <div class="box">
    <h2 style="margin:0 0 10px;color:#1e1b4b;">Matriz de Validação Jurídica (Referencial TCU)</h2>
    <table>
      <thead><tr><th>Apont.</th><th>Status TCU</th><th>Entendimento TCU Aplicável</th><th>Tipificação</th><th>Repercussão</th></tr></thead>
      <tbody>
        {% for v in d.validacoes_tcu %}
        <tr>
          <td><strong>{{ v.codigo_apontamento }}</strong></td>
          <td><span class="badge {{ v.status_validacao_tcu }}">{{ v.status_validacao_tcu }}</span></td>
          <td>{{ v.entendimento_tcu_aplicavel }}</td>
          <td>{{ v.tipificacao_controle_externo }}</td>
          <td>{{ v.repercussao_juridica }}</td>
        </tr>
        {% endfor %}
      </tbody>
    </table>
  </div>
  <div class="box"><h2 style="margin:0 0 10px;color:#1e1b4b;">Minuta 1 — Representação ao TCE-MG</h2><pre>{{ d.minuta_tce_mg }}</pre></div>
  <div class="box"><h2 style="margin:0 0 10px;color:#1e1b4b;">Minuta 2 — Notícia de Fato ao MPMG</h2><pre>{{ d.minuta_mpmg }}</pre></div>
</main></body></html>""")
    html_path = dest / "dossie_juridico_completo.html"
    html_path.write_text(tpl.render(d=dossie), encoding="utf-8")
    return {
        "json": json_path,
        "tce_mg": tce_path,
        "mpmg": mpmg_path,
        "parecer_md": parecer_md,
        "html": html_path,
    }
