"""Generic HTTP client for dados.cvm.gov.br — download with local disk cache.

Verified URL pattern (see docs/DATA_SOURCES.md): a single zip per competencia
month works uniformly across the entire history tested (2024-06 .. 2026-05),
containing cda_fi_BLC_1..8, cda_fi_PL, and (for recent months only) cda_fi_CONFID.
"""
from __future__ import annotations

import logging
from pathlib import Path
from zipfile import ZipFile

import requests

from app.config import settings

logger = logging.getLogger(__name__)

CDA_URL_TEMPLATE = f"{settings.cvm_base_url}/FI/DOC/CDA/DADOS/cda_fi_{{yyyymm}}.zip"

# CDA also has an annual HIST/ bundle (verified 11/jul/2026 against the real
# directory listing): one zip per YEAR for 2005-2022, each containing a single
# BLC_4_{year}.csv / PL_{year}.csv with all 12 months inside (DT_COMPTC varies
# per row) — same column layout otherwise. 2023 onward is monthly-only (the
# DADOS/ pattern above). Column names differ pre-cutover: CNPJ_FUNDO/TP_FUNDO
# instead of CNPJ_FUNDO_CLASSE/TP_FUNDO_CLASSE (Resolucao CVM 175 renamed
# them sometime between 2023-01 and 2024-06) — cda_ingestion.py normalizes
# this per-file by sniffing the header, not by year.
CDA_HIST_URL_TEMPLATE = f"{settings.cvm_base_url}/FI/DOC/CDA/DADOS/HIST/cda_fi_{{yyyy}}.zip"
CDA_HIST_FIRST_YEAR = 2005
CDA_HIST_LAST_YEAR = 2022  # last year still delivered as an annual HIST zip

# Informe Diario has two coexisting locations (verified against real listings,
# see docs/DATA_SOURCES.md): HIST/ has one zip per YEAR for 2000-2020 (each
# containing 12 monthly CSVs inside), DADOS/ has one zip per MONTH for 2021+.
# Together they're gapless from 2000 to the current month.
INF_DIARIO_HIST_URL_TEMPLATE = f"{settings.cvm_base_url}/FI/DOC/INF_DIARIO/DADOS/HIST/inf_diario_fi_{{yyyy}}.zip"
INF_DIARIO_RECENT_URL_TEMPLATE = f"{settings.cvm_base_url}/FI/DOC/INF_DIARIO/DADOS/inf_diario_fi_{{yyyymm}}.zip"
INF_DIARIO_HIST_LAST_YEAR = 2020  # last year still delivered as an annual HIST zip

# The last N months are revised by the CVM as fund administrators submit
# late/corrected filings — always re-download these, never trust the cache.
RECENT_MONTHS_ALWAYS_REFRESH = 3

# Programa de Recompra de Acoes — single always-current zip (not partitioned
# by month), refreshed daily by the CVM (verified against dados.cvm.gov.br/
# dataset/cia_aberta-eventos-recompra_acoes on 2026-07-10).
RECOMPRA_URL = f"{settings.cvm_base_url}/CIA_ABERTA/EVENTOS/RECOMPRA_ACOES/DADOS/cia_aberta_recompra_acoes.zip"

# Valores Mobiliarios Negociados e Detidos (VLMO) — negociacao de
# administradores/conselheiros/controladores com valores mobiliarios da
# propria companhia. Um zip POR ANO (2021-presente), cada um contendo
# vlmo_cia_aberta_{year}.csv (indice de documentos) e
# vlmo_cia_aberta_con_{year}.csv (movimentacoes consolidadas — o que
# realmente usamos). Verificado 10/jul/2026: dataset cia_aberta-doc-vlmo.
VLMO_URL_TEMPLATE = f"{settings.cvm_base_url}/CIA_ABERTA/DOC/VLMO/DADOS/vlmo_cia_aberta_{{year}}.zip"
VLMO_FIRST_YEAR = 2021

# Formulario Cadastral (FCA) — usamos so a secao "valor_mobiliario" (Codigo_
# Negociacao = ticker B3, ligado ao CNPJ_Companhia). E o unico jeito de ligar
# ticker (ex: PRIO3) a CNPJ, que e a chave usada em recompra/VLMO. Zip por
# ano, atualizado semanalmente pela CVM. Verificado 10/jul/2026: RDOR3 ->
# CNPJ 06.047.087/0001-39, bate com o CNPJ ja usado em company_buybacks.
FCA_URL_TEMPLATE = f"{settings.cvm_base_url}/CIA_ABERTA/DOC/FCA/DADOS/fca_cia_aberta_{{year}}.zip"
FCA_FIRST_YEAR = 2021


def cda_zip_path(yyyymm: str) -> Path:
    return Path(settings.data_cache_dir) / "cda" / yyyymm / f"cda_fi_{yyyymm}.zip"


def download_cda_zip(yyyymm: str, force: bool = False) -> Path:
    """Download (or reuse cached) CDA zip for a given competencia month."""
    dest = cda_zip_path(yyyymm)
    dest.parent.mkdir(parents=True, exist_ok=True)

    if dest.exists() and not force:
        logger.info("cda %s: usando cache local (%s)", yyyymm, dest)
        return dest

    url = CDA_URL_TEMPLATE.format(yyyymm=yyyymm)
    logger.info("cda %s: baixando %s", yyyymm, url)
    resp = requests.get(url, timeout=120)
    resp.raise_for_status()
    dest.write_bytes(resp.content)
    return dest


def cda_hist_zip_path(yyyy: int) -> Path:
    return Path(settings.data_cache_dir) / "cda_hist" / f"cda_fi_{yyyy}.zip"


def download_cda_hist_zip(yyyy: int, force: bool = False) -> Path:
    """Download (or reuse cached) annual CDA zip, 2005-2022 only. Closed years
    never get revised by the CVM, so the cache is trustworthy forever —
    force=True is only useful for re-downloading a corrupted/partial file."""
    dest = cda_hist_zip_path(yyyy)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and not force:
        logger.info("cda_hist %d: usando cache local (%s)", yyyy, dest)
        return dest
    url = CDA_HIST_URL_TEMPLATE.format(yyyy=yyyy)
    logger.info("cda_hist %d: baixando %s", yyyy, url)
    resp = requests.get(url, timeout=300)
    resp.raise_for_status()
    dest.write_bytes(resp.content)
    return dest


def inf_diario_hist_zip_path(yyyy: str) -> Path:
    return Path(settings.data_cache_dir) / "inf_diario" / "hist" / f"inf_diario_fi_{yyyy}.zip"


def inf_diario_recent_zip_path(yyyymm: str) -> Path:
    return Path(settings.data_cache_dir) / "inf_diario" / "recent" / f"inf_diario_fi_{yyyymm}.zip"


def download_inf_diario_year(yyyy: str, force: bool = False) -> Path:
    """Download (or reuse cached) annual Informe Diario zip, 2000-2020 only."""
    dest = inf_diario_hist_zip_path(yyyy)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and not force:
        logger.info("inf_diario %s: usando cache local (%s)", yyyy, dest)
        return dest
    url = INF_DIARIO_HIST_URL_TEMPLATE.format(yyyy=yyyy)
    logger.info("inf_diario %s: baixando %s", yyyy, url)
    resp = requests.get(url, timeout=180)
    resp.raise_for_status()
    dest.write_bytes(resp.content)
    return dest


def download_inf_diario_month(yyyymm: str, force: bool = False) -> Path:
    """Download (or reuse cached) monthly Informe Diario zip, 2021-present."""
    dest = inf_diario_recent_zip_path(yyyymm)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and not force:
        logger.info("inf_diario %s: usando cache local (%s)", yyyymm, dest)
        return dest
    url = INF_DIARIO_RECENT_URL_TEMPLATE.format(yyyymm=yyyymm)
    logger.info("inf_diario %s: baixando %s", yyyymm, url)
    resp = requests.get(url, timeout=180)
    resp.raise_for_status()
    dest.write_bytes(resp.content)
    return dest


def recompra_zip_path() -> Path:
    return Path(settings.data_cache_dir) / "recompra" / "cia_aberta_recompra_acoes.zip"


def download_recompra_zip(force: bool = False) -> Path:
    """Download (or reuse cached) buyback-programs zip. Unlike CDA/Informe
    Diario there's no competencia month to key on — always force=True from
    the scheduler since the CVM republishes this file daily in place."""
    dest = recompra_zip_path()
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and not force:
        logger.info("recompra: usando cache local (%s)", dest)
        return dest
    logger.info("recompra: baixando %s", RECOMPRA_URL)
    resp = requests.get(RECOMPRA_URL, timeout=120)
    resp.raise_for_status()
    dest.write_bytes(resp.content)
    return dest


def vlmo_zip_path(year: int) -> Path:
    return Path(settings.data_cache_dir) / "vlmo" / f"vlmo_cia_aberta_{year}.zip"


def download_vlmo_zip(year: int, force: bool = False) -> Path:
    """Download (or reuse cached) VLMO zip for one year. The current year's
    file is republished as filings roll in — callers should force=True for
    the current year and can trust the cache for closed past years."""
    dest = vlmo_zip_path(year)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and not force:
        logger.info("vlmo %d: usando cache local (%s)", year, dest)
        return dest
    url = VLMO_URL_TEMPLATE.format(year=year)
    logger.info("vlmo %d: baixando %s", year, url)
    resp = requests.get(url, timeout=180)
    resp.raise_for_status()
    dest.write_bytes(resp.content)
    return dest


def fca_zip_path(year: int) -> Path:
    return Path(settings.data_cache_dir) / "fca" / f"fca_cia_aberta_{year}.zip"


def download_fca_zip(year: int, force: bool = False) -> Path:
    """Download (or reuse cached) FCA zip for one year."""
    dest = fca_zip_path(year)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and not force:
        logger.info("fca %d: usando cache local (%s)", year, dest)
        return dest
    url = FCA_URL_TEMPLATE.format(year=year)
    logger.info("fca %d: baixando %s", year, url)
    resp = requests.get(url, timeout=180)
    resp.raise_for_status()
    dest.write_bytes(resp.content)
    return dest


def extract_member(zip_path: Path, member_suffix: str) -> bytes | None:
    """Extract a single member from the zip by filename suffix match
    (e.g. 'BLC_4_202605.csv' or 'PL_202605.csv'). Returns None if absent —
    CONFID files legitimately don't exist for months whose confidentiality
    window has already expired."""
    with ZipFile(zip_path) as zf:
        matches = [n for n in zf.namelist() if n.endswith(member_suffix)]
        if not matches:
            return None
        return zf.read(matches[0])
