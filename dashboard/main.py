"""
Intermarket Dashboard — Backend
Séries: IBOVESPA · 6L COT Asset Manager · NTN-B 2035 PU · Fluxo Estrangeiro
"""
import io
import os
import sqlite3
import zipfile
import logging
from datetime import date, datetime
from decimal import InvalidOperation
from typing import Optional

import pandas as pd
import requests
import yfinance as yf
from apscheduler.schedulers.background import BackgroundScheduler
from bs4 import BeautifulSoup
from curl_cffi import requests as cf_requests
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse

# ── Config ────────────────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "intermarket.db")
INDEX_PATH = os.path.join(BASE_DIR, "index.html")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

CFTC_BASE = "https://www.cftc.gov/files/dea/history"
CFTC_WEEKLY = "https://www.cftc.gov/dea/newcot/FinFutWk.txt"
CFTC_HIST_BUNDLE = f"{CFTC_BASE}/fin_fut_txt_2006_2016.zip"
NTNB_CSV = (
    "https://www.tesourotransparente.gov.br/ckan/dataset/"
    "df56aa42-484a-4a59-8184-7676580c81e3/resource/"
    "796d2059-14e9-44e3-80c9-2d9e30b405c1/download/precotaxatesourodireto.csv"
)

# ── Database ──────────────────────────────────────────────────────────────────
def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS ibov_daily (
            date TEXT PRIMARY KEY,
            close REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS cot_6l (
            report_date TEXT PRIMARY KEY,
            asset_mgr_long INTEGER NOT NULL,
            asset_mgr_short INTEGER NOT NULL,
            asset_mgr_net INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS ntnb35_pu (
            date TEXT PRIMARY KEY,
            pu REAL NOT NULL,
            yield_pct REAL
        );
        CREATE TABLE IF NOT EXISTS foreign_flow (
            date TEXT PRIMARY KEY,
            daily_flow_mm REAL,
            ytd_flow_mm REAL
        );
        CREATE TABLE IF NOT EXISTS di_rates (
            date TEXT PRIMARY KEY,
            di2033 REAL,
            di2034 REAL,
            di2035 REAL
        );
        CREATE TABLE IF NOT EXISTS br_indices (
            date TEXT PRIMARY KEY,
            iblv  REAL,
            ibhb  REAL,
            idiv  REAL,
            ifnc  REAL,
            util  REAL,
            usdbrl REAL
        );
        CREATE TABLE IF NOT EXISTS macro_indicators (
            date TEXT PRIMARY KEY,
            dxy REAL,
            us10y REAL,
            bcom REAL,
            us_cpi_yoy REAL
        );
    """)
    # Add smal11 column if it doesn't exist (migration for existing DBs)
    try:
        conn.execute("ALTER TABLE br_indices ADD COLUMN smal11 REAL")
        conn.commit()
    except Exception:
        pass
    conn.commit()
    conn.close()


BR_INDICES_TICKERS = {
    "iblv":  "BLVB11.SA",   # ETF Low Vol (tracks IBLV)
    "ibhb":  "BHYB11.SA",   # ETF High Beta (tracks IBHB)
    "idiv":  "DIVO11.SA",   # ETF Dividendos (tracks IDIV)
    "smal11": "SMAL11.SA",  # ETF Small Cap
    "usdbrl": "USDBRL=X",
}


def db_count(table: str) -> int:
    conn = get_conn()
    n = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    conn.close()
    return n


def rows_to_list(rows) -> list:
    return [{"date": r[0], "value": r[1]} for r in rows]


# ── Collector: IBOVESPA ───────────────────────────────────────────────────────
def collect_ibov(start: str = "2016-01-01") -> dict:
    log.info("IBOVESPA: downloading from Yahoo Finance...")
    try:
        df = yf.download("^BVSP", start=start, auto_adjust=True, progress=False)
        if df.empty:
            return {"status": "error", "message": "empty response", "rows": 0}
        conn = get_conn()
        n = 0
        for idx, row in df.iterrows():
            d = idx.date().isoformat() if hasattr(idx, "date") else str(idx)[:10]
            close_val = row["Close"]
            if hasattr(close_val, "__len__"):
                close_val = float(close_val.iloc[0])
            else:
                close_val = float(close_val)
            conn.execute(
                "INSERT OR REPLACE INTO ibov_daily (date, close) VALUES (?, ?)",
                (d, round(close_val, 2)),
            )
            n += 1
        conn.commit()
        conn.close()
        log.info(f"IBOVESPA: {n} rows")
        return {"status": "ok", "rows": n}
    except Exception as e:
        log.error(f"IBOVESPA: {e}")
        return {"status": "error", "message": str(e), "rows": 0}


# ── Collector: COT 6L (Asset Manager Net) ────────────────────────────────────
def _parse_tff_df(df: pd.DataFrame) -> pd.DataFrame:
    """Extract BRL (102741) Asset Manager positions from a TFF DataFrame (with headers)."""
    code_col = next(
        (c for c in df.columns if "contract_market_code" in c.lower()), None
    )
    if not code_col:
        log.warning(f"COT: no contract code column. cols={list(df.columns[:6])}")
        return pd.DataFrame()

    brl = df[df[code_col].astype(str).str.strip() == "102741"].copy()
    if brl.empty:
        return pd.DataFrame()

    date_col = next(
        (c for c in brl.columns if "date" in c.lower() and "yyyy" in c.lower()),
        next((c for c in brl.columns if "report_date" in c.lower()), None),
    )
    long_col = next(
        (c for c in brl.columns if "asset_mgr" in c.lower() and "long" in c.lower()), None
    )
    short_col = next(
        (c for c in brl.columns if "asset_mgr" in c.lower() and "short" in c.lower()), None
    )

    if not all([date_col, long_col, short_col]):
        log.warning(f"COT: missing cols date={date_col} long={long_col} short={short_col}")
        return pd.DataFrame()

    out = brl[[date_col, long_col, short_col]].copy()
    out.columns = ["report_date", "asset_mgr_long", "asset_mgr_short"]
    out["asset_mgr_long"] = pd.to_numeric(out["asset_mgr_long"], errors="coerce").fillna(0).astype(int)
    out["asset_mgr_short"] = pd.to_numeric(out["asset_mgr_short"], errors="coerce").fillna(0).astype(int)
    out["asset_mgr_net"] = out["asset_mgr_long"] - out["asset_mgr_short"]
    # Normalize date: both "YYYY-MM-DD" and "M/D/YYYY h:mm:ss AM" formats
    out["report_date"] = pd.to_datetime(out["report_date"], errors="coerce").dt.date.astype(str)
    out = out[out["report_date"] != "NaT"].dropna(subset=["report_date"])
    return out


def _upsert_cot(df: pd.DataFrame, conn: sqlite3.Connection) -> int:
    n = 0
    for _, row in df.iterrows():
        conn.execute(
            """INSERT OR REPLACE INTO cot_6l
               (report_date, asset_mgr_long, asset_mgr_short, asset_mgr_net)
               VALUES (?, ?, ?, ?)""",
            (row["report_date"], int(row["asset_mgr_long"]),
             int(row["asset_mgr_short"]), int(row["asset_mgr_net"])),
        )
        n += 1
    return n


def _load_zip_tff(url: str) -> pd.DataFrame:
    """Download a CFTC TFF ZIP and return parsed DataFrame."""
    r = cf_requests.get(url, impersonate="chrome", timeout=120)
    r.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        txt = next((f for f in z.namelist() if f.lower().endswith(".txt")), None)
        if not txt:
            return pd.DataFrame()
        raw = z.read(txt).decode("latin-1")
    return pd.read_csv(io.StringIO(raw), low_memory=False)


def collect_cot(full: bool = False) -> dict:
    """
    Download CFTC Traders in Financial Futures (TFF) data for BRL (6L, code 102741).

    Modo incremental (padrão — rápido, ~5s):
      Só baixa o ano corrente + semana atual. Usado em atualizações manuais/scheduled.

    Modo full (full=True — lento, vários minutos):
      Baixa o bundle 2006-2016 + todos os anuais desde 2017. Usado apenas na primeira
      carga ou para reconstruir o banco do zero.
    """
    log.info("COT 6L: iniciando coleta (full=%s)...", full)
    conn = get_conn()
    total = 0
    errors = []
    current_year = datetime.now().year

    # Detecta se banco já tem dados para decidir o modo
    last_date_row = conn.execute("SELECT MAX(report_date) FROM cot_6l").fetchone()
    has_data = last_date_row and last_date_row[0] is not None

    if full or not has_data:
        # ── Modo full: histórico completo ─────────────────────────────────────
        log.info("COT: modo full — baixando histórico completo")

        try:
            log.info("COT: baixando bundle 2006-2016")
            df = _load_zip_tff(CFTC_HIST_BUNDLE)
            parsed = _parse_tff_df(df)
            n = _upsert_cot(parsed, conn)
            conn.commit()
            total += n
            log.info(f"COT 2006-2016: {n} rows")
        except Exception as e:
            errors.append(f"hist-bundle: {e}")
            log.warning(f"COT 2006-2016 bundle: {e}")

        for year in range(2017, current_year + 1):
            url = f"{CFTC_BASE}/fut_fin_txt_{year}.zip"
            try:
                log.info(f"COT: baixando {year}")
                df = _load_zip_tff(url)
                parsed = _parse_tff_df(df)
                n = _upsert_cot(parsed, conn)
                conn.commit()
                total += n
                log.info(f"COT {year}: {n} rows")
            except Exception as e:
                errors.append(f"{year}: {e}")
                log.warning(f"COT {year}: {e}")
    else:
        # ── Modo incremental: apenas ano corrente ─────────────────────────────
        log.info("COT: modo incremental — baixando apenas %d", current_year)
        url = f"{CFTC_BASE}/fut_fin_txt_{current_year}.zip"
        try:
            df = _load_zip_tff(url)
            parsed = _parse_tff_df(df)
            n = _upsert_cot(parsed, conn)
            conn.commit()
            total += n
            log.info(f"COT {current_year}: {n} rows")
        except Exception as e:
            errors.append(f"{current_year}: {e}")
            log.warning(f"COT {current_year}: {e}")

    # ── Semana atual (sempre — tem o último release disponível) ───────────────
    try:
        log.info("COT: buscando semana atual FinFutWk.txt")
        r = cf_requests.get(CFTC_WEEKLY, impersonate="chrome", timeout=30)
        r.raise_for_status()
        df_wk = pd.read_csv(io.StringIO(r.text), header=None, low_memory=False)
        brl_wk = df_wk[df_wk[0].astype(str).str.contains("BRAZILIAN", na=False, case=False)]
        n_wk = 0
        for _, row in brl_wk.iterrows():
            try:
                d = str(row[2]).strip()
                lng = int(str(row[11]).strip())
                sht = int(str(row[12]).strip())
                conn.execute(
                    """INSERT OR REPLACE INTO cot_6l
                       (report_date, asset_mgr_long, asset_mgr_short, asset_mgr_net)
                       VALUES (?, ?, ?, ?)""",
                    (d, lng, sht, lng - sht),
                )
                n_wk += 1
            except Exception:
                continue
        conn.commit()
        total += n_wk
        log.info(f"COT semana atual: {n_wk} rows")
    except Exception as e:
        errors.append(f"weekly: {e}")
        log.warning(f"COT weekly: {e}")

    conn.close()
    log.info(f"COT total: {total} rows (full={full})")
    return {"status": "ok" if not errors else "partial", "rows": total, "errors": errors}


# ── Collector: NTN-B 2035 PU ─────────────────────────────────────────────────
def _br_float(s: str) -> Optional[float]:
    """Parse Brazilian number: '1.234,56' → 1234.56"""
    try:
        return float(str(s).strip().replace(".", "").replace(",", "."))
    except Exception:
        return None


def collect_ntnb35() -> dict:
    """
    Download NTN-B 2035 PU from Tesouro Transparente official CSV.
    Dataset: 'Taxas dos Títulos Ofertados pelo Tesouro Direto'
    URL: precotaxatesourodireto.csv
    Filter: Tipo Titulo contains 'IPCA' (NTN-B Principal = sem juros semestrais)
            AND Data Vencimento contains '2035'
            AND NOT 'Juros Semestrais' (that is NTN-B com cupom)
    PU used: 'PU Venda Manha' (price investors pay = market reference)
    """
    log.info("NTN-B 2035: downloading from Tesouro Transparente...")
    try:
        r = cf_requests.get(NTNB_CSV, impersonate="chrome", timeout=120)
        r.raise_for_status()
        log.info(f"NTN-B CSV: {len(r.content)} bytes received")
    except Exception as e:
        log.error(f"NTN-B download: {e}")
        return {"status": "error", "message": str(e), "rows": 0}

    try:
        df = pd.read_csv(io.StringIO(r.content.decode("utf-8")), sep=";", low_memory=False)
    except Exception as e:
        log.error(f"NTN-B CSV parse: {e}")
        return {"status": "error", "message": str(e), "rows": 0}

    # Filter: NTN-B Principal 2035 (sem cupom = "Tesouro IPCA+" without "Juros Semestrais")
    tipo = df["Tipo Titulo"].astype(str)
    venc = df["Data Vencimento"].astype(str)

    mask = (
        (tipo.str.contains("IPCA", case=False, na=False) | tipo.str.contains("NTN-B", case=False, na=False))
        & venc.str.contains("2035", na=False)
        & ~tipo.str.contains("Juros Semestrais", case=False, na=False)
    )
    filtered = df[mask].copy()
    log.info(f"NTN-B 2035 rows matched: {len(filtered)}")

    if filtered.empty:
        log.warning(f"NTN-B: no rows matched. Unique 'Tipo Titulo': {df['Tipo Titulo'].unique()[:10]}")
        log.warning(f"NTN-B: Unique 'Data Vencimento' with IPCA: {df[tipo.str.contains('IPCA', case=False, na=False)]['Data Vencimento'].unique()[:20]}")
        return {"status": "error", "message": "no NTN-B Principal 2035 rows found", "rows": 0}

    conn = get_conn()
    n = 0
    for _, row in filtered.iterrows():
        try:
            d = pd.to_datetime(row["Data Base"], dayfirst=True, errors="coerce")
            if pd.isna(d):
                continue
            pu = _br_float(row["PU Venda Manha"])
            if not pu or pu <= 0:
                continue
            taxa = _br_float(row["Taxa Venda Manha"])
            conn.execute(
                "INSERT OR REPLACE INTO ntnb35_pu (date, pu, yield_pct) VALUES (?, ?, ?)",
                (d.date().isoformat(), pu, taxa),
            )
            n += 1
        except Exception:
            continue

    conn.commit()
    conn.close()
    log.info(f"NTN-B 2035: {n} rows upserted")
    return {"status": "ok", "rows": n}


# ── Collector: Taxas DI (proxy NTN-F / Tesouro Prefixado c/ Juros Semestrais) ─
def collect_di_rates() -> dict:
    """
    Baixa o mesmo CSV do Tesouro Direto e extrai:
    - di2033: taxa do Tesouro Prefixado c/ Juros Semestrais venc. 01/01/2033
    - di2035: taxa do Tesouro Prefixado c/ Juros Semestrais venc. 01/01/2035
    - di2034: interpolação linear entre di2033 e di2035 (só quando ambos existem)
    """
    log.info("DI Rates: downloading Tesouro CSV...")
    try:
        r = cf_requests.get(NTNB_CSV, impersonate="chrome", timeout=120)
        r.raise_for_status()
    except Exception as e:
        log.error(f"DI Rates download: {e}")
        return {"status": "error", "message": str(e), "rows": 0}

    try:
        df = pd.read_csv(io.StringIO(r.content.decode("utf-8")), sep=";", low_memory=False)
    except Exception:
        try:
            df = pd.read_csv(io.StringIO(r.content.decode("latin-1")), sep=";", low_memory=False)
        except Exception as e:
            return {"status": "error", "message": str(e), "rows": 0}

    tipo = df["Tipo Titulo"].astype(str)
    pref = df[tipo.str.contains("Prefixado", case=False, na=False)].copy()

    def _extract(venc_year: str) -> dict:
        sub = pref[pref["Data Vencimento"].astype(str).str.contains(venc_year, na=False)]
        out: dict = {}
        for _, row in sub.iterrows():
            try:
                d = pd.to_datetime(row["Data Base"], dayfirst=True, errors="coerce")
                if pd.isna(d):
                    continue
                taxa = _br_float(row["Taxa Venda Manha"])
                if taxa is None or taxa <= 0:
                    continue
                out[d.date().isoformat()] = taxa
            except Exception:
                continue
        return out

    rates33 = _extract("2033")
    rates35 = _extract("2035")
    log.info(f"DI Rates: 2033={len(rates33)} pts, 2035={len(rates35)} pts")

    all_dates = sorted(set(rates33) | set(rates35))
    conn = get_conn()
    n = 0
    for dt in all_dates:
        r33 = rates33.get(dt)
        r35 = rates35.get(dt)
        r34 = (r33 + r35) / 2 if (r33 is not None and r35 is not None) else None
        conn.execute(
            "INSERT OR REPLACE INTO di_rates (date, di2033, di2034, di2035) VALUES (?, ?, ?, ?)",
            (dt, r33, r34, r35),
        )
        n += 1
    conn.commit()
    conn.close()
    log.info(f"DI Rates: {n} rows upserted")
    return {"status": "ok", "rows": n}


# ── Collector: Fluxo Estrangeiro ──────────────────────────────────────────────
def _parse_date_str(text: str) -> Optional[str]:
    t = text.strip()
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(t, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def _parse_number(text: str) -> Optional[float]:
    if not text:
        return None
    t = text.strip()
    if t in ("-", "", "n/d", "---", "N/D"):
        return None
    t = t.replace("R$", "").replace(" ", "").replace(".", "").replace(",", ".")
    clean = "".join(ch for ch in t if ch.isdigit() or ch in ".-")
    try:
        return float(clean)
    except (ValueError, InvalidOperation):
        return None


BACEN_SGS_FLOW = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.22927/dados"


def collect_foreign_flow_bacen() -> dict:
    """
    BACEN SGS série 22927 — 'Investimentos em carteira - ações - passivos - mensal - líquido'
    Net monthly foreign portfolio investment in Brazilian equities (USD millions).
    Stores cumulative running total as ytd_flow_mm, monthly net as daily_flow_mm.
    Monthly data, first day of each month, from 2010 to present.
    """
    log.info("Fluxo estrangeiro BACEN SGS 22927: baixando série histórica mensal...")
    params = {
        "formato": "json",
        "dataInicial": "01/01/2010",
        "dataFinal": date.today().strftime("%d/%m/%Y"),
    }
    try:
        r = cf_requests.get(BACEN_SGS_FLOW, params=params, impersonate="chrome", timeout=30)
        if r.status_code != 200:
            return {"status": "error", "message": f"BACEN HTTP {r.status_code}", "rows": 0}
        data = r.json()
    except Exception as e:
        return {"status": "error", "message": str(e), "rows": 0}

    conn = get_conn()
    n = 0
    cumulative = 0.0
    for item in data:
        try:
            d_str = item.get("data", "")
            val_str = item.get("valor", "")
            if not d_str or not val_str:
                continue
            day, month, year = d_str.split("/")
            iso_date = f"{year}-{month}-{day}"
            monthly_net = float(val_str.replace(",", "."))
            cumulative += monthly_net
            conn.execute(
                "INSERT OR REPLACE INTO foreign_flow (date, daily_flow_mm, ytd_flow_mm) VALUES (?, ?, ?)",
                (iso_date, monthly_net, cumulative),
            )
            n += 1
        except Exception:
            continue
    conn.commit()
    conn.close()
    log.info(f"BACEN fluxo estrangeiro: {n} meses inseridos")
    return {"status": "ok", "rows": n}


def collect_foreign_flow() -> dict:
    log.info("Fluxo estrangeiro: downloading from dadosdemercado.com.br...")
    try:
        r = cf_requests.get(
            "https://www.dadosdemercado.com.br/fluxo",
            impersonate="chrome", timeout=30
        )
        r.raise_for_status()
    except Exception as e:
        return {"status": "error", "message": str(e), "rows": 0}

    from bs4 import BeautifulSoup
    soup = BeautifulSoup(r.text, "lxml")
    table = None

    for t in soup.find_all("table"):
        hdr = t.find("thead") or t.find("tr")
        if hdr and ("estrangeiro" in hdr.get_text().lower() or "externo" in hdr.get_text().lower()):
            table = t
            break

    if not table:
        for heading in soup.find_all(["h1", "h2", "h3", "h4"]):
            if "estrangeiro" in heading.get_text().lower():
                parent = heading.find_parent(["section", "div", "article"])
                if parent:
                    t = parent.find("table")
                    if t:
                        table = t
                        break

    if not table:
        for t in soup.find_all("table"):
            trs = t.find_all("tr")
            if len(trs) > 5:
                cols = [td.get_text(strip=True) for td in trs[1].find_all("td")]
                if len(cols) >= 2 and cols[0] and _parse_date_str(cols[0]):
                    table = t
                    break

    if not table:
        return {"status": "error", "message": "tabela não encontrada", "rows": 0}

    trs = table.find_all("tr")
    cols_header = [th.get_text(strip=True).lower() for th in trs[0].find_all(["th", "td"])] if trs else []
    idx_data, idx_saldo, idx_acum = 0, 1, None
    for i, h in enumerate(cols_header):
        if "data" in h or "pregao" in h:
            idx_data = i
        elif "acumul" in h:
            idx_acum = i
        elif "saldo" in h and i > 0:
            idx_saldo = i

    raw_rows = []
    for tr in trs[1:]:
        cols = [td.get_text(strip=True) for td in tr.find_all("td")]
        if len(cols) < 2:
            continue
        d = _parse_date_str(cols[idx_data]) if idx_data < len(cols) else None
        daily = _parse_number(cols[idx_saldo]) if idx_saldo < len(cols) else None
        if not d or daily is None:
            continue
        acum = _parse_number(cols[idx_acum]) if (idx_acum is not None and idx_acum < len(cols)) else None
        raw_rows.append({"date": d, "daily": daily, "ytd": acum})

    if not raw_rows:
        return {"status": "error", "message": "nenhuma linha parseada", "rows": 0}

    raw_rows.sort(key=lambda r: r["date"])
    yr_accum: dict = {}
    for row in raw_rows:
        yr = row["date"][:4]
        yr_accum.setdefault(yr, 0.0)
        yr_accum[yr] += row["daily"]
        if row["ytd"] is None:
            row["ytd"] = yr_accum[yr]

    conn = get_conn()
    for row in raw_rows:
        conn.execute(
            "INSERT OR REPLACE INTO foreign_flow (date, daily_flow_mm, ytd_flow_mm) VALUES (?, ?, ?)",
            (row["date"], row["daily"], row["ytd"]),
        )
    conn.commit()
    conn.close()
    log.info(f"Fluxo estrangeiro dadosdemercado: {len(raw_rows)} rows")
    return {"status": "ok", "rows": len(raw_rows)}


# ── Collector: Índices B3 + USD/BRL ─────────────────────────────────────────
def _yf_close_series(ticker: str, **kwargs) -> dict:
    """Download a single ticker from yfinance and return {date_str: float}."""
    import math
    df = yf.download(ticker, auto_adjust=True, progress=False, **kwargs)
    if df.empty:
        return {}
    # yfinance may return MultiIndex columns even for a single ticker
    if isinstance(df.columns, pd.MultiIndex):
        close = df["Close"].iloc[:, 0]
    else:
        close = df["Close"] if "Close" in df.columns else df.iloc[:, 0]
    result = {}
    for idx, val in close.items():
        try:
            f = float(val)
            if not math.isnan(f):
                result[idx.date().isoformat()] = round(f, 4)
        except (TypeError, ValueError):
            pass
    return result


def collect_br_indices(start: str = "2016-01-01") -> dict:
    """Download B3 sector indices (5d rolling) and USD/BRL (full history) from Yahoo Finance.

    B3 sector indices (IBLV, IBHB, IDIV, IFNC, UTIL) are only available on Yahoo Finance
    for the last 5 trading days; USD/BRL has full history. Each daily run appends new rows.
    """
    log.info("BR Indices: downloading from Yahoo Finance...")
    try:
        import math

        # USD/BRL — full history from start date
        usdbrl_data = _yf_close_series("USDBRL=X", start=start)

        # B3 sector indices — only last 5d available on Yahoo Finance
        # BLVB11.SA and BHYB11.SA are not listed on Yahoo Finance
        b3_keys = {"idiv": "DIVO11.SA", "smal11": "SMAL11.SA"}
        b3_data: dict[str, dict] = {k: {} for k in b3_keys}
        for key, ticker in b3_keys.items():
            try:
                b3_data[key] = _yf_close_series(ticker, start="2020-01-01")
            except Exception as ex:
                log.warning(f"BR Indices: {ticker} failed: {ex}")

        # Merge all dates
        all_dates = set(usdbrl_data.keys())
        for d in b3_data.values():
            all_dates.update(d.keys())

        conn = get_conn()
        n = 0
        for d in sorted(all_dates):
            idiv   = b3_data.get("idiv", {}).get(d)
            smal11 = b3_data.get("smal11", {}).get(d)
            usdbrl = usdbrl_data.get(d)
            # Only insert if at least one value is present
            if any(v is not None for v in (idiv, smal11, usdbrl)):
                conn.execute(
                    """INSERT INTO br_indices (date, idiv, smal11, usdbrl)
                       VALUES (?, ?, ?, ?)
                       ON CONFLICT(date) DO UPDATE SET
                         idiv   = COALESCE(excluded.idiv,   idiv),
                         smal11 = COALESCE(excluded.smal11, smal11),
                         usdbrl = COALESCE(excluded.usdbrl, usdbrl)""",
                    (d, idiv, smal11, usdbrl),
                )
                n += 1
        conn.commit()
        conn.close()
        log.info(f"BR Indices: {n} rows upserted")
        return {"status": "ok", "rows": n}
    except Exception as e:
        log.error(f"BR Indices: {e}")
        return {"status": "error", "message": str(e), "rows": 0}


# ── Collector: Macro Global (DXY, US10Y, Bloomberg Commodity, US CPI YoY) ────
def _fred_csv_series(series_id: str) -> dict:
    """Download a FRED series via the no-key CSV endpoint and return {date_str: float}.

    Must parse line-by-line (not pd.read_csv) — fredgraph.csv's header/date column
    breaks pandas' date parsing, and missing observations are marked with '.'.
    """
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    result = {}
    for line in r.text.strip().split("\n")[1:]:
        parts = line.split(",")
        if len(parts) == 2 and parts[1].strip() not in (".", ""):
            try:
                result[parts[0].strip()] = float(parts[1].strip())
            except ValueError:
                pass
    return result


def _compute_yoy_from_monthly(series: dict) -> dict:
    """Given {date_str: level} for a monthly series (one point per month, no gaps),
    return {date_str: pct_change_vs_12_months_ago} for dates where that's computable."""
    dates = sorted(series.keys())
    yoy = {}
    for i in range(12, len(dates)):
        prev, cur = series[dates[i - 12]], series[dates[i]]
        if prev:
            yoy[dates[i]] = round((cur / prev - 1) * 100, 3)
    return yoy


def collect_macro_indicators(start: str = "2000-01-01") -> dict:
    """DXY (ICE US Dollar Index, Yahoo Finance), US10Y (10-Year Treasury Constant
    Maturity Rate, FRED DGS10 — official Fed/Treasury data), Bloomberg Commodity
    Index (via DJP — iPath ETN that tracks it; the raw ^BCOM index ticker has no
    usable history on Yahoo Finance, only ever returns 1 day), and US CPI YoY
    inflation rate (derived from FRED CPIAUCSL, official BLS data, no API key)."""
    log.info("Macro Indicators: downloading DXY/US10Y/BCOM/CPI YoY...")
    try:
        dxy_data = _yf_close_series("DX-Y.NYB", start=start)
        bcom_data = _yf_close_series("DJP", start=start)
        us10y_data = _fred_csv_series("DGS10")
        cpi_levels = _fred_csv_series("CPIAUCSL")
        cpi_yoy = _compute_yoy_from_monthly(cpi_levels)

        all_dates = set(dxy_data) | set(bcom_data) | set(us10y_data) | set(cpi_yoy)

        conn = get_conn()
        n = 0
        for d in sorted(all_dates):
            dxy = dxy_data.get(d)
            us10y = us10y_data.get(d)
            bcom = bcom_data.get(d)
            cpi = cpi_yoy.get(d)
            if any(v is not None for v in (dxy, us10y, bcom, cpi)):
                conn.execute(
                    """INSERT INTO macro_indicators (date, dxy, us10y, bcom, us_cpi_yoy)
                       VALUES (?, ?, ?, ?, ?)
                       ON CONFLICT(date) DO UPDATE SET
                         dxy        = COALESCE(excluded.dxy,        dxy),
                         us10y      = COALESCE(excluded.us10y,      us10y),
                         bcom       = COALESCE(excluded.bcom,       bcom),
                         us_cpi_yoy = COALESCE(excluded.us_cpi_yoy, us_cpi_yoy)""",
                    (d, dxy, us10y, bcom, cpi),
                )
                n += 1
        conn.commit()
        conn.close()
        log.info(f"Macro Indicators: {n} rows upserted")
        return {"status": "ok", "rows": n}
    except Exception as e:
        log.error(f"Macro Indicators: {e}")
        return {"status": "error", "message": str(e), "rows": 0}


# ── FastAPI ───────────────────────────────────────────────────────────────────
app = FastAPI(title="Intermarket Dashboard")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _collect_all_job():
    """Job diário: coleta todas as séries do Intermarket."""
    log.info("=== Coleta automática diária iniciando ===")
    try:
        collect_ibov()
    except Exception as e:
        log.error("Auto-collect ibov: %s", e)
    try:
        collect_cot()
    except Exception as e:
        log.error("Auto-collect cot: %s", e)
    try:
        collect_ntnb35()
    except Exception as e:
        log.error("Auto-collect ntnb35: %s", e)
    try:
        collect_di_rates()
    except Exception as e:
        log.error("Auto-collect di_rates: %s", e)
    try:
        collect_foreign_flow()
    except Exception as e:
        log.error("Auto-collect foreign_flow: %s", e)
    try:
        collect_br_indices()
    except Exception as e:
        log.error("Auto-collect br_indices: %s", e)
    try:
        collect_macro_indicators()
    except Exception as e:
        log.error("Auto-collect macro_indicators: %s", e)
    log.info("=== Coleta automática diária concluída ===")


@app.on_event("startup")
def on_startup():
    init_db()
    scheduler = BackgroundScheduler(timezone="America/Sao_Paulo")
    scheduler.add_job(_collect_all_job, "cron", hour=6,  minute=0, id="morning_collect")
    scheduler.add_job(_collect_all_job, "cron", hour=18, minute=0, id="evening_collect")
    scheduler.start()
    log.info("Scheduler iniciado — coleta às 06:00 e 18:00 BRT.")
    log.info("POST /api/collect/trigger para coleta manual.")


@app.get("/", response_class=HTMLResponse)
def index():
    if os.path.exists(INDEX_PATH):
        with open(INDEX_PATH, "r", encoding="utf-8") as f:
            return f.read()
    return HTMLResponse("<h1>index.html não encontrado</h1>")


@app.get("/api/status")
def status():
    return {
        "ibov": {"rows": db_count("ibov_daily")},
        "cot": {"rows": db_count("cot_6l")},
        "ntnb35": {"rows": db_count("ntnb35_pu")},
        "foreign_flow": {"rows": db_count("foreign_flow")},
        "di_rates": {"rows": db_count("di_rates")},
        "br_indices": {"rows": db_count("br_indices")},
        "macro_indicators": {"rows": db_count("macro_indicators")},
    }


@app.get("/api/ibov")
def api_ibov(
    from_date: str = Query(default="2023-01-01", alias="from"),
    to_date: str = Query(default=date.today().isoformat(), alias="to"),
):
    conn = get_conn()
    rows = conn.execute(
        "SELECT date, close FROM ibov_daily WHERE date >= ? AND date <= ? ORDER BY date",
        (from_date, to_date),
    ).fetchall()
    conn.close()
    return {"series": "ibov", "data": rows_to_list(rows)}


@app.get("/api/cot")
def api_cot(
    from_date: str = Query(default="2023-01-01", alias="from"),
    to_date: str = Query(default=date.today().isoformat(), alias="to"),
):
    conn = get_conn()
    rows = conn.execute(
        "SELECT report_date, asset_mgr_net FROM cot_6l WHERE report_date >= ? AND report_date <= ? ORDER BY report_date",
        (from_date, to_date),
    ).fetchall()
    conn.close()
    return {"series": "cot_6l", "data": rows_to_list(rows)}


@app.get("/api/ntnb35")
def api_ntnb35(
    from_date: str = Query(default="2023-01-01", alias="from"),
    to_date: str = Query(default=date.today().isoformat(), alias="to"),
):
    conn = get_conn()
    rows = conn.execute(
        "SELECT date, pu FROM ntnb35_pu WHERE date >= ? AND date <= ? ORDER BY date",
        (from_date, to_date),
    ).fetchall()
    conn.close()
    return {"series": "ntnb35_pu", "data": rows_to_list(rows)}


@app.get("/api/di-rates")
def api_di_rates(
    from_date: str = Query(default="2022-01-01", alias="from"),
    to_date: str = Query(default=date.today().isoformat(), alias="to"),
):
    conn = get_conn()
    rows = conn.execute(
        "SELECT date, di2033, di2034, di2035 FROM di_rates WHERE date >= ? AND date <= ? ORDER BY date",
        (from_date, to_date),
    ).fetchall()
    conn.close()
    return {
        "di2033": [{"date": r[0], "value": r[1]} for r in rows if r[1] is not None],
        "di2034": [{"date": r[0], "value": r[2]} for r in rows if r[2] is not None],
        "di2035": [{"date": r[0], "value": r[3]} for r in rows if r[3] is not None],
    }


@app.get("/api/foreign-flow")
def api_foreign_flow(
    from_date: str = Query(default="2023-01-01", alias="from"),
    to_date: str = Query(default=date.today().isoformat(), alias="to"),
):
    conn = get_conn()
    rows = conn.execute(
        "SELECT date, ytd_flow_mm FROM foreign_flow WHERE date >= ? AND date <= ? ORDER BY date",
        (from_date, to_date),
    ).fetchall()
    conn.close()
    return {"series": "foreign_flow", "data": rows_to_list(rows)}


@app.get("/api/all")
def api_all(
    from_date: str = Query(default="2023-01-01", alias="from"),
    to_date: str = Query(default=date.today().isoformat(), alias="to"),
):
    conn = get_conn()
    ibov = conn.execute(
        "SELECT date, close FROM ibov_daily WHERE date >= ? AND date <= ? ORDER BY date",
        (from_date, to_date),
    ).fetchall()
    cot = conn.execute(
        "SELECT report_date, asset_mgr_net FROM cot_6l WHERE report_date >= ? AND report_date <= ? ORDER BY report_date",
        (from_date, to_date),
    ).fetchall()
    ntnb = conn.execute(
        "SELECT date, pu FROM ntnb35_pu WHERE date >= ? AND date <= ? ORDER BY date",
        (from_date, to_date),
    ).fetchall()
    flow = conn.execute(
        "SELECT date, ytd_flow_mm FROM foreign_flow WHERE date >= ? AND date <= ? ORDER BY date",
        (from_date, to_date),
    ).fetchall()
    di = conn.execute(
        "SELECT date, di2033, di2034, di2035 FROM di_rates WHERE date >= ? AND date <= ? ORDER BY date",
        (from_date, to_date),
    ).fetchall()
    bri = conn.execute(
        "SELECT date, iblv, ibhb, idiv, smal11, usdbrl FROM br_indices WHERE date >= ? AND date <= ? ORDER BY date",
        (from_date, to_date),
    ).fetchall()
    macro = conn.execute(
        "SELECT date, dxy, us10y, bcom, us_cpi_yoy FROM macro_indicators WHERE date >= ? AND date <= ? ORDER BY date",
        (from_date, to_date),
    ).fetchall()
    conn.close()
    di2033 = [{"date": r[0], "value": r[1]} for r in di if r[1] is not None]
    di2034 = [{"date": r[0], "value": r[2]} for r in di if r[2] is not None]
    di2035 = [{"date": r[0], "value": r[3]} for r in di if r[3] is not None]
    def _bri(idx): return [{"date": r[0], "value": r[idx]} for r in bri if r[idx] is not None]
    def _macro(idx): return [{"date": r[0], "value": r[idx]} for r in macro if r[idx] is not None]
    return {
        "from": from_date,
        "to": to_date,
        "ibov": rows_to_list(ibov),
        "cot": rows_to_list(cot),
        "ntnb35": rows_to_list(ntnb),
        "foreign_flow": rows_to_list(flow),
        "di2033": di2033,
        "di2034": di2034,
        "di2035": di2035,
        "blvb11":  _bri(1),
        "bhyb11":  _bri(2),
        "divo11":  _bri(3),
        "smal11":  _bri(4),
        "usdbrl":  _bri(5),
        "dxy":        _macro(1),
        "us10y":      _macro(2),
        "bcom":       _macro(3),
        "us_cpi_yoy": _macro(4),
    }


@app.get("/api/br-indices")
def api_br_indices(
    from_date: str = Query(default="2016-01-01", alias="from"),
    to_date: str = Query(default=date.today().isoformat(), alias="to"),
):
    conn = get_conn()
    rows = conn.execute(
        "SELECT date, iblv, ibhb, idiv, smal11, usdbrl FROM br_indices WHERE date >= ? AND date <= ? ORDER BY date",
        (from_date, to_date),
    ).fetchall()
    conn.close()

    def _series(idx):
        return [{"date": r[0], "value": r[idx]} for r in rows if r[idx] is not None]

    return {
        "blvb11":  _series(1),
        "bhyb11":  _series(2),
        "divo11":  _series(3),
        "smal11":  _series(4),
        "usdbrl":  _series(5),
    }


@app.get("/api/macro-indicators")
def api_macro_indicators(
    from_date: str = Query(default="2000-01-01", alias="from"),
    to_date: str = Query(default=date.today().isoformat(), alias="to"),
):
    conn = get_conn()
    rows = conn.execute(
        "SELECT date, dxy, us10y, bcom, us_cpi_yoy FROM macro_indicators WHERE date >= ? AND date <= ? ORDER BY date",
        (from_date, to_date),
    ).fetchall()
    conn.close()

    def _series(idx):
        return [{"date": r[0], "value": r[idx]} for r in rows if r[idx] is not None]

    return {
        "dxy":        _series(1),
        "us10y":      _series(2),
        "bcom":       _series(3),
        "us_cpi_yoy": _series(4),
    }


@app.post("/api/collect/trigger")
def collect_trigger(series: str = Query(default="all"), full: bool = Query(default=False)):
    """
    Coleta incremental (padrão): rápida, só baixa dados novos.
    ?full=true: reconstrução completa do histórico (lento — só usar se o banco estiver corrompido).
    """
    results = {}
    if series in ("all", "ibov"):
        results["ibov"] = collect_ibov()
    if series in ("all", "cot"):
        results["cot"] = collect_cot(full=full)
    if series in ("all", "ntnb35"):
        results["ntnb35"] = collect_ntnb35()
    if series in ("all", "di_rates"):
        results["di_rates"] = collect_di_rates()
    if series == "foreign_flow_bacen":
        results["foreign_flow_bacen"] = collect_foreign_flow_bacen()
    if series in ("all", "foreign_flow"):
        results["foreign_flow"] = collect_foreign_flow()
    if series in ("all", "br_indices"):
        results["br_indices"] = collect_br_indices()
    if series in ("all", "macro_indicators"):
        results["macro_indicators"] = collect_macro_indicators()
    return results


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)
