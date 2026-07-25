"""
Coleta dados COT (Commitment of Traders) do CFTC.
Relatório: Disaggregated Futures Only.
Publicado semanalmente (sexta-feira, dados de terça).
"""
import io
import zipfile
import datetime
import logging

import pandas as pd
import requests

from app.database import upsert_cot
from app.settings import COT_CONTRACTS, COT_CONTRACTS_TFF

log = logging.getLogger(__name__)

CFTC_BASE = "https://www.cftc.gov/files/dea/history"

COLS_NEEDED = [
    "Market_and_Exchange_Names",
    "As_of_Date_In_Form_YYMMDD",
    "Report_Date_as_YYYY-MM-DD",
    "Report_Date_as_MM_DD_YYYY",       # formato alternativo 2010-2012
    "M_Money_Positions_Long_All",
    "M_Money_Positions_Short_All",
    "Other_Rept_Positions_Long_All",
    "Other_Rept_Positions_Short_All",
    "Open_Interest_All",
]

COLS_NEEDED_TFF = [
    "Market_and_Exchange_Names",
    "As_of_Date_In_Form_YYMMDD",
    "Report_Date_as_YYYY-MM-DD",
    "Report_Date_as_MM_DD_YYYY",       # formato alternativo 2010-2012
    "Asset_Mgr_Positions_Long_All",    # Asset Managers/Institutional (primary — igual Sharketo)
    "Asset_Mgr_Positions_Short_All",
    "Lev_Money_Positions_Long_All",    # Leveraged Funds (secondary)
    "Lev_Money_Positions_Short_All",
    "Open_Interest_All",
]


def _year_url(year: int) -> str:
    return f"{CFTC_BASE}/fut_disagg_txt_{year}.zip"


def _tff_year_url(year: int) -> str:
    return f"{CFTC_BASE}/fut_fin_txt_{year}.zip"


def _fetch_year(year: int) -> pd.DataFrame:
    url = _year_url(year)
    log.info("COT: baixando %d → %s", year, url)
    r = requests.get(url, timeout=90)
    r.raise_for_status()
    z = zipfile.ZipFile(io.BytesIO(r.content))
    fname = [n for n in z.namelist() if n.lower().endswith((".txt", ".csv"))][0]
    df_raw = pd.read_csv(z.open(fname), low_memory=False)
    avail = [c for c in COLS_NEEDED if c in df_raw.columns]
    df = df_raw[avail].copy()
    if "Market_and_Exchange_Names" in df.columns:
        df["Market_and_Exchange_Names"] = df["Market_and_Exchange_Names"].str.strip()
    return df


def _parse_cot_date(v) -> str | None:
    try:
        s = str(int(v)).zfill(6)
        return pd.to_datetime(s, format="%y%m%d").date().isoformat()
    except Exception:
        return None


def _iso_date(row) -> str | None:
    """Tenta Report_Date_as_YYYY-MM-DD, depois MM_DD_YYYY (2010-2012), depois YYMMDD."""
    v = row.get("Report_Date_as_YYYY-MM-DD")
    if pd.notna(v) and str(v).strip():
        try:
            return str(pd.to_datetime(str(v)).date())
        except Exception:
            pass
    v2 = row.get("Report_Date_as_MM_DD_YYYY")
    if pd.notna(v2) and str(v2).strip():
        try:
            return str(pd.to_datetime(str(v2)).date())
        except Exception:
            pass
    return _parse_cot_date(row.get("As_of_Date_In_Form_YYMMDD", ""))


def collect_cot():
    """Baixa COT CFTC de 2010 até o ano atual e armazena no banco."""
    name_to_key: dict[str, str] = {}
    for key, names in COT_CONTRACTS.items():
        for name in (names if isinstance(names, list) else [names]):
            name_to_key[name] = key
    contract_set = set(name_to_key.keys())
    today = datetime.date.today()

    all_rows: list[tuple] = []

    for year in range(2010, today.year + 1):
        try:
            df = _fetch_year(year)

            mask = df["Market_and_Exchange_Names"].isin(contract_set)
            df = df[mask].copy()
            if df.empty:
                log.warning("COT %d: nenhum contrato relevante encontrado", year)
                continue

            df["date_iso"] = df.apply(_iso_date, axis=1)
            df = df.dropna(subset=["date_iso"])

            for col in ["M_Money_Positions_Long_All", "M_Money_Positions_Short_All",
                        "Other_Rept_Positions_Long_All", "Other_Rept_Positions_Short_All",
                        "Open_Interest_All"]:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)
                else:
                    df[col] = 0.0

            df["mm_net"] = df["M_Money_Positions_Long_All"] - df["M_Money_Positions_Short_All"]
            # Large Speculators (≈ Non-Commercial do Legacy COT) = Managed Money + Other Reportables
            df["ls_net"] = (
                (df["M_Money_Positions_Long_All"]  + df["Other_Rept_Positions_Long_All"]) -
                (df["M_Money_Positions_Short_All"] + df["Other_Rept_Positions_Short_All"])
            )

            year_rows = []
            for _, row in df.iterrows():
                key = name_to_key.get(row["Market_and_Exchange_Names"])
                if key:
                    year_rows.append((
                        key,
                        row["date_iso"],
                        float(row["mm_net"]),
                        float(row["ls_net"]),       # Large Speculators ≈ Non-Commercial
                        float(row["Open_Interest_All"]),
                        float(row["M_Money_Positions_Long_All"]),
                        float(row["M_Money_Positions_Short_All"]),
                    ))

            all_rows.extend(year_rows)
            log.info("COT %d: %d registros (%d contratos distintos)",
                     year, len(year_rows), len(df["Market_and_Exchange_Names"].unique()))

        except Exception as e:
            log.error("COT %d erro: %s", year, e)

    if all_rows:
        upsert_cot(all_rows)
        log.info("COT total inserido: %d registros", len(all_rows))
    else:
        log.warning("COT: nenhum dado coletado")


def collect_cot_tff():
    """Baixa COT TFF (Traders in Financial Futures) do CFTC de 2010 até hoje."""
    # COT_CONTRACTS_TFF usa listas de nomes alternativos por contrato
    name_to_key: dict[str, str] = {}
    for key, names in COT_CONTRACTS_TFF.items():
        for name in (names if isinstance(names, list) else [names]):
            name_to_key[name] = key
    contract_set = set(name_to_key.keys())
    today = datetime.date.today()

    all_rows: list[tuple] = []

    for year in range(2010, today.year + 1):
        try:
            url = _tff_year_url(year)
            log.info("COT TFF: baixando %d → %s", year, url)
            r = requests.get(url, timeout=90)
            r.raise_for_status()
            z = zipfile.ZipFile(io.BytesIO(r.content))
            fname = [n for n in z.namelist() if n.lower().endswith((".txt", ".csv"))][0]
            df_raw = pd.read_csv(z.open(fname), low_memory=False)
            avail = [c for c in COLS_NEEDED_TFF if c in df_raw.columns]
            df = df_raw[avail].copy()
            if "Market_and_Exchange_Names" in df.columns:
                df["Market_and_Exchange_Names"] = df["Market_and_Exchange_Names"].str.strip()

            mask = df["Market_and_Exchange_Names"].isin(contract_set)
            df = df[mask].copy()
            if df.empty:
                log.warning("COT TFF %d: nenhum contrato relevante encontrado", year)
                continue

            df["date_iso"] = df.apply(_iso_date, axis=1)
            df = df.dropna(subset=["date_iso"])

            for col in ["Asset_Mgr_Positions_Long_All", "Asset_Mgr_Positions_Short_All",
                        "Lev_Money_Positions_Long_All", "Lev_Money_Positions_Short_All",
                        "Open_Interest_All"]:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)
                else:
                    df[col] = 0.0

            # mm_net = Asset Manager (institutional — primary, igual Sharketo)
            # ls_net = Leveraged Funds (hedge funds/CTAs — secondary)
            df["mm_net"] = df["Asset_Mgr_Positions_Long_All"] - df["Asset_Mgr_Positions_Short_All"]
            df["ls_net"] = df["Lev_Money_Positions_Long_All"] - df["Lev_Money_Positions_Short_All"]

            year_rows = []
            for _, row in df.iterrows():
                key = name_to_key.get(row["Market_and_Exchange_Names"])
                if key:
                    year_rows.append((
                        key,
                        row["date_iso"],
                        float(row["mm_net"]),
                        float(row["ls_net"]),
                        float(row["Open_Interest_All"]),
                        float(row["Asset_Mgr_Positions_Long_All"]),
                        float(row["Asset_Mgr_Positions_Short_All"]),
                    ))

            all_rows.extend(year_rows)
            log.info("COT TFF %d: %d registros (%d contratos distintos)",
                     year, len(year_rows), len(df["Market_and_Exchange_Names"].unique()))

        except Exception as e:
            log.error("COT TFF %d erro: %s", year, e)

    if all_rows:
        upsert_cot(all_rows)
        log.info("COT TFF total inserido: %d registros", len(all_rows))
    else:
        log.warning("COT TFF: nenhum dado coletado")
