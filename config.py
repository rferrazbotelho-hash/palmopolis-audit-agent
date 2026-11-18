"""Configuração central do Sistema de Auditoria Municipal - Palmópolis/MG."""
from __future__ import annotations

import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parent
DATA_DIR = ROOT_DIR / "data"
RAW_DIR = DATA_DIR / "raw"
OUTPUT_DIR = DATA_DIR / "output"
LOG_DIR = DATA_DIR / "logs"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT_DIR / ".env", env_file_encoding="utf-8", extra="ignore")

    audit_cnpj: str = "66234345000118"
    audit_entidade_nome: str = "Prefeitura Municipal de Palmópolis/MG"
    audit_codigo_ibge: str = "3146750"
    audit_exercicios: list[int] = Field(default_factory=lambda: [2025, 2026])

    memory_login_url: str = "https://ilai.memory.com.br/#/entidades/login/9C33PP/1/"
    memory_cod_cliente: str = "9C33PP"
    memory_unidade: str = "1"
    memory_base_url: str = "https://ilai.memory.com.br"
    memory_use_playwright: bool = True
    memory_page_size: int = 500

    pncp_base_url: str = "https://pncp.gov.br/api"
    pncp_page_size: int = 50
    pncp_fetch_itens: bool = True

    portal_url: str = "https://www.palmopolis.mg.gov.br/"

    cgu_api_key: str = ""

    http_timeout: float = 90.0
    http_max_retries: int = 6
    log_level: str = "INFO"


settings = Settings()

# Limites de dispensa por valor - Art. 75, I e II, Lei 14.133/2021 (atualizados pelo art. 182)
# 2025: Decreto nº 12.343/2024 | 2026: Decreto nº 12.807/2025
LIMITES_DISPENSA: dict[int, dict[str, float]] = {
    2025: {"inciso_I": 125_451.15, "inciso_II": 62_725.59, "decreto": "Decreto nº 12.343/2024"},  # type: ignore[dict-item]
    2026: {"inciso_I": 130_984.20, "inciso_II": 65_492.11, "decreto": "Decreto nº 12.807/2025"},  # type: ignore[dict-item]
}

# Prazos de divulgação no PNCP - Art. 94, Lei 14.133/2021 (dias úteis após assinatura)
PRAZO_PNCP_LICITACAO_DU = 20
PRAZO_PNCP_CONTRATACAO_DIRETA_DU = 10

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/130.0 Safari/537.36 PalmopolisAuditAgent/1.0"
)

RUN_ID = datetime.now().strftime("%Y%m%d_%H%M%S")


def ensure_dirs() -> None:
    for d in (RAW_DIR, OUTPUT_DIR, LOG_DIR):
        d.mkdir(parents=True, exist_ok=True)


def setup_logging(level: str | None = None) -> logging.Logger:
    ensure_dirs()
    lvl = getattr(logging, (level or settings.log_level).upper(), logging.INFO)
    fmt = logging.Formatter("%(asctime)s | %(levelname)-7s | %(name)-22s | %(message)s", "%Y-%m-%d %H:%M:%S")
    root = logging.getLogger()
    root.setLevel(lvl)
    root.handlers.clear()
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    try:
        sh.stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass
    fh = logging.FileHandler(LOG_DIR / f"audit_{RUN_ID}.log", encoding="utf-8")
    fh.setFormatter(fmt)
    root.addHandler(sh)
    root.addHandler(fh)
    for noisy in ("httpx", "httpcore", "asyncio"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    return logging.getLogger("audit")


def save_raw(source: str, name: str, payload: Any, meta: dict[str, Any] | None = None) -> Path:
    """Persiste o payload JSON bruto em data/raw/<source>/ para rastreabilidade de auditoria."""
    folder = RAW_DIR / source
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{name}.json"
    envelope = {
        "_audit_meta": {
            "source": source,
            "dataset": name,
            "collected_at": datetime.now().isoformat(timespec="seconds"),
            "run_id": RUN_ID,
            **(meta or {}),
        },
        "payload": payload,
    }
    path.write_text(json.dumps(envelope, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    return path


def load_raw(source: str, name: str) -> Any | None:
    path = RAW_DIR / source / f"{name}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8")).get("payload")
