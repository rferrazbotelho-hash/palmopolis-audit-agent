"""Scraper do Portal Institucional da Prefeitura Municipal de Palmópolis/MG.

Coleta e audita a transparência ativa no portal institucional (Lei 12.527/2011 - LAI
e Art. 54 da Lei 14.133/2021):
- Links estruturantes da página inicial (e-SIC, Ouvidoria, Transparência, LRF, Compras);
- Categorias de Documentos Públicos (/publicacao, incluindo Licitações/diretorio/14,
  Decretos, Leis, Portarias);
- Edições do Diário Oficial Municipal (POST /diario/listarDiario/diario);
- Notícias institucionais recentes (/noticia);
- Verificação dos links LRF/Sigafi referenciados no portal.

Todos os payloads brutos são salvos em data/raw/portal/.
"""
from __future__ import annotations

import logging
import re
from typing import Any
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from config import save_raw, settings
from connectors.http_utils import build_client, request
from connectors.memory_lai_client import ExtractionStatus

log = logging.getLogger("portal.scraper")

PUBLICACAO_CATEGORIAS: dict[str, str] = {
    "licitacoes_portal": "publicacao/diretorio/14",
    "decretos": "publicacao/diretorio/7",
    "leis": "publicacao/diretorio/8",
    "portarias": "publicacao/documento/6",
    "leis_complementares": "publicacao/documento/9",
    "lei_organica": "publicacao/documento/10",
}


class PortalScraper:
    def __init__(self, base_url: str | None = None, raw_source: str = "portal") -> None:
        self.base_url = (base_url or settings.portal_url).rstrip("/") + "/"
        self.raw_source = raw_source
        self.statuses: list[ExtractionStatus] = []

    def _status(self, dataset: str, n: int, st: str, detalhe: str = "", raw: str = "") -> None:
        self.statuses.append(
            ExtractionStatus(
                fonte="Portal Institucional",
                dataset=dataset,
                exercicio=None,
                registros=n,
                status=st,
                detalhe=detalhe,
                arquivo_raw=raw,
            )
        )

    def _get_soup(self, client: Any, path: str) -> tuple[str, BeautifulSoup]:
        url = urljoin(self.base_url, path.lstrip("/"))
        resp = request(client, "GET", url, accept_status={200})
        return str(resp.url), BeautifulSoup(resp.text, "lxml")

    def scrape_home_links(self, client: Any) -> list[dict[str, Any]]:
        """Extrai e classifica links institucionais obrigatórios pela LAI na página inicial."""
        url, soup = self._get_soup(client, "")
        links: list[dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()
        for a in soup.find_all("a", href=True):
            href = urljoin(url, a["href"].strip())
            texto = " ".join(a.get_text(" ", strip=True).split())
            key = (texto, href)
            if key in seen or href.startswith("javascript:"):
                continue
            seen.add(key)
            cat = "outros"
            low = f"{texto} {href}".lower()
            if "esic" in low or "e-sic" in low:
                cat = "e-SIC"
            elif "ouvidoria" in low:
                cat = "Ouvidoria"
            elif "transparencia" in low or "transparência" in low or "ilai.memory" in low:
                cat = "Portal Transparência"
            elif "licitac" in low or "licitaç" in low or "compras" in low:
                cat = "Licitações e Compras"
            elif "diario" in low or "diário" in low:
                cat = "Diário Oficial"
            elif "lrf" in low or "loa" in low or "ldo" in low or "ppa" in low or "rreo" in low or "rgf" in low:
                cat = "Planejamento e LRF"
            elif "lgpd" in low or "privacidade" in low:
                cat = "LGPD"
            links.append({"texto": texto, "url": href, "categoria": cat})

        raw = save_raw(self.raw_source, "home_links", links, {"url": url})
        self._status("home_links", len(links), "OK" if links else "VAZIO", raw=str(raw))
        log.info("[Portal] Home links: %d capturados", len(links))
        return links

    def scrape_publicacoes(self, client: Any) -> list[dict[str, Any]]:
        """Extrai publicações e documentos oficiais disponíveis nas categorias do portal."""
        itens: list[dict[str, Any]] = []
        for cat_key, rel_path in PUBLICACAO_CATEGORIAS.items():
            try:
                url, soup = self._get_soup(client, rel_path)
                main = soup.find(id="conteudo-principal") or soup.body or soup
                texto_bloco = " ".join(main.get_text(" ", strip=True).split())
                vazio_msg = "nenhum exercício disponível" in texto_bloco.lower()
                doc_links: list[dict[str, str]] = []
                for a in main.find_all("a", href=True):
                    href = urljoin(url, a["href"].strip())
                    txt = " ".join(a.get_text(" ", strip=True).split())
                    if href.rstrip("/") in {self.base_url.rstrip("/"), urljoin(self.base_url, "publicacao").rstrip("/")}:
                        continue
                    if any(ext in href.lower() for ext in (".pdf", "/arquivo", "/documento/", "/diretorio/", "/download")) or re.search(r"/202[456]", href):
                        doc_links.append({"titulo": txt, "url": href})
                itens.append({
                    "categoria": cat_key,
                    "url": url,
                    "vazio_declarado": vazio_msg,
                    "qtd_documentos": len(doc_links),
                    "documentos": doc_links,
                    "resumo_pagina": texto_bloco[:500],
                })
                log.info("[Portal] Categoria %-18s: %d docs (vazio=%s)", cat_key, len(doc_links), vazio_msg)
            except Exception as exc:
                log.warning("[Portal] Erro em %s: %s", cat_key, exc)
                itens.append({"categoria": cat_key, "url": rel_path, "erro": str(exc)})

        raw = save_raw(self.raw_source, "publicacoes", itens, {"categorias": list(PUBLICACAO_CATEGORIAS.keys())})
        total_docs = sum(int(i.get("qtd_documentos", 0)) for i in itens)
        self._status("publicacoes", total_docs, "OK" if total_docs else "VAZIO",
                     detalhe=f"{len(itens)} categorias inspecionadas", raw=str(raw))
        return itens

    def scrape_diario_oficial(self, client: Any) -> list[dict[str, Any]]:
        """Consulta a API interna do Diário Oficial do município."""
        url = urljoin(self.base_url, "diario/listarDiario/diario")
        edicoes: list[dict[str, Any]] = []
        try:
            resp = request(client, "POST", url, accept_status={200})
            data = resp.json() if resp.content else []
            if isinstance(data, list):
                for item in data:
                    pasta = item.get("pasta") or ""
                    arq = item.get("arquivo") or ""
                    edicoes.append({
                        "id": item.get("id"),
                        "numero_edicao": item.get("numero_edicao"),
                        "tipo_edicao": item.get("tpEdicao"),
                        "data": item.get("data"),
                        "url_pdf": urljoin(self.base_url, f"diario/arquivo/?f={pasta}{arq}") if arq else "",
                    })
            raw = save_raw(self.raw_source, "diario_oficial", edicoes, {"endpoint": url, "raw_count": len(data) if isinstance(data, list) else 0})
            self._status("diario_oficial", len(edicoes), "OK" if edicoes else "VAZIO", raw=str(raw))
            log.info("[Portal] Diário Oficial: %d edições", len(edicoes))
        except Exception as exc:
            log.warning("[Portal] Falha ao consultar Diário Oficial: %s", exc)
            save_raw(self.raw_source, "diario_oficial_ERRO", {"erro": str(exc)}, {"endpoint": url})
            self._status("diario_oficial", 0, "ERRO", str(exc)[:300])
        return edicoes

    def scrape_noticias(self, client: Any, max_pages: int = 3) -> list[dict[str, Any]]:
        """Coleta notícias recentes no portal institucional (contexto de atos e transparência)."""
        noticias: list[dict[str, Any]] = []
        seen: set[str] = set()
        for pg in range(1, max_pages + 1):
            path = "noticia" if pg == 1 else f"noticia?page={pg}"
            try:
                url, soup = self._get_soup(client, path)
                found_in_page = 0
                for a in soup.find_all("a", href=True):
                    href = urljoin(url, a["href"].strip())
                    if "/noticia/detalhe/" not in href or href in seen:
                        continue
                    seen.add(href)
                    txt = " ".join(a.get_text(" ", strip=True).split())
                    if not txt:
                        continue
                    m_dt = re.match(r"^(\d{2}/\d{2}/\d{4})\s*(.*)$", txt)
                    dt_pub, titulo = (m_dt.group(1), m_dt.group(2)) if m_dt else ("", txt)
                    noticias.append({"data": dt_pub, "titulo": titulo, "url": href})
                    found_in_page += 1
                if found_in_page == 0:
                    break
            except Exception as exc:
                log.warning("[Portal] Erro em notícias pág %d: %s", pg, exc)
                break

        raw = save_raw(self.raw_source, "noticias", noticias, {"paginas_lidas": max_pages})
        self._status("noticias", len(noticias), "OK" if noticias else "VAZIO", raw=str(raw))
        log.info("[Portal] Notícias coletadas: %d", len(noticias))
        return noticias

    def extract_all(self) -> dict[str, list[dict[str, Any]]]:
        """Executa toda a coleta do portal institucional."""
        out: dict[str, list[dict[str, Any]]] = {
            "home_links": [],
            "publicacoes": [],
            "diario_oficial": [],
            "noticias": [],
        }
        try:
            with build_client() as client:
                out["home_links"] = self.scrape_home_links(client)
                out["publicacoes"] = self.scrape_publicacoes(client)
                out["diario_oficial"] = self.scrape_diario_oficial(client)
                out["noticias"] = self.scrape_noticias(client)
        except Exception as exc:
            log.error("[Portal] Erro geral no scraper: %s", exc)
            self._status("portal_geral", 0, "ERRO", str(exc)[:300])
        return out
