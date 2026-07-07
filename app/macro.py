"""
Coleta dados macroeconômicos.
- CPI, Core CPI, NFP, Desemprego: BLS Public API (sem chave)
- Fed Funds Rate: FRED (se chave configurada) ou valor manual do JSON
"""
import json, requests, logging
from app.database import upsert_macro, last_macro_date
from app.settings import FRED_API_KEY

log = logging.getLogger(__name__)

BLS_ENDPOINT = "https://api.bls.gov/publicAPI/v1/timeseries/data/"

BLS_SERIES = {
    "CPI":         "CUUR0000SA0",
    "CORE_CPI":    "CUUR0000SA0L1E",
    "NFP":         "CES0000000001",
    "UNEMPLOYMENT":"LNS14000000",
}

FRED_SERIES = {
    "FED_RATE": "FEDFUNDS",
}


def _bls_fetch(series_ids: list[str], start_year: str, end_year: str) -> dict:
    payload = json.dumps({
        "seriesid":  series_ids,
        "startyear": start_year,
        "endyear":   end_year,
    })
    try:
        r = requests.post(
            BLS_ENDPOINT,
            data=payload,
            headers={"Content-type": "application/json"},
            timeout=30,
        )
        r.raise_for_status()
        return r.json()
    except Exception as e:
        log.error("BLS API error: %s", e)
        return {}


def _bls_month_to_date(year: str, period: str) -> str | None:
    """period like 'M01' -> '2024-01-01'"""
    if not period.startswith("M"):
        return None
    m = period[1:]
    if m == "13":  # annual average
        return None
    return f"{year}-{m}-01"


def collect_bls():
    import datetime
    cur_year = str(datetime.date.today().year)
    start_year = str(datetime.date.today().year - 9)  # BLS v1 free tier: max 10 years (inclusive)

    result = _bls_fetch(list(BLS_SERIES.values()), start_year, cur_year)
    if not result or result.get("status") != "REQUEST_SUCCEEDED":
        log.warning("BLS: request failed or empty: %s", result.get("message", ""))
        return

    for series_data in result.get("Results", {}).get("series", []):
        series_id_bls = series_data["seriesID"]
        # find our key
        our_key = next((k for k, v in BLS_SERIES.items() if v == series_id_bls), None)
        if not our_key:
            continue

        rows = []
        for obs in series_data.get("data", []):
            dt = _bls_month_to_date(obs["year"], obs["period"])
            if dt is None:
                continue
            try:
                val = float(obs["value"])
                rows.append((dt, val))
            except ValueError:
                pass

        if rows:
            upsert_macro(our_key, rows)
            log.info("BLS %s: %d registros", our_key, len(rows))


def collect_fred_rate():
    if not FRED_API_KEY:
        log.info("FRED key not configured — skipping Fed Funds Rate live fetch")
        return
    try:
        from fredapi import Fred
        fred = Fred(api_key=FRED_API_KEY)
        last = last_macro_date("FED_RATE")
        kwargs = {}
        if last:
            kwargs["observation_start"] = last
        s = fred.get_series("FEDFUNDS", **kwargs)
        rows = [(str(d.date()), float(v)) for d, v in s.items() if not str(v) == "nan"]
        if rows:
            upsert_macro("FED_RATE", rows)
            log.info("FRED FED_RATE: %d registros", len(rows))
    except Exception as e:
        log.error("FRED collect error: %s", e)


def collect_ipca_bcb():
    """IPCA mensal variação % (série 433 do Banco Central do Brasil)."""
    try:
        r = requests.get(
            "https://api.bcb.gov.br/dados/serie/bcdata.sgs.433/dados?formato=json",
            timeout=30,
        )
        r.raise_for_status()
        data = r.json()
        rows = []
        for item in data:
            d = item.get("data", "")
            v = item.get("valor", "")
            if d and v:
                parts = d.split("/")
                if len(parts) == 3:
                    dt = f"{parts[2]}-{parts[1]}-{parts[0]}"
                    rows.append((dt, float(v)))
        if rows:
            upsert_macro("IPCA", rows)
            log.info("BCB IPCA: %d registros", len(rows))
    except Exception as e:
        log.error("BCB IPCA error: %s", e)


def collect_all():
    log.info("Coletando dados macro BLS...")
    collect_bls()
    log.info("Coletando Fed Funds Rate (FRED)...")
    collect_fred_rate()
    log.info("Coletando IPCA (BCB)...")
    collect_ipca_bcb()
